"""
Integration tests for the training_extra module MCP tools (mocked Garmin client).
"""
import datetime
import json

import pytest
from garminconnect import GarminConnectConnectionError
from mcp.server.fastmcp import FastMCP

from garmin_mcp import training_extra

DAY = "2026-12-01"
TODAY = datetime.date.today().isoformat()


@pytest.fixture
def app(mock_garmin_client):
    training_extra.configure(mock_garmin_client)
    return training_extra.register_tools(FastMCP("Test Training Extra"))


async def _call(app, name, args=None):
    result = await app.call_tool(name, args or {})
    return result[0][0].text


async def test_get_training_plans_scopes(app, mock_garmin_client):
    mock_garmin_client.get_training_plans.return_value = {"trainingPlanList": [1]}
    mock_garmin_client.get_active_training_plans.return_value = {"trainingPlanList": [2]}
    mock_garmin_client.search_training_plans.return_value = {"trainingPlanList": [3]}
    await _call(app, "get_training_plans", {"scope": "mine", "status": "Scheduled", "limit": 5})
    mock_garmin_client.get_training_plans.assert_called_once_with(limit=5, start=None, status="Scheduled")
    await _call(app, "get_training_plans", {"scope": "active"})
    mock_garmin_client.get_active_training_plans.assert_called_once_with(TODAY)
    await _call(app, "get_training_plans", {"scope": "catalog", "start": 21, "locale": "nl-NL"})
    mock_garmin_client.search_training_plans.assert_called_once_with(start=21, limit=20, locale="nl-NL")
    assert "scope must be" in await _call(app, "get_training_plans", {"scope": "all"})
    assert "locale" in await _call(app, "get_training_plans", {"scope": "catalog", "locale": "x"})


async def test_get_training_plan(app, mock_garmin_client):
    mock_garmin_client.get_training_plan_by_id.return_value = {"name": "10K"}
    mock_garmin_client.get_adaptive_training_plan_by_id.return_value = {"name": "Coach"}
    mock_garmin_client.get_training_plan_tasks.return_value = [{"task": 1}]
    result = json.loads(await _call(app, "get_training_plan", {"plan_id": 7, "include_tasks": True}))
    assert result == {"plan": {"name": "10K"}, "tasks": [{"task": 1}]}
    mock_garmin_client.get_training_plan_tasks.assert_called_once_with(7, locale="en")
    adaptive = json.loads(await _call(app, "get_training_plan", {"plan_id": 8, "adaptive": True}))
    assert adaptive == {"plan": {"name": "Coach"}}


async def test_schedule_and_delete_training_plan(app, mock_garmin_client):
    assert json.loads(await _call(app, "schedule_training_plan", {"plan_id": 7, "start_date": DAY}))["status"] == "success"
    mock_garmin_client.schedule_training_plan.assert_called_once_with(7, DAY)
    mock_garmin_client.get_training_plan_by_id.return_value = {"name": "10K", "startDate": DAY}
    preview = json.loads(await _call(app, "delete_training_plan", {"plan_id": 7}))
    assert preview["status"] == "needs_confirmation" and preview["plan"]["name"] == "10K"
    mock_garmin_client.delete_training_plan.assert_not_called()
    assert json.loads(await _call(app, "delete_training_plan", {"plan_id": 7, "confirm": True}))["status"] == "success"
    mock_garmin_client.delete_training_plan.assert_called_once_with(7)


async def test_schedule_training_plan_error(app, mock_garmin_client):
    mock_garmin_client.schedule_training_plan.side_effect = GarminConnectConnectionError("API Error 409 - exists")
    result = json.loads(await _call(app, "schedule_training_plan", {"plan_id": 7, "start_date": DAY}))
    assert result["upstream_status"] == 409


async def test_get_calendar_overview(app, mock_garmin_client):
    mock_garmin_client.get_calendar_week.return_value = {"calendarItems": [1]}
    mock_garmin_client.get_calendar_year.return_value = {"days": [1]}
    await _call(app, "get_calendar_overview", {"date": DAY, "first_day_of_week": 7})
    mock_garmin_client.get_calendar_week.assert_called_once_with(DAY, 7)
    await _call(app, "get_calendar_overview", {"view": "year", "date": DAY})
    mock_garmin_client.get_calendar_year.assert_called_once_with(2026)
    assert "view must be" in await _call(app, "get_calendar_overview", {"view": "month"})


async def test_move_calendar_item(app, mock_garmin_client):
    result = json.loads(await _call(app, "move_calendar_item", {"item_type": "workout", "item_id": 3, "new_date": DAY}))
    assert result["status"] == "success"
    mock_garmin_client.move_calendar_item.assert_called_once_with("workout", 3, DAY)
    assert "itemType" in await _call(app, "move_calendar_item", {"item_type": "work out", "item_id": 3, "new_date": DAY})


async def test_calendar_notes(app, mock_garmin_client):
    mock_garmin_client.create_calendar_note.return_value = {"id": 55}
    created = json.loads(await _call(app, "create_calendar_note", {"date": DAY, "name": " Rust ", "content": "hersteldag"}))
    assert created["note_id"] == 55
    mock_garmin_client.create_calendar_note.assert_called_once_with(DAY, "Rust", "hersteldag")
    await _call(app, "update_calendar_note", {"note_id": 55, "date": DAY, "name": "Rust"})
    mock_garmin_client.update_calendar_note.assert_called_once_with(55, DAY, "Rust", "")
    assert json.loads(await _call(app, "delete_calendar_note", {"note_id": 55}))["status"] == "needs_confirmation"
    mock_garmin_client.delete_calendar_note.assert_not_called()
    await _call(app, "delete_calendar_note", {"note_id": 55, "confirm": True})
    mock_garmin_client.delete_calendar_note.assert_called_once_with(55)
    assert "name must not be empty" in await _call(app, "create_calendar_note", {"date": DAY, "name": ""})


async def test_create_course_from_activity(app, mock_garmin_client):
    mock_garmin_client.convert_activity_to_course.return_value = {"courseName": "Run", "geoPoints": [1]}
    mock_garmin_client.create_course.return_value = {"courseId": 900, "courseName": "Rondje"}
    result = json.loads(await _call(app, "create_course_from_activity", {"activity_id": 12, "name": "Rondje"}))
    assert result["course_id"] == 900
    assert mock_garmin_client.create_course.call_args.args[0]["courseName"] == "Rondje"


async def test_create_course_from_activity_without_track(app, mock_garmin_client):
    mock_garmin_client.convert_activity_to_course.return_value = {}
    assert "no track" in await _call(app, "create_course_from_activity", {"activity_id": 12})
    mock_garmin_client.create_course.assert_not_called()


async def test_update_course_merges(app, mock_garmin_client):
    mock_garmin_client.get_course.return_value = {"courseId": 9, "courseName": "Old", "geoPoints": [1, 2]}
    result = json.loads(await _call(app, "update_course", {"course_id": 9, "changes": '{"courseName": "New"}'}))
    assert result["changed"] == ["courseName"]
    course_id, sent = mock_garmin_client.update_course.call_args.args
    assert course_id == 9 and sent["courseName"] == "New" and sent["geoPoints"] == [1, 2]
    assert "cannot be changed" in await _call(app, "update_course", {"course_id": 9, "changes": '{"courseId": 1}'})


async def test_course_favorites_and_pace_bands(app, mock_garmin_client):
    mock_garmin_client.get_course_favorites.return_value = []
    assert "No favourite" in await _call(app, "get_course_favorites")
    await _call(app, "set_course_favorite", {"course_id": 9, "favorite": False})
    mock_garmin_client.set_course_favorite.assert_called_once_with(9, False)
    mock_garmin_client.get_pace_bands.return_value = [{"name": "Marathon 4h"}]
    assert json.loads(await _call(app, "get_pace_bands"))[0]["name"] == "Marathon 4h"
