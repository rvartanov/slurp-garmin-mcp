# Troubleshooting

## `get_training_effect` returns HTTP 403 for a valid activity

Garmin's activity-details endpoint (`/activity-service/activity/{id}`) can
return **403 Forbidden** even when the same activity is visible in list tools.
`get_training_effect` now falls back to activity list search, which still
includes aerobic/anaerobic training effect for recent activities.

If the activity is older than the recent-search window, list the activity with
`get_activities` / `get_activities_by_date` and retry, or use those list fields
directly.

## `get_goals` returns no goals that exist in Garmin Connect

Garmin's goal-service only returns goals created in Connect's current Goals UI
(named distance/time targets such as a monthly cycling goal) when the request
sends `Sec-Fetch-Site: same-origin` and uses a 1-based `start`. With
`start=0`, it returns an empty list. python-garminconnect's `get_goals()` does not do both
(through 0.3.16), so `get_goals` here calls `/goal-service/goal/goals`
directly the way Connect's Goals page does, and uses the library call only as
a fallback.

## "Failed to spawn process: No such file or directory"

If Claude Desktop can't find `uvx`, it's because `uvx` is not in the PATH that Claude Desktop uses. To fix this:

1. Find where `uvx` is installed:
```bash
which uvx
```

2. Use the full path in your configuration. For example, if `uvx` is at `/Users/username/.cargo/bin/uvx`:
```json
{
  "mcpServers": {
    "garmin": {
      "command": "/Users/username/.cargo/bin/uvx",
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

## Windows: Smart App Control blocks `uv` / `uvx`

On Windows 11 with **Smart App Control** enabled, `uv.exe` / `uvx.exe` may be blocked when launching Garmin_MCP — including when `uv` tries to load an unsigned `garmin-mcp.exe` from a local `.venv`.

This is **not** the same as Microsoft Defender Antivirus quarantine. Smart App Control is under:

**Windows Security → App & browser control → Smart App Control**

### Symptoms
- Smart App Control notification when running `uv`, `uvx`, or Claude Desktop with `command: "uvx"`
- Claude Desktop fails to spawn the server even though `uvx` appears installed
- Event Viewer → *Applications and Services Logs* → *Microsoft* → *Windows* → *CodeIntegrity* → *Operational* shows **CodeIntegrity Error 3077** mentioning `uv.exe` and `garmin-mcp.exe` (policy / Enterprise signing level)

### Confirm
1. Smart App Control is **On** (Evaluation or Enforcement).
2. Check the CodeIntegrity Operational log for event **3077** around the failed launch.
3. Defender “Virus & threat protection” history may be empty — that does not rule SAC out.

### Recoveries (prefer keeping Smart App Control on)
1. Install or reinstall `uv` via a packaged channel, then verify in PowerShell:
   ```powershell
   winget install --id=astral-sh.uv -e
   # or: scoop install main/uv
   uvx --version
   ```
2. Point Claude Desktop at the full path to `uvx.exe` (same idea as the PATH troubleshooting above), for example:
   ```json
   "command": "C:\\Users\\<you>\\.local\\bin\\uvx.exe"
   ```
3. If Enforcement still blocks loading `garmin-mcp.exe`, you may need an admin/policy exception for that binary path. Turning Smart App Control off globally is a last resort, not the default advice.
4. If local uvx remains blocked, use the [Docker image](deployment.md#docker) instead.

## Login Issues

If you encounter login issues:

1. Verify your credentials are correct
2. Check if Garmin Connect requires additional verification
3. Ensure the garminconnect package is up to date

## Logs

For other issues, check the Claude Desktop logs at:

- macOS: `~/Library/Logs/Claude/mcp-server-garmin.log`
- Windows: `%APPDATA%\Claude\logs\mcp-server-garmin.log`

## Garmin Connect Multi-Factor Authentication (MFA)

### Understanding MFA with MCP Servers

MCP servers run as background processes without direct terminal access. If your Garmin account has MFA enabled, you must authenticate once using the pre-authentication tool before the server can run.

### Recommended: Pre-Authentication Tool

The easiest way to handle MFA is using the dedicated authentication tool:

```bash
garmin-mcp-auth
```

This saves OAuth tokens to `~/.garminconnect` for future use. The server will automatically use these tokens when running in Claude Desktop or other MCP clients.

**Additional Options:**

```bash
# Use environment variables for credentials
GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=secret garmin-mcp-auth

# Verify existing tokens
garmin-mcp-auth --verify

# Show where tokens are looked up, what is on disk, and whether they work
garmin-mcp-auth --diagnose

# Force re-authentication (e.g., when tokens expire)
garmin-mcp-auth --force-reauth

# Use custom token location
garmin-mcp-auth --token-path ~/.garmin_tokens
```

### Alternative: Manual First Run

You can provide credentials from files to the authentication CLI:

```bash
# Store credentials in files for security
echo "your_email@example.com" > ~/.garmin_email
echo "your_password" > ~/.garmin_password
chmod 600 ~/.garmin_email ~/.garmin_password

# Run the authentication CLI before starting the server
GARMIN_EMAIL_FILE=~/.garmin_email GARMIN_PASSWORD_FILE=~/.garmin_password \
  uvx --python 3.12 --from git+https://github.com/rvartanov/slurp-garmin-mcp garmin-mcp-auth

# Enter MFA code when prompted
# Tokens will be saved automatically
# Now add to Claude Desktop config without credentials
```

After initial authentication, configure Claude Desktop **without** credentials (tokens are already saved):

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

### Using Docker with MFA

If using Docker, run the login in the container; see [deployment.md](deployment.md#docker).

### Troubleshooting MFA

**Error: "MFA required; run 'garmin-mcp-auth' before starting the server."**

Solution:
1. Open terminal
2. Run: `garmin-mcp-auth`
3. Enter credentials and MFA code
4. Restart Claude Desktop

**Token Expired**

OAuth tokens expire periodically (approximately every 6 months). Re-authenticate:
```bash
garmin-mcp-auth --force-reauth
```

**Verify Tokens Work**
```bash
garmin-mcp-auth --verify
```

**`garmin-mcp-auth` succeeded, but the server still cannot log in**

The server loads tokens only from `garmin_tokens.json` inside the token
directory (`$GARMINTOKENS`, default `~/.garminconnect`). Its startup error says
what it found there: no directory, no token file, a file it cannot read, or
tokens Garmin rejected. The usual cause is the MCP client starting the server
with a different `GARMINTOKENS` or `HOME` than the shell that ran
`garmin-mcp-auth` (common with Claude Desktop on Windows), so the two resolve
to different directories. Compare them with:
```bash
garmin-mcp-auth --diagnose
```
The server does not read a base64 copy of the tokens. `garmin-mcp-auth` and
a password login write one (owner-only) only when `GARMINTOKENS_BASE64` names
the file, for other garminconnect-based tools. An old
`~/.garminconnect_base64` from earlier versions can be deleted.
