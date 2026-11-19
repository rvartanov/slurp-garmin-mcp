"""
Achievements, goals, devices, profile, women's health and golf (Slurp garmin-mcp).

Exposes the remaining garminconnect >= 0.3.20 methods without a tool:
badges, challenges and personal-record metadata; wellness goals; devices,
sensors and device messages; profile, privacy and usage information;
menstrual cycle summaries, reports and logging; golf scorecards and stats.
Read-only data is bundled per domain with a ``kind`` argument; every write
is its own tool. Fork-specific module.
"""
import json
import re
from typing import Any, Callable, Dict, List, Optional

from garmin_mcp.health_extra import _choice, _compact, _date, _positive, _range
from garmin_mcp.race_events import _json_object
from garmin_mcp.write_errors import WriteTracker

# The garmin_client will be set by the main file
garmin_client = None

_UUID_RE = re.compile(r"^[0-9a-fA-F-]{16,40}$")
_GOAL_TYPES = ("INTENSITY_MINUTES", "FLOORS_CLIMBED", "HYDRATION", "WEIGHT_GRAMS")


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


# Fields kept per device in device lists unless detail=true; a device
# record has ~320 fields (feature flags, image urls, ...).
_DEVICE_FIELDS = (
    "deviceId", "unitId", "displayName", "productDisplayName", "deviceTypePk",
    "partNumber", "currentFirmwareVersion", "deviceStatus", "primaryActivityTrackerIndicator",
    "primaryTrainingDevice", "registeredDate", "lastUsed", "actualProductSku",
)


def _device_summaries(value: Any) -> Any:
    if isinstance(value, list):
        return [{k: d[k] for k in _DEVICE_FIELDS if k in d} if isinstance(d, dict) else d for d in value]
    return value


def _need(value: Any, name: str) -> Any:
    if value is None or value == "":
        raise ValueError(f"{name} is required for this kind")
    return value


def _string_list(value: Any, name: str) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of text values")
    return value


def register_tools(app):
    """Register the achievement, goal, device, profile, women's health and golf tools"""

    # ---- achievements ---------------------------------------------------

    @app.tool()
    async def get_achievements(kind: str, activity_id: Optional[int] = None, badge_id: Optional[int] = None,
                               challenge_id: Optional[str] = None, date: Optional[str] = None,
                               limit: int = 20) -> str:
        """Get badges, challenges and personal-record information from Garmin Connect

        kind:
          available_badges, in_progress_badges, latest_badges (limit),
          badges_for_day (date), badges_for_activity (activity_id),
          badge_detail (badge_id), badge_attributes (types, categories, difficulties),
          badge_challenge (challenge_id = the challenge uuid),
          virtual_challenges_available, virtual_challenges_completed,
          adhoc_challenges (running friend challenges),
          record_candidates (personal records awaiting confirmation),
          record_types (personal-record definitions),
          records_for_activity (activity_id)

        Args:
            kind: Which data, see the list above
            activity_id: Activity id for the *_for_activity kinds
            badge_id: Badge id for badge_detail
            challenge_id: Challenge uuid for badge_challenge
            date: Day for badges_for_day, YYYY-MM-DD (default today)
            limit: Number of results where a list is paged (default 20)
        """
        try:
            count = _positive(limit, "limit", 1000)
            options: Dict[str, Callable[[], Any]] = {
                "available_badges": lambda: garmin_client.get_available_badges(),
                "in_progress_badges": lambda: garmin_client.get_in_progress_badges(),
                "latest_badges": lambda: garmin_client.get_latest_earned_badges(count),
                "badges_for_day": lambda: garmin_client.get_badges_for_day(_date(date, "date", default_today=True)),
                "badges_for_activity": lambda: garmin_client.get_badges_for_activity(
                    _positive(_need(activity_id, "activity_id"), "activity_id")),
                "badge_detail": lambda: garmin_client.get_badge_detail(_positive(_need(badge_id, "badge_id"), "badge_id")),
                "badge_attributes": lambda: garmin_client.get_badge_attributes(),
                "badge_challenge": lambda: garmin_client.get_badge_challenge(_challenge(challenge_id)),
                "virtual_challenges_available": lambda: garmin_client.get_available_virtual_challenges(1, count),
                "virtual_challenges_completed": lambda: garmin_client.get_completed_virtual_challenges(1, count),
                "adhoc_challenges": lambda: garmin_client.get_active_adhoc_challenges(),
                "record_candidates": lambda: garmin_client.get_personal_record_candidates(),
                "record_types": lambda: garmin_client.get_personal_record_types(),
                "records_for_activity": lambda: garmin_client.get_personal_records_for_activity(
                    _positive(_need(activity_id, "activity_id"), "activity_id")),
            }
            fetch = _choice(kind, options, "kind")
            return _result(fetch(), f"No {kind} data.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving {kind}: {str(e)}"

    def _challenge(value: Any) -> str:
        if not isinstance(value, str) or not _UUID_RE.match(value):
            raise ValueError("challenge_id must be the challenge uuid")
        return value

    # ---- goals ----------------------------------------------------------

    @app.tool()
    async def get_wellness_goals(kind: str = "effective", date: Optional[str] = None,
                                 start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """Get wellness goals from Garmin Connect

        kind: effective (daily goals in effect on date: intensity minutes,
        floors, hydration, ...), steps (the effective step goal on date and
        whether it is the device's or yours), all (your wellness goals),
        weight (weight goal(s) between start_date and end_date).

        Args:
            kind: effective, steps, all or weight (default effective)
            date: Day for effective/steps, YYYY-MM-DD (default today)
            start_date: First day for weight, YYYY-MM-DD
            end_date: Last day for weight, YYYY-MM-DD
        """
        try:
            key = (kind or "").strip().lower()
            if key == "effective":
                data = garmin_client.get_effective_goals(_date(date, "date", default_today=True))
            elif key == "steps":
                data = garmin_client.get_steps_goal(_date(date, "date", default_today=True))
            elif key == "all":
                data = garmin_client.get_user_goals()
            elif key == "weight":
                data = garmin_client.get_weight_goal(*_range(start_date, end_date))
            else:
                return "kind must be effective, steps, all or weight"
            return _result(data, f"No {key} goals.", True)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving goals: {str(e)}"

    @app.tool()
    async def set_daily_goal(goal_type: str, value: float, date: Optional[str] = None) -> str:
        """Set a daily wellness goal (for the step goal use set_steps_goal)

        Args:
            goal_type: INTENSITY_MINUTES (weekly minutes), FLOORS_CLIMBED,
                HYDRATION (ml) or WEIGHT_GRAMS
            value: The goal value in the goal's unit
            date: Day from which it applies, YYYY-MM-DD (default today)
        """
        tracker = WriteTracker("set_daily_goal", "Error setting goal")
        try:
            key = (goal_type or "").strip().upper()
            if key not in _GOAL_TYPES:
                return f"goal_type must be one of: {', '.join(_GOAL_TYPES)}"
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                return "value must be a positive number"
            day = _date(date, "date", default_today=True)
            tracker.sending()
            result = garmin_client.set_daily_goal(key, value, day)
            tracker.committed()
            return _dump({"status": "success", "goal_type": key, "value": value, "date": day, "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    # ---- devices --------------------------------------------------------

    @app.tool()
    async def get_device_data(kind: str = "active", device_id: Optional[int] = None,
                              start_date: Optional[str] = None, end_date: Optional[str] = None,
                              detail: bool = False) -> str:
        """Get device, sensor and device-message information from Garmin Connect

        kind: active, all (including inactive), historical, registration
        (device_id: last upload/download times), app_info (device_id:
        device type and software), displayed_activities (device_id:
        activity profiles shown on the device), solar_gain (device_id,
        start_date, end_date), sensors (paired HRMs, power meters, ...),
        messages (pending software updates and pushed items).

        Args:
            kind: Which data, see the list above (default active)
            device_id: Device id for the per-device kinds (from kind=active)
            start_date: First day for solar_gain, YYYY-MM-DD
            end_date: Last day for solar_gain, YYYY-MM-DD
            detail: true for Garmin's full records (~320 fields per device);
                by default device lists keep their key fields and empty
                fields are left out
        """
        try:
            key = (kind or "").strip().lower()
            per_device = {
                "registration": lambda d: garmin_client.get_user_device(d),
                "app_info": lambda d: garmin_client.get_device_app_info(d),
                "displayed_activities": lambda d: garmin_client.get_device_displayed_activities(d),
                "solar_gain": lambda d: garmin_client.get_device_solar_gain(d, *_range(start_date, end_date)),
            }
            general = {
                "active": lambda: garmin_client.get_active_devices(),
                "all": lambda: garmin_client.get_all_devices(),
                "historical": lambda: garmin_client.get_historical_devices(),
                "sensors": lambda: garmin_client.get_sensors(),
                "messages": lambda: garmin_client.get_device_messages(),
            }
            if key in per_device:
                data = per_device[key](_positive(_need(device_id, "device_id"), "device_id"))
            else:
                data = _choice(key, general, "kind")()
                if not detail and key in ("active", "all", "historical"):
                    data = _device_summaries(data)
            return _result(data, f"No {key} device data.", detail)
        except ValueError as e:
            if "Unknown kind" in str(e):
                return ("Unknown kind; choose one of: active, all, historical, registration, app_info, "
                        "displayed_activities, solar_gain, sensors, messages")
            return str(e)
        except Exception as e:
            return f"Error retrieving device data: {str(e)}"

    @app.tool()
    async def update_device_settings(device_id: int, settings: str) -> str:
        """Change device settings (alarms, activity tracking, ...); only the given keys change

        Start from get_device_settings and send only what you change, e.g.
        {"activityTracking": {"moveAlertEnabled": true}}. Takes effect at the
        next device sync.

        Args:
            device_id: Device id
            settings: JSON object with the settings to change
        """
        tracker = WriteTracker("update_device_settings", "Error updating device settings")
        try:
            device = _positive(device_id, "device_id")
            patch = _json_object(settings, "settings")
            tracker.sending()
            result = garmin_client.update_device_settings(device, patch)
            tracker.committed()
            return _dump({"status": "success", "device_id": device, "changed": sorted(patch), "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def send_scheduled_workouts_to_devices() -> str:
        """Send all scheduled workouts to your devices (they arrive at the next sync)"""
        tracker = WriteTracker("send_scheduled_workouts_to_devices", "Error sending scheduled workouts")
        try:
            tracker.sending()
            result = garmin_client.send_scheduled_workouts_to_devices()
            tracker.committed()
            return _dump({"status": "success", "result": result})
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def set_primary_training_device(device_id: int) -> str:
        """Choose which device Garmin uses as the primary training device for training metrics

        Args:
            device_id: Device id (from get_device_data kind=active)
        """
        tracker = WriteTracker("set_primary_training_device", "Error setting primary training device")
        try:
            device = _positive(device_id, "device_id")
            tracker.sending()
            result = garmin_client.set_primary_training_device(device)
            tracker.committed()
            return _dump({"status": "success", "device_id": device, "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    # ---- profile --------------------------------------------------------

    @app.tool()
    async def get_profile_data(kind: str = "personal_information", detail: bool = False) -> str:
        """Get profile information from Garmin Connect

        kind: personal_information (birth date, gender, locale, biometrics,
        VO2 max), profile (base profile record), timezone (IANA name from
        the profile), privacy (activity, profile and wellness privacy),
        usage_indicators (features your devices and data support).

        Args:
            kind: Which data, see the list above (default personal_information)
            detail: true for the full response; by default empty and false
                fields are left out
        """
        try:
            options = {
                "personal_information": lambda: garmin_client.get_personal_information(),
                "profile": lambda: garmin_client.get_user_profile_base(),
                "timezone": lambda: garmin_client.get_user_timezone(),
                "privacy": lambda: garmin_client.get_privacy_settings(),
                "usage_indicators": lambda: garmin_client.get_usage_indicators(),
            }
            return _result(_choice(kind, options, "kind")(), f"No {kind} data.", detail)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving profile data: {str(e)}"

    @app.tool()
    async def update_user_settings(settings: str) -> str:
        """Change Garmin Connect user settings (units, formats, sleep times, training days, ...)

        Only the given keys change; userData merges one level deep, e.g.
        {"userData": {"measurementSystem": "metric"}}. See get_user_profile
        for the current settings and their names.

        Args:
            settings: JSON object with the settings to change
        """
        tracker = WriteTracker("update_user_settings", "Error updating user settings")
        try:
            patch = _json_object(settings, "settings")
            tracker.sending()
            result = garmin_client.update_user_settings(patch)
            tracker.committed()
            return _dump({"status": "success", "changed": sorted(patch), "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    # ---- women's health -------------------------------------------------

    @app.tool()
    async def get_menstrual_overview(kind: str = "summary", date: Optional[str] = None,
                                     number_of_cycles: int = 6) -> str:
        """Get menstrual cycle information from Garmin Connect

        kind: summary (cycle summary as of date), last_confirmed (the last
        confirmed cycle as of date), reports (reports for the last 1, 6 or
        12 cycles ending at date). Day-level data: get_menstrual_data_for_date.

        Args:
            kind: summary, last_confirmed or reports (default summary)
            date: Day, YYYY-MM-DD (default today)
            number_of_cycles: 1, 6 or 12 for reports (default 6)
        """
        try:
            day = _date(date, "date", default_today=True)
            key = (kind or "").strip().lower()
            if key == "summary":
                data = garmin_client.get_menstrual_cycle_summary(day)
            elif key == "last_confirmed":
                data = garmin_client.get_menstrual_last_confirmed(day)
            elif key == "reports":
                if number_of_cycles not in (1, 6, 12):
                    return "number_of_cycles must be 1, 6 or 12"
                data = garmin_client.get_menstrual_reports(day, number_of_cycles)
            else:
                return "kind must be summary, last_confirmed or reports"
            return _result(data, f"No menstrual {key} data.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving menstrual data: {str(e)}"

    @app.tool()
    async def log_menstrual_day(date: str, flow: Optional[str] = None, symptoms: Optional[str] = None,
                                moods: Optional[str] = None, discharge: Optional[str] = None,
                                sex_drive: Optional[str] = None, sexual_activity: Optional[str] = None,
                                notes: Optional[str] = None, ovulation_day: bool = False) -> str:
        """Write the menstrual log for one day (replaces that day's log)

        This replaces the whole day: omitted lists and values are cleared,
        except notes (left out keeps the note, "" clears it). Read the day
        with get_menstrual_data_for_date first and pass every value to keep.
        Values use Garmin's keys as get_menstrual_data_for_date shows them.

        Args:
            date: Day, YYYY-MM-DD
            flow: Flow key
            symptoms: Comma-separated symptom keys
            moods: Comma-separated mood keys
            discharge: Comma-separated discharge keys
            sex_drive: Sex drive key
            sexual_activity: Sexual activity key
            notes: Note for the day
            ovulation_day: true to mark the day as ovulation day
        """
        tracker = WriteTracker("log_menstrual_day", "Error writing menstrual log")
        try:
            day = _date(date, "date")
            kwargs = {
                "symptoms": _string_list(symptoms, "symptoms"),
                "moods": _string_list(moods, "moods"),
                "discharge": _string_list(discharge, "discharge"),
                "flow": flow, "sex_drive": sex_drive, "sexual_activity": sexual_activity,
                "notes": notes, "ovulation_day": bool(ovulation_day),
            }
            tracker.sending()
            result = garmin_client.update_menstrual_daily_log(day, **kwargs)
            tracker.committed()
            return _dump({"status": "success", "date": day, "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def set_menstrual_periods(start_date: str, end_date: str, periods: str) -> str:
        """Replace the confirmed period days between two dates on the cycle calendar

        Not a merge: confirmed days in the range that are not listed are
        removed. Do not post predicted cycles as confirmed.

        Args:
            start_date: First day of the range, YYYY-MM-DD
            end_date: Last day of the range, YYYY-MM-DD
            periods: JSON list of periods, each a list of consecutive YYYY-MM-DD days,
                e.g. [["2026-11-01","2026-11-02","2026-11-03"]]
        """
        tracker = WriteTracker("set_menstrual_periods", "Error writing menstrual periods")
        try:
            first, last = _range(start_date, end_date)
            value = json.loads(periods) if isinstance(periods, str) else periods
            if not isinstance(value, list) or not all(isinstance(p, list) for p in value):
                return "periods must be a JSON list of lists of YYYY-MM-DD days"
            for period in value:
                for day in period:
                    _date(day, "period day")
            tracker.sending()
            result = garmin_client.update_menstrual_calendar(first, last, value)
            tracker.committed()
            return _dump({"status": "success", "range": [first, last], "periods": len(value), "result": result})
        except json.JSONDecodeError as e:
            return f"periods is not valid JSON: {e.msg}"
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def confirm_menstrual_period(period_start_date: str, period_length: int, cycle_length: int,
                                       first_setup: bool = False, predicted_cycle: bool = False) -> str:
        """Confirm a period start (or set up cycle tracking with the first confirmed period)

        Args:
            period_start_date: First day of the period, YYYY-MM-DD
            period_length: Period length in days
            cycle_length: Cycle length in days
            first_setup: true to initialise cycle tracking with this period
            predicted_cycle: true when confirming a predicted period
        """
        tracker = WriteTracker("confirm_menstrual_period", "Error confirming period")
        try:
            day = _date(period_start_date, "period_start_date")
            period = _positive(period_length, "period_length", 15)
            cycle = _positive(cycle_length, "cycle_length", 100)
            tracker.sending()
            if first_setup:
                result = garmin_client.init_menstrual_cycle_setup(day, period, cycle)
            else:
                result = garmin_client.confirm_menstrual_period_start(day, period, cycle,
                                                                       predicted_cycle=bool(predicted_cycle))
            tracker.committed()
            return _dump({"status": "success", "period_start_date": day, "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_menstrual_settings(settings: str) -> str:
        """Change menstrual cycle tracking settings (userMenstrualCycleSettings)

        Args:
            settings: JSON object with the settings to change
        """
        tracker = WriteTracker("update_menstrual_settings", "Error updating menstrual settings")
        try:
            patch = _json_object(settings, "settings")
            tracker.sending()
            result = garmin_client.update_menstrual_settings(patch)
            tracker.committed()
            return _dump({"status": "success", "changed": sorted(patch), "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    # ---- golf -----------------------------------------------------------

    @app.tool()
    async def get_golf_data(kind: str = "summary", scorecard_id: Optional[int] = None,
                            holes: Optional[str] = None, limit: int = 100) -> str:
        """Get golf data from Garmin Connect

        kind: summary (your scorecards), scorecard (scorecard_id), shots
        (scorecard_id, optional holes such as "1,2,3"), clubs (club
        statistics), stats (overall golf statistics).

        Args:
            kind: Which data, see the list above (default summary)
            scorecard_id: Scorecard id for scorecard/shots
            holes: Comma-separated hole numbers for shots
            limit: Number of results for summary/clubs (default 100)
        """
        try:
            key = (kind or "").strip().lower()
            count = _positive(limit, "limit", 1000)
            if key == "summary":
                data = garmin_client.get_golf_summary(0, count)
            elif key == "scorecard":
                data = garmin_client.get_golf_scorecard(_positive(_need(scorecard_id, "scorecard_id"), "scorecard_id"))
            elif key == "shots":
                if holes and not re.fullmatch(r"\d+(,\d+)*", holes.replace(" ", "")):
                    return "holes must be comma-separated hole numbers, e.g. 1,2,3"
                data = garmin_client.get_golf_shot_data(_positive(_need(scorecard_id, "scorecard_id"), "scorecard_id"),
                                                        holes.replace(" ", "") if holes else None)
            elif key == "clubs":
                data = garmin_client.get_golf_club_stats(count)
            elif key == "stats":
                data = garmin_client.get_golf_user_stats()
            else:
                return "kind must be summary, scorecard, shots, clubs or stats"
            return _result(data, f"No golf {key} data.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving golf data: {str(e)}"

    return app
