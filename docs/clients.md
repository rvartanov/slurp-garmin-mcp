# Clients

How to connect an MCP client. There are two ways, depending on where the
server runs:

- **Local (stdio):** the client starts `garmin-mcp` itself on your computer.
  Nothing listens on the network. Log in once with `garmin-mcp-auth` first
  ([installation.md](installation.md#log-in-to-garmin-once)).
- **Remote (HTTP):** the server runs as a service ([deployment.md](deployment.md))
  and the client connects to its URL. This is the only option for claude.ai
  in the browser and the mobile apps.

A remote URL has one of two forms, depending on how the server is protected
([security.md](security.md)):

| Protection | URL | Extra |
|---|---|---|
| URL secret | `https://garmin.example.com/<secret>/mcp` | none; the URL is the credential |
| Bearer token | `https://garmin.example.com/mcp` | header `Authorization: Bearer <token>` |

## Claude.ai (custom connector)

Works on claude.ai, Claude Desktop and the Claude mobile apps; the connector is
added once and is then available everywhere you are signed in. Custom
connectors connect from Anthropic's servers, so the server must be reachable
from the internet over HTTPS.

1. Run the server with a URL secret behind TLS: [deployment.md](deployment.md).
2. In Claude: **Settings → Connectors → Add custom connector**.
3. Name it (for example "Garmin") and paste the URL
   `https://garmin.example.com/<secret>/mcp`. Leave the OAuth fields empty.
4. Enable the connector in a chat and ask "Show my recent activities".

The custom connector dialog takes a URL and optional OAuth settings, not a
custom header; that is what the URL secret is for. Set
`GARMIN_MCP_STATELESS_HTTP=true` on the server (the service and Docker
defaults do): claude.ai reports an expired session as a failed tool call.

## Claude Code

Remote server:

```bash
# URL secret
claude mcp add --transport http garmin https://garmin.example.com/<secret>/mcp

# Bearer token
claude mcp add --transport http garmin https://garmin.example.com/mcp \
  --header "Authorization: Bearer <token>"
```

Local, over stdio:

```bash
claude mcp add garmin -- uvx --python 3.12 --from git+https://github.com/rvartanov/slurp-garmin-mcp garmin-mcp
```

Add `--scope user` to make it available in every project, and
`--env GARMIN_TOOL_PROFILE=training,workouts` to load fewer tools
([configuration.md](configuration.md#tool-filtering)).

## Claude Desktop (local)

1. Create a configuration in Claude Desktop:

Edit your Claude Desktop configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

You have two options to run the MCP locally with Claude.

### Directly from github without cloning the repo:

1. Log in once in a terminal; this asks for your email, password and MFA code
   and saves OAuth tokens to `~/.garminconnect`, so no credentials go into the
   client config:

```bash
uvx --python 3.12 --from git+https://github.com/rvartanov/slurp-garmin-mcp garmin-mcp-auth
```

2. Add this server configuration:

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
      ]
    }
  }
}
```

You might have to add the full path to `uvx` you can check the full path with `which uvx`

Do not put `GARMIN_PASSWORD` in this file: client configs are plain text that
other programs and backups can read. If you need a password fallback, use
`GARMIN_PASSWORD_FILE` with an owner-only file (see
[troubleshooting.md](troubleshooting.md#alternative-manual-first-run)).

3. Restart Claude Desktop

### Directly from your local copy of the repository:

1. Add this server configuration:

```
{
  "mcpServers": {
    "garmin-local": {
      "command": "uv",
      "args": [
        "--directory",
        "<full path to your local repository>/garmin_mcp",
        "run",
        "garmin-mcp"
      ]
    }
  }
}
```

2. Restart Claude Desktop

## Codex

Codex uses TOML for MCP server configuration. Add one of the following entries to `~/.codex/config.toml` after authenticating with `garmin-mcp-auth`.

You can also ask your MCP-capable client to set this up for you. For example:

```text
Install the Garmin MCP server from https://github.com/rvartanov/slurp-garmin-mcp, authenticate with garmin-mcp-auth, and add it to my MCP configuration without storing my Garmin email or password.
```

### Directly from GitHub without cloning the repo

```toml
[mcp_servers.garmin]
command = "uvx"
args = [
  "--python",
  "3.12",
  "--from",
  "git+https://github.com/rvartanov/slurp-garmin-mcp",
  "garmin-mcp"
]
```

### Directly from your local copy of the repository

```toml
[mcp_servers.garmin-local]
command = "uv"
args = [
  "--directory",
  "/full/path/to/garmin_mcp",
  "run",
  "garmin-mcp"
]
```

Restart your MCP client after saving the file.

## opencode

[opencode](https://opencode.ai) auto-loads a project-level `opencode.json` when launched from a repository root, so contributors who clone this repo get the Garmin MCP wired up against the local source with no extra config.

### From a clone of this repository (recommended for development)

This repo ships an [`opencode.json`](../opencode.json) that runs the MCP via `uv run garmin-mcp`, so it always tracks the working tree.

```bash
git clone https://github.com/rvartanov/slurp-garmin-mcp.git
cd slurp-garmin-mcp
uv sync                # install dependencies
garmin-mcp-auth        # one-time Garmin login (skip if ~/.garminconnect already exists)
opencode               # launches with the garmin MCP attached
```

Verify the server is connected:

```bash
opencode mcp list
# ●  ✓ garmin   connected
#       uv run garmin-mcp
```

### From any other directory (GitHub install)

Add the server to your global opencode config at `~/.config/opencode/opencode.json` after running `garmin-mcp-auth`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "garmin": {
      "type": "local",
      "command": [
        "uvx",
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/rvartanov/slurp-garmin-mcp",
        "garmin-mcp"
      ],
      "enabled": true,
      "timeout": 30000
    }
  }
}
```

Restart opencode after saving the file. The first `uvx` invocation downloads and caches the package, so the initial startup may take a few seconds.

## Claude Desktop: Desktop Extension (.dxt)

The easiest way to add this server to Claude Desktop is via the `.dxt` Desktop Extension file — no JSON editing required.

### Download and install

1. Build `garmin-mcp.dxt` (see below), or download it from the [Releases page](https://github.com/rvartanov/slurp-garmin-mcp/releases) when a release provides one.
2. Drag the `.dxt` file into the Claude Desktop window, **or** double-click it, **or** go to **Settings → Extensions → Install Extension** and select the file.
3. Claude Desktop will prompt you for the optional token path. The extension
   does not ask for your Garmin password; it logs in with the tokens from
   `garmin-mcp-auth` below.

### First-time authentication

The extension installs and runs the server automatically, but you must authenticate with Garmin once before data can be fetched:

```bash
uvx --python 3.12 --from git+https://github.com/rvartanov/slurp-garmin-mcp garmin-mcp-auth
```

This saves OAuth tokens to `~/.garminconnect`. After that the server works without any credentials in the config.

> **Note:** Tokens are valid for approximately 6 months. Re-run `garmin-mcp-auth` when they expire.

### Build the `.dxt` yourself

```bash
bash scripts/build_dxt.sh   # produces garmin-mcp.dxt in the repo root
```


## Other MCP clients

Any client that speaks MCP works. For stdio, the command is `garmin-mcp` (or
the `uvx` form above). For streamable HTTP, use the `/mcp` URL with either
protection from the table at the top. The legacy SSE transport
(`GARMIN_MCP_TRANSPORT=sse`) serves `/sse`; under a URL secret that is
`/<secret>/sse`.

## MCP Inspector

The Inspector runs directly through npx without requiring installation. Run from the project root:

```bash
npx @modelcontextprotocol/inspector uv run garmin-mcp
```

You'll be able to inspect and test the tools.

For a remote server, start the Inspector with `npx @modelcontextprotocol/inspector`,
choose "Streamable HTTP" and enter the URL.
