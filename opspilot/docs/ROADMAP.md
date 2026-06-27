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

## ✅ v0.4 (this release) — PSA depth + IT documentation
- **SLA engine**: per-priority response/resolution targets with per-client/global
  overrides; due dates stamped on create, breach + at-risk tracking on every
  ticket, `sla-summary` for the dashboard.
- **Assignment & workload**: staff-only assignee, staff directory with open-ticket
  load, "my queue" filter, editable priority.
- **Time tracking**: billable/non-billable minutes per ticket with rollups.
- **Knowledge base / IT docs**: internal vs. client-visible, global vs.
  client-scoped, with query-layer visibility enforcement.

This makes Pulse a genuine unified **RMM + PSA** platform (the SuperOps niche):
monitoring + assets on the RMM side, SLA helpdesk + time + docs on the PSA side.

## ✅ v0.5 (this release) — Automation engine
- **Event→action rules**: triggers (alert opened, ticket created, SLA breached) +
  JSON conditions + safe in-platform actions (open/assign/prioritize/note tickets,
  acknowledge alerts, notify). Per-client or global scope; enable/disable; full
  run log + audit. No remote code execution — actions only touch OpsPilot records.
- **Scheduler tick** (`run-checks`): offline sweep + SLA-breach firing (deduped).
- **In-app notifications** with unread tracking, raised by the `notify` action.

The automation engine is the RMM/PSA force-multiplier: it ties monitoring, the
SLA helpdesk, and notifications together so routine response happens without a
human in the loop — while staying safe (no endpoint code execution) and fully
audited.

---

## v0.6 — Microsoft 365 (see docs/M365_PLAN.md)
- Multi-tenant Entra app, least-privilege read-only Graph scopes.
- Per-client connect/consent, encrypted token storage, scheduled sync.
- Auto-populate licenses from `subscribedSkus` (feeds the billing rollup);
  Secure Score + risky sign-ins surfaced as alerts via the existing engine
  (which automation rules can then act on automatically).

## v0.7 — Remote support, safely
- Quick Assist launcher + remote-support helper (agent side, opt-in).
- Script library: **disabled by default**, per-script + per-device enable,
  mandatory approval workflow, full before/after audit, rollback notes.
- NO arbitrary remote code execution — only approved, logged, reversible actions.

## v0.8 — Content workflow + richer dashboards + integrations
- Notification channels: email/Slack/Teams/webhook fan-out (a new `notify`
  channel behind the existing automation `notify` action + Notification model).
- Scheduled offline sweep + digest reports (APScheduler/cron driving run-checks).
- Billing exports + invoicing from time entries: Stripe/QuickBooks/Xero.
- Website content workflow: draft → review → approved → Cloudflare Pages deploy,
  with version history and no direct prod overwrite.

---

## ⏭️ EXACT PROMPT TO PASTE NEXT (to build v0.6)

> Continue BVTech OpsPilot. v0.5 is in the repo at `opspilot/` (FastAPI +
> SQLAlchemy + Jinja, Argon2/JWT/TOTP auth, 4-role RBAC, clients/devices/licenses,
> append-only audit, telemetry agent, monitoring/alerting engine + policies,
> billing MRR/renewals, SLA-tracked helpdesk with assignment + time tracking,
> knowledge base, **a server-side automation engine (event→action rules + in-app
> notifications)**, Docker/Caddy/Tunnel, Alembic). Pull the repo, run
> `python scripts/smoke_test.py` (it should pass), then build **v0.6 — Microsoft
> 365** per `docs/M365_PLAN.md`:
>
> 1. Multi-tenant Entra app registration with least-privilege, read-only Graph
>    scopes; per-client connect/consent flow with encrypted token storage (new
>    `m365_connection` model + migration).
> 2. Scheduled Graph sync: auto-populate `licenses` from `subscribedSkus` (so the
>    billing rollup reflects real M365 seats), pull Secure Score and risky
>    sign-ins.
> 3. Surface M365 risks as alerts through the EXISTING monitoring engine (new
>    alert kinds) so the dashboard shows them alongside device alerts — and the
>    automation engine can act on them (e.g. risky-sign-in → open a ticket).
>
> Keep the security posture: least privilege, RBAC on every route, audit every
> sensitive action, encrypted secrets at rest, no remote code execution in the
> agent. Extend the smoke test (mock Graph), run it, update the roadmap +
> changelog, package as v0.6, and give me the exact prompt for v0.7.
