# BVTech OpsPilot

Secure, cloud-hosted MSP command center, admin dashboard, and client portal for
**BVTech LLC** — evolving toward a lightweight RMM-style platform.

**Current version: v0.7.0** — a unified **RMM + PSA** platform: auth + RBAC +
clients/devices/licenses + audit log + telemetry agent, a monitoring/alerting
engine, billing (MRR & renewals) visibility, a **full SLA-tracked helpdesk**
(threading, assignment, time tracking), an **IT documentation / knowledge base**,
a **server-side automation engine** (event→action rules + notifications), a
**defensive security-posture module** (assessments, findings, scorecard), and a
**governed script library** (approval-gated, consent + audited deployments)
+ deployment scaffold.

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

## What's in the platform

**Foundation (v0.1–v0.2)**
- **Auth**: login, logout-everywhere, MFA setup/confirm, `/api/auth/me`
- **Admin dashboard** (`/dashboard`) and **client portal** (`/portal`), tenant-scoped
- **APIs**: clients, devices, licenses, audit, agent enroll/checkin
- **Support tickets** + client-admin user invites + device check-in history
- **Endpoint agent** (`agent/opspilot_agent.py`): Phase-1 telemetry only, no remote exec
- **Deploy**: Dockerfile, docker-compose (api+db+redis+caddy), Caddyfile, Alembic

**v0.3 — RMM monitoring + MSP business layer**
- **Monitoring/alerting engine**: thresholds → alerts (disk, CPU, RAM, AV,
  patching, low health, offline), idempotent with auto-resolve on recovery.
  - `GET /api/alerts` · `/api/alerts/summary` · ack/resolve · `POST /api/monitoring/sweep`
  - per-client/global thresholds via `GET/PUT /api/alert-policies`
- **Billing visibility**: `GET /api/billing/summary` (MRR/ARR, seat utilization,
  per-client breakdown) and `GET /api/billing/renewals` (renewal calendar).
- **Threaded helpdesk**: `GET/POST /api/tickets/{id}/comments` with client-visible
  vs. internal (staff-only) notes; clients reply on their own tickets in the portal.

**v0.4 — PSA depth + IT documentation**
- **SLA engine**: per-priority response/resolution targets (per-client/global
  overrides), breach + at-risk tracking on every ticket.
  - `GET /api/tickets/sla-summary` · `?breached=true` · `GET/PUT /api/sla-policies`
- **Assignment & workload**: staff-only assignee, `GET /api/staff` with open-ticket
  load, `GET /api/tickets?mine=true`.
- **Time tracking**: `POST/GET /api/tickets/{id}/time` (billable rollup).
- **Knowledge base**: `/api/kb` CRUD — internal vs. client-visible, global vs.
  client-scoped, query-layer visibility enforcement.

**v0.5 — Automation engine**
- **Event→action rules**: triggers (`alert.opened`, `ticket.created`,
  `ticket.sla_breached`) + JSON conditions + safe in-platform actions
  (`create_ticket`, `ack_alert`, `notify`, `assign` incl. auto least-loaded,
  `set_priority`, `add_note`). No remote code execution.
  - `GET/POST/PATCH/DELETE /api/automation/rules` · `GET /api/automation/runs`
  - `POST /api/automation/run-checks` (scheduler tick: offline sweep + SLA-breach firing)
- **In-app notifications**: `GET /api/notifications` (+ `?unread_only`),
  `POST /api/notifications/{id}/read` · `/read-all`. Tenant-scoped.

**v0.6 — Security posture & remediation** (defensive only — track & fix, never exploit)
- **Authorized assessments**: `/api/security/assessments` — engagements that
  require an `authorized_by` party (consent on record).
- **Vulnerability findings**: `/api/security/findings` — severity/CVE/remediation
  workflow; high/critical findings raise an alert and feed the automation engine.
- **Scorecard**: `/api/security/scorecard` — 0–100 posture score per client.
  Clients see only `client_visible` findings + their own score.

**v0.7 — Script library & deployment governance** (safe "scripts to push")
- **Library**: `/api/scripts` — versioned, risk-rated; **disabled by default**,
  owner-only enable.
- **Governed deployment**: `/api/scripts/{id}/deploy` → `/api/deployments` —
  content-pinned snapshot, consent + reason required, **owner approval with
  separation of duties** (approver ≠ requester); reject/cancel paths.
- **Agent job queue**: `GET /api/agent/jobs` + `POST /api/agent/jobs/{id}/result`
  — the agent pulls only its own approved jobs (opt-in runner). No ad-hoc commands.

See `docs/` for deployment and security details, and `docs/ROADMAP.md` for what's
next and the **exact prompt to paste**.

## Built by
Jordan Polasek · BVTech LLC · El Campo, TX · *"Whatever you do, work heartily." — Col 3:23*
