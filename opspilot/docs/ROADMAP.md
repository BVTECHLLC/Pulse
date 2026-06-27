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

## ✅ v0.2 — Client portal + agent prototype hardening
Support-request submission · client-admin scoped invites · device check-in
history + detail · Windows-service agent installer (NSSM) with consent screen.

## ✅ v0.3 (this release) — RMM monitoring + MSP business layer
- **Monitoring/alerting engine**: per-check-in threshold evaluation raising
  disk/CPU/RAM/AV/patch/health alerts; idempotent with auto-resolve on recovery.
- **Offline detection** sweep (scheduler-ready) + ack/resolve workflow + audit.
- **Alert policies**: per-client/global thresholds with built-in fallbacks.
- **Billing visibility**: MRR/ARR rollup, seat utilization, per-client breakdown,
  renewal calendar (reporting only — no charging yet).
- **Threaded helpdesk**: ticket comments with client-visible vs. internal notes;
  clients reply on their own tickets in the portal.

Pulled forward from the old v0.5 plan because monitoring + billing are the core
of an "all-in-one" RMM/MSP tool. M365 and remote support shift down one number.

---

## v0.4 — Microsoft 365 (see docs/M365_PLAN.md)
- Multi-tenant Entra app, least-privilege read-only Graph scopes.
- Per-client connect/consent, encrypted token storage, scheduled sync.
- Auto-populate licenses from `subscribedSkus` (feeds the billing rollup);
  Secure Score + risky sign-ins surfaced as alerts via the existing engine.

## v0.5 — Remote support, safely
- Quick Assist launcher + remote-support helper (agent side, opt-in).
- Script library: **disabled by default**, per-script + per-device enable,
  mandatory approval workflow, full before/after audit, rollback notes.
- NO arbitrary remote code execution — only approved, logged, reversible actions.

## v0.6 — Content workflow + richer dashboards + integrations
- Notifications: email/Slack/Teams/webhook fan-out from the alerting engine.
- Scheduled offline sweep + digest reports (APScheduler/cron).
- Billing exports: Stripe/QuickBooks/Xero/SuperOps.
- Website content workflow: draft → review → approved → Cloudflare Pages deploy,
  with version history and no direct prod overwrite.

---

## ⏭️ EXACT PROMPT TO PASTE NEXT (to build v0.4)

> Continue BVTech OpsPilot. v0.3 is in the repo at `opspilot/` (FastAPI +
> SQLAlchemy + Jinja, Argon2/JWT/TOTP auth, 4-role RBAC, clients/devices/licenses,
> append-only audit, telemetry agent, **monitoring/alerting engine + alert
> policies, billing MRR/renewals, threaded helpdesk**, Docker/Caddy/Tunnel,
> Alembic). Pull the repo, run `python scripts/smoke_test.py` (it should pass),
> then build **v0.4 — Microsoft 365** per `docs/M365_PLAN.md`:
>
> 1. Multi-tenant Entra app registration with least-privilege, read-only Graph
>    scopes; per-client connect/consent flow with encrypted token storage (new
>    `m365_connection` model + migration).
> 2. Scheduled Graph sync: auto-populate `licenses` from `subscribedSkus` (so the
>    billing rollup reflects real M365 seats), pull Secure Score and risky
>    sign-ins.
> 3. Surface M365 risks as alerts through the EXISTING monitoring engine (new
>    alert kinds), so they show on the dashboard alongside device alerts.
>
> Keep the security posture: least privilege, RBAC on every route, audit every
> sensitive action, encrypted secrets at rest, no remote code execution in the
> agent. Extend the smoke test (mock Graph), run it, update the roadmap +
> changelog, package as v0.4, and give me the exact prompt for v0.5.
