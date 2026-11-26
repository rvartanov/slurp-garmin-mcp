"""Ids and dates are checked locally before they are put into an API path."""
import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import nutrition, workouts
from garmin_mcp.workouts import _validate_id

BAD_DATES = ["2026-11-10/../../userprofile-service", "2026-11-10?x=1", "2026-13-01", "today"]


def _text(result):
    return result[0][0].text


@pytest.fixture
def nutrition_app(mock_garmin_client):
    nutrition.configure(mock_garmin_client)
    return nutrition.register_tools(FastMCP("t"))


def test_validate_id():
    assert _validate_id("0a1b2c3d-4e5f", "x") == "0a1b2c3d-4e5f"
    assert _validate_id(1234567, "x") == "1234567"
    for bad in ["", "../x", "a/b", "a?b", "a b", "x" * 65, True, None, 1.5]:
        with pytest.raises(ValueError):
            _validate_id(bad, "x")


@pytest.mark.parametrize("tool", [
    "get_nutrition_daily_food_log", "get_nutrition_daily_meals", "get_nutrition_daily_settings",
])
@pytest.mark.parametrize("bad", BAD_DATES)
async def test_nutrition_reads_reject_bad_dates(nutrition_app, mock_garmin_client, tool, bad):
    text = _text(await nutrition_app.call_tool(tool, {"date": bad}))
    assert "expected YYYY-MM-DD" in text
    mock_garmin_client.connectapi.assert_not_called()


async def test_set_nutrition_settings_rejects_bad_date(nutrition_app, mock_garmin_client):
    text = _text(await nutrition_app.call_tool(
        "set_nutrition_daily_settings", {"date": BAD_DATES[0], "calorie_goal": 2000}))
    assert "expected YYYY-MM-DD" in text
    mock_garmin_client.connectapi.assert_not_called()
    mock_garmin_client.client.put.assert_not_called()


async def test_delete_custom_food_rejects_bad_id(nutrition_app, mock_garmin_client):
    text = _text(await nutrition_app.call_tool(
        "delete_custom_food", {"food_id": "../../userprofile-service/x", "confirm": True}))
    assert "Invalid food_id" in text
    mock_garmin_client.client.delete.assert_not_called()


async def test_delete_food_log_rejects_bad_date_and_id(nutrition_app, mock_garmin_client):
    for args in (
        {"log_id": "0a1b", "meal_date": BAD_DATES[0], "confirm": True},
        {"log_id": "a/b", "meal_date": "2026-11-10", "confirm": True},
    ):
        text = _text(await nutrition_app.call_tool("delete_food_log", args))
        assert "Invalid" in text
    mock_garmin_client.connectapi.assert_not_called()
    mock_garmin_client.client.delete.assert_not_called()


async def test_get_workout_by_id_rejects_bad_uuid(mock_garmin_client):
    workouts.configure(mock_garmin_client)
    app = workouts.register_tools(FastMCP("t"))
    text = _text(await app.call_tool("get_workout_by_id", {"workout_id": "abc-def/../../x"}))
    assert "Invalid workout_id" in text
    mock_garmin_client.connectapi.assert_not_called()
