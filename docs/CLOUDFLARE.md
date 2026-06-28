# Cloudflare Tunnel + Security Tuning

How **BVTech OpsPilot** is published to the internet with **zero open inbound ports**,
and how to stop Cloudflare's bot challenges from breaking the JSON API and the
Windows agent.

- **Domain:** `bvtech.org` (managed in Cloudflare DNS)
- **Public hostname:** `portal.bvtech.org`
- **Origin:** the `api` container, `api:8000`, plain HTTP (TLS terminates at Cloudflare)
- **Tunnel name:** `bvtech-portal` (remote-managed / dashboard-managed)
- **Open inbound ports on the Linode:** SSH `22` only. No `80`/`443`.

---

## 1. How the tunnel is wired

We use a **remote-managed** Cloudflare Tunnel: the config (routes, hostnames)
lives in the Cloudflare dashboard, and the server only needs a `TUNNEL_TOKEN`.
`cloudflared` runs as a Docker Compose service alongside the app.

### 1.1 The cloudflared service

`cloudflared` is added on the server via `opspilot/docker-compose.override.yml`.
This file is **server-only and NOT committed** (it survives `git pull` because git
never touches it).

```yaml
# opspilot/docker-compose.override.yml  (lives ONLY on the server, not in git)
services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      - TUNNEL_TOKEN=${TUNNEL_TOKEN}
    depends_on:
      - api
```

`TUNNEL_TOKEN` is read from `opspilot/.env` (chmod 600), same file the `api`
service reads. **Never** commit the token or paste it into any tracked file.

Because Compose auto-merges `docker-compose.yml` + `docker-compose.override.yml`,
the normal deploy commands bring `cloudflared` up automatically:

```bash
cd /opt/bvtech-portal/opspilot
docker compose up -d            # starts db, redis, api, cloudflared
docker compose ps               # cloudflared should be "running"/"healthy"
docker compose logs -f cloudflared
```

> Note: the `caddy` service in `docker-compose.yml` is **deliberately unused** â€”
> the tunnel reaches `api:8000` directly, so there is no reverse proxy and no
> exposed web port.

### 1.2 Creating the tunnel (one-time, done in the dashboard)

If you ever need to recreate it:

1. Cloudflare Dashboard -> **Zero Trust** -> **Networks** -> **Tunnels**.
2. **Create a tunnel** -> connector **Cloudflared** -> name it `bvtech-portal` -> **Save**.
3. On the install screen, **copy the token** (the long `eyJ...` string from the
   `cloudflared ... run <TOKEN>` command). Put it in `opspilot/.env`:
   ```
   TUNNEL_TOKEN=eyJ...    # do not commit this
   ```
4. Restart the connector so it picks up the token:
   ```bash
   cd /opt/bvtech-portal/opspilot
   docker compose up -d cloudflared
   ```
5. Back in the tunnel page, the connector should show **HEALTHY**.

### 1.3 Routing the public hostname

In the tunnel's **Public Hostname** tab -> **Add a public hostname**:

| Field        | Value               |
|--------------|---------------------|
| Subdomain    | `portal`            |
| Domain       | `bvtech.org`        |
| Path         | *(leave empty)*     |
| Service Type | `HTTP`              |
| URL          | `api:8000`          |

Save. Cloudflare auto-creates the proxied (orange-cloud) `CNAME` for
`portal.bvtech.org` -> `<tunnel-id>.cfargotunnel.com`. No manual DNS record and
**no firewall change** are needed.

### 1.4 Why COOKIE_SECURE=true is correct

Visitors reach `https://portal.bvtech.org`; Cloudflare terminates HTTPS and
forwards plain HTTP to `api:8000` over the encrypted tunnel. The browser still
sees HTTPS, so the session cookie must carry the `Secure` flag. Keep:

```
COOKIE_SECURE=true     # in opspilot/.env â€” correct behind Cloudflare HTTPS
```

(The app trusts `CF-Connecting-IP` for the real client IP â€” see Â§4.)

---

## 2. The problem: bot challenges break the API and the agent

Cloudflare's **Bot Fight Mode** and **Managed Challenge** ("Just a momentâ€¦"
interstitial) assume a real browser that runs JavaScript and solves a challenge.
Two of our clients can't do that:

- The **JSON API** (`/api/*`) â€” programmatic callers, health checks, webhooks.
- The **Windows agent** â€” a headless client with no JS engine; it hits enrollment
  and reporting endpoints under `/api`.

If challenged, these get the HTML `Just a moment...` page (HTTP `403`/`503`)
instead of JSON, and silently break. The fix is to **skip the managed challenge
for `/api/*`** while keeping protection on the human login/portal UI.

---

## 3. Dashboard steps to fix it

Do **both** parts. Part A reduces blanket bot challenges; Part B carves out
`/api/*` precisely.

### 3.1 Part A â€” Turn off Bot Fight Mode (and sane Security Level)

1. Dashboard -> select zone **bvtech.org**.
2. **Security** -> **Bots**.
3. Set **Bot Fight Mode** to **Off**.
   (Bot Fight Mode is account-wide and ignores WAF skip rules, so it must be off â€”
   you cannot exempt `/api` from it with a rule.)
4. Optional but recommended â€” **Security** -> **Settings**:
   set **Security Level** to **Medium** (or **Essentially Off** if you still see
   false challenges on the API host). Security Level only affects threat-score
   based challenges; the WAF rule in Part B handles the rest.

### 3.2 Part B â€” WAF custom rule: SKIP managed challenge for /api

1. Dashboard -> zone **bvtech.org** -> **Security** -> **WAF** -> **Custom rules**.
2. **Create rule**.
   - **Rule name:** `Skip challenge for API`
   - **Field:** `URI Path`  **Operator:** `starts with`  **Value:** `/api`
     - Expression Editor equivalent:
       ```
       (starts_with(http.request.uri.path, "/api"))
       ```
     - To also pin it to the portal host, AND it together:
       ```
       (http.host eq "portal.bvtech.org" and starts_with(http.request.uri.path, "/api"))
       ```
   - **Action:** **Skip**
   - Under **WAF components to skip**, enable:
     - **All managed rules** (managed challenge / WAF managed rulesets)
     - **Super Bot Fight Mode** (if shown on your plan)
   - Under **More components to skip** also check **Browser Integrity Check** if
     present (it can also bounce non-JS clients).
3. **Deploy**.
4. Make sure this rule sits **above** any broader challenge/block rules â€” Skip
   rules are evaluated in order and stop further matching for `/api/*`.

> Result: `/api/*` (health, agent enroll/report, JSON endpoints) is never
> challenged. Everything else â€” `/`, `/login`, `/dashboard`, `/portal` â€” keeps
> normal protection, so the human login UI still benefits from the managed
> challenge when Cloudflare deems a request suspicious.

### 3.3 (Optional) Configuration Rule alternative

Instead of/in addition to a WAF custom rule, you can use
**Rules -> Configuration Rules** to set, for `URI Path starts with /api`,
**Security Level = Essentially Off** and **Browser Integrity Check = Off**.
The WAF Skip rule in Â§3.2 is the more complete fix; the Configuration Rule is a
lighter-touch supplement.

---

## 4. App-level rate limiting (keep this)

The app does its own per-client rate limiting keyed on the **real** client IP.
Because requests arrive via Cloudflare, the origin's socket IP is a Cloudflare
edge address â€” the true visitor IP is in the **`CF-Connecting-IP`** header.

- Keep the app reading `CF-Connecting-IP` (falling back to `X-Forwarded-For`) so
  rate limits and audit logs attribute requests to the actual client, not to
  Cloudflare.
- This app-level limiter is separate from Cloudflare's WAF Rate Limiting and
  stays in effect for `/api/*` even though we skip the managed *challenge* there.
- If you later add Cloudflare **Rate Limiting Rules** for `/api/login` or agent
  endpoints, that's complementary â€” Skip (Â§3.2) only skips managed challenges and
  managed rules, not rate-limiting rules.

---

## 5. Verifying

From any machine (your Windows box is fine â€” `curl.exe` ships with Windows):

### 5.1 Health endpoint should return JSON, not an interstitial

```bash
curl -s https://portal.bvtech.org/api/health
# expected:
# {"ok":true, ...}
```

If instead you see HTML containing **`Just a moment...`** (or
`cf-mitigated: challenge` in the headers), the managed challenge is still firing
â€” recheck Part A (Bot Fight Mode off) and that the WAF Skip rule matches `/api`
and is ordered above other rules.

### 5.2 Inspect headers / detect a challenge

```bash
curl -sI https://portal.bvtech.org/api/health
# A challenged response looks like:
#   HTTP/2 403            (or 503)
#   cf-mitigated: challenge
#   content-type: text/html; charset=UTF-8
# A good response:
#   HTTP/2 200
#   content-type: application/json
```

```bash
# Full body of any challenge (look for the phrase):
curl -s https://portal.bvtech.org/api/health | findstr /i "Just a moment"
#   (PowerShell)  curl.exe -s https://portal.bvtech.org/api/health | Select-String "Just a moment"
```

### 5.3 The human UI should still be reachable

```bash
curl -sI https://portal.bvtech.org/login
# 200 with content-type: text/html  (login page renders;
# a managed challenge may appear only if Cloudflare flags the request)
```

### 5.4 Simulate the agent (no JS, no cookies)

```bash
curl -s -X POST https://portal.bvtech.org/api/agent/enroll \
  -H "Content-Type: application/json" \
  -d '{"secret":"<AGENT_ENROLL_SECRET>"}'
# should reach the app (JSON response / app-level error),
# NOT the "Just a moment" HTML page
```

---

## 6. Quick reference

| Item                         | Value / Setting                                  |
|------------------------------|--------------------------------------------------|
| Public hostname              | `portal.bvtech.org` -> HTTP -> `api:8000`        |
| Tunnel name                  | `bvtech-portal` (remote-managed)                 |
| Connector                    | `cloudflared` Compose service (override.yml)     |
| Token source                 | `TUNNEL_TOKEN` in `opspilot/.env` (uncommitted)  |
| Open inbound ports           | `22` (SSH) only â€” no `80`/`443`                  |
| Bot Fight Mode               | **Off**                                          |
| Security Level               | Medium (or Essentially Off if needed)            |
| WAF rule                     | Skip managed challenge where `URI Path starts with /api` |
| Cookie flag                  | `COOKIE_SECURE=true` (correct behind CF HTTPS)   |
| Real client IP               | `CF-Connecting-IP` (used by app rate limiter)    |
| Challenge signature          | `Just a moment...` body / `cf-mitigated: challenge` header |
