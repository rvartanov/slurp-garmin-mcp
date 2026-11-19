# Deployment

Run Slurp garmin-mcp as a service, so remote clients such as claude.ai can
reach it. The recipe is the same everywhere:

1. The server listens on loopback with streamable HTTP, protected by a URL
   secret or bearer token ([security.md](security.md)).
2. You log in to Garmin once; the tokens stay on the server.
3. A reverse proxy or tunnel adds TLS and publishes it.

Pick [systemd](#systemd) or [Docker](#docker) for steps 1 and 2, then
[publish it](#publish-it-with-tls).

## systemd

### System service (recommended)

Needs root, Python 3.12 or newer with the `venv` module, and git.

```bash
git clone https://github.com/rvartanov/slurp-garmin-mcp
sudo slurp-garmin-mcp/deploy/install.sh
```

The installer is safe to run again; that is also how you upgrade. It:

- creates the user `garmin-mcp` (no login shell);
- installs the package into `/opt/slurp-garmin-mcp/venv`;
- creates `/etc/slurp-garmin-mcp/env` from
  [`deploy/env.example`](../deploy/env.example) and a random URL secret in
  `/etc/slurp-garmin-mcp/url-secret` (existing files are left alone);
- installs and enables `slurp-garmin-mcp.service`.

Install a specific version with `sudo REF=v1.0.0 deploy/install.sh`, or from
the checkout itself with `sudo SOURCE=. deploy/install.sh`.

Then log in to Garmin once, as the service user, and start the service:

```bash
sudo -u garmin-mcp env GARMINTOKENS=/var/lib/slurp-garmin-mcp HOME=/var/lib/slurp-garmin-mcp \
  /opt/slurp-garmin-mcp/venv/bin/garmin-mcp-auth
sudo systemctl start slurp-garmin-mcp
```

Check it:

```bash
systemctl status slurp-garmin-mcp
curl http://127.0.0.1:8000/healthz      # ok
curl http://127.0.0.1:8000/readyz       # {"status": "ready"} once logged in
journalctl -u slurp-garmin-mcp -f       # logs
```

| Path | Contents |
|---|---|
| `/etc/slurp-garmin-mcp/env` | Settings ([configuration.md](configuration.md)). Restart the service after a change. |
| `/etc/slurp-garmin-mcp/url-secret` | The URL secret. The MCP endpoint is `/<secret>/mcp`. |
| `/var/lib/slurp-garmin-mcp` | Garmin tokens and downloaded activity files. Back this up privately, or log in again after a restore. |
| `/opt/slurp-garmin-mcp/venv` | The installed package. |

Remove the service with `sudo deploy/uninstall.sh`. Settings and tokens are
kept; add `--purge` to delete those and the user as well.

### User service (no root)

```bash
python3 -m venv ~/.local/share/slurp-garmin-mcp/venv
~/.local/share/slurp-garmin-mcp/venv/bin/pip install git+https://github.com/rvartanov/slurp-garmin-mcp@main

mkdir -p ~/.config/slurp-garmin-mcp ~/.local/state/slurp-garmin-mcp ~/.config/systemd/user
chmod 700 ~/.config/slurp-garmin-mcp ~/.local/state/slurp-garmin-mcp
cp deploy/env.example ~/.config/slurp-garmin-mcp/env
openssl rand -hex 32 > ~/.config/slurp-garmin-mcp/url-secret
chmod 600 ~/.config/slurp-garmin-mcp/env ~/.config/slurp-garmin-mcp/url-secret
```

In `~/.config/slurp-garmin-mcp/env`, point `GARMIN_MCP_URL_SECRET_FILE` at
the full path of the secret file you just created. Then:

```bash
GARMINTOKENS=~/.local/state/slurp-garmin-mcp \
  ~/.local/share/slurp-garmin-mcp/venv/bin/garmin-mcp-auth

cp deploy/systemd/slurp-garmin-mcp.user.service ~/.config/systemd/user/slurp-garmin-mcp.service
systemctl --user daemon-reload
systemctl --user enable --now slurp-garmin-mcp
loginctl enable-linger "$USER"     # keep it running after logout
```

## Docker

The image serves streamable HTTP on port 8000 as a non-root user, keeps the
Garmin tokens in the `/data` volume, and refuses to start without a URL secret
or bearer token.

With Docker Compose, from a clone of the repository:

```bash
mkdir -p secrets
openssl rand -hex 32 > secrets/url_secret.txt
chmod 644 secrets/url_secret.txt     # the container user must be able to read it

# Log in to Garmin once (asks for the MFA code if enabled)
docker compose run --rm --entrypoint garmin-mcp-auth garmin-mcp

docker compose up -d
docker compose ps                    # STATUS shows "healthy"
docker compose logs -f garmin-mcp
```

The endpoint is `http://127.0.0.1:8000/<secret>/mcp`; the compose file
publishes the port on loopback only.

Without Compose:

```bash
docker build -t slurp-garmin-mcp .

docker run --rm -it -v garmin-tokens:/data --entrypoint garmin-mcp-auth slurp-garmin-mcp

docker run -d --name slurp-garmin-mcp --restart unless-stopped \
  -p 127.0.0.1:8000:8000 -v garmin-tokens:/data \
  -e GARMIN_MCP_URL_SECRET="$(cat secrets/url_secret.txt)" \
  slurp-garmin-mcp
```

Use `GARMIN_MCP_HTTP_TOKEN` (or `..._FILE` with a Docker secret) for a bearer
token instead of, or next to, the URL secret. The other settings in
[configuration.md](configuration.md) work as `-e` options too.

For a local stdio client, override the transport:
`docker run --rm -i -v garmin-tokens:/data -e GARMIN_MCP_TRANSPORT=stdio slurp-garmin-mcp`.

The `garmin-tokens` volume holds the Garmin login. Removing it
(`docker volume rm`) means logging in again.

## Publish it with TLS

The service listens on `127.0.0.1:8000`. Put one of these in front. Examples
are in [`deploy/reverse-proxy/`](../deploy/reverse-proxy/).

| Option | Use when | Example |
|---|---|---|
| Caddy | You have a domain name; certificates are automatic. | [`Caddyfile`](../deploy/reverse-proxy/Caddyfile) |
| nginx | You already run nginx. | [`nginx.conf`](../deploy/reverse-proxy/nginx.conf) |
| Tailscale Funnel | No domain or open port; you use Tailscale. | [`tailscale-funnel.md`](../deploy/reverse-proxy/tailscale-funnel.md) |

Whatever you use:

- Do not buffer responses; MCP answers are streams.
- Keep the request path out of access logs when you use a URL secret.
- Leave the server on loopback. Only the proxy or tunnel talks to it.

The MCP URL for clients is then `https://<your host>/<secret>/mcp`. Continue
with [clients.md](clients.md).

## Upgrading

- systemd: `git pull` in the clone and run `sudo deploy/install.sh` again.
- Docker: `git pull && docker compose up -d --build`.

Settings, secrets and Garmin tokens are kept in both cases. Changes per
version are in [CHANGELOG.md](../CHANGELOG.md).
