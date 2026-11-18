# Tailscale Funnel

[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) publishes a local port
on `https://<machine>.<tailnet>.ts.net` with a valid certificate, without
opening a port on your router. It adds no authentication of its own, so the
server must run with a URL secret or bearer token.

```bash
# Server on loopback, protected by a URL secret (see deploy/env.example)
sudo systemctl start slurp-garmin-mcp

# Publish it; --bg keeps the funnel across reboots
sudo tailscale funnel --bg 8000
tailscale funnel status
```

The MCP endpoint is then `https://<machine>.<tailnet>.ts.net/<secret>/mcp`.

To keep the server reachable only inside your tailnet (no public exposure),
use `tailscale serve --bg 8000` instead.

Stop publishing with `sudo tailscale funnel --https=443 off`.
