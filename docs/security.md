# Security

The server holds the keys to one Garmin account: it can read all health and
activity data and it can change and delete things. This page covers what to
protect and how.

## What to protect

| What | Where | Why |
|---|---|---|
| Garmin tokens | `GARMINTOKENS` directory (default `~/.garminconnect`) | Long-lived login. Anyone with a copy has the account, without password or MFA. |
| URL secret / bearer token | environment file or secret file | Whoever has it can use every tool. |
| The HTTP port | `GARMIN_MCP_HOST:GARMIN_MCP_PORT` | Without a token or URL secret it is open to everyone who can reach it. |

The token directory is created with owner-only permissions. Keep it out of
synced and shared folders and out of backups that others can read. Never
commit tokens, the environment file or secret files to a repository.

## Never serve HTTP beyond loopback without authentication

Over stdio nothing listens on the network; no extra protection is needed.

Over HTTP the server binds to `127.0.0.1` by default. As soon as it is
reachable from another machine (a non-loopback `GARMIN_MCP_HOST`, a reverse
proxy, a tunnel such as Tailscale Funnel) it must have a bearer token or a URL
secret. Set `GARMIN_MCP_REQUIRE_AUTH=true` so a configuration mistake stops
the server instead of exposing the account; the Docker image and the systemd
example do this.

Always put TLS in front (reverse proxy or tunnel). Both secrets travel with
every request and are readable on the wire over plain HTTP.

## Bearer token or URL secret?

**Bearer token** (`GARMIN_MCP_HTTP_TOKEN`) is the better mechanism: the secret
travels in a header, which proxies and browsers do not log or store. Use it
whenever the client can send a custom header (Claude Code, Claude Desktop with
a remote server entry, the MCP Inspector, SDK clients).

**URL secret** (`GARMIN_MCP_URL_SECRET`) is for clients that only accept a URL,
such as claude.ai custom connectors. The MCP endpoint is then
`https://host/<secret>/mcp`, and any other path is a `404` that does not
reveal whether a secret is configured. A URL is easier to leak than a header,
so:

- Do not paste the URL into chats, tickets or screenshots.
- Keep it out of proxy access logs. The examples in
  [`deploy/reverse-proxy/`](../deploy/reverse-proxy/) do this. The server
  itself writes `<secret>` in place of the real value in its own log.
- Use a long random value: `openssl rand -hex 32`.

Both are compared in constant time, and both can be combined. Neither applies
to `/healthz` and `/readyz`, which only report "up" and "logged in".

## Rotating a secret

1. Write the new value to the environment or secret file.
2. Restart the service.
3. Update the URL or header in each client.

The old value stops working at the restart. Rotate when a URL has been shared
by accident, and when someone who knew it should no longer have access.

To cut off access to Garmin itself, change the Garmin password; that
invalidates the saved tokens. Then run `garmin-mcp-auth --force-reauth`.

## Limit what a client can do

- `GARMIN_TOOL_PROFILE`, `GARMIN_ENABLED_TOOLS` and `GARMIN_DISABLED_TOOLS`
  decide which tools exist at all
  ([configuration.md](configuration.md#tool-filtering)). A read-only setup
  disables every tool marked `write` in [tools.md](tools.md).
- Write tools carry MCP annotations (`readOnlyHint`, `destructiveHint`), so
  clients can ask for confirmation before a change.
- `delete_activity` needs a second call with `confirm=true`.

## Service hardening

The systemd unit in [`deploy/systemd/`](../deploy/systemd/) runs as its own
user without a login shell, with a read-only file system apart from its state
directory, no access to `/home`, no new privileges and no capabilities. The
Docker image runs as a non-root user; the compose file adds a read-only root
file system and drops all capabilities.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
