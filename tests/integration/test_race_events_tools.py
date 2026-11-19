"""
Integration tests for the race_events module MCP tools (mocked Garmin client).
"""
import json

import pytest
from garminconnect import GarminConnectConnectionError
from mcp.server.fastmcp import FastMCP

from garmin_mcp import race_events

EVENT = {
    "id": 123,
    "title": "Some Marathon",
    "date": "2027-04-11",
    "location": "Somewhere",
    "isRace": True,
    "shareableEventUuid": "uuid-1",
    "eventCustomization": {
        "customGoal": {"value": 14400, "unit": "second", "unitType": "time"},
        "isPrimaryEvent": False,
    },
}

WORKOUT = {"workoutId": 77, "workoutName": "Tempo", "workoutSegments": [{"segmentOrder": 1}]}


@pytest.fixture
def app(mock_garmin_client):
    race_events.configure(mock_garmin_client)
    return race_events.register_tools(FastMCP("Test Race Events"))


async def _call(app, name, args=None):
    result = await app.call_tool(name, args or {})
    return result[0][0].text


async def test_get_calendar_event(app, mock_garmin_client):
    mock_garmin_client.get_calendar_event.return_value = EVENT
    text = await _call(app, "get_calendar_event", {"event_id": 123})
    assert json.loads(text)["title"] == "Some Marathon"
    mock_garmin_client.get_calendar_event.assert_called_once_with(123)


async def test_get_calendar_event_rejects_bad_id(app, mock_garmin_client):
    text = await _call(app, "get_calendar_event", {"event_id": -1})
    assert "positive integer" in text
    mock_garmin_client.get_calendar_event.assert_not_called()


async def test_get_calendar_event_error(app, mock_garmin_client):
    mock_garmin_client.get_calendar_event.side_effect = Exception("boom")
    assert "Error" in await _call(app, "get_calendar_event", {"event_id": 1})


async def test_get_upcoming_events(app, mock_garmin_client):
    mock_garmin_client.get_upcoming_events.return_value = [EVENT]
    text = await _call(app, "get_upcoming_events", {"days_forward": 30, "limit": 5})
    assert json.loads(text)[0]["id"] == 123
    mock_garmin_client.get_upcoming_events.assert_called_once_with(days_forward=30, limit=5)


async def test_get_upcoming_events_empty(app, mock_garmin_client):
    mock_garmin_client.get_upcoming_events.return_value = []
    assert "No upcoming events" in await _call(app, "get_upcoming_events")


async def test_get_primary_event_none(app, mock_garmin_client):
    mock_garmin_client.get_primary_event.return_value = None
    assert "No primary event" in await _call(app, "get_primary_event")


async def test_get_primary_event(app, mock_garmin_client):
    mock_garmin_client.get_primary_event.return_value = EVENT
    assert json.loads(await _call(app, "get_primary_event"))["id"] == 123


async def test_update_calendar_event_merges_nested_changes(app, mock_garmin_client):
    mock_garmin_client.get_calendar_event.return_value = EVENT
    changes = {"title": "Renamed", "eventCustomization": {"customGoal": {"value": 12600}}}
    text = await _call(app, "update_calendar_event", {"event_id": 123, "changes": json.dumps(changes)})

    assert json.loads(text)["status"] == "success"
    event_id, sent = mock_garmin_client.update_calendar_event.call_args.args
    assert event_id == 123
    assert sent["title"] == "Renamed"
    assert sent["eventCustomization"]["customGoal"] == {"value": 12600, "unit": "second", "unitType": "time"}
    # Untouched fields stay as they were.
    assert sent["eventCustomization"]["isPrimaryEvent"] is False
    assert sent["location"] == "Somewhere"


async def test_update_calendar_event_refuses_identity_fields(app, mock_garmin_client):
    text = await _call(app, "update_calendar_event", {"event_id": 123, "changes": '{"id": 9}'})
    assert "cannot be changed" in text
    mock_garmin_client.update_calendar_event.assert_not_called()


async def test_update_calendar_event_rejects_bad_json(app, mock_garmin_client):
    text = await _call(app, "update_calendar_event", {"event_id": 123, "changes": "{nope"})
    assert "not valid JSON" in text
    mock_garmin_client.update_calendar_event.assert_not_called()


async def test_update_calendar_event_not_found(app, mock_garmin_client):
    mock_garmin_client.get_calendar_event.return_value = {}
    text = await _call(app, "update_calendar_event", {"event_id": 5, "changes": '{"title": "x"}'})
    assert "No calendar event" in text
    mock_garmin_client.update_calendar_event.assert_not_called()


async def test_update_calendar_event_write_error_is_structured(app, mock_garmin_client):
    mock_garmin_client.get_calendar_event.return_value = EVENT
    mock_garmin_client.update_calendar_event.side_effect = GarminConnectConnectionError("API Error 400 - bad")
    result = json.loads(await _call(app, "update_calendar_event", {"event_id": 123, "changes": '{"title": "x"}'}))
    assert result["upstream_status"] == 400


async def test_delete_calendar_event_needs_confirmation(app, mock_garmin_client):
    mock_garmin_client.get_calendar_event.return_value = EVENT
    result = json.loads(await _call(app, "delete_calendar_event", {"event_id": 123}))
    assert result["status"] == "needs_confirmation"
    assert result["event"]["title"] == "Some Marathon"
    mock_garmin_client.delete_calendar_event.assert_not_called()


async def test_delete_calendar_event_confirmed(app, mock_garmin_client):
    result = json.loads(await _call(app, "delete_calendar_event", {"event_id": 123, "confirm": True}))
    assert result["status"] == "success"
    mock_garmin_client.delete_calendar_event.assert_called_once_with(123)


async def test_delete_calendar_event_error(app, mock_garmin_client):
    mock_garmin_client.delete_calendar_event.side_effect = GarminConnectConnectionError("API Error 404 - gone")
    result = json.loads(await _call(app, "delete_calendar_event", {"event_id": 123, "confirm": True}))
    assert result["upstream_status"] == 404


async def test_update_workout(app, mock_garmin_client):
    mock_garmin_client.update_workout.return_value = {"workoutId": 77}
    result = json.loads(await _call(app, "update_workout", {"workout_id": 77, "workout": json.dumps(WORKOUT)}))
    assert result["status"] == "success"
    mock_garmin_client.update_workout.assert_called_once_with(77, WORKOUT)


async def test_update_workout_requires_complete_workout(app, mock_garmin_client):
    text = await _call(app, "update_workout", {"workout_id": 77, "workout": '{"workoutName": "x"}'})
    assert "workoutSegments" in text
    mock_garmin_client.update_workout.assert_not_called()


async def test_update_workout_error(app, mock_garmin_client):
    mock_garmin_client.update_workout.side_effect = GarminConnectConnectionError("API Error 500 - oops")
    result = json.loads(await _call(app, "update_workout", {"workout_id": 77, "workout": json.dumps(WORKOUT)}))
    assert result["upstream_status"] == 500
