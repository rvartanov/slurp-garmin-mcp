"""
Workout library, body measurements and gear tools (Slurp garmin-mcp).

Exposes the workout, body and gear methods garminconnect >= 0.3.20 adds:
workout library counts and dictionaries, upcoming scheduled workouts,
copying workouts; weight and blood pressure series, deleting single
weigh-ins and readings, blood pressure notes; the gear v2 endpoints
(list, details, activities, types, catalogue search) and creating,
editing, retiring, defaulting and deleting gear. Fork-specific module.
"""
import json
import re
from typing import Any, Callable, Dict, Optional

from garmin_mcp.health_extra import _choice, _compact, _date, _positive, _range
from garmin_mcp.race_events import _json_object
from garmin_mcp.write_errors import WriteTracker

# The garmin_client will be set by the main file
garmin_client = None

_UUID_RE = re.compile(r"^[0-9a-fA-F-]{16,40}$")
_KEY_RE = re.compile(r"^[A-Za-z_]+$")
_GEAR_FIELDS = (
    "name", "brand", "model", "gear_type", "first_use_date", "usage_type",
    "max_usage_distance_km", "max_usage_duration_min", "notes", "activity_type_keys",
)


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _result(value: Any, empty: str, detail: bool = False) -> str:
    if value is None or value == [] or value == {}:
        return empty
    return _dump(value if detail else _compact(value))


def _uuid(value: Any, name: str = "gear_uuid") -> str:
    if not isinstance(value, str) or not _UUID_RE.match(value):
        raise ValueError(f"{name} must be the gear's uuid (from get_gear_data kind=list)")
    return value


def _find_version(value: Any, version: str) -> Optional[Dict[str, Any]]:
    """Find the blood pressure measurement with this version anywhere in a response."""
    if isinstance(value, dict):
        if str(value.get("version")) == str(version) and "systolic" in value:
            return value
        for item in value.values():
            found = _find_version(item, version)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_version(item, version)
            if found:
                return found
    return None


def _scheduled_summary(entry: Any) -> Any:
    """One scheduled workout without the full workout definition (~20 KB each)."""
    if not isinstance(entry, dict) or not isinstance(entry.get("workout"), dict):
        return entry
    workout = entry["workout"]
    sport = workout.get("sportType") if isinstance(workout.get("sportType"), dict) else {}
    short = {key: entry.get(key) for key in ("workoutScheduleId", "calendarDate", "race", "priority",
                                              "associatedActivityId", "tpType") if key in entry}
    short["workout"] = {key: workout.get(key) for key in ("workoutId", "workoutName", "description",
                                                          "estimatedDurationInSecs", "estimatedDistanceInMeters",
                                                          "trainingPlanId") if workout.get(key) is not None}
    if sport.get("sportTypeKey"):
        short["workout"]["sport"] = sport["sportTypeKey"]
    return short


_WORKOUT_LIBRARY: Dict[str, Callable[[], Any]] = {
    "count": lambda: garmin_client.get_workout_count(),
    "sport_types": lambda: garmin_client.get_workout_sport_types(),
    "workout_types": lambda: garmin_client.get_workout_types(),
    "strength_benchmarks": lambda: garmin_client.get_strength_benchmarks(),
}


def register_tools(app):
    """Register the workout library, body and gear tools with the MCP server app"""

    # ---- workouts -------------------------------------------------------

    @app.tool()
    async def get_workout_library(kind: str = "count") -> str:
        """Get information about the workout library

        kind: count (workouts per sport), sport_types (sports that have
        workouts), workout_types (Garmin's step, condition, target, sport
        and equipment dictionaries, for building workout JSON),
        strength_benchmarks (exercises used for one-rep-max targets).

        Args:
            kind: Which information, see the list above (default count)
        """
        try:
            fetch = _choice(kind, _WORKOUT_LIBRARY, "kind")
            return _result(fetch(), f"No {kind} data.", kind == "count")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving workout library {kind}: {str(e)}"

    @app.tool()
    async def get_upcoming_workouts(start_date: Optional[str] = None, end_date: Optional[str] = None,
                                    detail: bool = False) -> str:
        """Get scheduled workouts: the next one, or all in a period (including adaptive plans)

        Without dates this returns the earliest upcoming workout.

        Args:
            start_date: First day, YYYY-MM-DD (with end_date)
            end_date: Last day, YYYY-MM-DD (with start_date)
            detail: true for each workout's full definition (steps, targets);
                by default only its name, sport, duration and distance
        """
        try:
            if not start_date and not end_date:
                data = garmin_client.get_next_scheduled_workout()
                empty = "No upcoming scheduled workout."
            else:
                first, last = _range(start_date, end_date)
                data = garmin_client.get_scheduled_workouts_by_period(first, last)
                empty = f"No scheduled workouts between {first} and {last}."
            if not detail:
                data = [_scheduled_summary(e) for e in data] if isinstance(data, list) else _scheduled_summary(data)
            return _result(data, empty, True)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving scheduled workouts: {str(e)}"

    @app.tool()
    async def copy_workout(workout_id: int, name: str) -> str:
        """Duplicate a workout in the library under a new name

        Args:
            workout_id: Garmin workout id to copy
            name: Name of the copy
        """
        tracker = WriteTracker("copy_workout", "Error copying workout")
        try:
            workout = _positive(workout_id, "workout_id")
            if not isinstance(name, str) or not name.strip():
                return "name must not be empty"
            tracker.sending()
            copy = garmin_client.copy_workout(workout, name.strip())
            tracker.committed()
            return _dump({"status": "success", "workout_id": (copy or {}).get("workoutId") if isinstance(copy, dict) else None,
                          "name": name.strip()})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    # ---- body -----------------------------------------------------------

    @app.tool()
    async def get_weight_data(kind: str = "latest", start_date: Optional[str] = None,
                              end_date: Optional[str] = None, date: Optional[str] = None,
                              aggregation: str = "daily") -> str:
        """Get weight data from Garmin Connect

        kind:
          latest: the most recent weigh-in as of date (default today)
          first: the first weigh-in ever recorded
          daily_last: the last weigh-in of each day between start_date and end_date
          all: every weigh-in between start_date and end_date
          weekly: weekly averages for the 52 weeks ending at end_date (default today)
          power_to_weight: power-to-weight history between start_date and end_date

        Args:
            kind: Which data, see the list above (default latest)
            start_date: First day, YYYY-MM-DD (range kinds)
            end_date: Last day, YYYY-MM-DD (range kinds, weekly)
            date: Day for kind=latest, YYYY-MM-DD
            aggregation: daily, weekly or monthly for power_to_weight
        """
        try:
            key = (kind or "").strip().lower()
            if key == "latest":
                data = garmin_client.get_latest_weight(_date(date, "date", default_today=True))
            elif key == "first":
                data = garmin_client.get_first_weight()
            elif key == "weekly":
                data = garmin_client.get_weekly_weight(_date(end_date, "end_date", default_today=True))
            elif key in ("daily_last", "all", "power_to_weight"):
                first, last = _range(start_date, end_date)
                if key == "daily_last":
                    data = garmin_client.get_daily_last_weight(first, last)
                elif key == "all":
                    data = garmin_client.get_weight_snapshot(first, last)
                else:
                    data = garmin_client.get_power_to_weight_range(first, last, (aggregation or "daily").lower())
            else:
                return "kind must be latest, first, daily_last, all, weekly or power_to_weight"
            return _result(data, f"No {key} weight data.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving weight data: {str(e)}"

    @app.tool()
    async def get_blood_pressure_data(kind: str = "day", date: Optional[str] = None,
                                      start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """Get blood pressure readings from Garmin Connect

        kind: day (every reading of date, with the version needed to edit
        or delete one), daily_last (the last reading of each day between
        start_date and end_date), weekly (weekly averages for the 52 weeks
        ending at end_date).

        Args:
            kind: day, daily_last or weekly (default day)
            date: Day for kind=day, YYYY-MM-DD (default today)
            start_date: First day for daily_last, YYYY-MM-DD
            end_date: Last day for daily_last and weekly, YYYY-MM-DD
        """
        try:
            key = (kind or "").strip().lower()
            if key == "day":
                data = garmin_client.get_blood_pressure_day(_date(date, "date", default_today=True))
            elif key == "daily_last":
                first, last = _range(start_date, end_date)
                data = garmin_client.get_daily_last_blood_pressure(first, last)
            elif key == "weekly":
                data = garmin_client.get_weekly_blood_pressure(_date(end_date, "end_date", default_today=True))
            else:
                return "kind must be day, daily_last or weekly"
            return _result(data, f"No {key} blood pressure data.", key == "day")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving blood pressure data: {str(e)}"

    @app.tool()
    async def delete_weigh_in(weight_pk: str, date: str, confirm: bool = False) -> str:
        """Delete one weigh-in (delete_weigh_ins removes all of a day)

        Without confirm=true nothing is deleted.

        Args:
            weight_pk: The weigh-in's samplePk, from get_weight_data or get_daily_weigh_ins
            date: Day of the weigh-in, YYYY-MM-DD
            confirm: true to actually delete
        """
        tracker = WriteTracker("delete_weigh_in", "Error deleting weigh-in")
        try:
            if not re.fullmatch(r"\d+", str(weight_pk or "")):
                return "weight_pk must be the weigh-in's numeric samplePk"
            day = _date(date, "date")
            if not confirm:
                return _dump({"status": "needs_confirmation", "weight_pk": str(weight_pk), "date": day,
                              "message": "Call again with confirm=true to permanently delete this weigh-in."})
            tracker.sending()
            garmin_client.delete_weigh_in(str(weight_pk), day)
            tracker.committed()
            return _dump({"status": "success", "weight_pk": str(weight_pk), "date": day})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_blood_pressure_note(version: str, date: str, notes: str) -> str:
        """Change the note of a blood pressure reading

        Garmin only stores the note on this call; to correct values,
        delete the reading and add it again with set_blood_pressure.

        Args:
            version: The reading's version, from get_blood_pressure_data kind=day
            date: Day of the reading, YYYY-MM-DD
            notes: New note ("" clears it)
        """
        tracker = WriteTracker("update_blood_pressure_note", "Error updating blood pressure note")
        try:
            day = _date(date, "date")
            measurement = _find_version(garmin_client.get_blood_pressure_day(day), version)
            if measurement is None:
                return f"No blood pressure reading with version {version} on {day}."
            tracker.sending()
            result = garmin_client.update_blood_pressure(measurement, notes=notes or "")
            tracker.committed()
            return _dump({"status": "success", "version": version, "date": day, "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def delete_blood_pressure(version: str, date: str, confirm: bool = False) -> str:
        """Delete one blood pressure reading

        Without confirm=true this only shows the reading.

        Args:
            version: The reading's version, from get_blood_pressure_data kind=day
            date: Day of the reading, YYYY-MM-DD
            confirm: true to actually delete
        """
        tracker = WriteTracker("delete_blood_pressure", "Error deleting blood pressure reading")
        try:
            day = _date(date, "date")
            if not re.fullmatch(r"[0-9]+", str(version or "")):
                return "version must be the reading's numeric version"
            if not confirm:
                measurement = _find_version(garmin_client.get_blood_pressure_day(day), version)
                if measurement is None:
                    return _dump({"status": "not_found", "version": version, "date": day})
                return _dump({"status": "needs_confirmation", "reading": {
                    k: measurement.get(k) for k in ("systolic", "diastolic", "pulse", "measurementTimestampLocal", "notes")},
                    "message": "Review this reading, then call again with confirm=true to delete it."})
            tracker.sending()
            garmin_client.delete_blood_pressure(str(version), day)
            tracker.committed()
            return _dump({"status": "success", "version": version, "date": day})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    # ---- gear -----------------------------------------------------------

    @app.tool()
    async def get_gear_data(kind: str = "list", gear_uuid: Optional[str] = None,
                            activity_id: Optional[int] = None, keywords: Optional[str] = None,
                            status: Optional[str] = None, gear_type: Optional[str] = None,
                            start: int = 0, limit: int = 20) -> str:
        """Get gear data from Garmin Connect (the web app's gear v2 endpoints)

        kind:
          list: your gear, optionally filtered by status (ACTIVE, RETIRED)
            and gear_type (e.g. SHOES)
          details: one piece of gear (gear_uuid)
          activities: activities a piece of gear was used in (gear_uuid)
          types: all gear types Garmin knows
          user_types: gear types you have
          make_models: search Garmin's brand/model catalogue (keywords)
          activity: gear linked to an activity (activity_id)

        Args:
            kind: Which data, see the list above (default list)
            gear_uuid: Gear uuid for details/activities
            activity_id: Activity id for kind=activity
            keywords: Search text for kind=make_models
            status: Status filter for kind=list
            gear_type: Gear type filter for kind=list
            start: Offset for kind=list
            limit: Number of results (default 20, at most 1000)
        """
        try:
            key = (kind or "").strip().lower()
            count = _positive(limit, "limit", 1000)
            if key == "list":
                statuses = [status.upper()] if status else None
                data = garmin_client.get_gear_list(start=start, limit=count, gear_statuses=statuses,
                                                   gear_type=gear_type.upper() if gear_type else None)
            elif key == "details":
                data = garmin_client.get_gear_details(_uuid(gear_uuid))
            elif key == "activities":
                data = garmin_client.get_gear_activities(_uuid(gear_uuid), count)
            elif key == "types":
                data = garmin_client.get_gear_types()
            elif key == "user_types":
                data = garmin_client.get_user_gear_types()
            elif key == "make_models":
                if not keywords or not keywords.strip():
                    return "keywords must not be empty for kind=make_models"
                data = garmin_client.get_gear_make_models(keywords.strip())
            elif key == "activity":
                data = garmin_client.get_activity_gear_v2(_positive(activity_id, "activity_id"))
            else:
                return "kind must be list, details, activities, types, user_types, make_models or activity"
            return _result(data, f"No {key} gear data.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving gear data: {str(e)}"

    @app.tool()
    async def create_gear(gear_type: str, brand: str, model: str, name: str, first_use_date: str,
                          usage_type: str = "DISTANCE", max_usage_distance_km: Optional[float] = None,
                          max_usage_duration_min: Optional[float] = None, notes: str = "",
                          activity_types: str = "") -> str:
        """Add a piece of gear (shoes, bike, ...) to Garmin Connect

        Args:
            gear_type: Gear type key, e.g. SHOES or BIKE (see get_gear_data kind=types)
            brand: Brand, e.g. ASICS
            model: Model, e.g. Novablast 5
            name: Your name for it
            first_use_date: First use, YYYY-MM-DD
            usage_type: DISTANCE or TIME tracking (default DISTANCE)
            max_usage_distance_km: Retire reminder after this distance
            max_usage_duration_min: Retire reminder after this duration
            notes: Notes
            activity_types: Comma-separated activity type keys to use it for by default, e.g. running,trail_running
        """
        tracker = WriteTracker("create_gear", "Error creating gear")
        try:
            for label, value in (("gear_type", gear_type), ("usage_type", usage_type)):
                if not _KEY_RE.match(value or ""):
                    return f"{label} must be a key such as SHOES or DISTANCE"
            for label, value in (("brand", brand), ("model", model), ("name", name)):
                if not isinstance(value, str) or not value.strip():
                    return f"{label} must not be empty"
            day = _date(first_use_date, "first_use_date")
            keys = [k.strip() for k in (activity_types or "").split(",") if k.strip()] or None
            tracker.sending()
            gear = garmin_client.create_gear(gear_type.upper(), brand.strip(), model.strip(), name.strip(), day,
                                             usage_type=usage_type.upper(),
                                             max_usage_distance_km=max_usage_distance_km,
                                             max_usage_duration_min=max_usage_duration_min,
                                             notes=notes or "", activity_type_keys=keys)
            tracker.committed()
            return _dump({"status": "success", "gear": gear})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_gear(gear_uuid: str, changes: str) -> str:
        """Edit a piece of gear; only the given fields change

        changes: JSON object with any of name, brand, model, gear_type,
        first_use_date (YYYY-MM-DD), usage_type, max_usage_distance_km,
        max_usage_duration_min, notes ("" clears), activity_type_keys (list).
        0 for a max_usage field removes that retirement threshold.

        Args:
            gear_uuid: The gear's uuid
            changes: JSON object with the fields to change
        """
        tracker = WriteTracker("update_gear", "Error updating gear")
        try:
            uuid = _uuid(gear_uuid)
            patch = _json_object(changes, "changes")
            unknown = sorted(set(patch) - set(_GEAR_FIELDS))
            if unknown:
                return f"Unknown field(s): {', '.join(unknown)}; use: {', '.join(_GEAR_FIELDS)}"
            tracker.sending()
            gear = garmin_client.update_gear(uuid, **patch)
            tracker.committed()
            return _dump({"status": "success", "gear_uuid": uuid, "changed": sorted(patch), "gear": gear})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def set_gear_status(gear_uuid: str, status: str) -> str:
        """Retire a piece of gear, or make it active again

        Args:
            gear_uuid: The gear's uuid
            status: RETIRED or ACTIVE
        """
        tracker = WriteTracker("set_gear_status", "Error changing gear status")
        try:
            uuid = _uuid(gear_uuid)
            value = (status or "").strip().upper()
            if value not in ("ACTIVE", "RETIRED"):
                return "status must be ACTIVE or RETIRED"
            tracker.sending()
            garmin_client.set_gear_status(uuid, value)
            tracker.committed()
            return _dump({"status": "success", "gear_uuid": uuid, "gear_status": value})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def set_gear_default(gear_uuid: str, activity_type: str, default: bool = True) -> str:
        """Make gear the default for an activity type (new activities of that type get it), or remove that

        Args:
            gear_uuid: The gear's uuid
            activity_type: Activity type key, e.g. running
            default: true to make it the default, false to remove it as default
        """
        tracker = WriteTracker("set_gear_default", "Error changing default gear")
        try:
            uuid = _uuid(gear_uuid)
            if not _KEY_RE.match(activity_type or ""):
                return "activity_type must be a type key such as running"
            tracker.sending()
            garmin_client.set_gear_default(activity_type, uuid, bool(default))
            tracker.committed()
            return _dump({"status": "success", "gear_uuid": uuid, "activity_type": activity_type, "default": bool(default)})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def delete_gear(gear_uuid: str, confirm: bool = False) -> str:
        """Delete a piece of gear (set_gear_status RETIRED keeps its history)

        Without confirm=true this only shows the gear.

        Args:
            gear_uuid: The gear's uuid
            confirm: true to actually delete
        """
        tracker = WriteTracker("delete_gear", "Error deleting gear")
        try:
            uuid = _uuid(gear_uuid)
            if not confirm:
                gear = garmin_client.get_gear_details(uuid)
                if not gear:
                    return _dump({"status": "not_found", "gear_uuid": uuid})
                summary = {k: gear.get(k) for k in ("displayName", "customMakeModel", "gearTypeName", "gearStatusName")
                           if isinstance(gear, dict) and k in gear}
                return _dump({"status": "needs_confirmation", "gear_uuid": uuid, "gear": summary,
                              "message": "Review this gear, then call again with confirm=true to delete it."})
            tracker.sending()
            garmin_client.delete_gear(uuid)
            tracker.committed()
            return _dump({"status": "success", "gear_uuid": uuid})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    return app
