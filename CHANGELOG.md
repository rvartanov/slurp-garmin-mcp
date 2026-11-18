# Changelog

All notable changes to Slurp garmin-mcp. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `get_calendar_events` returns `event_id`, Garmin's id for the calendar
  event, in preparation for tools that change and delete events.

## [1.0.0] - 2026-11-18

First release as Slurp garmin-mcp, forked from
[Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) at commit
`a2ca5fc` (20 October 2026). Everything up to that commit is upstream's work;
its history is preserved in this repository.

### Added

- URL-secret mode: with `GARMIN_MCP_URL_SECRET` or
  `GARMIN_MCP_URL_SECRET_FILE` the MCP endpoints are served under
  `/<secret>/` only and every other path is a 404, except `/healthz` and
  `/readyz`. For clients that take a URL but cannot send an Authorization
  header. The secret is kept out of the server's log.
- `GARMIN_MCP_HTTP_TOKEN_FILE` next to `GARMIN_MCP_HTTP_TOKEN`, for systemd
  credentials and Docker secrets.
- `GARMIN_MCP_REQUIRE_AUTH`: refuse to start an HTTP transport without a
  bearer token or URL secret.
- `garmin-mcp --help` and `garmin-mcp --version`; `slurp-garmin-mcp` as an
  alias for `garmin-mcp`.
- systemd deployment: hardened system unit, user unit, `deploy/install.sh`
  and `deploy/uninstall.sh`, `deploy/env.example`.
- Reverse proxy examples for Caddy and nginx, and for Tailscale Funnel.
- Documentation in `docs/`, with `docs/tools.md` generated from the
  registered tools by `scripts/generate_tools_doc.py`.

### Changed

- Package name is `slurp-garmin-mcp` (was `garmin-mcp`); the Python module
  `garmin_mcp` and the commands `garmin-mcp` and `garmin-mcp-auth` are
  unchanged. The MCP server identifies itself as "Slurp garmin-mcp".
- Docker image: runs as a non-root user, serves streamable HTTP on port 8000
  by default (was stdio), requires a bearer token or URL secret, has a health
  check, keeps tokens in the `/data` volume (was `/root/.garminconnect`) and
  no longer contains the tests. Set `GARMIN_MCP_TRANSPORT=stdio` for the old
  behaviour.
- `docker-compose.yml` uses a URL secret from a Docker secret and publishes
  the port on loopback only.
- Development dependencies moved to `[dependency-groups]`.

### Removed

- The checked-in `garmin-mcp.dxt` bundle; build it with
  `scripts/build_dxt.sh`.
- Upstream maintainer tooling (`.claude/skills/babysit-prs`).

[Unreleased]: https://github.com/rvartanov/slurp-garmin-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/rvartanov/slurp-garmin-mcp/releases/tag/v1.0.0
