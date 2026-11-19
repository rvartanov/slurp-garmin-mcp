"""
Extended activity tools (Slurp garmin-mcp).

Exposes the activity methods garminconnect >= 0.3.20 adds: per-activity
detail (laps, rounds, workout steps, jumps, sub-second data, swim, map,
polyline, photos, segments, neighbours), activity search with the web app's
filters, favourites, training load per activity, weekly aggregates, fastest
splits, partial activity updates, manual activities from a full payload and
file uploads. Fork-specific module.
"""
import base64
import binascii
import json
import os
import re
import tempfile
from typing import Any, Callable, Dict, Optional

from garmin_mcp.health_extra import _choice, _compact, _positive, _range
from garmin_mcp.race_events import _json_object
from garmin_mcp.write_errors import WriteTracker

# The garmin_client will be set by the main file
garmin_client = None

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_UPLOAD_SUFFIXES = (".fit", ".gpx", ".tcx")
_TYPE_KEY_RE = re.compile(r"^[a-z_]+$")
# Fields update_activity refuses: they identify the activity or its owner.
_PROTECTED_ACTIVITY_FIELDS = frozenset({"activityId", "ownerId", "userProfileId"})


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _result(value: Any, empty: str, detail: bool) -> str:
    if value is None or value == [] or value == {}:
        return empty
    return _dump(value if detail else _compact(value))


# kind -> callable(activity_id)
_ACTIVITY_DATA: Dict[str, Callable[[int], Any]] = {
    "details": lambda a: garmin_client.get_activity_details(a),
    "laps": lambda a: garmin_client.get_activity_laps(a),
    "rounds": lambda a: garmin_client.get_activity_rounds(a),
    "workout_steps": lambda a: garmin_client.get_activity_step_details(a),
    "jumps": lambda a: garmin_client.get_activity_jump_details(a),
    "subsecond": lambda a: garmin_client.get_activity_subsecond_details(a),
    "swim": lambda a: garmin_client.get_activity_swim_details(a),
    "map": lambda a: garmin_client.get_activity_map_details(a),
    "polyline": lambda a: garmin_client.get_activity_polyline(a),
    "photos": lambda a: garmin_client.get_activity_images(a),
    "segments": lambda a: garmin_client.get_activity_segments(a),
    "adjacent": lambda a: garmin_client.get_adjacent_activities(a),
}

# Kinds that only exist for some activities; Garmin answers the others with
# HTTP 500 instead of an empty result.
_OPTIONAL_KINDS = {
    "workout_steps": "it was not a structured workout",
    "subsecond": "it has no sub-second data",
    "swim": "it is not a lap-swimming activity",
    "rounds": "it has no rounds",
    "jumps": "it has no jump data",
}

# Fields kept per activity in list results unless detail=true; a full
# summary has ~130 fields (owner profile images, per-zone times, ...).
_SUMMARY_FIELDS = (
    "activityId", "activityName", "startTimeLocal", "activityType", "eventType",
    "distance", "duration", "movingDuration", "elevationGain", "averageSpeed",
    "averageHR", "maxHR", "avgPower", "normPower", "calories",
    "aerobicTrainingEffect", "anaerobicTrainingEffect", "trainingEffectLabel",
    "activityTrainingLoad", "locationName", "favorite", "pr", "manualActivity",
)


def _summary(activity: Any) -> Any:
    if not isinstance(activity, dict):
        return activity
    short = {key: activity[key] for key in _SUMMARY_FIELDS if key in activity}
    for key in ("activityType", "eventType"):
        if isinstance(short.get(key), dict):
            short[key] = short[key].get("typeKey")
    return short


def _summaries(value: Any) -> Any:
    """Shorten every activity in a list result (or {activityList: [...]})."""
    if isinstance(value, list):
        return [_summary(item) for item in value]
    if isinstance(value, dict) and isinstance(value.get("activityList"), list):
        return {**value, "activityList": [_summary(item) for item in value["activityList"]]}
    if isinstance(value, dict) and "activityId" in value:
        return _summary(value)
    return value


# Filters search_activities passes through, as the web app names them.
_SEARCH_FILTERS = (
    "activityType", "activitySubType", "startDate", "endDate", "search", "favorite",
    "sortBy", "sortOrder", "minDistance", "maxDistance", "minDuration", "maxDuration",
    "minElevation", "maxElevation", "eventType", "excludeChildren",
)


def register_tools(app):
    """Register the extended activity tools with the MCP server app"""

    @app.tool()
    async def get_activity_data(activity_id: int, kind: str = "laps", detail: bool = False) -> str:
        """Get one part of an activity's data from Garmin Connect

        kind: details (charts and metrics), laps, rounds (HIIT, boxing with
        exercise sets), workout_steps (per step of a structured workout),
        jumps (jump rope), subsecond (when the activity has sub-second data),
        swim (lap swimming lengths), map (polyline and heat map), polyline
        (encoded track), photos, segments (matched segments), adjacent (ids
        of the previous and next activity).

        Args:
            activity_id: Garmin activity id
            kind: Which part, see the list above (default laps)
            detail: true for every sample; by default long series are shortened
        """
        try:
            fetch = _choice(kind, _ACTIVITY_DATA, "kind")
            activity = _positive(activity_id, "activity_id")
            try:
                data = fetch(activity)
            except Exception as e:
                reason = _OPTIONAL_KINDS.get(kind.strip().lower())
                if reason and ("500" in str(e) or "server error" in str(e).lower()):
                    return f"Activity {activity} has no {kind} data ({reason}; Garmin answered with a server error)."
                raise
            return _result(data, f"Activity {activity} has no {kind} data.", detail)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving activity {kind}: {str(e)}"

    @app.tool()
    async def find_activities(kind: str = "search", filters: str = "",
                              start: int = 0, limit: int = 20,
                              start_date: Optional[str] = None, end_date: Optional[str] = None,
                              detail: bool = False) -> str:
        """Find activities: search with the web app's filters, favourites, the last one, or training load per activity

        kind:
          search: filters as a JSON object, keys as the web app uses them:
            activityType (e.g. running), activitySubType, startDate, endDate
            (YYYY-MM-DD), search (free text), favorite (true), sortBy,
            sortOrder, minDistance/maxDistance (m), minDuration/maxDuration
            (s), minElevation/maxElevation (m), eventType, excludeChildren
          favorites: activities marked as favourite (limit)
          last: the most recent activity
          training_load: each activity's training load between start_date and end_date

        Args:
            kind: search, favorites, last or training_load (default search)
            filters: JSON object of search filters (kind=search)
            start: Offset of the first result (kind=search)
            limit: Number of results (default 20, at most 100)
            start_date: First day for kind=training_load, YYYY-MM-DD
            end_date: Last day for kind=training_load, YYYY-MM-DD
            detail: true for Garmin's full activity summaries (~130 fields each);
                by default each activity is shortened to its key fields
        """
        try:
            key = (kind or "").strip().lower()
            count = _positive(limit, "limit", 100)
            if key == "search":
                query = _json_object(filters, "filters") if filters else {}
                unknown = sorted(set(query) - set(_SEARCH_FILTERS))
                if unknown:
                    return f"Unknown filter(s): {', '.join(unknown)}; use: {', '.join(_SEARCH_FILTERS)}"
                if isinstance(start, bool) or not isinstance(start, int) or start < 0:
                    return "start must be 0 or more"
                result = garmin_client.search_activities(start, count, **query)
            elif key == "favorites":
                result = garmin_client.get_favorite_activities(count)
            elif key == "last":
                result = garmin_client.get_last_activity()
            elif key == "training_load":
                first, last = _range(start_date, end_date)
                result = garmin_client.get_training_load_activities(first, last)
            else:
                return "kind must be search, favorites, last or training_load"
            if not detail and key in ("search", "favorites", "last"):
                result = _summaries(result)
            return _result(result, "No activities found.", detail)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error finding activities: {str(e)}"

    @app.tool()
    async def get_activity_aggregates(kind: str, start_date: str, end_date: str,
                                      activity_type: str = "running", number_of_bests: int = 10) -> str:
        """Get activity aggregates over a date range

        kind:
          weekly: weekly totals per activity type (distance, duration, VO2 max, ...)
          fastest_splits: best times per distance for activity_type
          available_metrics: which progress metrics have data per activity type

        Args:
            kind: weekly, fastest_splits or available_metrics
            start_date: First day, YYYY-MM-DD
            end_date: Last day, YYYY-MM-DD
            activity_type: Activity type key for fastest_splits (default running)
            number_of_bests: Best efforts per distance for fastest_splits (default 10)
        """
        try:
            first, last = _range(start_date, end_date)
            key = (kind or "").strip().lower()
            if key == "weekly":
                result = garmin_client.get_weekly_activity_stats(first, last)
            elif key == "fastest_splits":
                if not _TYPE_KEY_RE.match(activity_type or ""):
                    return "activity_type must be a type key such as running or cycling"
                result = garmin_client.get_fastest_splits(first, last, activity_type,
                                                          _positive(number_of_bests, "number_of_bests", 50))
            elif key == "available_metrics":
                result = garmin_client.get_available_metrics(first, last)
            else:
                return "kind must be weekly, fastest_splits or available_metrics"
            return _result(result, f"No {key} data between {first} and {last}.", False)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving activity aggregates: {str(e)}"

    @app.tool()
    async def get_activity_event_types() -> str:
        """List the activity event types (race, training, recreation, ...) Garmin offers"""
        try:
            return _result(garmin_client.get_activity_event_types(), "No event types.", True)
        except Exception as e:
            return f"Error retrieving event types: {str(e)}"

    @app.tool()
    async def set_activity_favorite(activity_id: int, favorite: bool = True) -> str:
        """Mark an activity as favourite, or remove the mark

        Args:
            activity_id: Garmin activity id
            favorite: true to mark, false to unmark
        """
        tracker = WriteTracker("set_activity_favorite", "Error changing activity favourite")
        try:
            activity = _positive(activity_id, "activity_id")
            tracker.sending()
            garmin_client.set_activity_favorite(activity, bool(favorite))
            tracker.committed()
            return _dump({"status": "success", "activity_id": activity, "favorite": bool(favorite)})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_activity(activity_id: int, fields: str) -> str:
        """Change several fields of an activity in one call (the web app's activity editor)

        fields: JSON object with any of activityName, description,
        activityTypeDTO, eventTypeDTO, metadataDTO, accessControlRuleDTO
        (privacy), in the shapes get_activity returns. For one field the
        set_activity_name / set_activity_description / set_activity_type
        tools are simpler.

        Args:
            activity_id: Garmin activity id
            fields: JSON object with the fields to change
        """
        tracker = WriteTracker("update_activity", "Error updating activity")
        try:
            activity = _positive(activity_id, "activity_id")
            patch = _json_object(fields, "fields")
            protected = sorted(_PROTECTED_ACTIVITY_FIELDS & patch.keys())
            if protected:
                return f"These fields identify the activity and cannot be changed: {', '.join(protected)}."
            tracker.sending()
            result = garmin_client.update_activity(activity, patch)
            tracker.committed()
            return _dump({"status": "success", "activity_id": activity, "changed": sorted(patch), "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def create_activity_from_json(activity: str) -> str:
        """Create a manual activity from a complete Garmin activity payload

        For a simple manual activity create_manual_activity is easier; this
        one takes the full payload (summaryDTO, activityTypeDTO, ...) for
        fields that tool does not offer.

        Args:
            activity: Complete activity JSON object as Garmin's manual-activity endpoint expects
        """
        tracker = WriteTracker("create_activity_from_json", "Error creating activity")
        try:
            payload = _json_object(activity, "activity")
            tracker.sending()
            created = garmin_client.create_manual_activity_from_json(payload)
            tracker.committed()
            return _dump({"status": "success", "activity": created})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def upload_activity_file(filename: str, content_base64: str, as_import: bool = False) -> str:
        """Upload a FIT, GPX or TCX activity file to Garmin Connect

        The file is sent as base64 text, so remote clients can upload. With
        as_import=true it is stored as an import, which Garmin does not
        forward to linked services such as Strava.

        Args:
            filename: Original file name; must end in .fit, .gpx or .tcx
            content_base64: The file's bytes, base64-encoded (at most 25 MB decoded)
            as_import: true to upload as an import
        """
        tracker = WriteTracker("upload_activity_file", "Error uploading activity file")
        path = None
        try:
            name = os.path.basename(filename or "")
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in _UPLOAD_SUFFIXES:
                return "filename must end in .fit, .gpx or .tcx"
            try:
                data = base64.b64decode(content_base64 or "", validate=True)
            except (binascii.Error, ValueError):
                return "content_base64 is not valid base64"
            if not data:
                return "The file is empty."
            if len(data) > _MAX_UPLOAD_BYTES:
                return "The file is larger than 25 MB."
            handle, path = tempfile.mkstemp(suffix=suffix, prefix="slurp-upload-")
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            tracker.sending()
            result = (garmin_client.import_activity(path) if as_import
                      else garmin_client.upload_activity(path))
            tracker.committed()
            body = result.json() if hasattr(result, "json") else result
            return _dump({"status": "success", "filename": name, "as_import": bool(as_import), "result": body})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    return app
