# BVTech OpsPilot — Changelog

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
