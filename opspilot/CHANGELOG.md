# BVTech OpsPilot — Changelog

## v0.43.0 — Native CRM: our own lead/contact pipeline (June 2026)
- **We are the PSA/CRM now** — a native CRM replaces SuperOps' CRM side.
  New `crm_contacts` + `crm_activities` tables (Alembic migration verified
  up/down/up). `services/crm.py` + `routes/crm.py` + a **🤝 CRM** tab.
- Pipeline by status (new → contacted → qualified → proposal → customer / lost),
  contact CRUD with search, an **activity timeline** (note/call/email/meeting,
  auto-logged on create & status change), one-click **📞 Dialpad call** from a
  contact, and **Convert → Client** which spins up a real managed Client and
  links it (ties the CRM straight into the client list).
- Staff-only; deletes OWNER-only; every touch audited. Verified end-to-end:
  pipeline, CRUD, timeline, status validation, convert (+ conflict), RBAC.

## v0.42.0 — Command Center archived + Tactical RMM connector (June 2026)
- Archived the full **BVTech MSP Command Center v32.1** suite into `command-center/`
  as the porting source-of-truth, with `command-center/PORTING.md` mapping every
  module → its native Pulse port status. (No secrets — all modules load from env.)
- **Pulse is the MSP suite** (own agent + monitoring = native RMM). Added an
  **optional Tactical RMM connector** to bridge/migrate a legacy RMM:
  `services/tacticalrmm.py` (stdlib HTTP, **SSRF-guarded** user-supplied URL via
  the netdiag resolver) + `routes/rmm.py` + a new **🖥️ RMM** tab (dashboard
  rollup, agents, active alerts; reboot / resolve / service / update actions).
  Reads are staff; mutating actions OWNER-only + audited. Creds encrypted in the
  vault. Verified: SSRF rejection of private/loopback/metadata URLs, masked
  credential reads, RBAC.

## v0.41.0 — Integrations hub: secure mailbox, publishers & auto-dialer (June 2026)
- **Secure credential vault** (`services/secure_config.py`): integration secrets
  are entered in the Settings UI and stored **Fernet-encrypted at rest** (same key
  as cached M365 tokens). Reads return a masked hint (`••••1234`) + a `configured`
  flag and **never echo a secret back**; partial updates preserve untouched fields.
  Singleton "platform connection" per provider — multi-tenant ready.
- **📬 Microsoft 365 secure mailbox** — read & send your own mail from Pulse via
  app-only Graph (Mail.Read / Mail.Send). New Mailbox tab: folders, message list,
  reading pane (HTML mail sandboxed in an iframe), compose & reply. Credentials
  (tenant/app id/secret + default mailbox) configured in Settings → Mailbox.
  `GET/PUT /api/mailbox/settings`, `/test`, `/folders`, `/messages[/{id}]`,
  `/send`, `/messages/{id}/read`.
- **💼 LinkedIn auto-publisher** — store token + person URN (encrypted) and **post
  to LinkedIn now** straight from the portal (UGC share API).
  `PUT /api/publishers/linkedin`, `POST /api/publishers/linkedin/post`.
- **🌐 Website auto-publisher settings** — BVTech.org & **JordanPolasek.com**
  schedule/persona/topics/enabled (reputation-management surface for the daily
  publisher). `PUT /api/publishers/website/{bvtech|jp}`, `GET /api/publishers/settings`.
- **📞 Dialpad auto-dialer (click-to-call)** — store API key/user/caller-ID
  (encrypted); rings your Dialpad device then dials the number.
  `PUT /api/comms/dialpad/settings`, `POST /api/comms/dialpad/call`.
- New **🛠️ Settings** tab ties it together. All endpoints staff-scoped (saves are
  OWNER-only), audited, and reachable. Verified end-to-end in the smoke test:
  encrypted round-trips, masked reads, partial-update retention, RBAC, and that
  mail/call paths reach the upstream API.

## v0.40.0 — SLA performance analytics (June 2026)
- `GET /api/analytics/sla-performance?days=90` — the metrics MSPs report on:
  **response & resolution SLA attainment %**, **avg response/resolution time**,
  and a **per-priority breakdown**, over a rolling window. Tenant-scoped read
  model (`services/analytics.py`), feeds QBRs. Verified: attainment math,
  averages, by-priority, scoping.

## v0.39.0 — Maintenance windows: suppress alerts during planned work (June 2026)
- Schedule a **maintenance window** (per-device or whole-client) and the
  monitoring engine **suppresses all alerting** inside it — patching, reboots and
  migrations no longer page anyone. Telemetry is still recorded; only alerting
  pauses. Offline detection respects windows too.
- `POST/GET/DELETE /api/maintenance-windows` (staff manage, tenant-scoped reads),
  new `maintenance_windows` table (Alembic migration verified up/down/up on
  SQLite). Verified: a 99%/AV-off/behind check-in raises 0 alerts during a window
  and 6 after it's deleted; validation + RBAC.

## v0.38.0 — SLA breach auto-escalation (June 2026)
- When a ticket newly breaches its SLA, the run-checks tick now **escalates** it,
  not just flags it: bumps priority one level (low→normal→high→urgent, capped),
  posts an **internal note** documenting the breach, and raises a **critical
  notification** (in-app + channel fan-out). De-duplicated per breach.
- Deliberately does NOT re-stamp SLA targets on escalation (the ticket stays
  breached — no clock-resetting). `services/sla_escalation.py`; wired into
  `/api/automation/run-checks` (returns `escalated` count). Verified end-to-end.

## v0.37.0 — Bulk alert triage (June 2026)
- Triage an alert storm in one click: select alerts (or "select all") on the
  Alerts tab and **Ack** or **Resolve** them in bulk.
- `POST /api/alerts/bulk {ids, action}` (OWNER/TECH) — skips missing/already-
  resolved ids, audited, returns per-id results. Verified incl. validation.

## v0.36.0 — Action Center goes operational: one-click create-ticket (June 2026)
- Every Action Center item now has a **+ Ticket** button: turn any signal (a
  predicted disk-fill, an SLA breach, an open finding, a contract renewal) into a
  tracked **support ticket in one click**. Severity maps to priority
  (critical→urgent … low→low), SLA targets are stamped, and automation fires —
  identical to a hand-created ticket.
- `POST /api/action-center/create-ticket` (OWNER/TECH), audited and tenant-scoped.
- Verified: severity→priority mapping, SLA stamped, ticket really created, RBAC.

## v0.35.0 — Daily auto-publishing pipeline for BVTech.org (June 2026)

### Added — hands-off daily security advisories, live on the site
- `automation/` toolkit that lets Claude Code (headless, on the Linode box)
  write a fresh, fact-checked security advisory each day in Jordan's voice and
  publish it live to bvtech.org:
  - `bvtech_persona.md` — the writing voice/structure distilled from the
    existing posts (calm, SMB-focused, "⚡ 60-Second Version" box, sign-off).
  - `daily_blog_prompt.md` — the daily task: web-search a real current story,
    verify across sources, write, and publish (never fabricate, never leak data).
  - `daily_blog.sh` — cron wrapper: locks, pulls both repos, runs headless
    Claude with web+write+bash tools, and has a safety-net publish.
  - `SETUP.md` — full runbook: Cloudflare Pages ← GitHub auto-deploy, a Linode
    deploy key for push, Claude Code install, and the cron schedule.
- `scripts/publish_post.py` now also inserts the new post into `sitemap.xml`
  (idempotent) and stages it for the commit, so posts get crawled immediately.

### Notes
- Publishing runs from the **Linode box's** deploy key (this session's GitHub
  access is scoped to `bvtechllc/pulse`); the box is the publisher, which is the
  correct, secure design for unattended deploys.
- Verified: the JSON-driven publish path end-to-end against a real site copy
  (pixel-perfect clone + sitemap update) and `daily_blog.sh` shell syntax.

## v0.34.0 — Content Studio: publish on-brand pages to BVTech.org (June 2026)

### Added — generate blog/advisory pages that match bvtech.org exactly
- `services/content_studio.py` turns a title + lightweight-markdown body into a
  finished, SEO-complete HTML page. Two modes:
  - **Template-clone (pixel-perfect):** clones the newest real bvtech.org
    `/blog/*.html` as the skeleton and transplants the new `<title>`, meta
    description, canonical/OG URLs, schema.org JSON-LD, `<h1>`, dateline, and
    article body — keeping the live site's header, footer, fonts, and CSS.
  - **Standalone:** a self-contained on-brand page (BVTech navy/peri/gold,
    Poppins+Lato) so previews work anywhere before the website repo is wired.
- Full SEO out of the box: title/description, Open Graph, canonical, and
  BlogPosting + BreadcrumbList JSON-LD. Public-safe by construction — no tenant
  data is ever embedded.
- **Content Studio** portal tab (staff-only): compose, **live-preview exactly as
  it publishes** (iframe), and **stage** a post with its computed publish path.
- `POST /api/content/render | /preview | /stage` (OWNER/TECH only).
- `scripts/publish_post.py` — the CLI the daily job runs on the Linode box:
  renders + writes `<website-repo>/blog/<slug>.html`, with optional
  `--git` commit/push so Cloudflare Pages auto-deploys.
- Loosened the portal CSP to allow `frame-src 'self' blob:` so the preview
  iframe renders; added the Lato web font for typography parity with the site.

### Verified
- Generator (both modes) against a real bvtech.org blog skeleton, the publish
  CLI (dry-run + write), the full smoke suite, and the live portal tab headless
  (compose → preview → stage, zero console/CSP errors).

## v0.33.0 — Predictive Foresight + Client Health + Command Palette (June 2026)

### Added — Predictive Foresight: see problems before they happen
- A new engine (`services/foresight.py`) trends each device's check-in history
  with least-squares regression to **project the future**: days-until-disk-full,
  rising RAM/CPU pressure, and health trajectory (improving / stable / degrading).
- `GET /api/devices/{id}/forecast` (per-device) and `GET /api/foresight`
  (fleet-wide, severity-ordered). Honest about uncertainty — it only projects
  with enough history and a real trend.
- **Statistical anomaly detection**: z-scores the latest reading against each
  device's own baseline to catch *sudden* spikes (distinct from slow trends) —
  a spike must be both statistically extreme (≥3σ) and absolutely high, so it
  never cries wolf. Surfaces in the forecast (`anomalies`) and Action Center.
- Predictions flow straight into the **Action Center**: "Disk full in ~3 days"
  shows up as a ranked action *before* it's a 2 a.m. outage. Read-only, no agent
  changes, no new tables.

### Added — Client Health Score: one explainable number per client
- `services/client_health.py` rolls endpoint health, patch compliance, uptime,
  active alerts, SLA adherence, security findings, and ticket backlog into a
  weighted **0-100 score** with a letter grade, a **churn-risk** band
  (healthy / watch / high), and the **specific factors** pulling it down.
- `GET /api/clients/health` (portfolio, worst-first) and
  `GET /api/clients/{id}/health`. New **Client Health board** on the Clients tab
  with a portfolio gauge and per-client cards.

### Added — Command Palette (⌘K / Ctrl-K)
- Power-user launcher: fuzzy-jump to any section, run quick actions (deploy
  agent, add client, run monitoring sweep, open foresight), and search every
  entity — all from the keyboard, with ↑↓ + ↵ navigation.

### Notes
- All three are **tenant-scoped + RBAC** (staff see the portfolio; a client user
  only ever sees their own org) and pure read models.
- Verified: backend math, full smoke suite, and the live dashboard rendered
  headless (health board + command palette, zero console errors).

## v0.32.0 — Action Center: the "what to do next" brain (June 2026)

### Added — one ranked, explainable feed across every module
- New **Action Center** (`GET /api/action-center`, dedicated dashboard tab) fuses
  every signal we collect into a single prioritized list of what a tech should do
  next, across the whole book of business: **SLA breaches & at-risk tickets**,
  **active alerts**, **offline devices**, **AV disabled**, **low health**,
  **patch-behind**, **open high/critical security findings**, **warranties
  expiring**, **contracts up for renewal**, **unbilled time (revenue leak)**, and
  **overdue project tasks**.
- Every item carries a **0-100 priority score** (severity band + age + type
  nudge), a plain-English **reason** and **recommended action**, and a
  **deep-link** straight to the right tab — so triage is one glance, not twelve
  dashboards.
- An overall **Ops Score** (0-100) summarizes how much is on fire, shown as a
  hero gauge on the Overview home screen with severity chips, plus a filterable
  ranked feed on the Action Center tab (per-client filter for staff).
- Smart de-duplication: an offline device suppresses its own stale AV/health/
  patch noise so you see "it's offline," not five derived alarms.
- **Tenant-scoped + RBAC**: staff see all clients (optionally one); a client user
  only ever sees their own org, and a foreign `client_id` filter is denied.
- Pure read model — computes from existing tables, mutates nothing.
- Verified end-to-end: backend ranking/scoping, the smoke suite, and the live
  dashboard rendered headless (Action Center tab + Overview Ops Score hero).

## v0.31.0 — Preconfigured ("preloaded") agent installer (June 2026)

### Added — zero-copy-paste agent deployment: the token is baked in
- New **"Download ready-to-run installer (.cmd)"** button on the Deploy Agent
  card. Generate a client's installer, hand the **single file** to them, and they
  just **double-click it** — no token to paste, no URL to type. The installer
  (`/download/deploy.cmd?token=…`) self-elevates to Administrator, then hands off
  to the proven `install-exe.ps1`: downloads the standalone `opspilot-agent.exe`,
  **enrolls with the embedded token**, and registers the boot Scheduled Task.
- The agent (**v1.4.0**) gained **embedded-token auto-enroll**: a preconfigured
  agent reads its enrollment token from `OPSPILOT_ENROLL_TOKEN` (env) or a
  co-located `opspilot-enroll.json` / `opspilot-enroll.token` file, then enrolls
  silently on first run and starts reporting — truly "it just works." The token
  file is **single-use** (deleted after a successful enroll).
- `install-exe.ps1` now also drops that single-use token file beside the exe, so
  the boot task **self-enrolls** even if the first enroll is interrupted.
- The copy-paste one-liners (.exe, PowerShell, Linux/macOS) remain as options.
- Verified: token resolution (env + both file formats + single-use consume),
  the `deploy.cmd` endpoint (token embedded, self-elevation, file download
  headers), and the full smoke suite.

## v0.30.0 — Scheduled QBR emails + agent URL fix (June 2026)

### Fixed — agent enrollment failed when the URL was typed without a scheme
- If you typed `portal.bvtech.org` (no `https://`) at the agent's onboarding
  prompt, it built `portal.bvtech.org/api/agent/enroll` and urllib rejected it
  ("unknown url type"). The agent (**v1.3.1**) now **normalizes any URL** it's
  given — interactive prompt, `--url` flag, saved config, or `PULSE_URL` env —
  adding `https://` when no scheme is present and trimming trailing slashes.
  Verified: typing a bare host now enrolls and the device appears.

### Added — scheduled reports now carry the full QBR + CSV
- The recurring report email is now the **complete QBR**: a readable, sectioned
  body (Infrastructure, Security & Alerts, Service Desk, Projects, Investment)
  built from the same enriched summary as the report page, **with the metrics CSV
  attached**. `email.send()` gained attachment support; the CSV builder is shared
  with the export endpoint. Verified end-to-end (rich body + `.csv` attachment).

## v0.29.0 — QBR report builder (branded, exportable) (June 2026)

### Added — a client-facing deliverable you can hand over or resell
- The client report (`/api/reports/{id}/summary` + `/report/{id}`) now pulls in
  **everything we've built**: device health, **patch compliance %**, alerts,
  security score, ticket volume + **resolved** + SLA breaches, **active projects
  & task completion**, **assets + warranties expiring**, **service hours
  delivered (90d, billable split)**, and recurring revenue (MRR/ARR).
- **CSV export** (`/api/reports/{id}/export.csv`): the whole snapshot as a flat
  Metric,Value CSV — drop into Excel/Sheets or a QBR deck. Tenant-scoped.
- The branded report page gains a second KPI row (Patch Compliance, Tickets
  Resolved, Service Delivered, Assets) plus Projects and Infrastructure panels,
  an **Export CSV** button next to Print/Save-PDF, and stays print-ready.
- Staff and the owning client can both pull the report + CSV (read-only). Smoke
  test covers the enriched sections, the CSV download, and RBAC. No schema change.

## v0.28.0 — Agent self-onboarding (fix "I installed it but don't see myself") (June 2026)

### Fixed — a downloaded agent now actually registers
- The standalone `.exe`, when **double-clicked**, used to just print usage and
  exit — so it never enrolled and no device appeared. The agent (**v1.3.0**) now
  **self-onboards**: on first run with no config it asks for the portal URL
  (defaulting to `portal.bvtech.org`) and an **enrollment token**, enrolls, and
  immediately starts reporting. Paste the token → the computer shows up within a
  minute.
- `enroll <token>` now **chains straight into `run`** (no separate step), and the
  portal URL is **persisted** so the boot Scheduled Task and later double-clicks
  reconnect to the right server. An already-enrolled agent that's re-launched just
  resumes. Non-interactive/no-TTY launches still print usage.
- Dashboard **Deploy Agent** card now shows the **raw enrollment token** front and
  centre with a one-line "download the .exe, double-click, paste this" path, plus
  a ready-to-paste `opspilot-agent.exe enroll <token> --url …` command for an
  already-downloaded binary.
- Verified end-to-end: agent enroll → **device appears in the portal list** →
  check-in populates health (the exact thing that was missing).

## v0.27.0 — Asset management / CMDB + warranty tracking (June 2026)

### Added — track everything the agent can't
- **Assets** (`/api/assets`): a CMDB for non-agent gear — printers, switches,
  firewalls, phones, monitors, peripherals — with make/model/serial/asset-tag,
  location, assignee, status (active/in_repair/spare/retired), purchase date,
  **warranty expiry**, cost, notes, and an optional link to an agent device.
- **Warranty tracking**: each asset reports a `warranty_state`
  (ok / expiring ≤60d / expired); `GET /api/assets/warranty-expiring?days=` lists
  what's lapsing so nothing slips. Dashboard surfaces an expiring-soon banner.
- Staff manage; the owning **client can view their own inventory** (read-only).
  Filter by type/status; assets are in **global search** (name/serial/tag).
- Dashboard **Assets** tab with add form, warranty highlighting, and the full
  inventory table. New `assets` table (migration `a9bacbdcefab`); verified
  up/down/up on SQLite and **Postgres 16**. Smoke test covers CRUD, warranty
  filter, validation, RBAC, scoping, and search.

## v0.26.0 — Time tracking: live timers → billable hours → invoice (June 2026)

### Added — close the PSA money loop
- **Live timers** (`/api/timers/start|stop|current`): a per-user stopwatch on a
  ticket or project task. Starting a new timer **banks** the running one as a
  logged entry; stopping materializes a `TimeEntry` for the elapsed minutes.
- **Time on project tasks**, not just tickets: `time_entries.ticket_id` is now
  nullable and a `task_id` was added; `POST /api/tasks/{id}/time` logs manual task
  time (parity with the ticket endpoint).
- **Unbilled visibility** (`/api/time/unbilled`): billable, not-yet-invoiced time
  grouped by client — exactly what's ready to bill — plus `/api/time/entries`.
- The existing `/invoices/generate` consumes that billable time into line items,
  so the loop is closed: **start timer → work → stop → see unbilled → invoice**
  (verified: invoicing drops the client's unbilled total back to 0).
- Dashboard **Time** tab: a live HH:MM:SS tracker (start on an open ticket,
  billable toggle, stop & log), a "Ready to Bill" rollup, and recent entries.
- New `active_timers` table + `time_entries` changes (migration `f8a9bacbdcef`);
  up/down/up verified on **SQLite and Postgres 16** (batch alter for the nullable
  column). Staff-only; smoke test covers the full loop + RBAC.

## v0.25.0 — Live command-center overview (June 2026)

### Added — one pulse for the whole shop
- **`GET /api/overview`**: a single tenant-scoped call that fuses RMM + PSA +
  billing into one payload — devices online/offline + avg health, **patch
  compliance %**, active alerts (+critical), open tickets with **SLA breached /
  at-risk** counts, active projects + task progress, **MRR** + outstanding
  invoices, and a **live activity stream** (scoped audit feed). Staff see the
  whole fleet; client users see only their own org.
- Dashboard **Overview** becomes a real command center: a KPI strip (Devices
  Online, Patch Compliance, SLA Risk, Active Projects) plus a Live Activity feed,
  with **auto-refresh every 30s** (toggle).
- No schema change. Smoke test covers the rollup, the activity feed, and tenant
  scoping.

## v0.24.0 — PSA projects & Kanban board (June 2026)

### Added — project management
- **Projects** (`/api/projects`): client engagements (onboarding, migrations,
  rollouts) with status, due date, budget hours, and owner. Staff manage; the
  owning **client can view their own boards** (read-only transparency).
- **Kanban board** (`/api/projects/{id}/board`): tasks grouped into **To do /
  In progress / Review / Done** columns. `POST /api/tasks/{id}/move` is the
  drag-between-columns action — moving into *Done* stamps `completed_at`, moving
  out clears it; progress rolls up as done/total %.
- **Tasks**: title, description, assignee, priority, due date, estimate hours,
  position. Full CRUD; deleting a project cascades its tasks.
- Dashboard gains a **Projects** tab with a live board (per-card ← / → to move,
  add task, progress in the project switcher). Projects + tasks are now in
  **global search**.
- New `projects` + `project_tasks` tables (migration `e7f8a9bacbdc`); up/down/up
  verified on SQLite and **Postgres 16** (incl. the enum type).

## v0.23.0 — OAuth2 SSO + connectors (June 2026)

### Added — sign in with Microsoft / Google, and connect provider accounts
- A full **OAuth2 authorization-code framework with PKCE** (no third-party client
  lib). Providers light up automatically when their credentials are present:
  **Microsoft** (reuses `M365_CLIENT_ID/SECRET`, tenant `common`) and **Google**
  (`GOOGLE_CLIENT_ID/SECRET`). Custom providers can be added at runtime via
  `oauth.register_provider()`.
- **Single sign-on**: the login page shows "Sign in with Microsoft / Google"
  buttons. The callback matches the verified provider email to an existing,
  active Pulse user and issues the same DB-backed session as password login
  (no silent auto-provisioning). `OAUTH_ALLOW_SSO` gates it.
- **Connectors**: staff can connect a provider account; the access/refresh tokens
  are **encrypted at rest** (Fernet, keyed off `SECRET_KEY`) and never returned by
  the API. `/api/oauth/tokens` lists connections; revoke removes them.
- **Security**: CSRF is enforced by a **single-use, server-side state** row (10-min
  TTL); the **PKCE verifier never leaves the server** — only its S256 challenge is
  sent. New `oauth_states` + `oauth_tokens` tables (migration `d6e7f8a9bacb`).
- Integrations tab gains an **OAuth Connections** panel; sign-in helper resolved.

### Verified
- End-to-end smoke test against a live mock IdP: PKCE known-answer, authorize→
  callback→session SSO, forged/reused-state rejection, encrypted-token store +
  RBAC + revoke. Full migration chain clean on **Postgres 16** (single head).

## v0.22.0 — Comprehensive audit log + developer hub (June 2026)

### Added — log everything, not just logins
- A middleware now records **every mutating API call** (POST/PUT/PATCH/DELETE
  under `/api/`) to the audit trail — who (resolved from session cookie, Bearer
  token, or API key), what (method + path), outcome (HTTP status), and source IP.
  High-frequency machine telemetry (agent check-ins, job/diag polls, inventory/
  patch reports) is skipped so the log stays human-meaningful. Routes that
  already write rich targeted entries keep doing so; this guarantees nothing
  slips through. Verified: client create / API-key delete are logged, GETs are
  not.

### Added — developer hub
- **`/developers`**: a branded developer hub documenting API-key auth, the event
  catalog, webhook signature verification, and inbound ingest.
- **`/api/openapi.json`**: the complete machine-readable API schema (129
  endpoints) so any tool — Postman, Zapier, Make, a code generator — can import
  the entire Pulse API. Integrations tab links to the hub.

### Fixed / hardened
- **Add Client** flow made resilient: a failure in any unrelated dashboard loader
  can no longer hide a successful creation or block the UI, and a 401 now shows a
  clear "session expired" message instead of failing silently. (The create path
  itself was already correct — verified end-to-end in a headless browser.)

## v0.21.0 — Integrations & command center (June 2026)

### Added — interoperate with anything
- **API keys** (`/api/integrations/api-keys`): any external tool can call the
  Pulse API with an `X-API-Key` header. A key authenticates **as its owner**
  (inheriting role + client scope); only a SHA-256 hash is stored, plaintext is
  shown once. Wired into the core auth dependency, so keys work on **every**
  endpoint.
- **Outbound webhooks / event bus** (`/api/integrations/webhooks`): subscribe any
  URL to internal events (`ticket.created`, `alert.opened`, `ticket.sla_breached`,
  …). Deliveries are **HMAC-SHA256 signed** (`X-OpsPilot-Signature`), SSRF-guarded,
  and fired centrally from the automation dispatcher. Per-subscription event
  filter + client scope; test button.
- **Inbound ingest** (`POST /api/ingest/{token}`): generate a tokenized URL any
  external system can POST JSON to; Pulse creates a **ticket or alert** for the
  bound client (recognizes subject/title, body/message, severity, priority). The
  token is the auth — no session required. Ingested events also fan out on the
  event bus.
- **Integration catalog + connections** (`/api/integrations/catalog`,
  `/connections`): a curated directory (ConnectWise, Autotask, HaloPSA, Datto/
  Ninja/N-able RMM, IT Glue, Hudu, Slack/Teams, M365/Google, QuickBooks/Xero/
  Stripe, Pax8, SentinelOne/Bitdefender/Huntress, Zapier/Make, custom) plus saved
  connections storing each product's config. Config keys are listed back, never
  secret values.

### Added — search everywhere
- **Global search** (`/api/search`): one bar in the header searches clients,
  devices, tickets, alerts, invoices, licenses, KB, software inventory and
  integrations — tenant-scoped, typed results with jump targets. Press **/** to
  focus it.

### Notes
- New `api_keys`, `webhook_subscriptions`, `inbound_sources`,
  `integration_connections` tables (migration `c5d6e7f8a9ba`); up/down/up +
  single-head verified. Smoke test extended across all of the above (key
  auth/revoke, signed event delivery, inbound→ticket/alert fan-out, catalog,
  scoped search) — all passing.

## v0.20.0 — Patch management, metric history, scheduled reports (June 2026)

### Added — patch management
- **Agent (v1.2.0) reports pending OS/software updates** (read-only check, never
  installs): Windows via the Update Agent COM API (native PowerShell, no
  modules), Linux via `apt-get -s upgrade` / `dnf check-update`, macOS via
  `softwareupdate -l`. Reported on first check-in then ~every 6h.
- **`POST /api/agent/patches`** replaces the device's pending set and stores a
  `patches_pending` count for fast list views.
- **`GET /api/devices/{id}/patches`** (tenant-scoped). Devices tab shows an
  up-to-date / N-pending column and a per-device **Patches** drill-down.

### Added — live metric history
- **`GET /api/devices/{id}/metrics`** returns recent check-in trend (CPU / RAM /
  disk / health). New per-device **Metrics** drill-down renders dependency-free
  inline SVG sparklines (CSP-safe — no external chart libs).

### Added — scheduled client reports
- **`/api/report-schedules`** (staff CRUD + toggle + delete + run-now): email a
  branded service snapshot to a client contact on a **weekly / monthly /
  quarterly** cadence. The recurring **run-checks** tick delivers due reports
  (safe no-op/logged until SMTP is configured). Automation tab gains a
  **Scheduled Reports** panel.
- New `device_patches` + `report_schedules` tables and `devices.patches_pending`
  (migration `b4c5d6e7f8a9`); verified up/down/up and single-head. Agent patch
  collection verified live on Linux.

## v0.19.0 — Software inventory (RMM) (June 2026)

### Added — installed-software inventory across the fleet
- **Agent (v1.1.0) reports installed software** on first check-in then ~every 6h:
  Windows via the registry uninstall hives (no extra deps), Linux via
  `dpkg`/`rpm`, macOS via `system_profiler`. Read-only, best-effort.
- **`POST /api/agent/inventory`** (device-authenticated): replaces the device's
  full software set each report (dedup by name+version, capped for safety).
- **`GET /api/devices/{id}/software`**: per-device inventory, tenant-scoped
  (staff any client; client users their own).
- **`GET /api/software/search?q=`**: fleet-wide "who has app X?" — aggregates
  install counts by name+version across devices the caller can see. Powers
  license reconciliation and vulnerability response.
- **Dashboard Devices tab** gains a per-device **Software → View** drill-down.
- New `device_software` table (migration `a3b4c5d6e7f8`); verified up/down/up and
  single-head on SQLite. Agent Linux collection verified live (686 real pkgs).

## v0.18.0 — Standalone .exe download that actually works (June 2026)

### Added — no-Python agent install path
- **`/download/agent.exe`** now serves the binary from `agent/dist/` if present,
  otherwise **302-redirects to the published GitHub release asset**
  (`AGENT_RELEASE_BASE`, default the repo's `releases/latest/download`). The repo
  is public, so the `latest` URL downloads without auth — the `.exe` works the
  moment the `build-agent` workflow publishes it, with **no server-side sync**.
- **`/download/agent-linux`**: same strategy for the standalone Linux binary.
- **`/download/install-exe.ps1`**: a **no-Python** Windows installer — pulls the
  standalone `.exe`, enrolls with the embedded token, and registers a boot-time
  Scheduled Task. Endpoints need nothing pre-installed.
- Dashboard **Deploy Agent** card now offers three one-liners (standalone `.exe`,
  Python PowerShell, Linux/macOS) plus direct download links for the `.exe` and
  Linux binary.
- Tag `agent-v1.0.0` publishes the binaries via the `build-agent` workflow.

## v0.17.1 — No-store on HTML pages (June 2026)

### Fixed — site showed an old version after a successful deploy
- HTML page shells (`/`, `/signup`, `/dashboard`, `/portal`, `/invoice/*`,
  `/report/*`) were served with **no cache headers**, so the browser and
  Cloudflare could hold a stale copy — the login footer kept showing an old
  `vX.Y.Z` (and an old installer flow) even after the origin was upgraded.
- All HTML pages now send **`Cache-Control: no-store, no-cache, must-revalidate`**
  (+ `Pragma: no-cache`), so a new deploy is visible on the very next request.
  Static assets under `/static` keep their own caching.

## v0.17.0 — Self-healing auto-deploy (June 2026)

### Fixed — the real cause of the "installer still 404s" report
- **Auto-deploy could wedge on a half-failed run and never recover.** The old
  `deploy.sh` used `set -e` plus an early `exit 0` whenever git was unchanged, so
  a single failed step (e.g. a migration or an image rebuild) left the server
  running **old code against a half-updated tree** and it would never retry — the
  live site stayed pinned to a stale version while `main` moved on. That stale
  version, not the installer code, is why the download/installer endpoints 404'd
  in production even though they return HTTP 200 in a clean build. Verified the
  installer + `/download/agent` paths serve correctly in **production mode against
  real Postgres**, and the full Alembic chain (13 migrations) applies clean.
- **`deploy.sh` is now self-healing.** It redeploys whenever new commits exist
  **or** the running app version != the committed version, so a wedge fixes itself
  on the next 2-minute poll. It rebuilds **only** the `api` service (never the
  proxy/db, which could stall the whole stack), drops `set -e` so one failed step
  can't abort the rest, applies migrations, restarts `api`, and **logs the final
  running version** every run so ground truth is visible in the deploy log.

### Unstick command (run once on the server to recover a wedged deploy now)
```
cd /opt/bvtech-portal && git pull --ff-only origin main && chmod +x opspilot/deploy.sh && opspilot/deploy.sh
```

## v0.16.0 — Standalone agent binary + notification channels (June 2026)

### Added — Notification channels (v0.15)
- **`/api/notification-channels`**: staff-managed delivery targets — **email,
  Slack, Teams, generic webhook** — with a per-channel minimum severity and
  optional client scope. The automation `notify` action now **fans out** to all
  matching enabled channels (in addition to the in-app notification).
- **Test button** per channel; SSRF guard blocks the cloud-metadata address and
  requires http(s) for webhooks. Automation tab gains a Channels panel.
- Verified with a **real webhook delivery** test (local receiver), severity
  routing, the end-to-end automation→channel path, and RBAC.

### Added — Standalone agent binary (v0.16)
- **`build-agent` GitHub Actions workflow**: builds `opspilot-agent.exe`
  (Windows) and a Linux binary via **PyInstaller** and publishes them as release
  assets (on `agent-v*` tags or manual dispatch). Packaging verified locally
  (single-file binary runs).
- **Windows installer now auto-installs Python** via winget if it's missing —
  so endpoints need **nothing** pre-installed.
- **`/download/agent.exe`** serves the standalone binary once present in
  `agent/dist/` (graceful 404 with guidance until the build is published).

## v0.14.0 — Contracts, client reports & deploy-flow fixes (June 2026)

### Fixed
- **Agent deploy was unusable with no clients**: the Devices "Deploy Agent" panel
  posted to `/api/agent/enroll-token/` with an empty client id → 404 "Not Found".
  Added an **Add Client** form on the Clients tab (client creation was previously
  API-only), a guard so the installer button tells you to add a client first, and
  hardened `/download/agent` path resolution so the agent file always serves.
  Verified the full flow end-to-end: add client → generate installer → download
  agent → enroll → check-in.

### Added
- **Recurring contracts** (`/api/contracts`): flat monthly/quarterly/annual
  service agreements; active contracts feed **MRR** (normalized to monthly) in
  the billing rollup (`contract_mrr` + `license_mrr` split). Dashboard Billing
  tab gains a Contracts panel.
- **Branded client reports** (`/report/{client_id}` + `/api/reports/{id}/summary`):
  a one-click, print-to-PDF QBR snapshot — security score, device health, active
  alerts, helpdesk/SLA, and recurring revenue. "Report" link per client; clients
  can view their own.
- New Alembic migration (`contracts`) — verified reversible.
- Smoke test: contracts MRR (incl. quarterly normalization), report aggregation,
  RBAC, and the agent download + enroll-token flow.

## v0.13.0 — Production agent + one-click deploy (June 2026)

Makes the on-site agent real and turnkey — download, install, and it reports to
the portal with zero manual config.

### Added
- **Agent download & installers** (`/download/agent`, `/download/install.sh`,
  `/download/install.ps1`): the install scripts **auto-target the host that
  served them** (honoring the Cloudflare/Caddy proxy headers), embed the
  enrollment token, fetch the agent, install `psutil`, enroll, and start it
  (Scheduled Task on Windows / background on Linux/macOS).
- **Deploy Agent** card on the Devices tab: pick a client → generate a 72h
  installer → copy the Windows PowerShell or Linux/macOS one-liner.
- **Agent hardening** (`agent/opspilot_agent.py` → v1.0.0): branded banner,
  `--url` flag, enrollment **retry/backoff**, local logging (`agent.log`),
  default server now `portal.bvtech.org`. Verified end-to-end (enroll → check-in)
  against a live instance.
- Dockerfile now ships the agent in the image so the server can serve it.

### Notes
- Install scripts/agent are public by design; security is the signed,
  time-limited, client-scoped enrollment token (unchanged).
- Windows endpoints need Python 3 (the installer detects it and prints the
  one-line winget command if missing). A standalone signed `.exe` is the next
  hardening step.

## v0.12.0 — Network diagnostics & discovery (June 2026)

Diagnose client network issues live from the portal — two complementary layers.

### Added
- **Looking glass** (server-side, `/api/netdiag/{dns,reachability,port,http}`):
  run DNS / TCP reachability+latency / port / HTTP checks from the portal toward
  a client's **public** endpoints (site, mail, DNS). **SSRF-guarded** — every
  target is resolved and any private / loopback / link-local (incl. cloud
  metadata) / reserved address is refused. ICMP-free (TCP connect), so it works
  inside the container without privileges. Staff-only.
- **Agent diagnostics** (`/api/netdiag/diagnostics` + agent pull/report): queue
  **read-only** probes — `ping`, `traceroute`, `dns`, `port_check`,
  `subnet_discovery` (LAN ping-sweep) — for an on-site agent to run against the
  client's **internal** network and report back. Non-destructive by design.
- **Agent** gained diagnostic handlers and now processes the diagnostics queue
  each cycle (read-only; runs regardless of the script opt-in).
- **Dashboard Network tab**: a "Live Diagnostics (looking glass)" panel and a
  "Run on a device" panel with results.
- New Alembic migration (`diagnostic_requests`) — verified reversible.
- Smoke test: SSRF guard rejects private/loopback/metadata, RBAC, and the full
  agent queue → pull → report → read flow.

### Security
- Looking glass is staff-only and cannot reach internal/metadata ranges.
- Agent diagnostics are read-only (no config changes) and per-device scoped;
  every request is audited.

## v0.11.0 — Networking & IPAM (June 2026)

### Added
- **Sites** (`/api/net/sites`): per-client locations (HQ, branch, datacenter).
- **Networks / subnets** (`/api/net/networks`): CIDR-based subnet records with
  VLAN, gateway, DNS; each shows live **utilization** (tracked IPs ÷ usable hosts).
- **IPAM** (`/api/net/networks/{id}/ips`): allocate/release IPs with guards —
  must be a valid IP, **in-range** for the subnet, and **unique** per network
  (no conflicts); optional hostname/MAC/device link.
- **Subnet calculator** (`/api/net/subnet-calc`): network/broadcast/mask/usable
  host range — pure stdlib `ipaddress`, no external calls.
- **Dashboard Network tab**: subnet calculator, network create, utilization bars,
  click-through IP allocation table.
- New Alembic migration (`sites`, `networks`, `ip_addresses`) — verified reversible.
- Smoke test: subnet math, network create + validation, IPAM allocate with
  in-range/duplicate/invalid guards + release, client read-only RBAC.

### Security
- Writes are staff-only; client users get read-only visibility into their own
  org's network docs. Every change audited.

## v0.10.0 — Invoicing (June 2026)

Closes the PSA money loop: tracked billable time + licenses → invoices.

### Added
- **Invoice generation** (`POST /api/invoices/generate`): builds a draft for a
  client from **unbilled billable time** (`hourly_rate` × hours) and/or **license
  subscriptions** (`monthly_cost`), with optional tax. Billed time entries are
  flagged `invoiced` so they're **never double-billed** (verified in the test).
  Auto-numbered `INV-00001`.
- **Line items & lifecycle**: add manual line items to a draft; `draft → sent →
  paid` plus `void`; totals auto-recompute. `GET /api/invoices` (+ `/{id}` with
  line items).
- **Printable invoice** (`/invoice/{id}`): a clean, branded HTML invoice with a
  "Print / Save PDF" button.
- **Dashboard**: an Invoices section on the Billing tab (generate from time/subs +
  tax, list, send/mark-paid, open the printable view). **Client portal**: an
  Invoices card — clients see their own sent/paid invoices and can open/print them.
- New Alembic migration (`invoices`, `invoice_line_items` + `invoiced`/`invoice_id`
  on `time_entries`) — verified reversible.
- Smoke test: generate from time + licenses + tax (exact total), no-double-bill,
  manual line item recompute, send/paid/void lifecycle, client visibility, RBAC.

### Security
- Generation/edit/lifecycle are staff-only (void is owner-only); clients can view
  only their own non-draft invoices. Every action audited.

## v0.9.0 — Microsoft 365 integration (June 2026)

Read-only, app-only, multi-tenant Microsoft Graph integration. One Entra app
(credentials in env); each customer tenant grants admin consent.

### Added
- **Per-client M365 connections** (`/api/m365/connections`): link a customer's
  tenant to a client (one per client). `GET /api/m365/status` reports whether
  Graph credentials are configured. Owner-only delete.
- **Read-only sync** (`POST /api/m365/connections/{id}/sync`):
  - **Licenses** auto-populated from `subscribedSkus` (vendor "Microsoft 365",
    seats/used) — feeds the existing billing rollup. Idempotent (re-sync updates,
    never duplicates).
  - **Secure Score** stored on the connection.
  - **Risky sign-ins** raise alerts (`kind=m365_risky_signin:<upn>`) through the
    existing engine, so they appear on the dashboard **and the automation engine
    can act on them** (e.g. high-risk sign-in → open a ticket). Deduped per user.
  - Live sync returns **503** until `M365_CLIENT_ID` / `M365_CLIENT_SECRET` are set.
- **Encrypted secrets at rest** (`app/services/crypto.py`, Fernet keyed off
  `SECRET_KEY`): cached Graph tokens are stored encrypted.
- **Mockable Graph client**: `m365.sync_connection(db, conn, graph)` accepts any
  client implementing `get_subscribed_skus` / `get_secure_score` /
  `get_risky_signins`, so the whole pipeline is tested without creds or network.
- **Dashboard**: a Microsoft 365 panel on the Billing tab — connect a tenant,
  see status / Secure Score / license & risky-sign-in counts, sync or remove.
- New dependency `cryptography`; new Alembic migration (`m365_connections`) —
  verified reversible. `.env.example` documents the required Graph permissions.
- Smoke test exercises connect → (503 when unconfigured) → mock sync →
  license/score/alert population → encrypted-token roundtrip → idempotency → RBAC.

### Security
- Connections/sync are staff-only; delete is owner-only; every action audited.
- Graph scopes are **read-only**; credentials live only in env; tokens encrypted
  at rest. The agent remains telemetry-only.

## v0.8.0 — Branding, accounts & email (June 2026)

### Added
- **Brand system**: a BVTech OpsPilot logo mark (SVG) + favicon, a refined
  dark-mode theme (gradient backdrop, lifted cards, gradient buttons, gradient
  stat numbers), and a consistent logo lockup + footer across the login, signup,
  dashboard, and portal. Drop a real logo at `app/static/img/mark.svg` to
  rebrand everything at once.
- **Public signup / "Request access"** (`/signup` page, `POST /api/signup`):
  collects name/email/company/message as a reviewable **lead** (not an
  auto-provisioned account — open self-service into an MSP console would be
  unsafe). Rate-limited. Staff review via `GET/PATCH /api/signup-requests` and an
  **Access Requests** card on the dashboard.
- **Outbound email** (`app/services/email.py`): SMTP-backed, configured via env
  (`SMTP_HOST`, …). When unconfigured it safely **no-ops and logs** what it would
  send, so every environment runs. Wired to: signup confirmation (to requester) +
  notice (to `SUPPORT_EMAIL`), and client-user invites (credentials emailed; the
  response now reports `emailed`).
- **Owner account**: the bootstrap owner email now defaults to `help@bvtech.org`,
  and `SUPPORT_EMAIL` / `PUBLIC_BASE_URL` are configurable.

### Notes
- `.env.example` documents the new SMTP / branding / support settings.
- Smoke test extended: email no-op, public signup → staff review → RBAC, invite
  `emailed` flag, and branded-page render checks.
- Microsoft 365 (v0.8 on the old plan) moves out one slot; it needs live Graph
  credentials — ping with keys and it's next.

## v0.7.0 — Script library & deployment governance (June 2026)

Real "push a script to a device" capability — built so it can never become
arbitrary remote code execution.

### Added
- **Script library** (`/api/scripts`): versioned, categorized, risk-rated
  scripts (PowerShell/Bash/Python/cmd). **Disabled by default** — a script is
  inert until an **OWNER** enables it (`POST /api/scripts/{id}/enable`). Editing
  content bumps the version.
- **Deployment workflow** (`/api/scripts/{id}/deploy` → `/api/deployments`):
  - The deploy request **snapshots** the exact content+version, so later library
    edits can't change what was approved/runs.
  - Requires `consent_ack` and records a reason.
  - Needs **OWNER approval**, and the approver may **not** be the requester
    (separation of duties). Reject and cancel paths included.
- **Agent job queue** (`GET /api/agent/jobs`, `POST /api/agent/jobs/{id}/result`):
  the agent authenticates with its device key and pulls **only its own approved
  jobs**, runs the pinned content, and reports exit code + output. The server
  never pushes ad-hoc commands.
- **Agent runner** (`opspilot_agent.py run --enable-remote-scripts`): an
  **opt-in**, consent-bannered job runner. Off unless explicitly enabled; runs
  only server-approved jobs for its own enrolled device, with a 10-minute cap.
- **Dashboard**: new **Scripts** tab — library with owner enable toggle, deploy
  (device + reason + consent), and a deployments table with approve/reject/cancel.
- New Alembic migration (`scripts`, `script_deployments`) — verified reversible.
- Smoke test extended: disabled-deploy block, consent gate, separation-of-duties
  approval, agent pull→run→result, reject/cancel, and RBAC isolation.

### Security
- Enable, approve, reject are OWNER-gated; deploy requests are staff-only; clients
  have no access to the library or deployments. Every transition is audited.
- Content pinning + separation of duties + consent + owner-only enable mean there
  is **no arbitrary remote code execution path** — only approved, logged,
  attributable, content-locked jobs that the agent must opt in to run.

## v0.6.0 — Security posture & remediation (June 2026)

A **defensive** security module — it documents, tracks, and helps remediate
weaknesses. It does not scan, exploit, or run anything on any system.

### Added
- **Authorized security assessments** (`/api/security/assessments`): engagement
  records that **require** an `authorized_by` party at the client — there is
  always a record of who consented to the review. Planned → in-progress →
  completed lifecycle with timestamps and a summary.
- **Vulnerability findings** (`/api/security/findings`): title, CVSS-style
  severity (low/medium/high/critical), CVE, category, description,
  recommendation, and a remediation workflow (open → remediating → resolved /
  risk-accepted). Optionally tied to a device and/or an assessment.
- **Alert + automation integration**: a high or critical finding raises an alert
  through the existing engine (`kind=security_finding:<id>`), so it shows on the
  dashboard and **automation rules can act on it** (e.g. critical finding → open
  a ticket). Resolving the finding auto-resolves its linked alert.
- **Security scorecard** (`/api/security/scorecard`): a 0–100 posture score per
  client (100 minus weighted open findings) plus open-finding counts by severity.
- **Client visibility**: findings are staff-managed; a client sees only findings
  explicitly flagged `client_visible` and their own posture score — enforced at
  the query layer.
- **Dashboard**: new **Security** tab (per-client scorecard table, finding
  creation, severity badges, remediate/resolve actions). **Client portal**: a
  Security Score card + a shared-findings list.
- New Alembic migration (`security_assessments`, `security_findings`) — verified
  reversible.
- Smoke test extended: authorization gate, finding→alert→scorecard, resolve→score
  recovery + alert auto-resolve, client visibility + RBAC isolation.

### Security / ethics
- Assessments cannot be created without naming an authorizing party.
- All finding/assessment writes are staff-only and audited; clients are
  read-limited to shared findings and their own score.
- This module is intentionally **defensive**: no scanning, no exploitation, no
  command execution. The agent remains telemetry-only.

## v0.5.0 — Automation engine (June 2026)

### Added
- **Server-side automation engine** (`app/services/automation.py`): rules react
  to platform **events** and take safe, in-platform **actions**. No remote code
  execution — actions only manipulate OpsPilot's own records.
  - **Triggers**: `alert.opened`, `ticket.created`, `ticket.sla_breached`.
  - **Conditions**: JSON match (e.g. `{"severity":"critical"}`, `{"priority":"urgent"}`),
    optionally scoped to a single client.
  - **Actions**: `create_ticket`, `ack_alert`, `notify`, `assign` (explicit or
    auto least-loaded tech), `set_priority`, `add_note`. One bad action never
    aborts the rest; everything is logged.
- **Event wiring**: agent check-ins fire `alert.opened` for newly opened alerts;
  ticket creation fires `ticket.created`; the offline sweep fires `alert.opened`
  for newly-offline devices. Automation-created tickets do not re-trigger, so
  there are no loops.
- **Scheduler tick** — `POST /api/automation/run-checks`: sweeps offline devices
  and fires `ticket.sla_breached` for newly breached open tickets, de-duplicated
  via a per-ticket flag (reset on reopen). Built for cron; also on-demand.
- **Rule management**: `GET/POST /api/automation/rules`, `PATCH` (enable/disable/
  edit), owner-only `DELETE`; `GET /api/automation/runs` execution log.
- **In-app notifications**: raised by the `notify` action;
  `GET /api/notifications` (+ `?unread_only`), `POST /api/notifications/{id}/read`
  and `/read-all`. Scoped — staff see broadcast + their own; clients see only
  their own.
- **Dashboard**: new **Automation** tab (rule builder with per-trigger examples,
  rules list with enable toggle, run log, notifications panel + "run checks now")
  and a 🔔 unread-notification indicator in the top bar.
- New Alembic migration (`automation_rules`, `automation_runs`, `notifications`
  + `sla_breach_alerted` on `support_tickets`) — verified reversible.
- Smoke test extended: alert→ticket+notify, ticket→auto-assign+note, rule
  disable, SLA-breach tick with dedup, notification read flow, and RBAC isolation.

### Security
- Rules, runs, and `run-checks` are staff-only; rule deletion is owner-only.
  Every rule that fires writes an `automation.run` audit entry attributed to
  `automation@system`, plus an `automation_runs` row.
- Notifications are tenant-scoped at the query layer.
- The engine performs only in-platform actions — the agent stays telemetry-only,
  so there is still no remote code execution path anywhere in the product.

## v0.4.0 — PSA depth: SLAs, assignment, time tracking & IT documentation (June 2026)

### Added
- **SLA engine** (`app/services/sla.py`): per-priority response/resolution
  targets (built-in defaults, overridable per-client or globally). Due dates are
  stamped on ticket creation and re-based when priority changes; the first public
  staff reply satisfies the response SLA and resolving satisfies the resolution
  SLA. Every ticket payload now carries live SLA state (breached / minutes-left).
  - `GET /api/tickets/sla-summary` (breached + at-risk counts for the dashboard)
  - `GET /api/tickets?breached=true` filter
  - `GET/PUT /api/sla-policies` to view the effective matrix and set targets.
- **Technician assignment & workload**: tickets can be assigned only to staff
  users (validated); `GET /api/staff` returns the staff directory with each
  tech's open-ticket load; `GET /api/tickets?mine=true` filters to the caller's
  queue. Priority is now editable on a ticket.
- **Ticket time tracking**: `POST/GET /api/tickets/{id}/time` (staff only) with
  billable/non-billable minutes and notes; the ticket detail rolls up total and
  billable time — the foundation for PSA invoicing.
- **IT documentation / knowledge base** (`/api/kb`): staff author articles that
  are internal (staff-only) or client-visible, and global or client-scoped.
  Client portal users read only their permitted docs (enforced at the query
  layer — internal/other-client docs 404 even by direct id). Owner-only delete.
- **Dashboard**: Tickets tab gains SLA badges, "assigned to me" / "SLA breached"
  filters, and a richer detail panel (status + priority + assignee dropdowns,
  time logging, SLA countdown); new **Knowledge Base** tab to author/read docs;
  overview shows SLA-breach counts. **Client portal** gains a Documentation
  panel for client-visible articles.
- New Alembic migration (4 SLA columns on `support_tickets`; `sla_policies`,
  `time_entries`, `kb_articles` tables) — verified reversible.
- Smoke test extended: SLA stamping/breach/satisfy, breached filter + summary,
  staff-only assignment, time rollup, SLA-policy upsert, and full KB
  visibility/RBAC isolation.

### Security
- Assignment, time logging, SLA-policy edits, and KB authoring/deletion are all
  RBAC-guarded (staff/owner) and audited.
- KB visibility is enforced in the query, not the UI: a client user can neither
  list nor fetch internal or other-client documents.
- The agent remains telemetry-only — no remote execution path.

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
