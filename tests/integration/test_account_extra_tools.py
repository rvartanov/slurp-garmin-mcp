"""
Integration tests for the account_extra module MCP tools (mocked Garmin client).
"""
import datetime
import json

import pytest
from garminconnect import GarminConnectConnectionError
from mcp.server.fastmcp import FastMCP

from garmin_mcp import account_extra

DAY, START, END = "2026-11-10", "2026-10-01", "2026-10-31"
TODAY = datetime.date.today().isoformat()
UUID = "0123abcd-4567-89ef-0123-456789abcdef"


@pytest.fixture
def app(mock_garmin_client):
    account_extra.configure(mock_garmin_client)
    return account_extra.register_tools(FastMCP("Test Account Extra"))


async def _call(app, name, args=None):
    result = await app.call_tool(name, args or {})
    return result[0][0].text


@pytest.mark.parametrize("args, method, call", [
    ({"kind": "available_badges"}, "get_available_badges", ()),
    ({"kind": "in_progress_badges"}, "get_in_progress_badges", ()),
    ({"kind": "latest_badges", "limit": 3}, "get_latest_earned_badges", (3,)),
    ({"kind": "badges_for_day", "date": DAY}, "get_badges_for_day", (DAY,)),
    ({"kind": "badges_for_activity", "activity_id": 5}, "get_badges_for_activity", (5,)),
    ({"kind": "badge_detail", "badge_id": 7}, "get_badge_detail", (7,)),
    ({"kind": "badge_attributes"}, "get_badge_attributes", ()),
    ({"kind": "badge_challenge", "challenge_id": UUID}, "get_badge_challenge", (UUID,)),
    ({"kind": "virtual_challenges_available"}, "get_available_virtual_challenges", (1, 20)),
    ({"kind": "virtual_challenges_completed", "limit": 5}, "get_completed_virtual_challenges", (1, 5)),
    ({"kind": "adhoc_challenges"}, "get_active_adhoc_challenges", ()),
    ({"kind": "record_candidates"}, "get_personal_record_candidates", ()),
    ({"kind": "record_types"}, "get_personal_record_types", ()),
    ({"kind": "records_for_activity", "activity_id": 5}, "get_personal_records_for_activity", (5,)),
])
async def test_get_achievements(app, mock_garmin_client, args, method, call):
    getattr(mock_garmin_client, method).return_value = [{"x": 1}]
    assert json.loads(await _call(app, "get_achievements", args)) == [{"x": 1}]
    getattr(mock_garmin_client, method).assert_called_once_with(*call)


async def test_get_achievements_needs_ids(app, mock_garmin_client):
    assert "activity_id is required" in await _call(app, "get_achievements", {"kind": "badges_for_activity"})
    assert "uuid" in await _call(app, "get_achievements", {"kind": "badge_challenge", "challenge_id": "x"})


async def test_wellness_goals(app, mock_garmin_client):
    for m in ("get_effective_goals", "get_steps_goal", "get_user_goals", "get_weight_goal"):
        getattr(mock_garmin_client, m).return_value = {"g": 1}
    await _call(app, "get_wellness_goals")
    mock_garmin_client.get_effective_goals.assert_called_once_with(TODAY)
    await _call(app, "get_wellness_goals", {"kind": "steps", "date": DAY})
    mock_garmin_client.get_steps_goal.assert_called_once_with(DAY)
    await _call(app, "get_wellness_goals", {"kind": "weight", "start_date": START, "end_date": END})
    mock_garmin_client.get_weight_goal.assert_called_once_with(START, END)


async def test_set_daily_goal(app, mock_garmin_client):
    await _call(app, "set_daily_goal", {"goal_type": "floors_climbed", "value": 12, "date": DAY})
    mock_garmin_client.set_daily_goal.assert_called_once_with("FLOORS_CLIMBED", 12, DAY)
    assert "goal_type must be" in await _call(app, "set_daily_goal", {"goal_type": "STEPS", "value": 1})
    assert "positive number" in await _call(app, "set_daily_goal", {"goal_type": "HYDRATION", "value": 0})


async def test_get_device_data(app, mock_garmin_client):
    for m in ("get_active_devices", "get_user_device", "get_device_solar_gain", "get_sensors"):
        getattr(mock_garmin_client, m).return_value = [{"d": 1}]
    await _call(app, "get_device_data")
    mock_garmin_client.get_active_devices.assert_called_once_with()
    await _call(app, "get_device_data", {"kind": "registration", "device_id": 3})
    mock_garmin_client.get_user_device.assert_called_once_with(3)
    await _call(app, "get_device_data", {"kind": "solar_gain", "device_id": 3, "start_date": START, "end_date": END})
    mock_garmin_client.get_device_solar_gain.assert_called_once_with(3, START, END)
    assert "device_id is required" in await _call(app, "get_device_data", {"kind": "app_info"})
    assert "choose one of" in await _call(app, "get_device_data", {"kind": "firmware"})


async def test_device_writes(app, mock_garmin_client):
    await _call(app, "update_device_settings", {"device_id": 3, "settings": '{"activityTracking": {"moveAlertEnabled": true}}'})
    mock_garmin_client.update_device_settings.assert_called_once_with(3, {"activityTracking": {"moveAlertEnabled": True}})
    assert json.loads(await _call(app, "send_scheduled_workouts_to_devices"))["status"] == "success"
    await _call(app, "set_primary_training_device", {"device_id": 3})
    mock_garmin_client.set_primary_training_device.assert_called_once_with(3)


@pytest.mark.parametrize("kind, method", [
    ("personal_information", "get_personal_information"),
    ("profile", "get_user_profile_base"),
    ("timezone", "get_user_timezone"),
    ("privacy", "get_privacy_settings"),
    ("usage_indicators", "get_usage_indicators"),
])
async def test_get_profile_data(app, mock_garmin_client, kind, method):
    getattr(mock_garmin_client, method).return_value = {"p": 1}
    assert json.loads(await _call(app, "get_profile_data", {"kind": kind})) == {"p": 1}


async def test_update_user_settings(app, mock_garmin_client):
    await _call(app, "update_user_settings", {"settings": '{"userData": {"measurementSystem": "metric"}}'})
    mock_garmin_client.update_user_settings.assert_called_once_with({"userData": {"measurementSystem": "metric"}})


async def test_menstrual_overview(app, mock_garmin_client):
    for m in ("get_menstrual_cycle_summary", "get_menstrual_last_confirmed", "get_menstrual_reports"):
        getattr(mock_garmin_client, m).return_value = {"c": 1}
    await _call(app, "get_menstrual_overview", {"date": DAY})
    mock_garmin_client.get_menstrual_cycle_summary.assert_called_once_with(DAY)
    await _call(app, "get_menstrual_overview", {"kind": "reports", "date": DAY, "number_of_cycles": 12})
    mock_garmin_client.get_menstrual_reports.assert_called_once_with(DAY, 12)
    assert "1, 6 or 12" in await _call(app, "get_menstrual_overview", {"kind": "reports", "number_of_cycles": 3})


async def test_log_menstrual_day(app, mock_garmin_client):
    await _call(app, "log_menstrual_day", {"date": DAY, "flow": "MEDIUM", "symptoms": "CRAMPS, HEADACHE"})
    args, kwargs = mock_garmin_client.update_menstrual_daily_log.call_args
    assert args == (DAY,) and kwargs["symptoms"] == ["CRAMPS", "HEADACHE"] and kwargs["flow"] == "MEDIUM"
    assert kwargs["notes"] is None and kwargs["ovulation_day"] is False


async def test_set_menstrual_periods(app, mock_garmin_client):
    periods = [["2026-10-03", "2026-10-04"]]
    await _call(app, "set_menstrual_periods", {"start_date": START, "end_date": END, "periods": json.dumps(periods)})
    mock_garmin_client.update_menstrual_calendar.assert_called_once_with(START, END, periods)
    assert "YYYY-MM-DD" in await _call(app, "set_menstrual_periods", {"start_date": START, "end_date": END, "periods": '[["03-10-2026"]]'})


async def test_confirm_menstrual_period(app, mock_garmin_client):
    await _call(app, "confirm_menstrual_period", {"period_start_date": DAY, "period_length": 5, "cycle_length": 28})
    mock_garmin_client.confirm_menstrual_period_start.assert_called_once_with(DAY, 5, 28, predicted_cycle=False)
    await _call(app, "confirm_menstrual_period", {"period_start_date": DAY, "period_length": 5, "cycle_length": 28, "first_setup": True})
    mock_garmin_client.init_menstrual_cycle_setup.assert_called_once_with(DAY, 5, 28)


async def test_update_menstrual_settings_error(app, mock_garmin_client):
    mock_garmin_client.update_menstrual_settings.side_effect = GarminConnectConnectionError("API Error 400 - bad")
    result = json.loads(await _call(app, "update_menstrual_settings", {"settings": '{"x": 1}'}))
    assert result["upstream_status"] == 400


async def test_get_golf_data(app, mock_garmin_client):
    for m in ("get_golf_summary", "get_golf_scorecard", "get_golf_shot_data", "get_golf_club_stats", "get_golf_user_stats"):
        getattr(mock_garmin_client, m).return_value = {"golf": 1}
    await _call(app, "get_golf_data")
    mock_garmin_client.get_golf_summary.assert_called_once_with(0, 100)
    await _call(app, "get_golf_data", {"kind": "shots", "scorecard_id": 4, "holes": "1, 2"})
    mock_garmin_client.get_golf_shot_data.assert_called_once_with(4, "1,2")
    assert "hole numbers" in await _call(app, "get_golf_data", {"kind": "shots", "scorecard_id": 4, "holes": "a"})
    assert "scorecard_id is required" in await _call(app, "get_golf_data", {"kind": "scorecard"})


async def test_device_lists_are_summarised(app, mock_garmin_client):
    device = {"deviceId": 3, "productDisplayName": "Forerunner 965", "imageUrl": "x", "featureFlagA": True}
    mock_garmin_client.get_historical_devices.return_value = [device]
    assert json.loads(await _call(app, "get_device_data", {"kind": "historical"})) == [
        {"deviceId": 3, "productDisplayName": "Forerunner 965"}]
    assert json.loads(await _call(app, "get_device_data", {"kind": "historical", "detail": True})) == [device]
