"""Shared-secret auth for the HTTP transports (#339).

GARMIN_MCP_TRANSPORT=streamable-http|sse serves full read/write access to the
Garmin account. Two gates protect it; they can be combined:

* GARMIN_MCP_HTTP_TOKEN: every request must carry
  ``Authorization: Bearer <token>``.
* GARMIN_MCP_URL_SECRET: the MCP endpoints only exist under ``/<secret>/...``
  (``/<secret>/mcp``); every other path is a 404. For clients that take a URL
  but cannot send their own Authorization header.

Either value may come from a file instead (``..._FILE``), for systemd
credentials and Docker secrets. The liveness and readiness probes stay open
because they reveal nothing beyond "up" and "logged in".

FastMCP builds its Starlette app inside streamable_http_app() / sse_app() and
offers no middleware hook short of the full OAuth resource-server setup (its
AuthSettings require an issuer URL), so the built app is wrapped instead.
"""

import hmac
import ipaddress
import logging
import os

from starlette.responses import JSONResponse

# Probes carry no Garmin data and are polled by orchestrators that usually
# cannot attach headers.
UNAUTHENTICATED_PATHS = frozenset({"/healthz", "/readyz"})


# A URL secret ends up in a path segment, so keep it to characters that never
# need escaping, and long enough that it cannot be guessed.
URL_SECRET_MIN_LENGTH = 16
_URL_SECRET_ALPHABET = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
)


def _read_env_or_file(name: str) -> str | None:
    """Return $NAME, or the contents of the file named by $NAME_FILE.

    None when unset or blank. Raises ValueError when both are set or the file
    cannot be read.
    """
    value = os.getenv(name, "").strip()
    file_path = os.getenv(f"{name}_FILE", "").strip()
    if value and file_path:
        raise ValueError(f"Must only provide one of {name} and {name}_FILE, got both")
    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                value = fh.read().strip()
        except OSError as exc:
            raise ValueError(
                f"Cannot read {name}_FILE '{file_path}': {exc.strerror or exc}"
            ) from exc
        if not value:
            raise ValueError(f"{name}_FILE '{file_path}' is empty")
    return value or None


def resolve_http_token() -> str | None:
    """Read GARMIN_MCP_HTTP_TOKEN(_FILE); None when unset or blank."""
    return _read_env_or_file("GARMIN_MCP_HTTP_TOKEN")


def resolve_url_secret() -> str | None:
    """Read GARMIN_MCP_URL_SECRET(_FILE); None when unset or blank.

    Raises ValueError (without echoing the value) when it cannot serve as a
    path segment or is too short to be a secret.
    """
    secret = _read_env_or_file("GARMIN_MCP_URL_SECRET")
    if secret is None:
        return None
    if len(secret) < URL_SECRET_MIN_LENGTH:
        raise ValueError(
            f"GARMIN_MCP_URL_SECRET must be at least {URL_SECRET_MIN_LENGTH} "
            "characters (generate one with `openssl rand -hex 32`)"
        )
    if not _URL_SECRET_ALPHABET.issuperset(secret):
        raise ValueError(
            "GARMIN_MCP_URL_SECRET may only contain letters, digits and '-._~' "
            "(generate one with `openssl rand -hex 32`)"
        )
    return secret


def require_auth() -> bool:
    """Read GARMIN_MCP_REQUIRE_AUTH: refuse to serve HTTP without a gate."""
    return os.getenv("GARMIN_MCP_REQUIRE_AUTH", "").strip().lower() in ("true", "1", "yes")


def is_loopback(host: str) -> bool:
    """True when the bind address only accepts connections from this machine."""
    host = host.strip().strip("[]").lower()
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class BearerTokenGate:
    """ASGI wrapper that rejects HTTP requests without the shared bearer token."""

    def __init__(self, app, token: str):
        self._app = app
        self._token = token.encode("utf-8")

    def authorized(self, scope) -> bool:
        for name, value in scope.get("headers") or ():
            if name.lower() != b"authorization":
                continue
            scheme, _, credential = value.strip().partition(b" ")
            return scheme.lower() == b"bearer" and hmac.compare_digest(
                credential.strip(), self._token
            )
        return False

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope.get("path") not in UNAUTHENTICATED_PATHS
            and not self.authorized(scope)
        ):
            response = JSONResponse(
                {
                    "error": "unauthorized",
                    "detail": "Send 'Authorization: Bearer <GARMIN_MCP_HTTP_TOKEN>'.",
                },
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="garmin-mcp"'},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)


class UrlSecretGate:
    """ASGI wrapper that serves the app only under ``/<secret>/``.

    A matching request is forwarded with the prefix moved from ``path`` to
    ``root_path``, so the wrapped app routes ``/mcp`` as usual and still builds
    correct absolute URLs (the SSE transport advertises its message endpoint
    from ``root_path``). Anything else is a plain 404 that does not hint at a
    secret path. The probes answer with and without the prefix.
    """

    def __init__(self, app, secret: str):
        self._app = app
        self._secret = secret.encode("utf-8")
        self._prefix = "/" + secret

    def _inner_path(self, path: str) -> str | None:
        """The path behind the secret prefix, or None when it does not match."""
        segment, separator, rest = path[1:].partition("/")
        # Compare the whole first segment in constant time; never startswith().
        if not hmac.compare_digest(segment.encode("utf-8"), self._secret):
            return None
        return "/" + rest if separator else None

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path in UNAUTHENTICATED_PATHS:
            await self._app(scope, receive, send)
            return
        inner_path = self._inner_path(path) if path.startswith("/") else None
        if inner_path is None:
            if scope["type"] == "http":
                response = JSONResponse({"error": "not_found"}, status_code=404)
                await response(scope, receive, send)
            return
        forwarded = dict(scope)
        forwarded["path"] = inner_path
        forwarded["root_path"] = scope.get("root_path", "") + self._prefix
        raw_path = scope.get("raw_path")
        if raw_path is not None:
            forwarded["raw_path"] = raw_path[len(self._prefix.encode("utf-8")):]
        await self._app(forwarded, receive, send)


class _RedactUrlSecret(logging.Filter):
    """Keep the URL secret out of log lines (uvicorn's access log prints paths)."""

    def __init__(self, secret: str):
        super().__init__()
        self._secret = secret

    def _clean(self, value):
        return value.replace(self._secret, "<secret>") if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._clean(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._clean(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: self._clean(arg) for key, arg in record.args.items()}
        return True


def _wrap_http_apps(fastmcp, wrap) -> None:
    for builder_name in ("streamable_http_app", "sse_app"):
        builder = getattr(fastmcp, builder_name)

        def build(*args, _builder=builder, **kwargs):
            return wrap(_builder(*args, **kwargs))

        setattr(fastmcp, builder_name, build)


def install_http_bearer_auth(fastmcp, token: str) -> None:
    """Make fastmcp's HTTP apps require the bearer token on every request."""
    _wrap_http_apps(fastmcp, lambda app: BearerTokenGate(app, token))


def install_url_secret(fastmcp, secret: str) -> None:
    """Make fastmcp's HTTP apps reachable only under ``/<secret>/``.

    Install after the bearer gate so this one sits outermost: a wrong path is
    a 404 before the token is even looked at.
    """
    _wrap_http_apps(fastmcp, lambda app: UrlSecretGate(app, secret))
    redact = _RedactUrlSecret(secret)
    for logger_name in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(logger_name).addFilter(redact)


def exposure_warning(host: str, port: int) -> str:
    """Startup warning for an HTTP bind beyond loopback with no token."""
    return (
        f"WARNING: GARMIN_MCP_HOST={host} accepts connections from other machines "
        f"and neither GARMIN_MCP_HTTP_TOKEN nor GARMIN_MCP_URL_SECRET is set: "
        f"anyone who can reach port {port} has full read/write access to the "
        "Garmin account. Set GARMIN_MCP_HTTP_TOKEN or GARMIN_MCP_URL_SECRET, or "
        "front the server with an authenticating proxy."
    )
