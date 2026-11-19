"""
Race and calendar event tools (Slurp garmin-mcp).

Reads single events, upcoming events and the primary event, and changes or
deletes calendar events and workouts in place, through the calendar and
workout methods of garminconnect >= 0.3.20. Fork-specific module, kept apart
from upstream's calendar_events.py so upstream merges stay easy.
"""
import datetime
import json
import os
import re
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from garmin_mcp.write_errors import WriteTracker

# The garmin_client will be set by the main file
garmin_client = None

# Fields that identify an event or are maintained by Garmin; a change to them
# would either be ignored or move the change to another object.
_PROTECTED_EVENT_FIELDS = frozenset({"id", "shareableEventUuid", "ownerId"})


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def _positive_id(value: Any, name: str) -> int:
    """Return a positive integer id, or raise ValueError with a clear message."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive integer, got {value!r}") from None
    if number <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return number


def _json_object(value: Any, name: str) -> Dict[str, Any]:
    """Accept a dict or a JSON string holding an object."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} is not valid JSON: {exc.msg}") from None
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{name} must be a non-empty JSON object")
    return value


def _deep_merge(base: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
    """Return base with changes applied; nested objects merge, other values replace."""
    merged = dict(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_EVENT_TYPE_RE = re.compile(r"^[a-z_]+$")


def _build_event(name, date, event_type, distance_km, start_time, time_zone,
                 location, goal_time_seconds, note, is_race) -> Dict[str, Any]:
    """The event object Garmin's calendar-service expects for a custom event."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must not be empty")
    if not isinstance(date, str) or not _DATE_RE.match(date):
        raise ValueError(f"Invalid date {date!r}: expected YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise ValueError(f"Invalid date {date!r}: no such day") from None
    if not _EVENT_TYPE_RE.match(event_type or ""):
        raise ValueError("event_type must be a Garmin event type such as running or trail_running")
    event: Dict[str, Any] = {
        "eventName": name.strip(),
        "date": date,
        "eventType": event_type,
        "race": bool(is_race),
        "location": location,
        "note": note,
        "eventCustomization": {"isPrimaryEvent": False, "isTrainingEvent": True},
    }
    if distance_km is not None:
        if isinstance(distance_km, bool) or not isinstance(distance_km, (int, float)) or distance_km <= 0:
            raise ValueError("distance_km must be a positive number")
        event["completionTarget"] = {"value": float(distance_km), "unit": "kilometer", "unitType": "distance"}
    if start_time is not None:
        if not _TIME_RE.match(start_time):
            raise ValueError(f"Invalid start_time {start_time!r}: expected HH:MM")
        zone = (time_zone or os.getenv("GARMIN_TZ") or "UTC").strip()
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown time zone {zone!r}: use an IANA name such as Europe/Amsterdam") from None
        event["eventTimeLocal"] = {"startTimeHhMm": start_time, "timeZoneId": zone}
    if goal_time_seconds is not None:
        if isinstance(goal_time_seconds, bool) or not isinstance(goal_time_seconds, int) or goal_time_seconds <= 0:
            raise ValueError("goal_time_seconds must be a positive whole number of seconds")
        event["eventCustomization"]["customGoal"] = {
            "value": goal_time_seconds, "unit": "second", "unitType": "time",
        }
    return event


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def register_tools(app):
    """Register the race and calendar event tools with the MCP server app"""

    @app.tool()
    async def get_calendar_event(event_id: int) -> str:
        """Get the full details of one Garmin Connect calendar event (race or goal event)

        Returns Garmin's complete event object, including the custom goal
        (eventCustomization), start time, location, distance target and
        whether it is the primary event. Use the event_id from
        get_calendar_events or get_upcoming_events. The object returned here
        is also the shape update_calendar_event changes.

        Args:
            event_id: Garmin's calendar event id
        """
        try:
            event = garmin_client.get_calendar_event(_positive_id(event_id, "event_id"))
            if not event:
                return f"No calendar event found with id {event_id}."
            return _dump(event)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving calendar event: {str(e)}"

    @app.tool()
    async def get_upcoming_events(days_forward: int = 90, limit: int = 10) -> str:
        """Get the upcoming races and goal events on the Garmin Connect calendar

        Faster than get_calendar_events for "what is my next race": Garmin
        returns the next events from today, nearest first.

        Args:
            days_forward: How many days ahead to look (default 90)
            limit: Maximum number of events (default 10)
        """
        try:
            days = _positive_id(days_forward, "days_forward")
            count = _positive_id(limit, "limit")
            events = garmin_client.get_upcoming_events(days_forward=days, limit=count)
            if not events:
                return f"No upcoming events in the next {days} days."
            return _dump(events)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving upcoming events: {str(e)}"

    @app.tool()
    async def get_primary_event() -> str:
        """Get the primary (focus) race on Garmin Connect, if one is set

        The primary event is the race a training plan and the race-day
        widgets on the watch count down to.
        """
        try:
            event = garmin_client.get_primary_event()
            if not event:
                return "No primary event is set."
            return _dump(event)
        except Exception as e:
            return f"Error retrieving primary event: {str(e)}"

    @app.tool()
    async def create_race_event(
        name: str,
        date: str,
        event_type: str = "running",
        distance_km: Optional[float] = None,
        start_time: Optional[str] = None,
        time_zone: Optional[str] = None,
        location: Optional[str] = None,
        goal_time_seconds: Optional[int] = None,
        note: Optional[str] = None,
        is_race: bool = True,
    ) -> str:
        """Add a race or goal event to the Garmin Connect calendar

        Creates a custom event, like adding a race by hand in Connect. The
        watch and Connect then show it on the calendar and count down to
        it. Make it the primary race afterwards with update_calendar_event
        and {"eventCustomization": {"isPrimaryEvent": true}}.

        Args:
            name: Event name, e.g. "Rotterdam Marathon"
            date: Event date in YYYY-MM-DD format
            event_type: Garmin event type, e.g. running, trail_running, cycling,
                triathlon, swimming (default running)
            distance_km: Race distance in kilometers
            start_time: Local start time as HH:MM
            time_zone: IANA time zone of the start time, e.g. Europe/Amsterdam
                (default GARMIN_TZ, else UTC)
            location: Free-text location
            goal_time_seconds: Your goal finish time in seconds
            note: Free-text note
            is_race: true for a race, false for another goal event
        """
        tracker = WriteTracker("create_race_event", "Error creating race event")
        try:
            event = _build_event(name, date, event_type, distance_km, start_time,
                                 time_zone, location, goal_time_seconds, note, is_race)
            tracker.sending()
            created = garmin_client.create_calendar_event(event)
            tracker.committed()
            event_id = created.get("id") if isinstance(created, dict) else None
            return _dump({"status": "success", "event_id": event_id, "event": created})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_calendar_event(event_id: int, changes: str) -> str:
        """Change fields of an existing Garmin Connect calendar event in place

        Reads the full event, applies the changes and writes it back, so the
        event keeps its id and everything not mentioned stays as it is.
        Nested objects are merged (e.g. only the goal value inside
        eventCustomization), other values are replaced. Call
        get_calendar_event first to see the field names.

        Examples of changes:
          {"eventName": "Rotterdam Marathon"}
          {"eventCustomization": {"customGoal": {"value": 12600, "unit": "second", "unitType": "time"}}}
          {"eventCustomization": {"isPrimaryEvent": true}}   (make it the primary race)

        Args:
            event_id: Garmin's calendar event id
            changes: JSON object with the fields to change
        """
        tracker = WriteTracker("update_calendar_event", "Error updating calendar event")
        try:
            event_id = _positive_id(event_id, "event_id")
            patch = _json_object(changes, "changes")
            protected = sorted(_PROTECTED_EVENT_FIELDS & patch.keys())
            if protected:
                return f"These fields identify the event and cannot be changed: {', '.join(protected)}."
            current = garmin_client.get_calendar_event(event_id)
            if not isinstance(current, dict) or not current:
                return f"No calendar event found with id {event_id}."
            updated = _deep_merge(current, patch)
            tracker.sending()
            garmin_client.update_calendar_event(event_id, updated)
            tracker.committed()
            after = garmin_client.get_calendar_event(event_id)
            return _dump({"status": "success", "event_id": event_id, "event": after or updated})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def delete_calendar_event(event_id: int, confirm: bool = False) -> str:
        """Delete a race or event from the Garmin Connect calendar

        Without confirm=true this only shows the event that would be deleted.
        Call again with confirm=true to delete it permanently.

        Args:
            event_id: Garmin's calendar event id
            confirm: true to actually delete
        """
        tracker = WriteTracker("delete_calendar_event", "Error deleting calendar event")
        try:
            event_id = _positive_id(event_id, "event_id")
            if not confirm:
                event = garmin_client.get_calendar_event(event_id)
                if not event:
                    return _dump({"status": "not_found", "event_id": event_id})
                return _dump({
                    "status": "needs_confirmation",
                    "event_id": event_id,
                    "event": {k: event.get(k) for k in ("eventName", "date", "location", "race") if k in event},
                    "message": "Review this event, then call again with confirm=true to permanently delete it.",
                })
            tracker.sending()
            garmin_client.delete_calendar_event(event_id)
            tracker.committed()
            return _dump({"status": "success", "event_id": event_id, "message": f"Calendar event {event_id} deleted."})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_workout(workout_id: int, workout: str) -> str:
        """Replace an existing workout in place, keeping its id and schedules

        Changing a workout with delete + upload would give it a new id and
        drop it from the calendar; this keeps the id, so scheduled copies
        stay valid. The workout must be the complete structure, as returned
        by get_workout_by_id, with your changes applied.

        Args:
            workout_id: Garmin's workout id
            workout: Complete workout JSON object (as from get_workout_by_id)
        """
        tracker = WriteTracker("update_workout", "Error updating workout")
        try:
            workout_id = _positive_id(workout_id, "workout_id")
            body = _json_object(workout, "workout")
            if not body.get("workoutSegments"):
                return ("workout must be the complete workout including workoutSegments; "
                        "fetch it with get_workout_by_id, change it, and pass the whole object.")
            tracker.sending()
            result = garmin_client.update_workout(workout_id, body)
            tracker.committed()
            return _dump({"status": "success", "workout_id": workout_id, "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    return app
