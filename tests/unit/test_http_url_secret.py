"""URL-secret mode and *_FILE variants for the HTTP transports.

GARMIN_MCP_URL_SECRET serves the MCP endpoints only under ``/<secret>/...``,
for clients that cannot send an Authorization header (custom connectors that
only take a URL). GARMIN_MCP_HTTP_TOKEN_FILE / GARMIN_MCP_URL_SECRET_FILE read
the value from a file (systemd credentials, Docker secrets).
"""

from unittest.mock import Mock

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

import garmin_mcp
from garmin_mcp import http_auth

SECRET = "c0ffee-url-secret-0123456789abcdef"
TOKEN = "s3cret-token"

_ENV = (
    "GARMIN_MCP_HOST",
    "GARMIN_MCP_PORT",
    "GARMIN_MCP_HTTP_TOKEN",
    "GARMIN_MCP_HTTP_TOKEN_FILE",
    "GARMIN_MCP_URL_SECRET",
    "GARMIN_MCP_URL_SECRET_FILE",
    "GARMIN_MCP_REQUIRE_AUTH",
    "GARMIN_MCP_STATELESS_HTTP",
    "GARMIN_ENABLED_TOOLS",
    "GARMIN_DISABLED_TOOLS",
)


@pytest.fixture
def http_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(garmin_mcp, "init_api", lambda _email, _password: Mock())
    return monkeypatch


def _run_main_and_build(monkeypatch, transport="streamable-http"):
    built = {}

    def capture_run(self, **_kwargs):
        built["app"] = (
            self.streamable_http_app() if transport == "streamable-http" else self.sse_app()
        )

    monkeypatch.setenv("GARMIN_MCP_TRANSPORT", transport)
    monkeypatch.setattr(FastMCP, "run", capture_run)
    garmin_mcp.main()
    return built["app"]


def test_mcp_is_only_reachable_under_the_secret_path(http_env):
    http_env.setenv("GARMIN_MCP_URL_SECRET", SECRET)
    app = _run_main_and_build(http_env)

    with TestClient(app) as client:
        bare = client.post("/mcp", json={})
        wrong = client.post(f"/{SECRET}x/mcp", json={})
        prefix_only = client.post(f"/{SECRET[:-1]}/mcp", json={})
        secret_alone = client.get(f"/{SECRET}")
        root = client.get("/")
        with_secret = client.post(f"/{SECRET}/mcp", json={})
        probe = client.get("/healthz")
        ready = client.get("/readyz")
        hidden_probe = client.get(f"/{SECRET}/healthz")

    for response in (bare, wrong, prefix_only, root):
        assert response.status_code == 404
        # A 404 must not reveal that a secret path exists.
        assert SECRET not in response.text
    # The handshake rejects an empty body, but the gate let it through.
    assert with_secret.status_code not in (401, 404)
    assert secret_alone.status_code == 404
    assert probe.status_code == 200 and probe.text == "ok"
    assert ready.status_code in (200, 503)
    assert hidden_probe.status_code == 200


def test_sse_under_the_secret_path(http_env):
    http_env.setenv("GARMIN_MCP_URL_SECRET", SECRET)
    app = _run_main_and_build(http_env, "sse")

    with TestClient(app) as client:
        bare = client.post("/messages/", json={})
        with_secret = client.post(f"/{SECRET}/messages/", json={})

    assert bare.status_code == 404
    assert with_secret.status_code != 404


def test_url_secret_and_bearer_token_combine(http_env):
    http_env.setenv("GARMIN_MCP_URL_SECRET", SECRET)
    http_env.setenv("GARMIN_MCP_HTTP_TOKEN", TOKEN)
    app = _run_main_and_build(http_env)

    with TestClient(app) as client:
        no_token = client.post(f"/{SECRET}/mcp", json={})
        token_wrong_path = client.post(
            "/mcp", json={}, headers={"Authorization": f"Bearer {TOKEN}"}
        )
        both = client.post(
            f"/{SECRET}/mcp", json={}, headers={"Authorization": f"Bearer {TOKEN}"}
        )

    assert no_token.status_code == 401
    assert token_wrong_path.status_code == 404
    assert both.status_code not in (401, 404)


def test_gate_sets_root_path_and_strips_the_prefix():
    seen = {}

    async def inner(scope, receive, send):
        seen.update(path=scope["path"], root_path=scope["root_path"], raw=scope["raw_path"])

    gate = http_auth.UrlSecretGate(inner, SECRET)
    scope = {
        "type": "http",
        "path": f"/{SECRET}/mcp",
        "raw_path": f"/{SECRET}/mcp".encode(),
        "root_path": "",
        "headers": [],
    }

    import asyncio

    asyncio.run(gate(scope, None, None))

    assert seen == {"path": "/mcp", "root_path": f"/{SECRET}", "raw": b"/mcp"}
    # The caller's scope is left untouched.
    assert scope["path"] == f"/{SECRET}/mcp"


def test_secret_is_read_from_a_file(http_env, tmp_path):
    secret_file = tmp_path / "url-secret"
    secret_file.write_text(SECRET + "\n")
    http_env.setenv("GARMIN_MCP_URL_SECRET_FILE", str(secret_file))
    app = _run_main_and_build(http_env)

    with TestClient(app) as client:
        assert client.post("/mcp", json={}).status_code == 404
        assert client.post(f"/{SECRET}/mcp", json={}).status_code != 404


def test_token_is_read_from_a_file(http_env, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN + "\n")
    http_env.setenv("GARMIN_MCP_HTTP_TOKEN_FILE", str(token_file))
    app = _run_main_and_build(http_env)

    with TestClient(app) as client:
        anonymous = client.post("/mcp", json={})
        with_token = client.post("/mcp", json={}, headers={"Authorization": f"Bearer {TOKEN}"})

    assert anonymous.status_code == 401
    assert with_token.status_code != 401


@pytest.mark.parametrize("name", ["GARMIN_MCP_HTTP_TOKEN", "GARMIN_MCP_URL_SECRET"])
def test_value_and_file_together_are_rejected(http_env, tmp_path, capsys, name):
    secret_file = tmp_path / "secret"
    secret_file.write_text(SECRET)
    http_env.setenv(name, SECRET)
    http_env.setenv(f"{name}_FILE", str(secret_file))

    with pytest.raises(SystemExit) as excinfo:
        _run_main_and_build(http_env)

    assert excinfo.value.code == 1
    assert f"{name}_FILE" in capsys.readouterr().err


def test_unreadable_file_is_a_startup_error(http_env, tmp_path, capsys):
    http_env.setenv("GARMIN_MCP_URL_SECRET_FILE", str(tmp_path / "missing"))

    with pytest.raises(SystemExit) as excinfo:
        _run_main_and_build(http_env)

    assert excinfo.value.code == 1
    assert "GARMIN_MCP_URL_SECRET_FILE" in capsys.readouterr().err


@pytest.mark.parametrize("secret", ["short", "has/slash-0123456789abcdef", "spa ce-0123456789abcdef", "healthz"])
def test_unusable_url_secrets_are_rejected(http_env, capsys, secret):
    http_env.setenv("GARMIN_MCP_URL_SECRET", secret)

    with pytest.raises(SystemExit) as excinfo:
        _run_main_and_build(http_env)

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "GARMIN_MCP_URL_SECRET" in err
    # Never echo the secret itself.
    assert secret not in err


def test_startup_log_does_not_print_the_secret(http_env, capsys):
    http_env.setenv("GARMIN_MCP_URL_SECRET", SECRET)
    http_env.setenv("GARMIN_MCP_HOST", "0.0.0.0")
    _run_main_and_build(http_env)

    captured = capsys.readouterr()
    assert SECRET not in captured.err and SECRET not in captured.out
    assert "/<secret>/" in captured.err
    # A URL secret counts as protection: no exposure warning.
    assert "WARNING" not in captured.err


def test_require_auth_refuses_to_start_unprotected(http_env, capsys):
    http_env.setenv("GARMIN_MCP_REQUIRE_AUTH", "true")

    with pytest.raises(SystemExit) as excinfo:
        _run_main_and_build(http_env)

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "GARMIN_MCP_HTTP_TOKEN" in err and "GARMIN_MCP_URL_SECRET" in err


@pytest.mark.parametrize("name", ["GARMIN_MCP_HTTP_TOKEN", "GARMIN_MCP_URL_SECRET"])
def test_require_auth_is_satisfied_by_either_gate(http_env, name):
    http_env.setenv("GARMIN_MCP_REQUIRE_AUTH", "true")
    http_env.setenv(name, SECRET)

    assert _run_main_and_build(http_env) is not None


def test_require_auth_does_not_affect_stdio(http_env):
    http_env.setenv("GARMIN_MCP_REQUIRE_AUTH", "true")
    http_env.setenv("GARMIN_MCP_TRANSPORT", "stdio")
    ran = {}
    http_env.setattr(FastMCP, "run", lambda self, **kwargs: ran.update(kwargs))

    garmin_mcp.main()

    assert ran == {"transport": "stdio"}


@pytest.mark.parametrize("flag, expected", [("--help", "GARMIN_MCP_URL_SECRET"), ("--version", "slurp-garmin-mcp")])
def test_help_and_version_exit_before_starting(monkeypatch, capsys, flag, expected):
    monkeypatch.setattr("sys.argv", ["garmin-mcp", flag])
    monkeypatch.setattr(garmin_mcp, "init_api", lambda *_: pytest.fail("must not log in"))

    with pytest.raises(SystemExit) as excinfo:
        garmin_mcp.main()

    assert excinfo.value.code == 0
    assert expected in capsys.readouterr().out
