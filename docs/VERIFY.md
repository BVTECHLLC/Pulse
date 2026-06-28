# Phase 6 â€” Verification Checklist

Copy-paste verification for **BVTech OpsPilot** after a deploy. Commands are written for
**Windows PowerShell** on the operator's laptop. The deploy SSH key lives at:

```
C:\Users\bvtec\.ssh\opspilot_linode
```

Shorthand used below:

```powershell
# Set once per PowerShell session, then reuse $SSH everywhere.
$KEY = "C:\Users\bvtec\.ssh\opspilot_linode"
$HOSTNAME = "45.33.29.100"
$SSH = "ssh -i `"$KEY`" deploy@$HOSTNAME"
```

> The app runs from `/opt/bvtech-portal/opspilot`. `docker compose` on the server must be run
> from that directory. The remote commands below `cd` into it for you.

---

## 1. Public portal reachable (Cloudflare Tunnel)

The portal is served through Cloudflare Tunnel at `https://portal.bvtech.org` (zero open inbound
ports on the Linode â€” only SSH/22).

### 1a. Health endpoint

```powershell
curl.exe -sS https://portal.bvtech.org/api/health
```

Expected:

```json
{"ok":true,"version":"0.2.0","env":"production"}
```

(Field set may vary slightly; the load-bearing part is `"ok":true`.)

### 1b. Portal root

```powershell
curl.exe -sS -o NUL -w "%{http_code}`n" https://portal.bvtech.org/
```

Expected: `200` (the server-rendered login page). A redirect to `/login` showing `200`/`302`/`303`
is also fine.

> **Cloudflare challenge caveat:** Cloudflare may return an interstitial **challenge / managed
> bot page** (HTTP `403` or `503` with a `cf-mitigated` header) to `curl` because it has no
> browser fingerprint. That does **not** mean the portal is down. To confirm the UI, open
> **https://portal.bvtech.org/** in a real browser and verify the login page renders. Use the
> "from inside" check (Section 2) to confirm the app itself is healthy regardless of Cloudflare.

---

## 2. Backend health from inside the container

This bypasses Cloudflare entirely and hits uvicorn directly inside the `api` container â€” the
ground-truth app health check.

```powershell
ssh -i "$KEY" deploy@45.33.29.100 "cd /opt/bvtech-portal/opspilot && docker compose exec -T api curl -sS http://localhost:8000/api/health"
```

Expected:

```json
{"ok":true,"version":"0.2.0","env":"production"}
```

If this returns `{"ok":true,...}` but Section 1 fails, the problem is in Cloudflare / the tunnel
(see Section 5), not the application.

---

## 3. Container status

```powershell
ssh -i "$KEY" deploy@45.33.29.100 "cd /opt/bvtech-portal/opspilot && docker compose ps"
```

Expected â€” `db`, `redis`, `api`, and `cloudflared` all `Up` / `running` (and `api`
`(healthy)` if a healthcheck is defined):

```
NAME                       IMAGE                STATUS                   PORTS
opspilot-api-1             opspilot-api         Up 3 minutes (healthy)   8000/tcp
opspilot-cloudflared-1     cloudflare/cloudflared   Up 3 minutes
opspilot-db-1              postgres:16-alpine   Up 3 minutes             5432/tcp
opspilot-redis-1           redis:7-alpine       Up 3 minutes             6379/tcp
```

Notes:
- **`caddy` is intentionally absent** â€” it exists in `docker-compose.yml` but is not started;
  public access is via Cloudflare Tunnel.
- **`cloudflared`** comes from the server-only `docker-compose.override.yml` (not committed). If
  it is missing here, the override file is gone â€” restore it before the next `up`.
- No host port should be published for `api` (only the internal `8000/tcp`). If you see
  `0.0.0.0:80->...` something is misconfigured.

If a container is restarting, inspect it:

```powershell
ssh -i "$KEY" deploy@45.33.29.100 "cd /opt/bvtech-portal/opspilot && docker compose logs --tail=50 api"
```

---

## 4. GitHub Actions deployment

The CI/CD pipeline: push/merge to `main` -> GitHub Actions SSHes to `deploy@45.33.29.100` ->
`git pull --ff-only` -> `alembic upgrade head` -> `docker compose up -d --build api` ->
`docker image prune -f`.

### 4a. From PowerShell (GitHub CLI)

```powershell
gh run list --repo BVTECHLLC/Pulse --limit 5
```

Expected â€” the most recent run for `main` shows `completed  success`:

```
STATUS   TITLE              WORKFLOW   BRANCH  EVENT  ID           ELAPSED  AGE
completed  success  Deploy ...  Deploy     main    push   1234567890   1m20s    2m
```

Watch / inspect the latest run:

```powershell
gh run watch --repo BVTECHLLC/Pulse                       # live-tail the in-progress run
gh run view --repo BVTECHLLC/Pulse --log-failed           # logs for the most recent failed run
```

### 4b. From a browser (or phone)

Open **https://github.com/BVTECHLLC/Pulse/actions** and confirm the latest workflow run has a
green check. Click into it to read the SSH deploy step (the migration + build output appears
there).

### 4c. Confirm the deployed revision matches `main`

```powershell
# Latest commit on origin/main
gh repo view BVTECHLLC/Pulse --json defaultBranchRef -q ".defaultBranchRef.target.oid" 2>$null
# What the server actually has checked out
ssh -i "$KEY" deploy@45.33.29.100 "cd /opt/bvtech-portal && git rev-parse HEAD"
```

The two SHAs should match. (You can also verify by checking the `version` field from Section 1/2
matches `APP_VERSION` in `opspilot/app/core/config.py`.)

---

## 5. Cloudflare DNS / proxy and tunnel connector

### 5a. DNS resolves and is proxied

```powershell
Resolve-DnsName portal.bvtech.org -Type A
```

Expected â€” the returned `IPAddress` values are **Cloudflare** addresses (the record is
**proxied / orange-cloud**), e.g. `104.x.x.x`, `172.64.x.x`, `172.67.x.x`, or `188.114.x.x`.

> **Important:** the public DNS must **NOT** resolve to the Linode origin `45.33.29.100`. If it
> does, the record is grey-clouded (DNS-only) and the tunnel is being bypassed â€” re-enable the
> proxy on the `portal` CNAME/record in the Cloudflare dashboard.

Cross-check the headers come from Cloudflare:

```powershell
curl.exe -sS -I https://portal.bvtech.org/api/health | Select-String -Pattern "server|cf-ray"
```

Expected to include `server: cloudflare` and a `cf-ray:` header.

### 5b. Tunnel connector healthy

```powershell
# Connector container is up
ssh -i "$KEY" deploy@45.33.29.100 "cd /opt/bvtech-portal/opspilot && docker compose ps cloudflared"

# Recent connector logs
ssh -i "$KEY" deploy@45.33.29.100 "cd /opt/bvtech-portal/opspilot && docker compose logs --tail=30 cloudflared"
```

Expected in the logs â€” registered connections to Cloudflare edge data centers and no auth
errors:

```
INF Registered tunnel connection connIndex=0 ... location=...
INF Registered tunnel connection connIndex=1 ... location=...
INF Updated to new configuration ...
```

Bad signs to watch for: `error parsing token`, `Unauthorized`, `failed to connect to the edge`,
or the container in a restart loop -> the `TUNNEL_TOKEN` in `.env` is wrong/expired, or the
public hostname mapping in the Cloudflare Zero Trust dashboard is misconfigured (it should map
`portal.bvtech.org` -> `HTTP` -> `api:8000`).

You can also verify the tunnel status in the dashboard: **Cloudflare Zero Trust -> Networks ->
Tunnels** â€” the tunnel should show **HEALTHY**.

---

## Quick pass/fail summary

| # | Check | Pass condition |
|---|-------|----------------|
| 1 | Public `/api/health` | `{"ok":true,...}` (or Cloudflare challenge â€” confirm UI in browser) |
| 2 | Internal `api` health | `{"ok":true,...}` from inside the container |
| 3 | `docker compose ps` | `db`, `redis`, `api`, `cloudflared` all Up (no `caddy`) |
| 4 | GitHub Actions | Latest `main` run = green; server HEAD == `origin/main` |
| 5 | DNS + tunnel | Resolves to Cloudflare IPs (proxied); `cloudflared` registered/HEALTHY |

If **2** passes but **1** fails -> Cloudflare/tunnel issue (Section 5). If **2** fails -> app/DB
issue (check `docker compose logs api`; confirm migrations ran with
`docker compose run --rm api alembic upgrade head`).
