"""GARMIN_MCP_ALLOWED_HOSTS / GARMIN_MCP_ALLOWED_ORIGINS.

On a loopback bind the MCP SDK turns on DNS-rebinding protection and only
accepts a loopback Host header. A tunnel such as Tailscale Funnel forwards the
public Host (``<machine>.<tailnet>.ts.net``), which the SDK answers with
421 Invalid Host header. These settings add the public names to the allowlist
without switching the protection off.
"""

from unittest.mock import Mock

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

import garmin_mcp
from garmin_mcp import http_auth

SECRET = "c0ffee-url-secret-0123456789abcdef"
PUBLIC = "luxor.example.ts.net"

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}

_ENV = (
    "GARMIN_MCP_HOST",
    "GARMIN_MCP_PORT",
    "GARMIN_MCP_HTTP_TOKEN",
    "GARMIN_MCP_HTTP_TOKEN_FILE",
    "GARMIN_MCP_URL_SECRET",
    "GARMIN_MCP_URL_SECRET_FILE",
    "GARMIN_MCP_REQUIRE_AUTH",
    "GARMIN_MCP_STATELESS_HTTP",
    "GARMIN_MCP_ALLOWED_HOSTS",
    "GARMIN_MCP_ALLOWED_ORIGINS",
    "GARMIN_ENABLED_TOOLS",
    "GARMIN_DISABLED_TOOLS",
)


@pytest.fixture
def http_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(garmin_mcp, "init_api", lambda _email, _password: Mock())
    monkeypatch.setenv("GARMIN_MCP_STATELESS_HTTP", "true")
    return monkeypatch


def _build(monkeypatch):
    built = {}

    def capture_run(self, **_kwargs):
        built["app"] = self.streamable_http_app()

    monkeypatch.setenv("GARMIN_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setattr(FastMCP, "run", capture_run)
    garmin_mcp.main()
    return built["app"]


@pytest.fixture
def serve(http_env):
    """Build the app and keep one TestClient (and its lifespan) open per test."""
    clients = []

    def _serve():
        client = TestClient(_build(http_env))
        client.__enter__()
        clients.append(client)
        return client

    yield _serve
    for client in clients:
        client.__exit__(None, None, None)


def _initialize(client, path="/mcp", **headers):
    return client.post(path, json=INITIALIZE, headers={**MCP_HEADERS, **headers})


def test_public_host_is_rejected_by_default(http_env, serve):
    # The SDK default on a loopback bind; the reason this setting exists.
    c = serve()

    assert _initialize(c, host="127.0.0.1:8000").status_code == 200
    assert _initialize(c, host=PUBLIC).status_code == 421


def test_allowed_host_is_accepted_with_and_without_port(http_env, serve):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", PUBLIC)
    c = serve()

    assert _initialize(c, host=PUBLIC).status_code == 200
    assert _initialize(c, host=f"{PUBLIC}:443").status_code == 200
    # Loopback stays allowed, so local probes and curl keep working.
    assert _initialize(c, host="127.0.0.1:8000").status_code == 200
    assert _initialize(c, host="localhost:8000").status_code == 200


def test_other_hosts_stay_rejected(http_env, serve):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", PUBLIC)
    c = serve()

    assert _initialize(c, host="evil.example").status_code == 421
    assert _initialize(c, host=f"{PUBLIC}.evil.example").status_code == 421
    assert _initialize(c, host=f"x{PUBLIC}").status_code == 421


def test_explicit_port_is_not_widened(http_env, serve):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", f"{PUBLIC}:8443")
    c = serve()

    assert _initialize(c, host=f"{PUBLIC}:8443").status_code == 200
    assert _initialize(c, host=PUBLIC).status_code == 421
    assert _initialize(c, host=f"{PUBLIC}:443").status_code == 421


def test_several_hosts_and_blank_entries(http_env, serve):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", f" {PUBLIC} , ,mcp.example.org,")
    c = serve()

    assert _initialize(c, host=PUBLIC).status_code == 200
    assert _initialize(c, host="mcp.example.org").status_code == 200


def test_works_together_with_the_url_secret(http_env, serve):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", PUBLIC)
    http_env.setenv("GARMIN_MCP_URL_SECRET", SECRET)
    c = serve()

    assert _initialize(c, f"/{SECRET}/mcp", host=PUBLIC).status_code == 200
    assert _initialize(c, "/mcp", host=PUBLIC).status_code == 404


def test_foreign_origin_is_rejected_unless_allowed(http_env, serve):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", PUBLIC)
    c = serve()

    # No Origin header (server-to-server clients) is fine.
    assert _initialize(c, host=PUBLIC).status_code == 200
    assert _initialize(c, host=PUBLIC, origin="https://claude.ai").status_code == 403


def test_allowed_origin_is_accepted(http_env, serve):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", PUBLIC)
    http_env.setenv("GARMIN_MCP_ALLOWED_ORIGINS", "https://claude.ai, https://claude.com")
    c = serve()

    assert _initialize(c, host=PUBLIC, origin="https://claude.ai").status_code == 200
    assert _initialize(c, host=PUBLIC, origin="https://claude.com").status_code == 200
    assert _initialize(c, host=PUBLIC, origin="https://evil.example").status_code == 403


def test_allowlist_also_protects_a_non_loopback_bind(http_env, serve):
    # The SDK leaves protection off for 0.0.0.0; setting an allowlist turns it on.
    http_env.setenv("GARMIN_MCP_HOST", "0.0.0.0")
    http_env.setenv("GARMIN_MCP_URL_SECRET", SECRET)
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", PUBLIC)
    c = serve()

    assert _initialize(c, f"/{SECRET}/mcp", host=PUBLIC).status_code == 200
    assert _initialize(c, f"/{SECRET}/mcp", host="evil.example").status_code == 421


@pytest.mark.parametrize(
    "value",
    ["*", "https://luxor.example.ts.net", "luxor.example.ts.net/mcp", "a b", "host:abc"],
)
def test_unusable_hosts_are_a_startup_error(http_env, capsys, value):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", value)

    with pytest.raises(SystemExit) as excinfo:
        _build(http_env)

    assert excinfo.value.code == 1
    assert "GARMIN_MCP_ALLOWED_HOSTS" in capsys.readouterr().err


@pytest.mark.parametrize(
    "value", ["*", "claude.ai", "https://claude.ai/", "https://claude.ai/x", "ftp://claude.ai"]
)
def test_unusable_origins_are_a_startup_error(http_env, capsys, value):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", PUBLIC)
    http_env.setenv("GARMIN_MCP_ALLOWED_ORIGINS", value)

    with pytest.raises(SystemExit) as excinfo:
        _build(http_env)

    assert excinfo.value.code == 1
    assert "GARMIN_MCP_ALLOWED_ORIGINS" in capsys.readouterr().err


def test_startup_log_names_the_allowed_hosts(http_env, capsys):
    http_env.setenv("GARMIN_MCP_ALLOWED_HOSTS", PUBLIC)
    _build(http_env)

    assert PUBLIC in capsys.readouterr().err


def test_unset_means_sdk_default(http_env):
    assert http_auth.resolve_transport_security() is None
