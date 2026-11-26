"""Destructive tools preview first and bulk calls are capped."""
import json

import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import gear_management, workouts


def _data(result):
    return json.loads(result[0][0].text)


@pytest.fixture
def workouts_app(mock_garmin_client):
    workouts.configure(mock_garmin_client)
    return workouts.register_tools(FastMCP("t"))


async def test_unschedule_workout_previews_without_confirm(workouts_app, mock_garmin_client):
    mock_garmin_client.get_scheduled_workout_by_id.return_value = {
        "calendarDate": "2026-11-12", "workout": {"workoutId": 42, "workoutName": "Easy run"}}
    data = _data(await workouts_app.call_tool("unschedule_workout", {"scheduled_workout_id": 7}))
    assert data["status"] == "needs_confirmation"
    assert data["scheduled_workout"] == {
        "scheduled_workout_id": 7, "date": "2026-11-12", "workout_id": 42, "workout_name": "Easy run"}
    mock_garmin_client.unschedule_workout.assert_not_called()


async def test_unschedule_workouts_previews_without_confirm(workouts_app, mock_garmin_client):
    data = _data(await workouts_app.call_tool("unschedule_workouts", {"scheduled_workout_ids": [1, 2]}))
    assert data["status"] == "needs_confirmation" and data["total"] == 2
    mock_garmin_client.unschedule_workout.assert_not_called()


@pytest.mark.parametrize("tool,field", [
    ("unschedule_workouts", "scheduled_workout_ids"),
    ("delete_workouts", "workout_ids"),
])
async def test_bulk_calls_are_capped(workouts_app, mock_garmin_client, tool, field):
    ids = list(range(1, 27))
    data = _data(await workouts_app.call_tool(tool, {field: ids, "confirm": True}))
    assert data["status"] == "failed" and "at most 25" in data["message"]
    mock_garmin_client.unschedule_workout.assert_not_called()
    mock_garmin_client.delete_workout.assert_not_called()
    mock_garmin_client.get_workout_by_id.assert_not_called()

    mock_garmin_client.unschedule_workout.return_value = {}
    mock_garmin_client.delete_workout.return_value = {}
    data = _data(await workouts_app.call_tool(tool, {field: ids[:25], "confirm": True}))
    assert data["succeeded"] == 25


async def test_remove_gear_previews_without_confirm(mock_garmin_client):
    gear_management.configure(mock_garmin_client)
    app = gear_management.register_tools(FastMCP("t"))
    mock_garmin_client.get_activity_gear.return_value = [
        {"uuid": "0A1B2C3D", "displayName": "Trail shoes"}]
    data = _data(await app.call_tool(
        "remove_gear_from_activity", {"activity_id": 1234567, "gear_uuid": "0a1b2c3d"}))
    assert data["status"] == "needs_confirmation"
    assert data["gear"] == {"activity_id": 1234567, "gear_uuid": "0a1b2c3d", "linked": True,
                            "gear_name": "Trail shoes"}
    mock_garmin_client.remove_gear_from_activity.assert_not_called()
