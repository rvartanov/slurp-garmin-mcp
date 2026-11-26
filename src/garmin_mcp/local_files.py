"""
Where tools may read and write files on the server (Slurp garmin-mcp).

Tools that save downloads (download_activity_file, download_course_gpx, the
save=true downloads) or read a local file (upload_course) take paths from
the AI client. The rule for those paths:

- GARMIN_FIT_DOWNLOAD_DIR set: every path must resolve, symlinks included,
  to that directory or below it.
- Not set, HTTP transport: the same, with a default directory the server
  creates under its state directory (<state>/downloads).
- Not set, stdio: no restriction (the client runs as the local user anyway).

Fork-specific module.
"""
import os
import stat
from typing import Optional

# Largest file a tool reads, uploads or unpacks into memory.
MAX_FILE_BYTES = 25 * 1024 * 1024

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_BINARY = getattr(os, "O_BINARY", 0)


def http_transport() -> bool:
    """True when the server is configured for an HTTP transport."""
    return os.getenv("GARMIN_MCP_TRANSPORT", "stdio").strip().lower() != "stdio"


def state_dir() -> str:
    """The server's state directory.

    $STATE_DIRECTORY (set by systemd's StateDirectory=), else
    $XDG_STATE_HOME/slurp-garmin-mcp, else ~/.local/state/slurp-garmin-mcp.
    """
    systemd_dir = os.getenv("STATE_DIRECTORY", "").split(":")[0]
    if systemd_dir:
        return os.path.abspath(systemd_dir)
    base = os.getenv("XDG_STATE_HOME") or "~/.local/state"
    return os.path.abspath(os.path.join(os.path.expanduser(base), "slurp-garmin-mcp"))


def default_download_dir() -> str:
    """Download directory used on HTTP when GARMIN_FIT_DOWNLOAD_DIR is not set."""
    return os.path.join(state_dir(), "downloads")


def allowed_root() -> Optional[str]:
    """Real path that tool file paths must stay in, or None for no limit."""
    env_dir = os.getenv("GARMIN_FIT_DOWNLOAD_DIR")
    if env_dir:
        return os.path.realpath(os.path.expanduser(env_dir))
    if http_transport():
        return os.path.realpath(default_download_dir())
    return None


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives on Windows
        return False


def _absolute(path: str, root: Optional[str]) -> str:
    """Expand ~ and make path absolute; relative paths start at root if any."""
    expanded = os.path.expanduser(path)
    if root is not None and not os.path.isabs(expanded):
        expanded = os.path.join(root, expanded)
    return os.path.abspath(expanded)


def check_dir(path: str, what: str = "directory") -> str:
    """Return the directory to use for path, or raise ValueError when it is
    outside the allowed root. Under a root the real path is returned."""
    root = allowed_root()
    absolute = _absolute(path, root)
    if root is None:
        return absolute
    real = os.path.realpath(absolute)
    if not _inside(real, root):
        raise ValueError(f"{what} must be inside the download directory {root}")
    return real


def write_file(directory: str, filename: str, data: bytes) -> str:
    """Write data to directory/filename without following a symlink there."""
    if not filename or os.path.basename(filename) != filename or filename in (".", ".."):
        raise ValueError(f"invalid file name: {filename!r}")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _NOFOLLOW | _BINARY, 0o666)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
    return path


def check_input_file(path: str, suffix: str) -> str:
    """Resolve a file a tool should read: a regular file ending in suffix,
    inside the allowed root (if any) after resolving symlinks."""
    root = allowed_root()
    absolute = _absolute(path, root)
    if os.path.splitext(absolute)[1].lower() != suffix:
        ext = os.path.splitext(absolute)[1]
        raise ValueError(f"only {suffix} files are allowed, got: {ext or '(no extension)'}")
    real = os.path.realpath(absolute)
    if root is not None and not _inside(real, root):
        raise ValueError(f"the file must be inside the download directory {root}")
    if os.path.splitext(real)[1].lower() != suffix:
        raise ValueError(f"only {suffix} files are allowed (the path is a link to another file type)")
    if not os.path.isfile(real):
        raise FileNotFoundError(f"file not found: {real}")
    return real


def read_file(path: str, limit: int = MAX_FILE_BYTES) -> bytes:
    """Read a regular file of at most limit bytes, refusing a symlink."""
    fd = os.open(path, os.O_RDONLY | _NOFOLLOW | _BINARY)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError(f"not a regular file: {path}")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"file is larger than {limit // (1024 * 1024)} MB")
    return data
