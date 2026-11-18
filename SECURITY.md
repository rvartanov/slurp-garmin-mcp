# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue:

1. Go to <https://github.com/rvartanov/garmin-mcp/security/advisories/new>
   ("Report a vulnerability" on the repository's Security tab).
2. Describe the problem, how to reproduce it and what an attacker gains.

You will get a reply within a week. Please allow time for a fix before
publishing details.

Never include real Garmin tokens, passwords, URL secrets or personal health
data in a report, issue or pull request.

## Supported versions

Fixes are made on `main` and released as a new version. Only the latest
release is supported.

## Scope

In scope: the server and its deployment files, for example a way around the
bearer token or URL secret, a secret that ends up in a log, or a tool that
does more than its description and annotations say.

Out of scope: Garmin Connect itself, and problems in
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect) or
the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk);
report those to their projects.

How to run the server safely is described in [docs/security.md](docs/security.md).
