# Slurp garmin-mcp

An [MCP](https://modelcontextprotocol.io) server for Garmin Connect. It gives
Claude and other MCP clients access to your activities, health data, training
metrics, workouts, nutrition, gear and calendar: more than 150 tools, about a
third of which can also change things.

It runs locally next to a desktop client, or as a service on a server
(systemd or Docker) for claude.ai and other remote clients.

> Not affiliated with Garmin. Garmin Connect has no public API for personal
> use; this server uses the same endpoints as the Garmin Connect website,
> through [python-garminconnect](https://github.com/cyberjunky/python-garminconnect).
> Those endpoints can change without notice.

## Quick start (local)

Needs Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```bash
# 1. Log in to Garmin once (asks for your MFA code if enabled)
uvx --from git+https://github.com/rvartanov/slurp-garmin-mcp garmin-mcp-auth

# 2. Add the server to your client, for example Claude Code:
claude mcp add garmin -- uvx --from git+https://github.com/rvartanov/slurp-garmin-mcp garmin-mcp
```

Claude Desktop, in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/rvartanov/slurp-garmin-mcp", "garmin-mcp"]
    }
  }
}
```

No password goes into the client configuration; the server uses the tokens
saved in step 1.

## Quick start (server)

```bash
git clone https://github.com/rvartanov/slurp-garmin-mcp
sudo slurp-garmin-mcp/deploy/install.sh     # systemd service, prints the next steps
```

or with Docker:

```bash
mkdir -p secrets && openssl rand -hex 32 > secrets/url_secret.txt && chmod 644 secrets/url_secret.txt
docker compose run --rm --entrypoint garmin-mcp-auth garmin-mcp
docker compose up -d
```

Put a reverse proxy or tunnel with TLS in front and add
`https://<your host>/<secret>/mcp` as a custom connector in Claude. The full
steps are in [docs/deployment.md](docs/deployment.md).

## Things to ask

- "Show me my recent activities"
- "What was my sleep like last night?"
- "Show my training load and HRV trend for the last six weeks"
- "Create a 5 x 1 km interval workout and schedule it for Thursday"
- "Which races are on my Garmin calendar?"

## Documentation

| | |
|---|---|
| [Installation](docs/installation.md) | pip, uv and uvx; first login and MFA; several accounts; garmin.cn |
| [Clients](docs/clients.md) | Claude.ai custom connector, Claude Desktop, Claude Code, Codex, opencode, others |
| [Deployment](docs/deployment.md) | systemd, Docker, reverse proxy, Tailscale Funnel |
| [Configuration](docs/configuration.md) | every environment variable; tool profiles and allow/deny lists |
| [Security](docs/security.md) | tokens, bearer token, URL secret, hardening |
| [Tools](docs/tools.md) | all tools, generated from the code |
| [Workout tools](docs/workouts.md) | the workout builders and the raw workout format |
| [Tool notes](docs/tool-notes.md) | gear, file downloads, strength sets, skipped endpoints |
| [Troubleshooting](docs/troubleshooting.md) | login, MFA, known Garmin quirks, logs |

[Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [Security policy](SECURITY.md)

## Credits

Slurp garmin-mcp is a fork of
[Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) by Alexandre
Domingues and its contributors, who built the server and nearly all of its
tools. This fork adds packaging as a standalone service (URL-secret mode,
secret files, systemd and Docker deployment) and its own documentation; see
[NOTICE](NOTICE) and the [changelog](CHANGELOG.md).

Garmin Connect access is provided by
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect) by
cyberjunky.

## License

[MIT](LICENSE). Copyright (c) 2025 Alexandre Domingues, Copyright (c) 2026
Robert Vartanov.
