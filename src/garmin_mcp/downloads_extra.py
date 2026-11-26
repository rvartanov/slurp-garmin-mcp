"""
File downloads (Slurp garmin-mcp): courses as GPX/FIT, Health Snapshot
ZIP/FIT files and PDF report exports.

Files come back base64-encoded in the result by default, so remote clients
(claude.ai connectors) receive them; save=true writes them to the server's
download directory instead (GARMIN_FIT_DOWNLOAD_DIR or set_fit_download_dir,
on HTTP the default directory under the state directory), like
download_activity_file. Fork-specific module.
"""
import base64
import json
import os
import re
from typing import Any, Optional
from urllib.parse import quote

from garmin_mcp import local_files
from garmin_mcp.activity_analysis import _resolve_download_dir
from garmin_mcp.health_extra import _date, _positive, _range
from garmin_mcp.race_events import _json_object
from garmin_mcp.write_errors import WriteTracker

# The garmin_client will be set by the main file
garmin_client = None

_MAX_INLINE_BYTES = 5 * 1024 * 1024
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# Garmin's report ids are base64 text (letters, digits, + / =). garminconnect
# 0.3.20 only accepts [A-Za-z0-9_-] and so refuses every real id; the two
# report endpoints are therefore called directly with the id URL-encoded.
_REPORT_ID_RE = re.compile(r"^[A-Za-z0-9+/=_-]{1,2048}$")
_REPORT_URL = "/reportexport-service/export"
_MIME = {".gpx": "application/gpx+xml", ".fit": "application/vnd.ant.fit",
         ".zip": "application/zip", ".pdf": "application/pdf"}


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _deliver(data: Any, filename: str, save: bool) -> str:
    """Return the file inline as base64, or save it to the download directory."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, (bytes, bytearray)) or not data:
        return f"Garmin returned no file for {filename}."
    suffix = os.path.splitext(filename)[1].lower()
    if save:
        directory = _resolve_download_dir(None)
        if not directory:
            return ("No download directory is configured; set GARMIN_FIT_DOWNLOAD_DIR or call "
                    "set_fit_download_dir, or call again without save to get the file inline.")
        path = local_files.write_file(directory, filename, bytes(data))
        return _dump({"status": "success", "saved_to": path, "bytes": len(data)})
    if len(data) > _MAX_INLINE_BYTES:
        return (f"{filename} is {len(data) // 1024} KB, more than the 5 MB that is returned inline; "
                "call again with save=true to store it in the server's download directory.")
    return _dump({"status": "success", "filename": filename, "mime_type": _MIME.get(suffix, "application/octet-stream"),
                  "bytes": len(data), "content_base64": base64.b64encode(bytes(data)).decode("ascii")})


def register_tools(app):
    """Register the download tools with the MCP server app"""

    @app.tool()
    async def download_course_file(course_id: int, file_format: str = "gpx", save: bool = False) -> str:
        """Download a course as a GPX or FIT file

        Args:
            course_id: Garmin course id
            file_format: gpx or fit (default gpx)
            save: true to store it in the server's download directory instead
                of returning it base64-encoded
        """
        try:
            course = _positive(course_id, "course_id")
            fmt = (file_format or "").strip().lower()
            if fmt not in ("gpx", "fit"):
                return "file_format must be gpx or fit"
            return _deliver(garmin_client.download_course(course, fmt), f"course_{course}.{fmt}", save)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error downloading course: {str(e)}"

    @app.tool()
    async def download_health_snapshot_file(date: str, snapshot_id: Optional[str] = None, save: bool = False) -> str:
        """Download Health Snapshot data: a day's ZIP, or one session as a FIT file

        Args:
            date: Day of the snapshot(s), YYYY-MM-DD
            snapshot_id: Session uuid for one session's FIT file (from
                get_health_day kind=health_snapshots); omit for the day's ZIP
            save: true to store it in the server's download directory instead
                of returning it base64-encoded
        """
        try:
            day = _date(date, "date")
            if snapshot_id:
                if not _ID_RE.match(snapshot_id):
                    return "snapshot_id must be the snapshot's uuid"
                data = garmin_client.download_health_snapshot_session(day, snapshot_id)
                return _deliver(data, f"health_snapshot_{day}_{snapshot_id[:8]}.fit", save)
            return _deliver(garmin_client.download_health_snapshot(day), f"health_snapshot_{day}.zip", save)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error downloading health snapshot: {str(e)}"

    @app.tool()
    async def request_report(category: str, start_date: str, end_date: str,
                             options: str = "", locale: str = "en-US") -> str:
        """Start a PDF report export in Garmin Connect (fetch it with download_report)

        Categories the web app uses: bloodPressure (options e.g.
        {"reportSubCategory": "FourWeeks", "reportFormat": "PDF",
        "contentToSkip": []}; sub categories Daily, SevenDays, FourWeeks,
        Yearly) and wellnessactivity (options {"supplementalId": "<snapshot
        uuid>"}).

        Args:
            category: Report category key, e.g. bloodPressure
            start_date: First day, YYYY-MM-DD
            end_date: Last day, YYYY-MM-DD
            options: JSON object with report options (see above)
            locale: Report language, e.g. en-US or nl-NL
        """
        tracker = WriteTracker("request_report", "Error requesting report")
        try:
            if not re.fullmatch(r"[A-Za-z]+", category or ""):
                return "category must be a report category key such as bloodPressure"
            first, last = _range(start_date, end_date)
            opts = _json_object(options, "options") if options else None
            if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", locale or ""):
                return "locale must look like en-US or nl-NL"
            tracker.sending()
            result = garmin_client.request_report(category, first, last, opts, locale)
            tracker.committed()
            return _dump({"status": "success", "report": result,
                          "next": "call download_report with the reportId once Garmin has built it"})
        except ValueError as e:
            return str(e)
        except Exception as e:
            return tracker.error(e)

    @app.tool()
    async def download_report(report_id: str, save: bool = False) -> str:
        """Download a PDF report started with request_report, or report its progress while it is being built

        Args:
            report_id: The reportId from request_report
            save: true to store the PDF in the server's download directory
                instead of returning it base64-encoded
        """
        try:
            if not _REPORT_ID_RE.match(str(report_id or "")):
                return "report_id must be the reportId from request_report"
            encoded = quote(str(report_id), safe="")
            status = garmin_client.connectapi(f"{_REPORT_URL}/reportStatus/{encoded}")
            if not isinstance(status, dict) or not isinstance(status.get("progress"), dict):
                return f"Unexpected report status from Garmin: {str(status)[:300]}"
            state = status["progress"].get("status")
            if state in ("FAILED", "ERROR"):
                return _dump({"status": "failed", "progress": status["progress"]})
            if state != "READY":
                return _dump({"status": "not_ready", "progress": status["progress"],
                              "message": "Garmin is still building the report; try again shortly."})
            pdf = garmin_client.download(f"{_REPORT_URL}/reportContent/{encoded}")
            if not isinstance(pdf, (bytes, bytearray)) or not bytes(pdf).startswith(b"%PDF"):
                return "Garmin did not return a PDF for this report."
            return _deliver(pdf, "report.pdf", save)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error downloading report: {str(e)}"

    return app
