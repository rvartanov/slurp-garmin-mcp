# Configuration

The server is configured through environment variables only. Set them in the
client's `env` block (local use), in the service's environment file, or in
`docker-compose.yml`. [`deploy/env.example`](../deploy/env.example) is a
ready-to-edit file with all of them.

Variables with a `_FILE` twin read the value from that file instead; set one
of the two, never both. That is what systemd credentials and Docker secrets
need.

## Garmin account

| Variable | Default | Meaning |
|---|---|---|
| `GARMINTOKENS` | `~/.garminconnect` | Directory with the tokens saved by `garmin-mcp-auth`. `~` and `${HOME}` are expanded. |
| `GARMINTOKENS_BASE64` | | The tokens as one base64 string, for platforms without a persistent disk. |
| `GARMIN_EMAIL`, `GARMIN_EMAIL_FILE` | | Login email. Only needed for `garmin-mcp-auth`, or as a fallback for accounts without MFA. |
| `GARMIN_PASSWORD`, `GARMIN_PASSWORD_FILE` | | Password, same use as the email. |
| `GARMIN_IS_CN` | `false` | `true` for Garmin Connect China (garmin.cn). |
| `GARMIN_TZ` | server time zone | Your IANA time zone, e.g. `Europe/Amsterdam`. Write tools that take a date or local time (`add_body_composition`, `set_blood_pressure`) read it in this zone, and `get_device_last_used` reports times in it. Set it when the server runs in another zone than you (Docker, a remote host in UTC); otherwise a date-only weigh-in can land on the wrong day. |

## Transport

| Variable | Default | Meaning |
|---|---|---|
| `GARMIN_MCP_TRANSPORT` | `stdio` | `stdio` for a local client, `streamable-http` for a service, `sse` for legacy clients. |
| `GARMIN_MCP_HOST` | `127.0.0.1` | Bind address for the HTTP transports. Anything other than loopback needs HTTP authentication (below). |
| `GARMIN_MCP_PORT` | `8000` | Bind port for the HTTP transports. |
| `GARMIN_MCP_STATELESS_HTTP` | `false` | `true` runs streamable HTTP without sessions. Recommended for long-lived services: a stateful session is dropped after 30 minutes idle, and some clients (claude.ai connectors among them) report the resulting `404 Session not found` as a failed tool call. No tool depends on session state. |
| `GARMIN_MCP_CALL_TIMEOUT` | `90` | Seconds before a stalled request to Garmin is abandoned with a clear, retryable error. `0` disables the limit. |

With an HTTP transport:

- MCP clients connect to **`/mcp`** (streamable HTTP) or **`/sse`** (SSE).
- **`GET /healthz`** answers `ok` as soon as the server is up: a liveness probe.
- **`GET /readyz`** answers `200 {"status": "ready"}` once the Garmin login
  succeeded, and `503` with `pending` or `failed` otherwise: a readiness probe.

## HTTP authentication

The HTTP transports give full read and write access to the Garmin account.
Details and advice are in [security.md](security.md).

| Variable | Meaning |
|---|---|
| `GARMIN_MCP_HTTP_TOKEN`, `GARMIN_MCP_HTTP_TOKEN_FILE` | Bearer token. Every request must send `Authorization: Bearer <token>`; anything else gets `401`. |
| `GARMIN_MCP_URL_SECRET`, `GARMIN_MCP_URL_SECRET_FILE` | URL secret. The MCP endpoints exist only under `/<secret>/` (`/<secret>/mcp`); every other path gets `404`. At least 16 characters; letters, digits and `-._~`. |
| `GARMIN_MCP_REQUIRE_AUTH` | `true` makes the server refuse to start an HTTP transport when neither of the two is set. The Docker image and the service example set it. |

Both can be set together; a request must then pass both. `/healthz` and
`/readyz` never need either. Generate a value with `openssl rand -hex 32`.

## Host and Origin checks

On a loopback bind (the default) the MCP SDK protects against DNS rebinding
and accepts only a loopback `Host` header. A reverse proxy or tunnel that
forwards the public host name (Tailscale Funnel, Caddy, nginx with
`proxy_set_header Host $host`) then gets `421 Invalid Host header`. List the
public names instead of switching the check off:

| Variable | Meaning |
|---|---|
| `GARMIN_MCP_ALLOWED_HOSTS` | Comma-separated host names to accept in addition to loopback, e.g. `myhost.tailnet.ts.net`. A name without a port is accepted with any port; `name:8443` accepts only that port. No scheme, path or wildcard host. Setting it also turns the check on for a non-loopback bind. |
| `GARMIN_MCP_ALLOWED_ORIGINS` | Comma-separated origins to accept in the `Origin` header, e.g. `https://claude.ai`. Requests without an `Origin` header (server-to-server clients) always pass. Requires `GARMIN_MCP_ALLOWED_HOSTS`. |

## Activity file downloads

| Variable | Default | Meaning |
|---|---|---|
| `GARMIN_FIT_DOWNLOAD_DIR` | | Directory for files saved by `download_activity_file`. When set, the first-run question is skipped. |
| `GARMIN_FIT_CONFIG` | `~/.garminconnect_fit_config.json` | Where the chosen download directory is remembered. |

## Tool Filtering

This server registers 155 tools by default, which is a lot of context for an
LLM to carry in every session. You can expose only the tools you need with
three optional environment variables:

| Env var | Effect |
|---|---|
| `GARMIN_TOOL_PROFILE` | A built-in subset by area: `minimal`, `health`, `activities`, `workouts`, `training`, `nutrition`, or `all` (the default). Combine several with commas, e.g. `health,training`. |
| `GARMIN_ENABLED_TOOLS` | Comma-separated **allowlist** — if set, *only* these tools are registered. With a profile, these are **added** to it instead. |
| `GARMIN_DISABLED_TOOLS` | Comma-separated **denylist** — listed tools are skipped. Ignored if an allowlist is set, unless a profile is also set; then it removes tools from the profile. |

Tool names are case-insensitive. With none of them set, all tools register
(unchanged default behaviour). Names that match no tool are ignored with a
warning on stderr, which makes typos easy to spot. An unknown profile name
stops the server at startup with the list of known profiles.

### Profiles

| Profile | Tools | What it covers |
|---|---:|---|
| `minimal` | 20 | Recent activities with splits, daily stats, sleep, HRV, stress, body battery, training readiness and status |
| `health` | 53 | Every health_wellness tool plus weight, body composition, blood pressure, hydration, women's health, fitness age, HRV and respiration trends |
| `activities` | 41 | Activity list, detail, splits and edits; FIT analysis and power curve; gear; courses |
| `workouts` | 26 | Workout library, upload, schedule and delete; the high-level builders; the calendar |
| `training` | 38 | Training status, load, effect, VO2max, FTP, lactate threshold, endurance and hill scores, readiness, recovery time, personal records, race predictions, goals, badges |
| `nutrition` | 23 | Food log, custom foods, daily nutrition settings, hydration, energy balance |

Every profile also includes the identity and unit tools (`get_full_name`, `get_heart_rate_zones`, `get_unit_system`, `get_user_profile`, `get_userprofile_settings`), so the
client can label the numbers it gets back.

Example — a coaching session that needs training metrics and the workout tools:

```json
"env": {
  "GARMIN_TOOL_PROFILE": "training,workouts"
}
```

Example — the health profile plus recent activities, without the write tools:

```json
"env": {
  "GARMIN_TOOL_PROFILE": "health",
  "GARMIN_ENABLED_TOOLS": "get_activities,get_activity",
  "GARMIN_DISABLED_TOOLS": "add_weigh_in,add_weigh_in_with_timestamps,delete_weigh_ins,add_body_composition,add_hydration_data,set_blood_pressure"
}
```

Example — hand-pick tools without a profile:

```json
"env": {
  "GARMIN_ENABLED_TOOLS": "get_sleep_data,get_stress_summary,get_activities"
}
```

Which tool is in which profile is listed per tool in [tools.md](tools.md).
