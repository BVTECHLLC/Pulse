# BVTech OpsPilot

Secure, cloud-hosted MSP command center, admin dashboard, and client portal for
**BVTech LLC** — evolving toward a lightweight RMM-style platform.

**Current version: v0.1.0** — auth + RBAC + clients/devices/licenses + audit log
+ telemetry-only endpoint agent + deployment scaffold.

---

## Architecture

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **FastAPI** (Python) | Keeps the existing Command Center integration classes reusable; async; auto-validation |
| Database | **Postgres 16** | Real multi-tenant store; Alembic migrations |
| Cache/limits | **Redis** | Session/rate-limit backing (optional in v0.1) |
| Frontend | **Jinja + vanilla JS** | Ships fast, no build step; clean upgrade path to Next.js |
| Auth | Argon2id + JWT + DB sessions + TOTP MFA | Revocable sessions, MFA-ready |
| Proxy/TLS | **Caddy** (auto-HTTPS) or **Cloudflare Tunnel** | Tunnel keeps the VPS with *zero* exposed ports |
| Deploy | **Docker Compose** | Reproducible; one-command bring-up |

### Roles (RBAC)
- **OWNER** — BVTech owner/admin, full control
- **TECH** — BVTech technician, operational (no destructive config)
- **CLIENT_ADMIN** — a client's admin, scoped to their org
- **CLIENT_VIEWER** — client read-only

Client users can only ever see their own `client_id`'s data — enforced at the query layer.

---

## Local development

```bash
cd pulse
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# For local dev, edit .env:
#   ENV=development
#   DATABASE_URL=sqlite:///./pulse_dev.db
#   COOKIE_SECURE=false
#   SECRET_KEY / AGENT_ENROLL_SECRET = any long random strings
#   BOOTSTRAP_ADMIN_PASSWORD=ChooseOne123!

uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 — log in as `admin@bvtech.org`. In development the
tables auto-create; in production you run Alembic migrations instead.

### Quick sanity test
```bash
python scripts/smoke_test.py     # runs the full enroll→checkin→audit flow
```

---

## What's in v0.1

- **Auth**: login, logout-everywhere, MFA setup/confirm, `/api/auth/me`
- **Admin dashboard** (`/dashboard`): overview stats + clients/devices/licenses/audit tabs
- **Client portal** (`/portal`): read-only, scoped to the signed-in client
- **APIs**: clients, devices, licenses, audit, agent enroll/checkin
- **Endpoint agent** (`agent/opspilot_agent.py`): Phase-1 telemetry only, no remote exec
- **Deploy**: Dockerfile, docker-compose (api+db+redis+caddy), Caddyfile, Alembic
- **Docs**: deployment, security checklist, M365 plan, roadmap

See `docs/` for deployment and security details, and `docs/ROADMAP.md` for
v0.2 → v0.5 and the **exact prompt to paste next**.

## Built by
Jordan Polasek · BVTech LLC · El Campo, TX · *"Whatever you do, work heartily." — Col 3:23*
