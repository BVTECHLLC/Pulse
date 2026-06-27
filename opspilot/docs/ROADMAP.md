# BVTech OpsPilot — Roadmap

## ✅ v0.1 (this release) — Foundation
Auth + MFA + 4-role RBAC · clients/devices/licenses · append-only audit log ·
Phase-1 telemetry agent · Docker/Caddy/Tunnel deploy · Alembic migrations · docs.

**Status of every piece:**
- Working & tested end-to-end: auth, RBAC, client/license/device APIs, agent
  enroll + check-in (with health scoring), audit log, security headers, rate limit.
- Scaffolded, needs your infra to fully exercise: Docker Compose (needs a Docker
  host), Postgres (dev uses SQLite), Cloudflare DNS/Tunnel (needs your account).
- Intentionally absent (later phases): client self-service portal writes, M365,
  remote support, billing integrations, content workflow.

Nothing is broken. SQLite is the dev fallback; production is Postgres via compose.

---

## v0.2 — Client portal + agent prototype hardening
- Client portal: support-request submission, security recommendations view,
  onboarding documents list.
- Self-service: client admin can invite client_viewer users (scoped).
- Agent: package as a Windows service (NSSM or pywin32), build the installer with
  consent screen + branding, add psutil to the bundle, signed-installer plan.
- Device detail page (per-device history, health trend).

## v0.3 — Microsoft 365 (see docs/M365_PLAN.md)
- Multi-tenant Entra app, least-privilege read-only Graph scopes.
- Per-client connect/consent, encrypted token storage, scheduled sync.
- Auto-populate licenses from `subscribedSkus`; Secure Score + risky sign-ins.

## v0.4 — Remote support, safely
- Quick Assist launcher + remote-support helper (agent side, opt-in).
- Script library: **disabled by default**, per-script + per-device enable,
  mandatory approval workflow, full before/after audit, rollback notes.
- NO arbitrary remote code execution — only approved, logged, reversible actions.

## v0.5 — Billing visibility + content workflow + dashboards
- Billing module: MRR rollup, renewal calendar, invoice status placeholders,
  later Stripe/QuickBooks/Xero/SuperOps export.
- Website content workflow: draft → review → approved → Cloudflare Pages deploy
  via the existing `cloudflare_pages_deploy.py` deployer (ported from the
  Command Center), with version history and no direct prod overwrite.
- Richer dashboards: alerts, backup status, security posture scoring.

---

## ⏭️ EXACT PROMPT TO PASTE NEXT (to build v0.2)

> Continue BVTech OpsPilot. v0.1 is in the repo at `pulse/` (FastAPI + SQLAlchemy +
> Jinja, Argon2/JWT/TOTP auth, 4-role RBAC, clients/devices/licenses, append-only
> audit log, Phase-1 telemetry agent, Docker/Caddy/Tunnel deploy, Alembic). Pull
> the repo, confirm the smoke test passes, then build **v0.2**:
>
> 1. Client portal writes: a "Request Support" form that creates a `support_ticket`
>    row (new model + migration), visible to staff on the dashboard.
> 2. Client-admin user management: invite/create CLIENT_VIEWER users scoped to
>    their own client_id only, with audit entries.
> 3. Device detail page with check-in history (new `device_checkin` table storing
>    each snapshot; keep the latest summary on `devices`).
> 4. Package the Windows agent as a service (NSSM-based install script) with a
>    branded consent screen and psutil bundled; add a signed-installer plan doc.
>
> Keep the same security posture: least privilege, RBAC guards on every new route,
> audit every sensitive action, no remote code execution in the agent. Update the
> smoke test to cover the new flows, run it, and update the roadmap + changelog.
> When done, package as v0.2 and give me the exact prompt for v0.3.
