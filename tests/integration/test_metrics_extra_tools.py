"""
Integration tests for the metrics_extra module MCP tools (mocked Garmin client).
"""
import datetime
import json

import pytest
from garminconnect import GarminConnectConnectionError
from mcp.server.fastmcp import FastMCP

from garmin_mcp import metrics_extra

DAY, START, END = "2026-11-10", "2026-10-01", "2026-10-28"
TODAY = datetime.date.today().isoformat()


@pytest.fixture
def app(mock_garmin_client):
    metrics_extra.configure(mock_garmin_client)
    return metrics_extra.register_tools(FastMCP("Test Metrics Extra"))


async def _call(app, name, args=None):
    result = await app.call_tool(name, args or {})
    return result[0][0].text


@pytest.mark.parametrize("metric, method, args", [
    ("vo2max", "get_max_metrics_latest", (DAY,)),
    ("training_status", "get_daily_training_status", (DAY,)),
    ("load_balance", "get_training_four_week_load_balance", (DAY,)),
    ("heat_altitude_acclimation", "get_heat_altitude_acclimation", (DAY,)),
    ("spo2_acclimation", "get_spo2_acclimation_data", (DAY,)),
    ("cycling_ability", "get_cycling_ability", (DAY,)),
    ("running_economy", "get_running_economy", (DAY,)),
    ("critical_swim_speed", "get_critical_swim_speed", (DAY,)),
    ("stamina_running", "get_stamina_curve", (DAY, "running")),
    ("stamina_cycling", "get_stamina_curve", (DAY, "cycling")),
    ("fitness_age", "get_fitness_age_details", (DAY,)),
    ("one_rep_max", "get_one_rep_max", (DAY,)),
    ("glucose", "get_glucose_data", (DAY,)),
    ("biometrics", "get_current_biometrics", ()),
])
async def test_get_performance_metric_dispatch(app, mock_garmin_client, metric, method, args):
    getattr(mock_garmin_client, method).return_value = {"value": 1}
    assert json.loads(await _call(app, "get_performance_metric", {"metric": metric, "date": DAY})) == {"value": 1}
    getattr(mock_garmin_client, method).assert_called_once_with(*args)


async def test_get_performance_metric_default_date_and_unknown(app, mock_garmin_client):
    mock_garmin_client.get_max_metrics_latest.return_value = None
    assert f"No vo2max data as of {TODAY}" in await _call(app, "get_performance_metric", {"metric": "vo2max"})
    assert "Unknown metric" in await _call(app, "get_performance_metric", {"metric": "iq"})


@pytest.mark.parametrize("metric, method, args", [
    ("vo2max", "get_max_metrics_range", (START, END, "weekly")),
    ("ftp", "get_functional_threshold_power_range", (START, END)),
    ("training_readiness", "get_training_readiness_range", (START, END)),
    ("training_status_weekly", "get_weekly_training_status", (START, END)),
    ("heat_altitude_acclimation", "get_heat_altitude_acclimation_range", (START, END, "weekly")),
    ("spo2_acclimation", "get_acclimation_stats", (START, END)),
    ("cycling_ability", "get_cycling_ability_range", (START, END, "WEEKLY")),
    ("running_economy", "get_running_economy_range", (START, END, "weekly")),
    ("critical_swim_speed", "get_critical_swim_speed_range", (START, END, "weekly")),
    ("biometrics", "get_biometric_stats", (START, END, "weekly")),
    ("fitness_age", "get_fitness_age_daily", (START, END)),
    ("fitness_age_weekly", "get_fitness_age_weekly", (END, 4)),
    ("glucose", "get_glucose_data_range", (START, END)),
    ("power_curve_cycling", "get_power_curve", (START, END, "cycling")),
    ("power_curve_rowing", "get_power_curve", (START, END, "rowing")),
])
async def test_get_performance_history_dispatch(app, mock_garmin_client, metric, method, args):
    getattr(mock_garmin_client, method).return_value = [{"v": 1}]
    await _call(app, "get_performance_history", {"metric": metric, "start_date": START, "end_date": END, "aggregation": "Weekly"})
    getattr(mock_garmin_client, method).assert_called_once_with(*args)


async def test_get_performance_history_passes_library_validation_errors(app, mock_garmin_client):
    mock_garmin_client.get_max_metrics_range.side_effect = ValueError("aggregation must be 'daily', 'weekly' or 'monthly'")
    text = await _call(app, "get_performance_history", {"metric": "vo2max", "start_date": START, "end_date": END, "aggregation": "hourly"})
    assert text == "aggregation must be 'daily', 'weekly' or 'monthly'"


async def test_get_performance_history_error(app, mock_garmin_client):
    mock_garmin_client.get_glucose_data_range.side_effect = Exception("boom")
    assert "Error retrieving glucose" in await _call(app, "get_performance_history", {"metric": "glucose", "start_date": START, "end_date": END})


async def test_get_training_zones(app, mock_garmin_client):
    mock_garmin_client.get_power_zones.return_value = [{"sport": "CYCLING"}]
    mock_garmin_client.get_power_zones_for_sport.return_value = {"sport": "RUNNING"}
    mock_garmin_client.get_heart_rate_zones_v2.return_value = [{"sport": "DEFAULT"}]
    assert json.loads(await _call(app, "get_training_zones")) == [{"sport": "CYCLING"}]
    assert json.loads(await _call(app, "get_training_zones", {"kind": "power", "sport": "running"}))["sport"] == "RUNNING"
    mock_garmin_client.get_power_zones_for_sport.assert_called_once_with("running")
    assert json.loads(await _call(app, "get_training_zones", {"kind": "heart_rate"})) == [{"sport": "DEFAULT"}]
    assert "kind must be" in await _call(app, "get_training_zones", {"kind": "pace"})


async def test_set_power_zones(app, mock_garmin_client):
    zones = [{"sport": "CYCLING", "functionalThresholdPower": 250, "zone1Floor": 0}]
    result = json.loads(await _call(app, "set_power_zones", {"zones": json.dumps(zones)}))
    assert result["status"] == "success" and result["sports"] == ["CYCLING"]
    mock_garmin_client.update_power_zones.assert_called_once_with(zones)


async def test_set_power_zones_rejects_bad_input(app, mock_garmin_client):
    assert "not valid JSON" in await _call(app, "set_power_zones", {"zones": "{x"})
    assert "each with a sport" in await _call(app, "set_power_zones", {"zones": '[{"ftp": 1}]'})
    mock_garmin_client.update_power_zones.assert_not_called()


async def test_set_power_zones_write_error(app, mock_garmin_client):
    mock_garmin_client.update_power_zones.side_effect = GarminConnectConnectionError("API Error 400 - bad")
    result = json.loads(await _call(app, "set_power_zones", {"zones": '[{"sport": "CYCLING"}]'}))
    assert result["upstream_status"] == 400


async def test_get_one_rep_max_history(app, mock_garmin_client):
    mock_garmin_client.get_one_rep_max_history.return_value = [{"kg": 80}]
    await _call(app, "get_one_rep_max_history", {"exercise_type": "BENCH_PRESS", "start_date": START, "end_date": END, "aggregation": "Monthly"})
    mock_garmin_client.get_one_rep_max_history.assert_called_once_with("BENCH_PRESS", START, END, "monthly")
    assert "exercise key" in await _call(app, "get_one_rep_max_history", {"exercise_type": "bench/press", "start_date": START, "end_date": END})


async def test_get_activity_power_curve(app, mock_garmin_client):
    mock_garmin_client.get_activity_power_curve.return_value = {}
    assert "no power data" in await _call(app, "get_activity_power_curve", {"activity_id": 42})
    mock_garmin_client.get_activity_power_curve.assert_called_once_with(42)
    assert "positive whole number" in await _call(app, "get_activity_power_curve", {"activity_id": 0})
