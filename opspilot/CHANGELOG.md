# BVTech OpsPilot — Changelog

## v0.3.0 — Monitoring, alerting, billing & helpdesk threading (June 2026)

### Added
- **Monitoring & alerting engine** (`app/services/monitoring.py`): every agent
  check-in is now evaluated against thresholds and raises/auto-resolves alerts
  for disk-full, high CPU/RAM, antivirus-off, patching-behind, and low composite
  health. The engine is idempotent — at most one non-resolved alert per
  (device, kind) — so it never floods. Conditions clearing auto-resolves.
- **Offline detection**: `POST /api/monitoring/sweep` flags devices that have
  gone silent past their policy window (and never-checked-in devices). Built to
  be driven by a scheduler in production; also callable on demand by staff.
- **Alerts API**: `GET /api/alerts` (+ `/summary`), `POST /api/alerts/{id}/ack`,
  `POST /api/alerts/{id}/resolve`. Tenant-scoped; mutation is staff-only; every
  ack/resolve audited.
- **Alert policies**: per-client or global threshold config via
  `GET/PUT /api/alert-policies` (staff only) with sane built-in fallbacks.
- **Billing visibility**: `GET /api/billing/summary` (MRR/ARR rollup, per-client
  breakdown, seat utilization) and `GET /api/billing/renewals` (upcoming +
  overdue renewal calendar). Reporting only — no charging. Clients see only
  their own numbers. License create now accepts `renewal_date`.
- **Helpdesk threading**: `GET /api/tickets/{id}`, `GET/POST
  /api/tickets/{id}/comments`. Comments can be client-visible or **internal**
  (staff-only notes). Clients can never read or create internal notes — a client
  posting `internal=true` is silently downgraded.
- **Dashboard**: new Alerts, Tickets (with conversation + status control), and
  Billing tabs; overview gains active-alert, open-ticket, MRR, utilization, and
  renewal stats. **Client portal**: active-alerts panel and a two-way ticket
  conversation so clients can follow up on their own requests.
- New Alembic migration (`alerts`, `alert_policies`, `ticket_comments`).
- Smoke test extended to cover the full alert lifecycle, offline sweep, policy
  upsert, ticket threading + internal-note isolation, and billing rollup/scope.

### Security
- All new mutating routes are RBAC-guarded; alert ack/resolve, policy edits, and
  the sweep are staff-only and audited.
- Internal ticket notes are filtered at the query layer for client users, not
  just hidden in the UI.
- Billing and alert listings enforce the same per-client tenant scope as the
  rest of the app. The agent remains telemetry-only — no remote execution path.

## v0.2.0 — Portal writes, tickets, history (June 2026)

### Added
- **Support tickets**: clients submit requests from the portal ("Request Support"
  form); staff list/triage and update status (open → in_progress → resolved → closed).
  Tenant-isolated; every create/update audited.
- **Client-admin user invites**: a CLIENT_ADMIN can create CLIENT_VIEWER/CLIENT_ADMIN
  users in *their own* client only. Privilege escalation to staff roles is blocked
  (verified in smoke test). Temp password issued once, never stored in plaintext.
- **Device check-in history**: every agent check-in is now recorded to
  `device_checkins`; `GET /api/devices/{id}/history` returns the trend. Latest
  summary still denormalized on `devices` for fast lists.
- **Agent-as-a-service**: `agent/install_service.bat` installs the telemetry agent
  as a Windows service (NSSM), with an explicit consent prompt and psutil install.
- New Alembic migration for `support_tickets` + `device_checkins`.
- Smoke test extended to cover tickets, invites, escalation-block, and history.

### Security
- Client admins are hard-capped to client-side roles in their own org.
- Ticket listing and history both enforce per-client scope.
- Agent service still telemetry-only — no remote execution path exists.

## v0.1.0 — Foundation (June 2026)
First cloud-native release. Replaces the local-only Command Center's no-auth,
single-user, plaintext-secret model with a real multi-tenant, authenticated,
audited platform.

### Added
- **FastAPI backend** with auto-validation and security middleware.
- **Auth**: Argon2id passwords, JWT access tokens, DB-backed revocable refresh
  sessions, TOTP MFA (setup/confirm), login rate limiting, generic auth errors.
- **RBAC**: OWNER / TECH / CLIENT_ADMIN / CLIENT_VIEWER with per-client tenant
  isolation enforced at the query layer.
- **Resources**: clients, devices, licenses APIs + admin dashboard and client
  portal shells (Jinja + vanilla JS, BVTech navy/periwinkle theme).
- **Append-only audit log** capturing actor, role, target, client, IP, outcome.
- **Endpoint agent (Phase 1)**: signed client-scoped enrollment tokens, per-device
  hashed agent keys, telemetry-only check-in with server-side health scoring.
  No remote execution exists by design.
- **Deploy**: Dockerfile (non-root), docker-compose (api+db+redis+caddy),
  Caddyfile, Cloudflare Tunnel instructions, Alembic migrations (+ initial revision).
- **Docs**: README, DEPLOYMENT, SECURITY checklist, M365_PLAN, ROADMAP.
- **Smoke test** covering login → client → license → enroll → check-in → audit →
  unauth-blocked.

### Security posture
- All secrets via env; `.env` git-ignored; separate keys for sessions vs agent.
- Security headers (HSTS/CSP/nosniff/frame-deny), Secure+HttpOnly+SameSite cookies.
- Cloudflare Tunnel option exposes zero inbound ports.

### Known limitations (by design, see ROADMAP)
- Dev uses SQLite; production uses Postgres via compose.
- No M365, billing, remote support, or content workflow yet (v0.3–v0.5).
- Rate limiter is in-memory (single worker); move to Redis for multi-worker prod.
