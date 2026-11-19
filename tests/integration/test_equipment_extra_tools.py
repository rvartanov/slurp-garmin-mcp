"""
Integration tests for the equipment_extra module MCP tools (mocked Garmin client).
"""
import datetime
import json

import pytest
from garminconnect import GarminConnectConnectionError
from mcp.server.fastmcp import FastMCP

from garmin_mcp import equipment_extra

DAY, START, END = "2026-11-10", "2026-10-01", "2026-10-31"
TODAY = datetime.date.today().isoformat()
UUID = "0123abcd-4567-89ef-0123-456789abcdef"
BP_DAY = {"measurementSummaries": [{"measurements": [
    {"version": 1700000000001, "systolic": 120, "diastolic": 80, "pulse": 60, "notes": ""}]}]}


@pytest.fixture
def app(mock_garmin_client):
    equipment_extra.configure(mock_garmin_client)
    return equipment_extra.register_tools(FastMCP("Test Equipment Extra"))


async def _call(app, name, args=None):
    result = await app.call_tool(name, args or {})
    return result[0][0].text


@pytest.mark.parametrize("kind, method", [
    ("count", "get_workout_count"),
    ("sport_types", "get_workout_sport_types"),
    ("workout_types", "get_workout_types"),
    ("strength_benchmarks", "get_strength_benchmarks"),
])
async def test_get_workout_library(app, mock_garmin_client, kind, method):
    getattr(mock_garmin_client, method).return_value = {"x": 1}
    assert json.loads(await _call(app, "get_workout_library", {"kind": kind})) == {"x": 1}


async def test_get_upcoming_workouts(app, mock_garmin_client):
    mock_garmin_client.get_next_scheduled_workout.return_value = {"workoutId": 1}
    mock_garmin_client.get_scheduled_workouts_by_period.return_value = [{"workoutId": 2}]
    assert json.loads(await _call(app, "get_upcoming_workouts"))["workoutId"] == 1
    await _call(app, "get_upcoming_workouts", {"start_date": START, "end_date": END})
    mock_garmin_client.get_scheduled_workouts_by_period.assert_called_once_with(START, END)


async def test_copy_workout(app, mock_garmin_client):
    mock_garmin_client.copy_workout.return_value = {"workoutId": 99}
    result = json.loads(await _call(app, "copy_workout", {"workout_id": 5, "name": " Tempo kopie "}))
    assert result["workout_id"] == 99
    mock_garmin_client.copy_workout.assert_called_once_with(5, "Tempo kopie")
    assert "name must not be empty" in await _call(app, "copy_workout", {"workout_id": 5, "name": " "})


@pytest.mark.parametrize("args, method, call", [
    ({"kind": "latest", "date": DAY}, "get_latest_weight", (DAY,)),
    ({"kind": "first"}, "get_first_weight", ()),
    ({"kind": "daily_last", "start_date": START, "end_date": END}, "get_daily_last_weight", (START, END)),
    ({"kind": "all", "start_date": START, "end_date": END}, "get_weight_snapshot", (START, END)),
    ({"kind": "weekly", "end_date": END}, "get_weekly_weight", (END,)),
    ({"kind": "power_to_weight", "start_date": START, "end_date": END, "aggregation": "Weekly"},
     "get_power_to_weight_range", (START, END, "weekly")),
])
async def test_get_weight_data(app, mock_garmin_client, args, method, call):
    getattr(mock_garmin_client, method).return_value = {"w": 70}
    await _call(app, "get_weight_data", args)
    getattr(mock_garmin_client, method).assert_called_once_with(*call)


async def test_get_blood_pressure_data(app, mock_garmin_client):
    mock_garmin_client.get_blood_pressure_day.return_value = BP_DAY
    mock_garmin_client.get_daily_last_blood_pressure.return_value = [1]
    mock_garmin_client.get_weekly_blood_pressure.return_value = [2]
    assert "1700000000001" in await _call(app, "get_blood_pressure_data", {"date": DAY})
    await _call(app, "get_blood_pressure_data", {"kind": "daily_last", "start_date": START, "end_date": END})
    mock_garmin_client.get_daily_last_blood_pressure.assert_called_once_with(START, END)
    await _call(app, "get_blood_pressure_data", {"kind": "weekly"})
    mock_garmin_client.get_weekly_blood_pressure.assert_called_once_with(TODAY)


async def test_delete_weigh_in(app, mock_garmin_client):
    assert json.loads(await _call(app, "delete_weigh_in", {"weight_pk": "123", "date": DAY}))["status"] == "needs_confirmation"
    mock_garmin_client.delete_weigh_in.assert_not_called()
    await _call(app, "delete_weigh_in", {"weight_pk": "123", "date": DAY, "confirm": True})
    mock_garmin_client.delete_weigh_in.assert_called_once_with("123", DAY)
    assert "numeric samplePk" in await _call(app, "delete_weigh_in", {"weight_pk": "x", "date": DAY})


async def test_update_blood_pressure_note(app, mock_garmin_client):
    mock_garmin_client.get_blood_pressure_day.return_value = BP_DAY
    result = json.loads(await _call(app, "update_blood_pressure_note", {"version": "1700000000001", "date": DAY, "notes": "na koffie"}))
    assert result["status"] == "success"
    measurement = mock_garmin_client.update_blood_pressure.call_args.args[0]
    assert measurement["systolic"] == 120
    assert mock_garmin_client.update_blood_pressure.call_args.kwargs == {"notes": "na koffie"}
    assert "No blood pressure reading" in await _call(app, "update_blood_pressure_note", {"version": "5", "date": DAY, "notes": ""})


async def test_delete_blood_pressure(app, mock_garmin_client):
    mock_garmin_client.get_blood_pressure_day.return_value = BP_DAY
    preview = json.loads(await _call(app, "delete_blood_pressure", {"version": "1700000000001", "date": DAY}))
    assert preview["reading"]["systolic"] == 120
    mock_garmin_client.delete_blood_pressure.assert_not_called()
    await _call(app, "delete_blood_pressure", {"version": "1700000000001", "date": DAY, "confirm": True})
    mock_garmin_client.delete_blood_pressure.assert_called_once_with("1700000000001", DAY)


async def test_get_gear_data(app, mock_garmin_client):
    for method in ("get_gear_list", "get_gear_details", "get_gear_activities", "get_gear_types",
                   "get_user_gear_types", "get_gear_make_models", "get_activity_gear_v2"):
        getattr(mock_garmin_client, method).return_value = [{"ok": 1}]
    await _call(app, "get_gear_data", {"status": "retired", "gear_type": "shoes", "limit": 5})
    mock_garmin_client.get_gear_list.assert_called_once_with(start=0, limit=5, gear_statuses=["RETIRED"], gear_type="SHOES")
    await _call(app, "get_gear_data", {"kind": "details", "gear_uuid": UUID})
    mock_garmin_client.get_gear_details.assert_called_once_with(UUID)
    await _call(app, "get_gear_data", {"kind": "activities", "gear_uuid": UUID, "limit": 10})
    mock_garmin_client.get_gear_activities.assert_called_once_with(UUID, 10)
    await _call(app, "get_gear_data", {"kind": "make_models", "keywords": "asics"})
    mock_garmin_client.get_gear_make_models.assert_called_once_with("asics")
    await _call(app, "get_gear_data", {"kind": "activity", "activity_id": 7})
    mock_garmin_client.get_activity_gear_v2.assert_called_once_with(7)
    assert "uuid" in await _call(app, "get_gear_data", {"kind": "details", "gear_uuid": "nope"})


async def test_create_gear(app, mock_garmin_client):
    mock_garmin_client.create_gear.return_value = {"uuid": UUID}
    await _call(app, "create_gear", {"gear_type": "shoes", "brand": "ASICS", "model": "Novablast", "name": "Blauw",
                                     "first_use_date": DAY, "max_usage_distance_km": 800, "activity_types": "running, trail_running"})
    args, kwargs = mock_garmin_client.create_gear.call_args
    assert args == ("SHOES", "ASICS", "Novablast", "Blauw", DAY)
    assert kwargs["activity_type_keys"] == ["running", "trail_running"] and kwargs["max_usage_distance_km"] == 800
    assert "brand must not be empty" in await _call(app, "create_gear", {"gear_type": "SHOES", "brand": "", "model": "x",
                                                                          "name": "y", "first_use_date": DAY})


async def test_update_gear(app, mock_garmin_client):
    await _call(app, "update_gear", {"gear_uuid": UUID, "changes": '{"notes": "", "max_usage_distance_km": 900}'})
    mock_garmin_client.update_gear.assert_called_once_with(UUID, notes="", max_usage_distance_km=900)
    assert "Unknown field" in await _call(app, "update_gear", {"gear_uuid": UUID, "changes": '{"colour": "red"}'})


async def test_gear_status_default_delete(app, mock_garmin_client):
    await _call(app, "set_gear_status", {"gear_uuid": UUID, "status": "retired"})
    mock_garmin_client.set_gear_status.assert_called_once_with(UUID, "RETIRED")
    assert "ACTIVE or RETIRED" in await _call(app, "set_gear_status", {"gear_uuid": UUID, "status": "lost"})
    await _call(app, "set_gear_default", {"gear_uuid": UUID, "activity_type": "running", "default": False})
    mock_garmin_client.set_gear_default.assert_called_once_with("running", UUID, False)
    mock_garmin_client.get_gear_details.return_value = {"displayName": "Blauw"}
    assert json.loads(await _call(app, "delete_gear", {"gear_uuid": UUID}))["gear"]["displayName"] == "Blauw"
    mock_garmin_client.delete_gear.assert_not_called()
    await _call(app, "delete_gear", {"gear_uuid": UUID, "confirm": True})
    mock_garmin_client.delete_gear.assert_called_once_with(UUID)


async def test_write_error(app, mock_garmin_client):
    mock_garmin_client.set_gear_status.side_effect = GarminConnectConnectionError("API Error 404 - gone")
    assert json.loads(await _call(app, "set_gear_status", {"gear_uuid": UUID, "status": "ACTIVE"}))["upstream_status"] == 404


async def test_upcoming_workouts_are_summarised(app, mock_garmin_client):
    entry = {"workoutScheduleId": 3, "calendarDate": "2026-11-20", "ownerId": 1,
             "workout": {"workoutId": 9, "workoutName": "Tempo", "sportType": {"sportTypeKey": "running"},
                         "estimatedDurationInSecs": 3600, "workoutSegments": [{"steps": list(range(30))}]}}
    mock_garmin_client.get_scheduled_workouts_by_period.return_value = [entry]
    short = json.loads(await _call(app, "get_upcoming_workouts", {"start_date": START, "end_date": END}))
    assert short == [{"workoutScheduleId": 3, "calendarDate": "2026-11-20",
                      "workout": {"workoutId": 9, "workoutName": "Tempo", "estimatedDurationInSecs": 3600, "sport": "running"}}]
    full = json.loads(await _call(app, "get_upcoming_workouts", {"start_date": START, "end_date": END, "detail": True}))
    assert full[0]["workout"]["workoutSegments"]
