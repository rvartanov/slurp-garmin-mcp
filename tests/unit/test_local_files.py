"""Where tools may read and write local files (local_files and its callers)."""
import io
import json
import os
import zipfile

import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import activity_analysis, courses, downloads_extra, local_files

ACTIVITY_ID = 1234567


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in ("GARMIN_FIT_DOWNLOAD_DIR", "GARMIN_MCP_TRANSPORT", "STATE_DIRECTORY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("GARMIN_FIT_CONFIG", str(tmp_path / "fit_config.json"))


@pytest.fixture
def root(tmp_path, monkeypatch):
    directory = tmp_path / "downloads"
    directory.mkdir()
    monkeypatch.setenv("GARMIN_FIT_DOWNLOAD_DIR", str(directory))
    return directory


def _text(result):
    return result[0][0].text


# --- the rule -------------------------------------------------------------

def test_stdio_without_env_keeps_any_directory(tmp_path):
    assert local_files.allowed_root() is None
    assert local_files.check_dir(str(tmp_path / "anywhere")) == str(tmp_path / "anywhere")


def test_env_root_accepts_inside_and_relative(root):
    assert local_files.check_dir(str(root / "sub")) == str(root / "sub")
    assert local_files.check_dir("sub") == str(root / "sub")


def test_env_root_rejects_outside_and_dotdot(root, tmp_path):
    with pytest.raises(ValueError, match="inside the download directory"):
        local_files.check_dir(str(tmp_path / "elsewhere"))
    with pytest.raises(ValueError):
        local_files.check_dir(str(root / ".." / "elsewhere"))
    with pytest.raises(ValueError):
        local_files.check_dir("/etc")


def test_env_root_rejects_symlink_out(root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(ValueError):
        local_files.check_dir(str(root / "link"))


def test_http_without_env_uses_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_MCP_TRANSPORT", "streamable-http")
    expected = tmp_path / "state" / "slurp-garmin-mcp" / "downloads"
    assert local_files.allowed_root() == str(expected)
    with pytest.raises(ValueError):
        local_files.check_dir(str(tmp_path))
    monkeypatch.setenv("STATE_DIRECTORY", str(tmp_path / "svc"))
    assert local_files.allowed_root() == str(tmp_path / "svc" / "downloads")


def test_write_file_does_not_follow_a_symlink(tmp_path):
    victim = tmp_path / "victim"
    victim.write_bytes(b"keep")
    (tmp_path / "1.fit").symlink_to(victim)
    with pytest.raises(OSError):
        local_files.write_file(str(tmp_path), "1.fit", b"new")
    assert victim.read_bytes() == b"keep"
    with pytest.raises(ValueError):
        local_files.write_file(str(tmp_path), "../x.fit", b"new")


def test_check_input_file(root, tmp_path):
    inside = root / "route.gpx"
    inside.write_text("<gpx/>")
    assert local_files.check_input_file("route.gpx", ".gpx") == str(inside)

    secret = tmp_path / "secret.gpx"
    secret.write_text("x")
    (root / "out.gpx").symlink_to(secret)
    with pytest.raises(ValueError, match="inside the download directory"):
        local_files.check_input_file(str(root / "out.gpx"), ".gpx")
    with pytest.raises(ValueError):
        local_files.check_input_file(str(secret), ".gpx")

    other = root / "notes.txt"
    other.write_text("x")
    (root / "disguised.gpx").symlink_to(other)
    with pytest.raises(ValueError, match="link to another file type"):
        local_files.check_input_file(str(root / "disguised.gpx"), ".gpx")
    with pytest.raises(ValueError, match="only .gpx"):
        local_files.check_input_file(str(other), ".gpx")
    (root / "dir.gpx").mkdir()
    with pytest.raises(FileNotFoundError):
        local_files.check_input_file(str(root / "dir.gpx"), ".gpx")


def test_read_file_caps_size(tmp_path):
    big = tmp_path / "big.gpx"
    big.write_bytes(b"x" * 11)
    assert local_files.read_file(str(big), limit=11) == b"x" * 11
    with pytest.raises(ValueError, match="larger"):
        local_files.read_file(str(big), limit=10)


# --- the tools ------------------------------------------------------------

def _analysis_app(client):
    activity_analysis.configure(client)
    return activity_analysis.register_tools(FastMCP("t"))


def _fit_zip(payload):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.fit", payload)
    return buf.getvalue()


async def test_download_activity_file_rejects_output_dir_outside_root(root, tmp_path, mock_garmin_client):
    app = _analysis_app(mock_garmin_client)
    text = _text(await app.call_tool(
        "download_activity_file", {"activity_id": ACTIVITY_ID, "output_dir": str(tmp_path / "x")}))
    assert "inside the download directory" in text
    mock_garmin_client.download_activity.assert_not_called()
    assert not (tmp_path / "x").exists()


async def test_download_activity_file_on_http_saves_in_default_dir(monkeypatch, tmp_path, mock_garmin_client):
    monkeypatch.setenv("GARMIN_MCP_TRANSPORT", "streamable-http")
    mock_garmin_client.download_activity.return_value = _fit_zip(b"\x0e\x10FIT")
    app = _analysis_app(mock_garmin_client)
    data = json.loads(_text(await app.call_tool("download_activity_file", {"activity_id": ACTIVITY_ID})))
    expected = tmp_path / "state" / "slurp-garmin-mcp" / "downloads" / f"{ACTIVITY_ID}.fit"
    assert data["file_path"] == str(expected) and expected.read_bytes() == b"\x0e\x10FIT"


async def test_http_ignores_a_saved_directory_outside_root(monkeypatch, tmp_path, mock_garmin_client):
    monkeypatch.setenv("GARMIN_MCP_TRANSPORT", "streamable-http")
    (tmp_path / "fit_config.json").write_text(json.dumps({"download_dir": str(tmp_path / "old")}))
    assert activity_analysis._resolve_download_dir(None) == local_files.default_download_dir()


async def test_set_fit_download_dir_only_on_stdio(monkeypatch, root, tmp_path, mock_garmin_client):
    app = _analysis_app(mock_garmin_client)
    assert "set_fit_download_dir" in {t.name for t in await app.list_tools()}
    assert "inside the download directory" in _text(
        await app.call_tool("set_fit_download_dir", {"path": str(tmp_path / "elsewhere")}))
    assert not (tmp_path / "fit_config.json").exists()
    assert json.loads(_text(await app.call_tool("set_fit_download_dir", {"path": "sub"})))["download_dir"] == str(root / "sub")

    monkeypatch.setenv("GARMIN_MCP_TRANSPORT", "streamable-http")
    http_app = _analysis_app(mock_garmin_client)
    names = {t.name for t in await http_app.list_tools()}
    assert "set_fit_download_dir" not in names and "download_activity_file" in names


async def test_download_course_gpx_rejects_path_outside_root(root, tmp_path, mock_garmin_client):
    courses.configure(mock_garmin_client)
    app = courses.register_tools(FastMCP("t"))
    mock_garmin_client.client.connectapi.return_value = {"geoPoints": [{"latitude": 1.0, "longitude": 2.0}]}
    text = _text(await app.call_tool("download_course_gpx", {"course_id": 7, "output_path": str(tmp_path / "x.gpx")}))
    assert "inside the download directory" in text and not (tmp_path / "x.gpx").exists()
    data = json.loads(_text(await app.call_tool("download_course_gpx", {"course_id": 7, "output_path": "c.gpx"})))
    assert data["gpx_path"] == str(root / "c.gpx") and (root / "c.gpx").is_file()


async def test_upload_course_rejects_file_outside_root(root, tmp_path, mock_garmin_client):
    courses.configure(mock_garmin_client)
    app = courses.register_tools(FastMCP("t"))
    outside = tmp_path / "route.gpx"
    outside.write_text("<gpx/>")
    (root / "route.gpx").symlink_to(outside)
    for path in (str(outside), str(root / "route.gpx")):
        assert "inside the download directory" in _text(await app.call_tool("upload_course", {"gpx_path": path}))
    mock_garmin_client.client.post.assert_not_called()


async def test_deliver_save_on_http_uses_default_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_MCP_TRANSPORT", "sse")
    data = json.loads(downloads_extra._deliver(b"FIT", "course_9.fit", save=True))
    expected = tmp_path / "state" / "slurp-garmin-mcp" / "downloads" / "course_9.fit"
    assert data["saved_to"] == str(expected) and expected.read_bytes() == b"FIT"


# --- unpacking downloads ----------------------------------------------------

def test_extract_fit_bytes_caps_zip_and_gzip(monkeypatch):
    import gzip

    monkeypatch.setattr(local_files, "MAX_FILE_BYTES", 100)
    assert activity_analysis._extract_fit_bytes(_fit_zip(b"x" * 100)) == b"x" * 100
    assert activity_analysis._extract_fit_bytes(gzip.compress(b"x" * 100)) == b"x" * 100
    with pytest.raises(ValueError, match="larger than"):
        activity_analysis._extract_fit_bytes(_fit_zip(b"x" * 101))
    with pytest.raises(ValueError, match="larger than"):
        activity_analysis._extract_fit_bytes(gzip.compress(b"x" * 101))

