"""
Extended health and wellness tools (Slurp garmin-mcp).

Exposes the health methods garminconnect >= 0.3.20 adds. Related read-only
series are bundled into a few tools with a ``metric`` or ``kind`` argument, so
clients get every series without a tool per endpoint. Writes stay separate
tools. Fork-specific module, kept apart from upstream's health_wellness.py.
"""
import datetime
import json
import re
from typing import Any, Callable, Dict, Optional

from garmin_mcp.write_errors import WriteTracker

# The garmin_client will be set by the main file
garmin_client = None

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_RANGE_DAYS = 366


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def _date(value: Optional[str], name: str, default_today: bool = False) -> Optional[str]:
    if value is None or value == "":
        return datetime.date.today().isoformat() if default_today else None
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValueError(f"Invalid {name} {value!r}: expected YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid {name} {value!r}: no such day") from None
    return value


def _range(start: str, end: str) -> tuple:
    start = _date(start, "start_date")
    end = _date(end, "end_date")
    first, last = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
    if first > last:
        raise ValueError("start_date must be on or before end_date")
    if (last - first).days >= _MAX_RANGE_DAYS:
        raise ValueError(f"The range may cover at most {_MAX_RANGE_DAYS} days")
    return start, end


def _positive(value: Any, name: str, maximum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive whole number")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} may be at most {maximum}")
    return value


def _choice(value: str, options: Dict[str, Any], name: str) -> Any:
    key = (value or "").strip().lower()
    if key not in options:
        raise ValueError(f"Unknown {name} {value!r}; choose one of: {', '.join(sorted(options))}")
    return options[key]


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _result(value: Any, empty: str) -> str:
    if value is None or value == [] or value == {}:
        return empty
    return _dump(value)


def _flights(value: Any) -> list:
    """Parse and check Jet Lag Adviser flights (one dict per leg)."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"flights is not valid JSON: {exc.msg}") from None
    if not isinstance(value, list) or not value:
        raise ValueError("flights must be a non-empty JSON list of flight legs")
    required = ("originLocation", "originTimezone", "originTimestamp",
                "destinationLocation", "destinationTimezone", "destinationTimestamp")
    for index, leg in enumerate(value, 1):
        if not isinstance(leg, dict):
            raise ValueError(f"flight {index} must be an object")
        missing = [key for key in required if not leg.get(key)]
        if missing:
            raise ValueError(f"flight {index} is missing: {', '.join(missing)}")
    return value


# metric -> callable(start, end)
_DAILY_SERIES: Dict[str, Callable[[str, str], Any]] = {
    "heart_rate": lambda s, e: garmin_client.get_daily_heart_rate_stats(s, e),
    "resting_heart_rate": lambda s, e: garmin_client.get_rhr_daily(s, e),
    "hrv": lambda s, e: garmin_client.get_hrv_data_range(s, e),
    "stress": lambda s, e: garmin_client.get_daily_stress_stats(s, e),
    "body_battery": lambda s, e: garmin_client.get_daily_body_battery_stats(s, e),
    "intensity_minutes": lambda s, e: garmin_client.get_daily_intensity_minutes_stats(s, e),
    "respiration": lambda s, e: garmin_client.get_daily_respiration_stats(s, e),
    "floors": lambda s, e: garmin_client.get_daily_floors_stats(s, e),
    "hydration": lambda s, e: garmin_client.get_daily_hydration_stats(s, e),
    "calories": lambda s, e: garmin_client.get_calories_daily(s, e),
    "steps": lambda s, e: garmin_client.get_daily_stats(s, e, "STEPS"),
    "pushes": lambda s, e: garmin_client.get_daily_stats(s, e, "PUSHES"),
    "sleep": lambda s, e: garmin_client.get_sleep_daily(s, e),
    "sleep_overall": lambda s, e: garmin_client.get_sleep_stats_overall(s, e),
    "averages": lambda s, e: garmin_client.get_stats_averages(s, e),
    "daily_summaries": lambda s, e: garmin_client.get_daily_summaries(s, e),
    "health_snapshots": lambda s, e: garmin_client.get_health_snapshots_range(s, e),
    "ecg": lambda s, e: garmin_client.get_ecg_daily(s, e),
    "calorie_intake": lambda s, e: garmin_client.get_calorie_summary(s, e),
}

# metric -> callable(end, count)
_TRENDS: Dict[str, Callable[[str, int], Any]] = {
    "heart_rate_weekly": lambda e, n: garmin_client.get_weekly_heart_rate_stats(e, n),
    "floors_weekly": lambda e, n: garmin_client.get_weekly_floors_stats(e, n),
    "hydration_weekly": lambda e, n: garmin_client.get_weekly_hydration_stats(e, n),
    "calories_weekly": lambda e, n: garmin_client.get_weekly_calories_stats(e, n),
    "sleep_weekly": lambda e, n: garmin_client.get_sleep_stats_weekly(e, n),
    "steps_monthly": lambda e, n: garmin_client.get_monthly_steps(e, n),
}

# kind -> callable(date)
_DAY_DETAILS: Dict[str, Callable[[str], Any]] = {
    "intensity_minutes": lambda d: garmin_client.get_intensity_minutes_data(d),
    "hourly_intensity_minutes": lambda d: garmin_client.get_hourly_intensity_minutes(d, 1),
    "movement": lambda d: garmin_client.get_daily_movement(d),
    "hydration": lambda d: garmin_client.get_hydration_all_data(d),
    "sleep": lambda d: garmin_client.get_daily_sleep(d),
    "naps": lambda d: garmin_client.get_naps(d),
    "week_average_resting_heart_rate": lambda d: garmin_client.get_week_average_resting_hr(d),
    "jetlag": lambda d: garmin_client.get_jetlag_status(d),
    "health_snapshots": lambda d: garmin_client.get_health_snapshots(d),
}

_ACCOUNT_STATS: Dict[str, Callable[[], Any]] = {
    "lifetime_totals": lambda: garmin_client.get_lifetime_totals(),
    "activity_statistics": lambda: garmin_client.get_user_statistics(),
    "last_sync": lambda: garmin_client.get_sync_timestamp(),
    "nutrition_status": lambda: garmin_client.get_nutrition_status(),
}


def register_tools(app):
    """Register the extended health tools with the MCP server app"""

    @app.tool()
    async def get_health_stats(metric: str, start_date: str, end_date: str) -> str:
        """Get a daily health series from Garmin Connect for a date range (one value set per day)

        One tool for many series; pick it with metric:
          heart_rate (resting/min/max), resting_heart_rate, hrv, stress,
          body_battery (daily low/high), intensity_minutes, respiration,
          floors, hydration, calories (active + BMR), steps, pushes
          (wheelchair), sleep (daily sleep summaries), sleep_overall
          (averages over the range), averages (steps and resting HR),
          daily_summaries (full daily summaries), health_snapshots, ecg,
          calorie_intake (nutrition totals per meal with goals).

        Args:
            metric: Which series, see the list above
            start_date: First day, YYYY-MM-DD
            end_date: Last day, YYYY-MM-DD (at most 366 days after start_date)
        """
        try:
            fetch = _choice(metric, _DAILY_SERIES, "metric")
            start, end = _range(start_date, end_date)
            return _result(fetch(start, end), f"No {metric} data between {start} and {end}.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving {metric}: {str(e)}"

    @app.tool()
    async def get_health_trend(metric: str, end_date: Optional[str] = None, periods: int = 4) -> str:
        """Get weekly or monthly health totals from Garmin Connect, ending at a date

        metric: heart_rate_weekly (incl. abnormal heart rate alerts),
        floors_weekly, hydration_weekly, calories_weekly, sleep_weekly,
        steps_monthly.

        Args:
            metric: Which trend, see the list above
            end_date: Last day, YYYY-MM-DD (default today)
            periods: Number of weeks or months (default 4, at most 52)
        """
        try:
            fetch = _choice(metric, _TRENDS, "metric")
            end = _date(end_date, "end_date", default_today=True)
            count = _positive(periods, "periods", 52)
            return _result(fetch(end, count), f"No {metric} data up to {end}.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving {metric}: {str(e)}"

    @app.tool()
    async def get_health_day(kind: str, date: Optional[str] = None) -> str:
        """Get one day's health detail from Garmin Connect

        kind: intensity_minutes, hourly_intensity_minutes (this week only),
        movement (per 15-minute block), hydration (intake, goal, sweat loss),
        sleep (newer sleep endpoint), naps, week_average_resting_heart_rate,
        jetlag (Jet Lag Adviser guidance), health_snapshots (sessions that
        day; details with get_health_snapshot).

        Args:
            kind: Which detail, see the list above
            date: Day, YYYY-MM-DD (default today)
        """
        try:
            fetch = _choice(kind, _DAY_DETAILS, "kind")
            day = _date(date, "date", default_today=True)
            return _result(fetch(day), f"No {kind} data for {day}.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving {kind}: {str(e)}"

    @app.tool()
    async def get_account_stats(kind: str = "lifetime_totals") -> str:
        """Get account-wide Garmin Connect totals and status

        kind: lifetime_totals (distance, steps, calories, active days),
        activity_statistics (totals per activity type), last_sync (time of
        the last device sync, UTC), nutrition_status (whether nutrition
        tracking or MyFitnessPal is in use).

        Args:
            kind: Which value, see the list above (default lifetime_totals)
        """
        try:
            fetch = _choice(kind, _ACCOUNT_STATS, "kind")
            return _result(fetch(), f"No {kind} data.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving {kind}: {str(e)}"

    @app.tool()
    async def get_health_snapshot(date: str, snapshot_id: str, include_samples: bool = False) -> str:
        """Get one Health Snapshot session (2-minute HR, HRV, SpO2, respiration, stress check)

        Find the snapshot_id with get_health_day(kind="health_snapshots").

        Args:
            date: Day of the snapshot, YYYY-MM-DD
            snapshot_id: The session's uuid
            include_samples: true to add the per-epoch samples
        """
        try:
            day = _date(date, "date")
            if not isinstance(snapshot_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", snapshot_id):
                return "snapshot_id must be the snapshot's uuid"
            result: Dict[str, Any] = {"summary": garmin_client.get_health_snapshot(day, snapshot_id)}
            if include_samples:
                result["samples"] = garmin_client.get_health_snapshot_epochs(snapshot_id)
            return _dump(result)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving health snapshot: {str(e)}"

    @app.tool()
    async def get_ecg_recordings(start_date: str, end_date: Optional[str] = None,
                                 page_size: int = 20, page: Optional[str] = None) -> str:
        """List ECG app recordings (rhythm classification, heart rate, time)

        Args:
            start_date: First day, YYYY-MM-DD
            end_date: Last day, YYYY-MM-DD (default today)
            page_size: Recordings per page (default 20, at most 100)
            page: Page token from a previous result, for the next page
        """
        try:
            start = _date(start_date, "start_date")
            end = _date(end_date, "end_date", default_today=True)
            _range(start, end)
            size = _positive(page_size, "page_size", 100)
            return _result(garmin_client.get_ecg_list(start, end, page_size=size, page=page),
                           f"No ECG recordings between {start} and {end}.")
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving ECG recordings: {str(e)}"

    @app.tool()
    async def get_ecg(ecg_id: str) -> str:
        """Get one ECG recording, including its waveform

        Args:
            ecg_id: The recording id from get_ecg_recordings
        """
        try:
            if not isinstance(ecg_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", str(ecg_id)):
                return "ecg_id must be the recording id from get_ecg_recordings"
            return _result(garmin_client.get_ecg(ecg_id), f"No ECG recording {ecg_id}.")
        except Exception as e:
            return f"Error retrieving ECG recording: {str(e)}"

    @app.tool()
    async def get_jetlag_trips() -> str:
        """List Jet Lag Adviser trips with their flights"""
        try:
            return _result(garmin_client.get_jetlag_trips(), "No Jet Lag Adviser trips.")
        except Exception as e:
            return f"Error retrieving jet lag trips: {str(e)}"

    _FLIGHTS_HELP = (
        "flights: JSON list, one object per leg, each with originLocation, "
        "originTimezone (UTC offset there on that date, e.g. \"+01:00\"), "
        "originTimestamp (local time, e.g. \"2027-03-04T15:20:00.00\") and the "
        "same three destination* keys. A connection is two legs."
    )

    @app.tool()
    async def create_jetlag_trip(start_date: str, end_date: str, flights: str) -> str:
        """Create a Jet Lag Adviser trip so the watch guides light, sleep and caffeine timing

        flights: JSON list, one object per leg, each with originLocation,
        originTimezone (UTC offset there on that date, e.g. "+01:00"),
        originTimestamp (local time, e.g. "2027-03-04T15:20:00.00") and the
        same three destination* keys. A connection is two legs. Garmin does
        not geocode the location, so the offsets must be right.

        Args:
            start_date: Trip start, YYYY-MM-DD
            end_date: Trip end, YYYY-MM-DD
            flights: JSON list of flight legs (see above)
        """
        tracker = WriteTracker("create_jetlag_trip", "Error creating jet lag trip")
        try:
            start, end = _range(start_date, end_date)
            legs = _flights(flights)
            tracker.sending()
            created = garmin_client.add_jetlag_trip(start, end, legs)
            tracker.committed()
            return _dump({"status": "success", "trip": created})
        except ValueError as e:
            return f"{e}. {_FLIGHTS_HELP}" if "flight" in str(e) else str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def update_jetlag_trip(trip_id: int, start_date: str, end_date: str, flights: str) -> str:
        """Replace a Jet Lag Adviser trip (dates and all flights)

        Args:
            trip_id: The trip id from get_jetlag_trips
            start_date: Trip start, YYYY-MM-DD
            end_date: Trip end, YYYY-MM-DD
            flights: Complete JSON list of flight legs, same format as create_jetlag_trip
        """
        tracker = WriteTracker("update_jetlag_trip", "Error updating jet lag trip")
        try:
            trip = _positive(trip_id, "trip_id")
            start, end = _range(start_date, end_date)
            legs = _flights(flights)
            tracker.sending()
            updated = garmin_client.update_jetlag_trip(trip, start, end, legs)
            tracker.committed()
            return _dump({"status": "success", "trip_id": trip, "trip": updated})
        except ValueError as e:
            return f"{e}. {_FLIGHTS_HELP}" if "flight" in str(e) else str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def delete_jetlag_trip(trip_id: int, confirm: bool = False) -> str:
        """Delete a Jet Lag Adviser trip

        Without confirm=true this only shows the trip. Call again with
        confirm=true to delete it.

        Args:
            trip_id: The trip id from get_jetlag_trips
            confirm: true to actually delete
        """
        tracker = WriteTracker("delete_jetlag_trip", "Error deleting jet lag trip")
        try:
            trip = _positive(trip_id, "trip_id")
            if not confirm:
                trips = garmin_client.get_jetlag_trips() or []
                match = next((t for t in trips if isinstance(t, dict) and str(t.get("id", t.get("tripId"))) == str(trip)), None)
                if match is None:
                    return _dump({"status": "not_found", "trip_id": trip})
                return _dump({"status": "needs_confirmation", "trip_id": trip, "trip": match,
                              "message": "Review this trip, then call again with confirm=true to delete it."})
            tracker.sending()
            garmin_client.delete_jetlag_trip(trip)
            tracker.committed()
            return _dump({"status": "success", "trip_id": trip, "message": f"Jet lag trip {trip} deleted."})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def set_steps_goal(steps: int = 0, date: Optional[str] = None) -> str:
        """Set a manual daily step goal, or go back to the watch's automatic goal

        Args:
            steps: Daily step goal; 0 restores the automatic goal
            date: Day from which the goal applies, YYYY-MM-DD (default today)
        """
        tracker = WriteTracker("set_steps_goal", "Error setting step goal")
        try:
            if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0 or steps > 200000:
                return "steps must be a whole number between 0 and 200000 (0 = automatic goal)"
            day = _date(date, "date", default_today=True)
            tracker.sending()
            result = garmin_client.set_steps_goal(steps or None, day)
            tracker.committed()
            return _dump({"status": "success", "date": day,
                          "goal": steps or "automatic", "result": result})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    return app
