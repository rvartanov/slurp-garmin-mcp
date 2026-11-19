"""
Integration tests for the health_extra module MCP tools (mocked Garmin client).
"""
import datetime
import json

import pytest
from garminconnect import GarminConnectConnectionError
from mcp.server.fastmcp import FastMCP

from garmin_mcp import health_extra

START, END = "2026-11-01", "2026-11-07"
TODAY = datetime.date.today().isoformat()

FLIGHT = {
    "originLocation": "AMS", "originTimezone": "+01:00", "originTimestamp": "2027-03-04T10:00:00.00",
    "destinationLocation": "JFK", "destinationTimezone": "-05:00", "destinationTimestamp": "2027-03-04T12:30:00.00",
}


@pytest.fixture
def app(mock_garmin_client):
    health_extra.configure(mock_garmin_client)
    return health_extra.register_tools(FastMCP("Test Health Extra"))


async def _call(app, name, args=None):
    result = await app.call_tool(name, args or {})
    return result[0][0].text


@pytest.mark.parametrize("metric, method, extra", [
    ("heart_rate", "get_daily_heart_rate_stats", ()),
    ("resting_heart_rate", "get_rhr_daily", ()),
    ("hrv", "get_hrv_data_range", ()),
    ("stress", "get_daily_stress_stats", ()),
    ("body_battery", "get_daily_body_battery_stats", ()),
    ("intensity_minutes", "get_daily_intensity_minutes_stats", ()),
    ("respiration", "get_daily_respiration_stats", ()),
    ("floors", "get_daily_floors_stats", ()),
    ("hydration", "get_daily_hydration_stats", ()),
    ("calories", "get_calories_daily", ()),
    ("steps", "get_daily_stats", ("STEPS",)),
    ("pushes", "get_daily_stats", ("PUSHES",)),
    ("sleep", "get_sleep_daily", ()),
    ("sleep_overall", "get_sleep_stats_overall", ()),
    ("averages", "get_stats_averages", ()),
    ("daily_summaries", "get_daily_summaries", ()),
    ("health_snapshots", "get_health_snapshots_range", ()),
    ("ecg", "get_ecg_daily", ()),
    ("calorie_intake", "get_calorie_summary", ()),
])
async def test_get_health_stats_dispatch(app, mock_garmin_client, metric, method, extra):
    getattr(mock_garmin_client, method).return_value = {"values": [1]}
    text = await _call(app, "get_health_stats", {"metric": metric, "start_date": START, "end_date": END})
    assert json.loads(text) == {"values": [1]}
    getattr(mock_garmin_client, method).assert_called_once_with(START, END, *extra)


async def test_get_health_stats_unknown_metric(app):
    text = await _call(app, "get_health_stats", {"metric": "mood", "start_date": START, "end_date": END})
    assert "Unknown metric" in text and "body_battery" in text


@pytest.mark.parametrize("start, end, message", [
    ("2026-11-07", "2026-11-01", "on or before"),
    ("2025-01-01", "2026-11-07", "at most 366"),
    ("2026-13-01", "2026-11-07", "no such day"),
    ("01-11-2026", "2026-11-07", "YYYY-MM-DD"),
])
async def test_get_health_stats_bad_range(app, mock_garmin_client, start, end, message):
    text = await _call(app, "get_health_stats", {"metric": "stress", "start_date": start, "end_date": end})
    assert message in text
    mock_garmin_client.get_daily_stress_stats.assert_not_called()


async def test_get_health_stats_empty_and_error(app, mock_garmin_client):
    mock_garmin_client.get_daily_floors_stats.return_value = []
    assert "No floors data" in await _call(app, "get_health_stats", {"metric": "floors", "start_date": START, "end_date": END})
    mock_garmin_client.get_daily_floors_stats.side_effect = Exception("boom")
    assert "Error retrieving floors" in await _call(app, "get_health_stats", {"metric": "floors", "start_date": START, "end_date": END})


@pytest.mark.parametrize("metric, method", [
    ("heart_rate_weekly", "get_weekly_heart_rate_stats"),
    ("floors_weekly", "get_weekly_floors_stats"),
    ("hydration_weekly", "get_weekly_hydration_stats"),
    ("calories_weekly", "get_weekly_calories_stats"),
    ("sleep_weekly", "get_sleep_stats_weekly"),
    ("steps_monthly", "get_monthly_steps"),
])
async def test_get_health_trend_dispatch(app, mock_garmin_client, metric, method):
    getattr(mock_garmin_client, method).return_value = [{"week": 1}]
    await _call(app, "get_health_trend", {"metric": metric, "end_date": END, "periods": 8})
    getattr(mock_garmin_client, method).assert_called_once_with(END, 8)


async def test_get_health_trend_defaults_and_limits(app, mock_garmin_client):
    mock_garmin_client.get_monthly_steps.return_value = [1]
    await _call(app, "get_health_trend", {"metric": "steps_monthly"})
    mock_garmin_client.get_monthly_steps.assert_called_once_with(TODAY, 4)
    assert "at most 52" in await _call(app, "get_health_trend", {"metric": "steps_monthly", "periods": 99})


@pytest.mark.parametrize("kind, method, extra", [
    ("intensity_minutes", "get_intensity_minutes_data", ()),
    ("hourly_intensity_minutes", "get_hourly_intensity_minutes", (1,)),
    ("movement", "get_daily_movement", ()),
    ("hydration", "get_hydration_all_data", ()),
    ("sleep", "get_daily_sleep", ()),
    ("naps", "get_naps", ()),
    ("week_average_resting_heart_rate", "get_week_average_resting_hr", ()),
    ("jetlag", "get_jetlag_status", ()),
    ("health_snapshots", "get_health_snapshots", ()),
])
async def test_get_health_day_dispatch(app, mock_garmin_client, kind, method, extra):
    getattr(mock_garmin_client, method).return_value = {"x": 1}
    await _call(app, "get_health_day", {"kind": kind, "date": START})
    getattr(mock_garmin_client, method).assert_called_once_with(START, *extra)


async def test_get_health_day_defaults_to_today(app, mock_garmin_client):
    mock_garmin_client.get_naps.return_value = []
    assert f"No naps data for {TODAY}" in await _call(app, "get_health_day", {"kind": "naps"})


@pytest.mark.parametrize("kind, method", [
    ("lifetime_totals", "get_lifetime_totals"),
    ("activity_statistics", "get_user_statistics"),
    ("last_sync", "get_sync_timestamp"),
    ("nutrition_status", "get_nutrition_status"),
])
async def test_get_account_stats_dispatch(app, mock_garmin_client, kind, method):
    getattr(mock_garmin_client, method).return_value = {"ok": True}
    assert json.loads(await _call(app, "get_account_stats", {"kind": kind})) == {"ok": True}


async def test_get_health_snapshot_with_samples(app, mock_garmin_client):
    mock_garmin_client.get_health_snapshot.return_value = {"hr": 60}
    mock_garmin_client.get_health_snapshot_epochs.return_value = [{"hr": 61}]
    result = json.loads(await _call(app, "get_health_snapshot", {"date": START, "snapshot_id": "ab-12", "include_samples": True}))
    assert result == {"summary": {"hr": 60}, "samples": [{"hr": 61}]}
    mock_garmin_client.get_health_snapshot.assert_called_once_with(START, "ab-12")


async def test_get_health_snapshot_rejects_bad_id(app, mock_garmin_client):
    assert "uuid" in await _call(app, "get_health_snapshot", {"date": START, "snapshot_id": "../x"})
    mock_garmin_client.get_health_snapshot.assert_not_called()


async def test_get_ecg_recordings(app, mock_garmin_client):
    mock_garmin_client.get_ecg_list.return_value = {"items": [1]}
    await _call(app, "get_ecg_recordings", {"start_date": START, "end_date": END, "page_size": 5})
    mock_garmin_client.get_ecg_list.assert_called_once_with(START, END, page_size=5, page=None)


async def test_get_ecg(app, mock_garmin_client):
    mock_garmin_client.get_ecg.return_value = {"id": "e1"}
    assert json.loads(await _call(app, "get_ecg", {"ecg_id": "e1"}))["id"] == "e1"


async def test_create_jetlag_trip(app, mock_garmin_client):
    mock_garmin_client.add_jetlag_trip.return_value = {"id": 5}
    result = json.loads(await _call(app, "create_jetlag_trip", {
        "start_date": "2027-03-04", "end_date": "2027-03-10", "flights": json.dumps([FLIGHT])}))
    assert result["status"] == "success"
    mock_garmin_client.add_jetlag_trip.assert_called_once_with("2027-03-04", "2027-03-10", [FLIGHT])


async def test_create_jetlag_trip_rejects_incomplete_flight(app, mock_garmin_client):
    leg = {k: v for k, v in FLIGHT.items() if k != "destinationTimezone"}
    text = await _call(app, "create_jetlag_trip", {"start_date": "2027-03-04", "end_date": "2027-03-10", "flights": json.dumps([leg])})
    assert "destinationTimezone" in text and "UTC offset" in text
    mock_garmin_client.add_jetlag_trip.assert_not_called()


async def test_update_jetlag_trip(app, mock_garmin_client):
    await _call(app, "update_jetlag_trip", {"trip_id": 5, "start_date": "2027-03-04", "end_date": "2027-03-10", "flights": json.dumps([FLIGHT])})
    mock_garmin_client.update_jetlag_trip.assert_called_once_with(5, "2027-03-04", "2027-03-10", [FLIGHT])


async def test_delete_jetlag_trip_preview_and_confirm(app, mock_garmin_client):
    mock_garmin_client.get_jetlag_trips.return_value = [{"id": 5, "flights": [FLIGHT]}]
    preview = json.loads(await _call(app, "delete_jetlag_trip", {"trip_id": 5}))
    assert preview["status"] == "needs_confirmation"
    mock_garmin_client.delete_jetlag_trip.assert_not_called()
    done = json.loads(await _call(app, "delete_jetlag_trip", {"trip_id": 5, "confirm": True}))
    assert done["status"] == "success"
    mock_garmin_client.delete_jetlag_trip.assert_called_once_with(5)


async def test_delete_jetlag_trip_not_found(app, mock_garmin_client):
    mock_garmin_client.get_jetlag_trips.return_value = []
    assert json.loads(await _call(app, "delete_jetlag_trip", {"trip_id": 9}))["status"] == "not_found"


async def test_set_steps_goal_manual_and_automatic(app, mock_garmin_client):
    await _call(app, "set_steps_goal", {"steps": 9000, "date": START})
    mock_garmin_client.set_steps_goal.assert_called_with(9000, START)
    result = json.loads(await _call(app, "set_steps_goal", {"steps": 0, "date": START}))
    mock_garmin_client.set_steps_goal.assert_called_with(None, START)
    assert result["goal"] == "automatic"


async def test_set_steps_goal_rejects_bad_value(app, mock_garmin_client):
    assert "between 0 and 200000" in await _call(app, "set_steps_goal", {"steps": -1})
    mock_garmin_client.set_steps_goal.assert_not_called()


async def test_write_error_is_structured(app, mock_garmin_client):
    mock_garmin_client.set_steps_goal.side_effect = GarminConnectConnectionError("API Error 400 - nope")
    assert json.loads(await _call(app, "set_steps_goal", {"steps": 5000}))["upstream_status"] == 400


async def test_long_series_are_shortened_by_default(app, mock_garmin_client):
    mock_garmin_client.get_daily_sleep.return_value = {"sleepLevels": list(range(500)), "score": 80, "short": [1, 2]}
    compact = json.loads(await _call(app, "get_health_day", {"kind": "sleep", "date": START}))
    assert compact["score"] == 80 and compact["short"] == [1, 2]
    assert compact["sleepLevels"]["omitted_items"] == 500
    assert compact["sleepLevels"]["first"] == 0 and compact["sleepLevels"]["last"] == 499
    full = json.loads(await _call(app, "get_health_day", {"kind": "sleep", "date": START, "detail": True}))
    assert full["sleepLevels"] == list(range(500))


async def test_nested_long_lists_are_shortened(app, mock_garmin_client):
    mock_garmin_client.get_daily_summaries.return_value = [{"day": i, "samples": list(range(100))} for i in range(3)]
    compact = json.loads(await _call(app, "get_health_stats", {"metric": "daily_summaries", "start_date": START, "end_date": END}))
    assert len(compact) == 3 and compact[0]["samples"]["omitted_items"] == 100


async def test_empty_and_false_fields_are_left_out_by_default(app, mock_garmin_client):
    mock_garmin_client.get_naps.return_value = {"a": 0, "b": None, "c": False, "d": "", "e": [], "f": {"g": None}, "h": True}
    assert json.loads(await _call(app, "get_health_day", {"kind": "naps", "date": START})) == {"a": 0, "h": True}
    full = json.loads(await _call(app, "get_health_day", {"kind": "naps", "date": START, "detail": True}))
    assert full["c"] is False and full["b"] is None
