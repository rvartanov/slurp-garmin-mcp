# Installation

Slurp garmin-mcp is a Python package (3.10 or newer). Installing it gives you
these commands:

| Command | What it does |
|---|---|
| `garmin-mcp` | The MCP server. `slurp-garmin-mcp` is an alias. |
| `garmin-mcp-auth` | One-time Garmin login; saves the tokens the server uses. |

To run it as a service on a server, go to [deployment.md](deployment.md). To
connect a client, see [clients.md](clients.md).

## Install

Pick one. All install from GitHub; replace `main` with a tag to pin a version.

```bash
# uv: installs the commands into ~/.local/bin
uv tool install git+https://github.com/rvartanov/slurp-garmin-mcp@main

# pip, into a virtualenv
python3 -m venv ~/.venvs/garmin-mcp
~/.venvs/garmin-mcp/bin/pip install git+https://github.com/rvartanov/slurp-garmin-mcp@main

# uvx: no install, runs straight from GitHub (used in most client configs)
uvx --from git+https://github.com/rvartanov/slurp-garmin-mcp garmin-mcp --version
```

From a clone:

```bash
git clone https://github.com/rvartanov/slurp-garmin-mcp
cd slurp-garmin-mcp
uv sync            # development environment, then: uv run garmin-mcp
pip install .      # or a regular install
```

Check the install with `garmin-mcp --version` and `garmin-mcp --help`.

## Log in to Garmin (once)

The server never asks for a password while it runs. Log in once in a terminal;
the tokens are saved and reused, and refreshed automatically.

```bash
garmin-mcp-auth
```

You are asked for your Garmin email and password, and for the MFA code if
multi-factor authentication is on for the account. Tokens are saved to
`~/.garminconnect`, or to the directory in `GARMINTOKENS`.

```bash
garmin-mcp-auth --verify         # check the saved tokens
garmin-mcp-auth --diagnose       # where tokens are looked up and whether they work
garmin-mcp-auth --force-reauth   # log in again, e.g. after the tokens expired
garmin-mcp-auth --token-path ~/.garmin_tokens
```

Log in again when `--verify` fails. Treat the token directory as a password:
anyone who has it has full access to the account. See
[security.md](security.md).

Accounts without MFA can skip this step and give the server `GARMIN_EMAIL` and
`GARMIN_PASSWORD` (or the `_FILE` variants) instead. Tokens are the better
choice: no password in any configuration.

More on MFA, including what to do when a login fails:
[troubleshooting.md](troubleshooting.md#garmin-connect-multi-factor-authentication-mfa).

## Run

```bash
garmin-mcp                                        # stdio, for a local client
GARMIN_MCP_TRANSPORT=streamable-http garmin-mcp   # HTTP on 127.0.0.1:8000
```

Every setting is an environment variable: [configuration.md](configuration.md).

## Using more than one Garmin account

A single server process is bound to one Garmin account. To use several accounts
at once, run **one server instance per account**, each with its own token
directory, selected with the `GARMINTOKENS` environment variable.

`GARMINTOKENS` defaults to `~/.garminconnect`. Point it somewhere else and the
server reads and writes tokens there instead, leaving the default store
untouched.

### Step 1: Authenticate each account into its own directory

```bash
garmin-mcp-auth --token-path ~/.garminconnect-alice
garmin-mcp-auth --token-path ~/.garminconnect-bob
```

`--token-path` also accepts `$GARMINTOKENS`, so `GARMINTOKENS=~/.garminconnect-alice garmin-mcp-auth`
is equivalent.

### Step 2: Declare one server per account

```json
{
  "mcpServers": {
    "garmin-alice": {
      "command": "uvx",
      "args": ["--python", "3.12", "--from", "git+https://github.com/rvartanov/slurp-garmin-mcp", "garmin-mcp"],
      "env": {
        "GARMINTOKENS": "${HOME}/.garminconnect-alice"
      }
    },
    "garmin-bob": {
      "command": "uvx",
      "args": ["--python", "3.12", "--from", "git+https://github.com/rvartanov/slurp-garmin-mcp", "garmin-mcp"],
      "env": {
        "GARMINTOKENS": "${HOME}/.garminconnect-bob"
      }
    }
  }
}
```

Each server logs the directory it authenticates from on startup, so you can
confirm the wiring:

```
Trying to login to Garmin Connect using token data from directory '/home/you/.garminconnect-alice'...
```

### Notes

- **No silent fallback.** If `GARMINTOKENS` points at a directory with no valid
  tokens and login fails, the server logs the failure and tool calls fail;
  HTTP `/readyz` remains unavailable (503). The server does not switch to the
  default token store, so a misconfigured second server cannot silently reuse
  the first account's session.
- **`${HOME}` is expanded** even when an MCP client passes it through
  unresolved, and `~` works on Windows via `USERPROFILE`.
- **Restrict write tools on secondary accounts.** Tools such as
  `upload_workout` and `schedule_workout` write to whichever account the server
  is bound to. Pair `GARMINTOKENS` with `GARMIN_ENABLED_TOOLS` (see
  [Tool Filtering](configuration.md#tool-filtering)) to make an account read-only:

  ```json
  "env": {
    "GARMINTOKENS": "${HOME}/.garminconnect-bob",
    "GARMIN_ENABLED_TOOLS": "get_activities,get_activities_by_date,get_activity,get_activity_splits"
  }
  ```
- **Token directories hold long-lived credentials.** They are created with
  owner-only permissions; keep them out of shared or synced folders.

## Garmin Connect China (garmin.cn)

If you use Garmin Connect China (garmin.cn) instead of the international version, set the `GARMIN_IS_CN` environment variable to `true`:

```bash
# Pre-authenticate with Garmin Connect China
GARMIN_IS_CN=true garmin-mcp-auth

# Or use the CLI flag
garmin-mcp-auth --is-cn
```

For Claude Desktop, add `GARMIN_IS_CN` to the `env` section:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/rvartanov/slurp-garmin-mcp",
        "garmin-mcp"
      ],
      "env": {
        "GARMIN_IS_CN": "true"
      }
    }
  }
}
```

For Docker, uncomment `GARMIN_IS_CN` in `docker-compose.yml`; for the systemd service, set it in the environment file.
