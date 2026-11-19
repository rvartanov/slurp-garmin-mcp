"""
Extended performance-metric tools (Slurp garmin-mcp).

Exposes the metrics methods garminconnect >= 0.3.20 adds: VO2 max, heat and
altitude acclimation, Cycling Ability, Running Economy, Critical Swim Speed,
stamina, Fitness Age, biometrics, glucose, one-rep max, training status and
readiness history, power curves and zones. Read-only values are bundled into
two tools with a ``metric`` argument; writes stay separate. Fork-specific
module.
"""
import datetime
import json
import math
from typing import Any, Callable, Dict, Optional

from garmin_mcp.health_extra import _choice, _compact, _date, _positive, _range
from garmin_mcp.write_errors import WriteTracker

# The garmin_client will be set by the main file
garmin_client = None


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


# metric -> callable(date)
_LATEST: Dict[str, Callable[[str], Any]] = {
    "vo2max": lambda d: garmin_client.get_max_metrics_latest(d),
    "training_status": lambda d: garmin_client.get_daily_training_status(d),
    "load_balance": lambda d: garmin_client.get_training_four_week_load_balance(d),
    "heat_altitude_acclimation": lambda d: garmin_client.get_heat_altitude_acclimation(d),
    "spo2_acclimation": lambda d: garmin_client.get_spo2_acclimation_data(d),
    "cycling_ability": lambda d: garmin_client.get_cycling_ability(d),
    "running_economy": lambda d: garmin_client.get_running_economy(d),
    "critical_swim_speed": lambda d: garmin_client.get_critical_swim_speed(d),
    "stamina_running": lambda d: garmin_client.get_stamina_curve(d, "running"),
    "stamina_cycling": lambda d: garmin_client.get_stamina_curve(d, "cycling"),
    "fitness_age": lambda d: garmin_client.get_fitness_age_details(d),
    "one_rep_max": lambda d: garmin_client.get_one_rep_max(d),
    "glucose": lambda d: garmin_client.get_glucose_data(d),
    "biometrics": lambda d: garmin_client.get_current_biometrics(),
}

# metric -> callable(start, end, aggregation)
_HISTORY: Dict[str, Callable[[str, str, str], Any]] = {
    "vo2max": lambda s, e, a: garmin_client.get_max_metrics_range(s, e, a),
    "ftp": lambda s, e, a: garmin_client.get_functional_threshold_power_range(s, e),
    "training_readiness": lambda s, e, a: garmin_client.get_training_readiness_range(s, e),
    "training_status_weekly": lambda s, e, a: garmin_client.get_weekly_training_status(s, e),
    "heat_altitude_acclimation": lambda s, e, a: garmin_client.get_heat_altitude_acclimation_range(s, e, a),
    "spo2_acclimation": lambda s, e, a: garmin_client.get_acclimation_stats(s, e),
    "cycling_ability": lambda s, e, a: garmin_client.get_cycling_ability_range(s, e, a.upper()),
    "running_economy": lambda s, e, a: garmin_client.get_running_economy_range(s, e, a),
    "critical_swim_speed": lambda s, e, a: garmin_client.get_critical_swim_speed_range(s, e, a),
    "biometrics": lambda s, e, a: garmin_client.get_biometric_stats(s, e, a),
    "fitness_age": lambda s, e, a: garmin_client.get_fitness_age_daily(s, e),
    "fitness_age_weekly": lambda s, e, a: garmin_client.get_fitness_age_weekly(
        e, max(1, math.ceil(((datetime.date.fromisoformat(e) - datetime.date.fromisoformat(s)).days + 1) / 7))),
    "glucose": lambda s, e, a: garmin_client.get_glucose_data_range(s, e),
    "power_curve_cycling": lambda s, e, a: garmin_client.get_power_curve(s, e, "cycling"),
    # Garmin's range power curve supports cycling and rowing only (400 otherwise);
    # a running activity's curve is available through get_activity_power_curve.
    "power_curve_rowing": lambda s, e, a: garmin_client.get_power_curve(s, e, "rowing"),
}


def register_tools(app):
    """Register the extended performance-metric tools with the MCP server app"""

    @app.tool()
    async def get_performance_metric(metric: str, date: Optional[str] = None, detail: bool = False) -> str:
        """Get the latest value of a Garmin performance metric as of a day

        metric: vo2max, training_status (that day), load_balance (4-week
        load focus), heat_altitude_acclimation, spo2_acclimation,
        cycling_ability, running_economy, critical_swim_speed,
        stamina_running, stamina_cycling, fitness_age (with components and
        targets), one_rep_max (strength estimates), glucose (logged readings
        that day), biometrics (current height, weight, VO2 max, lactate
        threshold, FTP; ignores date).

        Args:
            metric: Which metric, see the list above
            date: Day, YYYY-MM-DD (default today)
            detail: true for every sample; by default long series are shortened
        """
        try:
            fetch = _choice(metric, _LATEST, "metric")
            day = _date(date, "date", default_today=True)
            return _result(fetch(day), f"No {metric} data as of {day}.", detail)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving {metric}: {str(e)}"

    @app.tool()
    async def get_performance_history(metric: str, start_date: str, end_date: str,
                                      aggregation: str = "daily", detail: bool = False) -> str:
        """Get the history of a Garmin performance metric over a date range

        metric: vo2max, ftp, training_readiness, training_status_weekly,
        heat_altitude_acclimation, spo2_acclimation, cycling_ability,
        running_economy, critical_swim_speed, biometrics (weight, body fat,
        lactate threshold per period), fitness_age, fitness_age_weekly,
        glucose, power_curve_cycling, power_curve_rowing (best power per
        duration over the range; Garmin has no range curve for running, use
        get_activity_power_curve for one run).

        Args:
            metric: Which metric, see the list above
            start_date: First day, YYYY-MM-DD
            end_date: Last day, YYYY-MM-DD (at most 366 days after start_date)
            aggregation: daily, weekly or monthly where the metric supports it
                (vo2max, heat_altitude_acclimation, cycling_ability,
                running_economy, critical_swim_speed, biometrics)
            detail: true for every sample; by default long series are shortened
        """
        try:
            fetch = _choice(metric, _HISTORY, "metric")
            start, end = _range(start_date, end_date)
            agg = (aggregation or "daily").strip().lower()
            return _result(fetch(start, end, agg), f"No {metric} data between {start} and {end}.", detail)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving {metric}: {str(e)}"

    @app.tool()
    async def get_training_zones(kind: str = "power", sport: Optional[str] = None) -> str:
        """Get configured training zones per sport

        kind: power (power zones with FTP per sport) or heart_rate (heart
        rate zones per sport from the endpoint the web app uses). For heart
        rate zones of one sport profile, get_heart_rate_zones also works.

        Args:
            kind: power or heart_rate (default power)
            sport: Only this Garmin sport key, e.g. cycling or running (power only)
        """
        try:
            key = (kind or "").strip().lower()
            if key == "power":
                zones = garmin_client.get_power_zones_for_sport(sport) if sport else garmin_client.get_power_zones()
            elif key == "heart_rate":
                if sport:
                    return "sport is only supported for kind=power; use get_heart_rate_zones for one sport profile."
                zones = garmin_client.get_heart_rate_zones_v2()
            else:
                return "kind must be power or heart_rate"
            return _result(zones, f"No {key} zones configured.", True)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving training zones: {str(e)}"

    @app.tool()
    async def set_power_zones(zones: str) -> str:
        """Write power zones (and FTP) for one or more sports

        Pass the complete per-sport objects as returned by
        get_training_zones(kind="power"), changed where needed: sport,
        functionalThresholdPower, zone1Floor ... zone7Floor. Sports not in
        the list keep their zones.

        Args:
            zones: JSON list of per-sport power zone objects
        """
        tracker = WriteTracker("set_power_zones", "Error writing power zones")
        try:
            value = json.loads(zones) if isinstance(zones, str) else zones
            if isinstance(value, dict):
                value = [value]
            if not isinstance(value, list) or not value or not all(isinstance(z, dict) and z.get("sport") for z in value):
                return "zones must be a JSON list of power zone objects, each with a sport (from get_training_zones)."
            tracker.sending()
            result = garmin_client.update_power_zones(value)
            tracker.committed()
            return _dump({"status": "success", "sports": [z["sport"] for z in value], "result": result})
        except json.JSONDecodeError as e:
            return f"zones is not valid JSON: {e.msg}"
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def get_one_rep_max_history(exercise_type: str, start_date: str, end_date: str,
                                      aggregation: str = "daily") -> str:
        """Get the estimated one-rep-max history of a strength exercise

        Args:
            exercise_type: Garmin exercise key, e.g. BENCH_PRESS, SQUAT, DEADLIFT
                (one_rep_max in get_performance_metric lists the ones with data)
            start_date: First day, YYYY-MM-DD
            end_date: Last day, YYYY-MM-DD
            aggregation: daily or monthly (default daily)
        """
        try:
            if not isinstance(exercise_type, str) or not exercise_type.strip().replace("_", "").isalnum():
                return "exercise_type must be a Garmin exercise key such as BENCH_PRESS"
            start, end = _range(start_date, end_date)
            return _result(garmin_client.get_one_rep_max_history(exercise_type, start, end, (aggregation or "daily").lower()),
                           f"No one-rep-max history for {exercise_type}.", True)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving one-rep-max history: {str(e)}"

    @app.tool()
    async def get_activity_power_curve(activity_id: int) -> str:
        """Get the power curve (best power per duration) of one activity

        Args:
            activity_id: Garmin activity id
        """
        try:
            activity = _positive(activity_id, "activity_id")
            return _result(garmin_client.get_activity_power_curve(activity),
                           f"Activity {activity} has no power data.", True)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error retrieving activity power curve: {str(e)}"

    return app
