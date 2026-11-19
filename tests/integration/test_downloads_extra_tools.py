"""
Integration tests for the downloads_extra module MCP tools (mocked Garmin client).
"""
import base64
import json

import pytest
from garminconnect import GarminConnectConnectionError
from mcp.server.fastmcp import FastMCP

from garmin_mcp import downloads_extra

DAY = "2026-11-10"


@pytest.fixture
def app(mock_garmin_client, monkeypatch):
    monkeypatch.delenv("GARMIN_FIT_DOWNLOAD_DIR", raising=False)
    monkeypatch.setattr(downloads_extra, "_resolve_download_dir", lambda _d: None)
    downloads_extra.configure(mock_garmin_client)
    return downloads_extra.register_tools(FastMCP("Test Downloads Extra"))


async def _call(app, name, args=None):
    result = await app.call_tool(name, args or {})
    return result[0][0].text


async def test_download_course_file_inline(app, mock_garmin_client):
    mock_garmin_client.download_course.return_value = b"<gpx/>"
    result = json.loads(await _call(app, "download_course_file", {"course_id": 9}))
    assert result["filename"] == "course_9.gpx" and result["mime_type"] == "application/gpx+xml"
    assert base64.b64decode(result["content_base64"]) == b"<gpx/>"
    mock_garmin_client.download_course.assert_called_once_with(9, "gpx")
    assert "gpx or fit" in await _call(app, "download_course_file", {"course_id": 9, "file_format": "kml"})


async def test_save_needs_a_download_dir(app, mock_garmin_client):
    mock_garmin_client.download_course.return_value = b"FIT"
    assert "No download directory" in await _call(app, "download_course_file", {"course_id": 9, "file_format": "fit", "save": True})


async def test_save_writes_the_file(app, mock_garmin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(downloads_extra, "_resolve_download_dir", lambda _d: str(tmp_path))
    mock_garmin_client.download_course.return_value = b"FIT"
    result = json.loads(await _call(app, "download_course_file", {"course_id": 9, "file_format": "fit", "save": True}))
    assert (tmp_path / "course_9.fit").read_bytes() == b"FIT" and result["bytes"] == 3


async def test_large_file_is_not_inlined(app, mock_garmin_client, monkeypatch):
    monkeypatch.setattr(downloads_extra, "_MAX_INLINE_BYTES", 4)
    mock_garmin_client.download_course.return_value = b"12345"
    assert "save=true" in await _call(app, "download_course_file", {"course_id": 9})


async def test_download_health_snapshot_file(app, mock_garmin_client):
    mock_garmin_client.download_health_snapshot.return_value = b"PK"
    mock_garmin_client.download_health_snapshot_session.return_value = b"FIT"
    day = json.loads(await _call(app, "download_health_snapshot_file", {"date": DAY}))
    assert day["filename"] == f"health_snapshot_{DAY}.zip"
    one = json.loads(await _call(app, "download_health_snapshot_file", {"date": DAY, "snapshot_id": "abcd1234-ef"}))
    assert one["filename"].endswith(".fit")
    mock_garmin_client.download_health_snapshot_session.assert_called_once_with(DAY, "abcd1234-ef")


async def test_request_and_download_report(app, mock_garmin_client):
    mock_garmin_client.request_report.return_value = {"reportId": "r1"}
    result = json.loads(await _call(app, "request_report", {"category": "bloodPressure", "start_date": "2026-10-01",
                                                            "end_date": DAY, "options": '{"reportSubCategory": "FOUR_WEEKS"}'}))
    assert result["report"]["reportId"] == "r1"
    mock_garmin_client.request_report.assert_called_once_with("bloodPressure", "2026-10-01", DAY,
                                                             {"reportSubCategory": "FOUR_WEEKS"}, "en-US")
    mock_garmin_client.get_report_status.return_value = {"progress": {"status": "IN_PROGRESS"}}
    assert json.loads(await _call(app, "download_report", {"report_id": "r1"}))["status"] == "not_ready"
    mock_garmin_client.download_report.assert_not_called()
    mock_garmin_client.get_report_status.return_value = {"progress": {"status": "READY"}}
    mock_garmin_client.download_report.return_value = b"%PDF"
    pdf = json.loads(await _call(app, "download_report", {"report_id": "r1"}))
    assert pdf["mime_type"] == "application/pdf"


async def test_request_report_validation_and_error(app, mock_garmin_client):
    assert "category" in await _call(app, "request_report", {"category": "blood-pressure", "start_date": DAY, "end_date": DAY})
    assert "locale" in await _call(app, "request_report", {"category": "bloodPressure", "start_date": DAY, "end_date": DAY, "locale": "nl"})
    mock_garmin_client.request_report.side_effect = GarminConnectConnectionError("API Error 400 - bad")
    result = json.loads(await _call(app, "request_report", {"category": "bloodPressure", "start_date": DAY, "end_date": DAY}))
    assert result["upstream_status"] == 400
