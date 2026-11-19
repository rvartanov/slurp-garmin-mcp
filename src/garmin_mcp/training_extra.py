"""
Training plans, calendar notes and course management (Slurp garmin-mcp).

Exposes the training, calendar and course methods garminconnect >= 0.3.20
adds: training plans (yours, active, catalogue; schedule and remove),
calendar week/year overviews, moving calendar items, calendar notes, course
creation from an activity, course edits and favourites, and PacePro pace
bands. Fork-specific module.
"""
import json
import re
from typing import Any, Optional

from garmin_mcp.health_extra import _compact, _date, _positive
from garmin_mcp.race_events import _deep_merge, _json_object
from garmin_mcp.write_errors import WriteTracker

# The garmin_client will be set by the main file
garmin_client = None

_ITEM_TYPE_RE = re.compile(r"^[A-Za-z_-]+$")
_LOCALE_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _result(value: Any, empty: str, detail: bool = True) -> str:
    if value is None or value == [] or value == {}:
        return empty
    return _dump(value if detail else _compact(value))


def _locale(value: str) -> str:
    if not isinstance(value, str) or not _LOCALE_RE.match(value):
        raise ValueError("locale must look like en or nl-NL")
    return value


def _text(value: Any, name: str, required: bool = True) -> str:
    if value is None or value == "":
        if required:
            raise ValueError(f"{name} must not be empty")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    return value.strip()


def register_tools(app):
    """Register the training plan, calendar and course tools with the MCP server app"""

    # ---- training plans -------------------------------------------------

    @app.tool()
    async def get_training_plans(scope: str = "mine", date: Optional[str] = None,
                                 status: Optional[str] = None, start: int = 1,
                                 limit: int = 20, locale: str = "en") -> str:
        """List Garmin Connect training plans: yours, the ones active on a day, or the catalogue

        Args:
            scope: mine (your plans), active (running on date) or catalog
                (Garmin's plan catalogue to choose from)
            date: Day for scope=active, YYYY-MM-DD (default today)
            status: Optional status filter for scope=mine, as Garmin uses it
            start: First catalogue entry, 1-based (scope=catalog)
            limit: Number of plans (default 20, at most 100)
            locale: Language of catalogue texts, e.g. en or nl-NL (scope=catalog)
        """
        try:
            key = (scope or "").strip().lower()
            count = _positive(limit, "limit", 100)
            if key == "mine":
                plans = garmin_client.get_training_plans(limit=count, start=None, status=status)
            elif key == "active":
                plans = garmin_client.get_active_training_plans(_date(date, "date", default_today=True))
            elif key == "catalog":
                plans = garmin_client.search_training_plans(start=_positive(start, "start"), limit=count,
                                                            locale=_locale(locale))
            else:
                return "scope must be mine, active or catalog"
            return _result(plans, f"No {key} training plans.", key != "catalog")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving training plans: {str(e)}"

    @app.tool()
    async def get_training_plan(plan_id: int, adaptive: bool = False, include_tasks: bool = False,
                                locale: str = "en") -> str:
        """Get one training plan, optionally with its workout tasks

        Args:
            plan_id: Training plan id
            adaptive: true for a Garmin Coach / adaptive plan
            include_tasks: true to add the plan's workout tasks
            locale: Language of task texts, e.g. en or nl-NL
        """
        try:
            plan = _positive(plan_id, "plan_id")
            details = (garmin_client.get_adaptive_training_plan_by_id(plan) if adaptive
                       else garmin_client.get_training_plan_by_id(plan))
            result = {"plan": details}
            if include_tasks:
                result["tasks"] = garmin_client.get_training_plan_tasks(plan, locale=_locale(locale))
            return _dump(_compact(result))
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving training plan: {str(e)}"

    @app.tool()
    async def schedule_training_plan(plan_id: int, start_date: str) -> str:
        """Put a training plan from Garmin's catalogue on your calendar from a start date

        Args:
            plan_id: Catalogue plan id (from get_training_plans scope=catalog)
            start_date: First day of the plan, YYYY-MM-DD
        """
        tracker = WriteTracker("schedule_training_plan", "Error scheduling training plan")
        try:
            plan = _positive(plan_id, "plan_id")
            day = _date(start_date, "start_date")
            tracker.sending()
            result = garmin_client.schedule_training_plan(plan, day)
            tracker.committed()
            return _dump({"status": "success", "plan_id": plan, "start_date": day, "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def delete_training_plan(plan_id: int, confirm: bool = False) -> str:
        """Remove a scheduled training plan and its workouts from your calendar

        Without confirm=true this only shows the plan.

        Args:
            plan_id: Your training plan id (from get_training_plans scope=mine)
            confirm: true to actually remove it
        """
        tracker = WriteTracker("delete_training_plan", "Error removing training plan")
        try:
            plan = _positive(plan_id, "plan_id")
            if not confirm:
                details = garmin_client.get_training_plan_by_id(plan)
                if not details:
                    return _dump({"status": "not_found", "plan_id": plan})
                summary = {k: details.get(k) for k in ("name", "startDate", "endDate", "trainingStatus") if isinstance(details, dict) and k in details}
                return _dump({"status": "needs_confirmation", "plan_id": plan, "plan": summary,
                              "message": "Review this plan, then call again with confirm=true to remove it."})
            tracker.sending()
            garmin_client.delete_training_plan(plan)
            tracker.committed()
            return _dump({"status": "success", "plan_id": plan, "message": f"Training plan {plan} removed."})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    # ---- calendar -------------------------------------------------------

    @app.tool()
    async def get_calendar_overview(view: str = "week", date: Optional[str] = None,
                                    first_day_of_week: int = 1, detail: bool = False) -> str:
        """Get the Garmin Connect calendar for a week (all items) or a year (which days have items)

        Args:
            view: week or year (default week)
            date: A day in the week, or in the year, YYYY-MM-DD (default today)
            first_day_of_week: 1 = Monday ... 7 = Sunday, for view=week (default 1)
            detail: true for the full items; by default empty and false fields
                are left out
        """
        try:
            day = _date(date, "date", default_today=True)
            key = (view or "").strip().lower()
            if key == "week":
                first = _positive(first_day_of_week, "first_day_of_week", 7)
                data = garmin_client.get_calendar_week(day, first)
            elif key == "year":
                data = garmin_client.get_calendar_year(int(day[:4]))
            else:
                return "view must be week or year"
            return _result(data, f"No calendar items for that {key}.", detail)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving calendar: {str(e)}"

    @app.tool()
    async def move_calendar_item(item_type: str, item_id: int, new_date: str) -> str:
        """Move a calendar item (a scheduled workout, a note, ...) to another day

        For scheduled workouts reschedule_workout does the same.

        Args:
            item_type: The item's itemType from get_calendar_overview, e.g. workout or note
            item_id: The item's id
            new_date: Target day, YYYY-MM-DD
        """
        tracker = WriteTracker("move_calendar_item", "Error moving calendar item")
        try:
            if not _ITEM_TYPE_RE.match(item_type or ""):
                return "item_type must be an itemType such as workout or note"
            item = _positive(item_id, "item_id")
            day = _date(new_date, "new_date")
            tracker.sending()
            result = garmin_client.move_calendar_item(item_type, item, day)
            tracker.committed()
            return _dump({"status": "success", "item_type": item_type, "item_id": item, "date": day, "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def create_calendar_note(date: str, name: str, content: str = "") -> str:
        """Add a note to a day on the Garmin Connect calendar

        Args:
            date: Day, YYYY-MM-DD
            name: Note title
            content: Note text
        """
        tracker = WriteTracker("create_calendar_note", "Error creating calendar note")
        try:
            day = _date(date, "date")
            title = _text(name, "name")
            body = _text(content, "content", required=False)
            tracker.sending()
            note = garmin_client.create_calendar_note(day, title, body)
            tracker.committed()
            return _dump({"status": "success", "note_id": note.get("id") if isinstance(note, dict) else None, "note": note})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_calendar_note(note_id: int, date: str, name: str, content: str = "") -> str:
        """Change a calendar note's day, title or text (all three are written)

        Args:
            note_id: The note's id
            date: Day, YYYY-MM-DD
            name: Note title
            content: Note text
        """
        tracker = WriteTracker("update_calendar_note", "Error updating calendar note")
        try:
            note = _positive(note_id, "note_id")
            day = _date(date, "date")
            title = _text(name, "name")
            body = _text(content, "content", required=False)
            tracker.sending()
            result = garmin_client.update_calendar_note(note, day, title, body)
            tracker.committed()
            return _dump({"status": "success", "note_id": note, "note": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def delete_calendar_note(note_id: int, confirm: bool = False) -> str:
        """Delete a calendar note

        Without confirm=true nothing is deleted.

        Args:
            note_id: The note's id
            confirm: true to actually delete
        """
        tracker = WriteTracker("delete_calendar_note", "Error deleting calendar note")
        try:
            note = _positive(note_id, "note_id")
            if not confirm:
                return _dump({"status": "needs_confirmation", "note_id": note,
                              "message": "Call again with confirm=true to permanently delete this note."})
            tracker.sending()
            garmin_client.delete_calendar_note(note)
            tracker.committed()
            return _dump({"status": "success", "note_id": note, "message": f"Calendar note {note} deleted."})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    # ---- courses --------------------------------------------------------

    @app.tool()
    async def create_course_from_activity(activity_id: int, name: Optional[str] = None) -> str:
        """Save a course built from an activity's GPS track

        Args:
            activity_id: Garmin activity id with a GPS track
            name: Course name (default: Garmin's name for the converted track)
        """
        tracker = WriteTracker("create_course_from_activity", "Error creating course")
        try:
            activity = _positive(activity_id, "activity_id")
            course = garmin_client.convert_activity_to_course(activity)
            if not isinstance(course, dict) or not course:
                return f"Activity {activity} has no track to turn into a course."
            if name:
                course["courseName"] = _text(name, "name")
            tracker.sending()
            created = garmin_client.create_course(course)
            tracker.committed()
            course_id = created.get("courseId") if isinstance(created, dict) else None
            return _dump({"status": "success", "course_id": course_id,
                          "course_name": (created or {}).get("courseName") if isinstance(created, dict) else None})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_course(course_id: int, changes: str) -> str:
        """Change fields of an existing course in place (name, description, activity type, ...)

        Reads the full course, merges the changes and writes it back, so the
        track and everything not mentioned stay as they are.

        Examples of changes: {"courseName": "Rondje Amstel"},
        {"description": "Flat 10 km"}

        Args:
            course_id: Garmin course id
            changes: JSON object with the fields to change
        """
        tracker = WriteTracker("update_course", "Error updating course")
        try:
            course = _positive(course_id, "course_id")
            patch = _json_object(changes, "changes")
            if "courseId" in patch:
                return "courseId identifies the course and cannot be changed."
            current = garmin_client.get_course(course)
            if not isinstance(current, dict) or not current:
                return f"No course found with id {course}."
            tracker.sending()
            garmin_client.update_course(course, _deep_merge(current, patch))
            tracker.committed()
            return _dump({"status": "success", "course_id": course, "changed": sorted(patch)})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def get_course_favorites() -> str:
        """List the courses marked as favourite"""
        try:
            return _result(garmin_client.get_course_favorites(), "No favourite courses.")
        except Exception as e:
            return f"Error retrieving favourite courses: {str(e)}"

    @app.tool()
    async def set_course_favorite(course_id: int, favorite: bool = True) -> str:
        """Mark a course as favourite, or remove the mark

        Args:
            course_id: Garmin course id
            favorite: true to mark, false to unmark
        """
        tracker = WriteTracker("set_course_favorite", "Error changing course favourite")
        try:
            course = _positive(course_id, "course_id")
            tracker.sending()
            garmin_client.set_course_favorite(course, bool(favorite))
            tracker.committed()
            return _dump({"status": "success", "course_id": course, "favorite": bool(favorite)})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def get_pace_bands(detail: bool = False) -> str:
        """List your PacePro pace bands (pace plans per split for a course or distance)

        Args:
            detail: true for every split; by default long split lists are
                shortened and empty fields left out
        """
        try:
            return _result(garmin_client.get_pace_bands(), "No PacePro pace bands.", detail)
        except Exception as e:
            return f"Error retrieving pace bands: {str(e)}"

    return app
