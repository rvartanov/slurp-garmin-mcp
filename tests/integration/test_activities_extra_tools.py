"""
Integration tests for the activities_extra module MCP tools (mocked Garmin client).
"""
import base64
import json
import os

import pytest
from garminconnect import GarminConnectConnectionError
from mcp.server.fastmcp import FastMCP

from garmin_mcp import activities_extra

START, END = "2026-10-01", "2026-10-31"


@pytest.fixture
def app(mock_garmin_client):
    activities_extra.configure(mock_garmin_client)
    return activities_extra.register_tools(FastMCP("Test Activities Extra"))


async def _call(app, name, args=None):
    result = await app.call_tool(name, args or {})
    return result[0][0].text


@pytest.mark.parametrize("kind, method", [
    ("details", "get_activity_details"),
    ("laps", "get_activity_laps"),
    ("rounds", "get_activity_rounds"),
    ("workout_steps", "get_activity_step_details"),
    ("jumps", "get_activity_jump_details"),
    ("subsecond", "get_activity_subsecond_details"),
    ("swim", "get_activity_swim_details"),
    ("map", "get_activity_map_details"),
    ("polyline", "get_activity_polyline"),
    ("photos", "get_activity_images"),
    ("segments", "get_activity_segments"),
    ("adjacent", "get_adjacent_activities"),
])
async def test_get_activity_data_dispatch(app, mock_garmin_client, kind, method):
    getattr(mock_garmin_client, method).return_value = {"x": 1}
    assert json.loads(await _call(app, "get_activity_data", {"activity_id": 77, "kind": kind})) == {"x": 1}
    getattr(mock_garmin_client, method).assert_called_once_with(77)


async def test_get_activity_data_empty_and_bad_input(app, mock_garmin_client):
    mock_garmin_client.get_activity_laps.return_value = {}
    assert "has no laps data" in await _call(app, "get_activity_data", {"activity_id": 77})
    assert "Unknown kind" in await _call(app, "get_activity_data", {"activity_id": 77, "kind": "videos"})
    assert "positive whole number" in await _call(app, "get_activity_data", {"activity_id": -3})


async def test_find_activities_search_passes_filters(app, mock_garmin_client):
    mock_garmin_client.search_activities.return_value = [{"activityId": 1}]
    filters = {"activityType": "running", "minDistance": 10000, "favorite": True}
    await _call(app, "find_activities", {"filters": json.dumps(filters), "start": 20, "limit": 10})
    mock_garmin_client.search_activities.assert_called_once_with(20, 10, **filters)


async def test_find_activities_rejects_unknown_filter(app, mock_garmin_client):
    text = await _call(app, "find_activities", {"filters": '{"colour": "red"}'})
    assert "Unknown filter" in text and "colour" in text
    mock_garmin_client.search_activities.assert_not_called()


async def test_find_activities_other_kinds(app, mock_garmin_client):
    mock_garmin_client.get_favorite_activities.return_value = {"activityList": []}
    mock_garmin_client.get_last_activity.return_value = {"activityId": 9}
    mock_garmin_client.get_training_load_activities.return_value = [{"load": 50}]
    await _call(app, "find_activities", {"kind": "favorites", "limit": 3})
    mock_garmin_client.get_favorite_activities.assert_called_once_with(3)
    assert json.loads(await _call(app, "find_activities", {"kind": "last"}))["activityId"] == 9
    await _call(app, "find_activities", {"kind": "training_load", "start_date": START, "end_date": END})
    mock_garmin_client.get_training_load_activities.assert_called_once_with(START, END)
    assert "kind must be" in await _call(app, "find_activities", {"kind": "all"})


async def test_get_activity_aggregates(app, mock_garmin_client):
    mock_garmin_client.get_weekly_activity_stats.return_value = [1]
    mock_garmin_client.get_fastest_splits.return_value = [2]
    mock_garmin_client.get_available_metrics.return_value = [3]
    await _call(app, "get_activity_aggregates", {"kind": "weekly", "start_date": START, "end_date": END})
    mock_garmin_client.get_weekly_activity_stats.assert_called_once_with(START, END)
    await _call(app, "get_activity_aggregates", {"kind": "fastest_splits", "start_date": START, "end_date": END,
                                                 "activity_type": "cycling", "number_of_bests": 3})
    mock_garmin_client.get_fastest_splits.assert_called_once_with(START, END, "cycling", 3)
    await _call(app, "get_activity_aggregates", {"kind": "available_metrics", "start_date": START, "end_date": END})
    mock_garmin_client.get_available_metrics.assert_called_once_with(START, END)
    assert "type key" in await _call(app, "get_activity_aggregates", {"kind": "fastest_splits", "start_date": START,
                                                                       "end_date": END, "activity_type": "Run!"})


async def test_set_activity_favorite_and_event_types(app, mock_garmin_client):
    assert json.loads(await _call(app, "set_activity_favorite", {"activity_id": 5, "favorite": False}))["favorite"] is False
    mock_garmin_client.set_activity_favorite.assert_called_once_with(5, False)
    mock_garmin_client.get_activity_event_types.return_value = [{"typeKey": "race"}]
    assert json.loads(await _call(app, "get_activity_event_types"))[0]["typeKey"] == "race"


async def test_update_activity(app, mock_garmin_client):
    fields = {"activityName": "Long run", "description": "easy"}
    result = json.loads(await _call(app, "update_activity", {"activity_id": 5, "fields": json.dumps(fields)}))
    assert result["changed"] == ["activityName", "description"]
    mock_garmin_client.update_activity.assert_called_once_with(5, fields)
    assert "cannot be changed" in await _call(app, "update_activity", {"activity_id": 5, "fields": '{"activityId": 1}'})


async def test_update_activity_error(app, mock_garmin_client):
    mock_garmin_client.update_activity.side_effect = GarminConnectConnectionError("API Error 403 - no")
    result = json.loads(await _call(app, "update_activity", {"activity_id": 5, "fields": '{"activityName": "x"}'}))
    assert result["upstream_status"] == 403


async def test_create_activity_from_json(app, mock_garmin_client):
    mock_garmin_client.create_manual_activity_from_json.return_value = {"activityId": 11}
    payload = {"activityName": "Yoga", "summaryDTO": {"duration": 1800}}
    result = json.loads(await _call(app, "create_activity_from_json", {"activity": json.dumps(payload)}))
    assert result["activity"]["activityId"] == 11
    mock_garmin_client.create_manual_activity_from_json.assert_called_once_with(payload)


@pytest.mark.parametrize("as_import, method", [(False, "upload_activity"), (True, "import_activity")])
async def test_upload_activity_file(app, mock_garmin_client, as_import, method):
    seen = {}

    def fake(path):
        seen["path"] = path
        seen["bytes"] = open(path, "rb").read()
        return {"detailedImportResult": {"successes": [1]}}

    getattr(mock_garmin_client, method).side_effect = fake
    content = base64.b64encode(b"FIT-BYTES").decode()
    result = json.loads(await _call(app, "upload_activity_file", {"filename": "run.FIT", "content_base64": content,
                                                                  "as_import": as_import}))
    assert result["status"] == "success"
    assert seen["bytes"] == b"FIT-BYTES" and seen["path"].endswith(".fit")
    assert not os.path.exists(seen["path"])  # temp file removed


@pytest.mark.parametrize("filename, content, message", [
    ("run.exe", base64.b64encode(b"x").decode(), ".fit, .gpx or .tcx"),
    ("run.gpx", "not base64!!", "not valid base64"),
    ("run.gpx", "", "empty"),
])
async def test_upload_activity_file_rejects_bad_input(app, mock_garmin_client, filename, content, message):
    assert message in await _call(app, "upload_activity_file", {"filename": filename, "content_base64": content})
    mock_garmin_client.upload_activity.assert_not_called()
