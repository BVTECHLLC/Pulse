# BVTech OpsPilot — Changelog

## v0.80.0 — AI marketing pack: Claude writes the month's posts (July 2026)
- **✨ AI write** button in the Auto-post queue: Claude composes a batch of
  **distinct, on-brand, locally-relevant** social posts from your city + keywords
  and drops them straight into the queue — a month of content in one click.
- **Bulletproof:** always returns exactly the count you asked for (tops up from
  the template engine if Claude returns fewer), and **falls back entirely to the
  templates** when Claude isn't connected — so the button always works.
  `post_generator.generate_ai_drafts` + `use_ai` on `POST /api/autopost/generate`.
- Verified offline (smoke): with Claude stubbed, `use_ai` enqueues the full count
  (AI output + template top-up); the template fallback path is unit-tested.

## v0.79.0 — ⌘K command palette (July 2026)
- **Press ⌘K (or Ctrl-K) anywhere** to jump to any tab or run a quick action —
  Ask Pulse, run automation checks, generate posts, sign out — by typing. Arrow
  keys + Enter, Esc to close. Auto-builds its list from the nav, so it stays in
  sync as the portal grows.
- Pure front-end (no backend, no schema); the smoke suite guards that the
  dashboard shell still ships the palette + AI copilot + branding script.

## v0.78.0 — CSAT: client satisfaction after every ticket (July 2026)
- **Close the feedback loop.** When a request is resolved, the client gets a
  one-tap **👍/👎 (+ optional comment)** right in the portal. `POST
  /api/tickets/{id}/rate` (client, own ticket, resolved-only).
- **A number HQ can benchmark.** `GET /api/tickets/csat/summary` (staff) rolls up
  **satisfaction %** across the practice (or one client) with the **recent
  negatives** surfaced for follow-up; the score shows on the **MSP Practice
  Health** card. Franchise HQ compares CSAT across locations; established MSPs
  prove their value; solos catch unhappy clients early.
- `support_tickets.csat_rating/comment/at` (migration `d0e1f2a3b4c6` + startup
  self-heal); portal rating prompt on resolved tickets.
- Verified offline (smoke): can't rate before resolve; invalid ratings rejected;
  a 👍 and a 👎 roll into the satisfaction % with the negative surfaced; the
  rollup is staff-only (RBAC). Migration up/down/up clean.

## v0.77.0 — AI "explain this alert" — senior-tech guidance on tap (July 2026)
- **One ✨ click on any alert** and Claude explains, in plain English, what it
  likely means, the top likely causes, and **step-by-step fix actions**
  (Windows-first) — using the alert + that device's live telemetry (CPU/RAM/disk,
  health, AV, pending patches). The answer opens in the Ask Pulse copilot.
- **Why it matters for everyone:** a junior tech at a growing/franchise MSP gets
  senior-level triage instantly; a busy owner resolves faster. `POST
  /api/ai/alerts/{id}/explain` (staff-only), graceful 503 when Claude isn't
  connected, 404 for a missing alert.
- Verified offline (smoke): explaining a real alert returns fix guidance (Claude
  stubbed), a missing alert 404s, and clients are locked out (RBAC).

## v0.76.0 — MSP Practice Health: grade your own operation (July 2026)
- **One A–F grade for how well the MSP itself is running** — not any single
  client, but *your practice*. Four domains, each 0–100, weighted into an overall
  grade with a "do next" list:
  - **Service** — SLA response + resolution attainment (90-day)
  - **Security** — average client security-posture score
  - **Endpoints** — fleet online % blended with patch compliance
  - **Billing** — share of A/R that's current (not overdue)
- **Built for everyone:** a franchise HQ benchmarks locations with it, an
  established MSP tracks it month over month, a solo operator sees where to focus.
  Domains with no data yet are excluded (not scored zero), so a new install grades
  fairly. It headlines the **Overview** with a grade ring + per-domain grades +
  recommendations.
- `services/practice_health.py` (pure aggregation over SLA analytics, posture,
  inventory/patching, and A/R aging) + `GET /api/practice/health` (staff-only).
  No schema change.
- Verified offline (smoke + unit): domains score + grade, weighting excludes
  empty domains, recommendations fire on real gaps, and it's staff-only (RBAC).

## v0.75.0 — White-label branding (resell it as your own) (July 2026)
- **Make the whole portal yours.** A new **🎨 Branding / White-label** card
  (Settings, owner-only) sets the **company + product name, logo, accent color,
  support email, and tagline** — applied **everywhere**: the login page, the
  staff dashboard, and the client portal (title, lockup, logo, accent). The
  foundation for reselling OpsPilot under another MSP's brand.
- `services/branding.py` + `GET /api/branding` (**public** — the login page needs
  it, so it returns display-only values, no secrets) + `PUT /api/branding`
  (owner). A shared `static/js/brand.js` applies the brand on every page; invalid
  colors are rejected so the CSS can't break. No schema change.
- Verified offline (smoke): safe public defaults; an owner rebrand shows through
  the public endpoint (even unauthenticated); a bad color is ignored; a client
  user can't change branding (RBAC).

## v0.74.0 — Claude, baked in: the "Ask Pulse" AI copilot (July 2026)
- **A floating ✨ Ask Pulse copilot on every dashboard page.** Ask in plain
  English — "who's overdue?", "how's security looking?", "write a LinkedIn post
  about backups", "draft a reply for ticket 12" — and Claude answers using a
  live, safe snapshot of your operations (A/R, open tickets, offline devices,
  riskiest security grades — aggregates only, no secrets).
- **AI drafting anywhere:** `POST /api/ai/draft` writes client emails, advisories,
  and social posts; `POST /api/ai/tickets/{id}/reply-draft` turns a ticket thread
  into a ready-to-send reply. The copilot auto-routes "draft a reply for ticket N".
- **Graceful + safe:** `services/ai.py` is a thin stdlib Anthropic client with the
  key read from the server env (never logged); when Claude isn't connected, AI
  features return a clear "add your Anthropic API key" message instead of failing.
  The HTTP call is injectable, so every AI feature is tested offline.
- `GET /api/ai/status`, staff-only across the board (RBAC). No schema change —
  just set `ANTHROPIC_API_KEY` on the server to light it up.
- Verified offline (smoke): ask + draft + ticket-reply all return content (Claude
  stubbed); a missing key yields a clean 503; clients are locked out.

## v0.73.0 — Auto-posting that writes itself (SEO drafts + auto-refill) (July 2026)
- **Never write a post again.** Set your **city + keywords** once and OpsPilot
  generates **SEO-tuned, on-brand** post drafts straight into the queue — a
  curated library of high-performing MSP/security angles woven with your town and
  a rotating keyword (locally relevant + varied, exactly what LinkedIn and Google
  Business reward). **✨ Generate 6 drafts** in one click.
- **The feed truly runs itself.** Turn on **auto-refill** and the scheduler tops
  the queue back up whenever it runs low (below your `min_queue`), so with weekly
  publishing on, your LinkedIn + Google Business stay active with zero effort.
- **No AI key, no cost, no dependency.** The generator is a deterministic template
  engine — it keeps working even when an AI API is missing or out of credit (an
  AI writer can layer on later). `services/post_generator.py` + `autopost`
  brand-profile config + `POST /api/autopost/generate`, wired into `run-checks`.
- Verified offline (smoke + unit): generation produces varied, keyword-/CTA-woven
  drafts into the queue; saving a brand profile + enabling auto-refill tops the
  queue up to `min_queue` on the tick; a full queue is a no-op; clients can't
  generate (RBAC). No schema change.

## v0.72.0 — Smoother onboarding: one-click location picker + guided setup (July 2026)
- **No more typing Google IDs.** After you Connect Google Business, click **Load
  my locations** in Settings → Google Business Profile and **pick your listing
  from a dropdown** — it fills the account + location for you. (`GET
  /api/gbp/locations` lists every location the connected account manages via the
  Business Profile Account/Info APIs.) The "Post now" box also takes an image.
- **Guided setup checklist.** A new **🚀 Getting started** card on the Overview
  shows exactly what's connected and what's left — deploy the agent, connect
  Microsoft 365 / Stripe / payment methods / QuickBooks / Dialpad / LinkedIn /
  Google Business, turn on auto-posting, set up email — with a progress bar and
  one-click jumps to the right tab. It auto-hides once you're set up.
  (`GET /api/setup/status`, staff-only.)
- `services/gbp` can now list accounts+locations with just the OAuth connection
  (IDs no longer required to construct the client); `routes/setup.py` aggregates
  connection state across the vault + devices. No schema change.
- Verified offline (smoke + unit): the location picker returns pickable
  account/location/title/address (Google listing stubbed); the setup checklist
  returns structured items + progress; both are staff-only (RBAC).

## v0.71.0 — Auto-post to Google Business Profile (with photos), weekly (July 2026)
- **Google Business Profile is now an auto-post channel.** The auto-poster can
  publish to **LinkedIn and/or Google Business Profile**; each queued post can
  carry an **image** (published as the Google Business **photo** — big lift for
  engagement + local SEO) and a call-to-action link. Pick the cadence: **168h =
  weekly**, 24h = daily.
- The GBP publisher (`services/gbp.create_post`) gained **photo support** (`media`
  sourceUrl), and the manual **`POST /api/gbp/post`** accepts an `image_url` too.
- Multi-channel publishing: a post fans out to all its channels, is marked
  **posted** if any channel succeeds, **failed** if all attempted error, and
  **left queued** (never burned) if no channel is connected yet. Per-channel
  results are recorded.
- `social_posts.image_url` (migration `c9d0e1f2a3b5` + startup self-heal); the
  Auto-post card gains channel checkboxes + an image field; settings expose
  per-channel readiness (LinkedIn / Google Business connected?).
- Verified offline (smoke + unit): a post fans out to LinkedIn + Google Business
  with the **image passed through** to the GBP photo; weekly cadence holds
  (no second post for 7 days); an unconfigured channel leaves the post queued;
  per-channel results recorded; client RBAC. Migration up/down/up clean.

## v0.70.0 — Auto-posting: keep the feed alive on autopilot (July 2026)
- **Queue a few posts, walk away.** A new **📣 Auto-post queue** in Content Studio
  lets you load social posts; with auto-publish on, the scheduler publishes the
  **oldest due** one to **LinkedIn** about **once a day** (configurable minimum
  gap) — so your feed stays active without daily effort.
- **Safe by default:** auto-publish is **off** until you turn it on; it never
  double-posts (cadence gap tracked off the last published post); an unconfigured
  LinkedIn leaves posts **queued** (never burns them); failures are recorded and
  surfaced, not silently dropped. Plus **post-now** to publish immediately and a
  per-post delete.
- `services/autopost.py` (queue + cadence + injectable publisher so it's testable
  offline), `routes/autopost.py` (queue CRUD, settings, post-now — staff-gated),
  wired into `run-checks`. New `social_posts` table (migration `b8c9d0e1f2a4` +
  startup self-heal).
- Verified offline (smoke + unit): off-by-default; enabling publishes the oldest
  queued post on the tick; the cadence gap blocks an immediate second post;
  post-now bypasses the gap; scheduled-for-future posts wait; a failing publish is
  marked failed without crashing the tick; clients can't touch the queue (RBAC).
  Migration up/down/up clean.

## v0.69.0 — Installer that actually works (and never lies) (July 2026)
- **Fixed the "it says installed but no device shows up" bug.** The one-click
  `deploy.cmd` used to `irm <portal>/install-exe.ps1 | iex` — but the portal is
  behind Cloudflare, which served a **bot-challenge page** instead of the script,
  so the install silently failed while the batch still printed "installed."
- The double-click installer is now **fully self-contained**: it embeds the
  install PowerShell directly (base64), so it **never fetches a script through
  Cloudflare**. The standalone `.exe` is pulled from the **GitHub release**
  (not behind the portal's Cloudflare), the download is **verified** (real
  `MZ` executable, not an HTML challenge page), enrollment's **exit code is
  checked**, and the installer reports the **real result** — loud failure with a
  cause instead of a false success.
- Same hardening across **all** installers (`install-exe.ps1`, `install.ps1`,
  `install.sh`): GitHub-sourced downloads with retries + a browser User-Agent,
  size/format checks, honest SUCCESS/ERROR exit codes. The agent (`v1.5.2`) now
  sends a browser User-Agent on its API calls to reduce Cloudflare friction.
- **Note:** if Cloudflare still challenges the agent's API, add a WAF **Skip**
  rule for `/api/agent/*` and `/download/*` on `portal.bvtech.org` (Bot Fight
  Mode / Browser Integrity Check) — the installer now tells you when this is the
  cause instead of failing silently.
- Verified offline (smoke): `deploy.cmd` is self-contained (no `irm|iex`), embeds
  the token, decodes to pull the release `.exe` and fail loudly; `install-exe.ps1`
  sources the `.exe` from GitHub, checks the MZ header, and honors the enroll exit
  code.

## v0.68.0 — Fleet software inventory + patch compliance (July 2026)
- **See your whole fleet's software at a glance.** A new **📦 Inventory** tab
  aggregates every agent-reported title across all devices — install count,
  client spread, version count, publisher — with search. Click a title to see
  **exactly which devices run it** (instant vulnerability response: "who's on
  OpenSSL 3.0.1?").
- **Patch compliance, fleet-wide.** A rollup of **% compliant, devices reporting,
  total pending, and critical-pending**, plus **compliance by client**, the
  **worst-offending devices**, and the **most-common pending updates** (by KB,
  with device spread). Pairs with auto-remediation — add a `patch_behind` rule to
  auto-fix the laggards.
- `services/inventory.py` (read-only aggregation over `device_software` /
  `device_patches`), `routes/inventory.py`: `GET /api/inventory/software`,
  `GET /api/inventory/software/devices`, `GET /api/inventory/patches` (patch
  rollup staff-only; software scoped to the caller's client for client users).
  **No schema change.**
- Verified offline (smoke + unit): titles aggregate with correct device/version/
  client counts; the device drill-down finds machines running a title; the patch
  rollup computes compliance %, severity mix, worst devices, and top pending
  updates; client software is self-scoped and the patch rollup is staff-only (RBAC).

## v0.67.0 — Posture trend + grade-drop alerting (July 2026)
- **Catch a slipping client before the QBR.** The scheduler now **snapshots every
  client's security scorecard ~daily**, and the moment a client's grade **slips
  between snapshots** (e.g. B→C) it raises a staff notification — so a degrading
  posture surfaces immediately instead of three months later.
- **Trend everywhere it matters:** the Security Scorecards portfolio shows a
  **▲/▼ delta** next to each client's score; `GET /api/posture/{id}` now carries
  a `trend` (latest vs previous), and `GET /api/posture/{id}/history` returns the
  snapshot series (staff or that client's own users) for charting.
- `services/posture_history.py` (snapshot + throttle + grade-drop detection;
  A→F ladder, "N/A" never alerts), wired into `run-checks` (≈20h throttle), with
  `POST /api/posture/snapshot` to force one now (staff). New `posture_snapshots`
  table (migration `a7b8c9d0e1f3` + startup self-heal).
- Verified offline (smoke + unit): a snapshot is taken and throttled; worsening a
  client's devices drops the grade on the next snapshot and raises a
  **posture_drop** notification; history grows and trend reads *down*; a client
  can read their own history but can't trigger the portfolio snapshot (RBAC).
  Migration up/down/up clean.

## v0.66.0 — Client portal, reimagined (self-service that sells your value) (June 2026)
- **A portal clients actually want to log into.** The self-service portal is
  rebuilt around what a client cares about:
  - A **hero with their A–F security grade** + overall score — "managed &
    monitored by BVTech" — backed by a **"How we're protecting you"** card that
    breaks the grade into Endpoints / Patching / Microsoft 365 / Threats and
    lists **"what we're working on for you"** (the posture recommendations).
  - A **Balance Due** KPI + a pay banner: outstanding total, unpaid count, and a
    one-tap link to **pay online by any method** (card, PayPal, Venmo, wire,
    check…). Invoices now show the **remaining balance** and a *Pay / view* link.
  - KPI strip (Devices · Active Alerts · Balance Due · Open Requests), polished
    devices/alerts tables, submit-a-ticket + threaded conversation, security
    findings, and documentation — all client-scoped.
- Pure front-end on top of existing client-scoped APIs (`/api/posture/{id}`,
  `/api/billing/aging`, `/api/invoices` with balance, tickets, KB) — **no new
  endpoints, no schema change**; everything stays behind the same RBAC.
- Verified offline (smoke): the portal shell renders and a **client** can read
  exactly what it surfaces — their own posture grade + domains, their balance/
  aging (scoped to them), and invoices carrying a balance with **drafts never
  exposed**.

## v0.65.0 — Auto-remediation: detect → fix, automatically (June 2026)
- **Close the loop without a human in the middle.** Define a **remediation rule**
  ("when **device_offline** on this client, run **Restart-Agent**") and when a
  matching monitoring alert opens, Pulse queues an **already-approved**
  deployment of that script on the affected device. The native agent pulls it on
  its next check-in, runs it, and reports the exit code + output back.
- **Real safety rails** (this is remote execution): the target script must be
  **enabled** (a disabled script never auto-runs), a **per-device + per-script
  cooldown** stops a flapping alert from re-firing instantly, and a **daily cap**
  stops a stuck condition from hammering the box. Every auto-run is an approved,
  audited, tagged deployment — and an active alert never re-fires (no spam).
- Rules can target one client or all; they only ever run on the device the alert
  is about. `services/auto_remediation.py` (cooldown/cap/enabled-guard, hooked
  into both the agent check-in and the `run-checks` sweep), `routes/remediation.py`
  (rule CRUD + `/recent` + `/alert-kinds`, staff-gated), new `remediation_rules`
  table (migration `f6a7b8c9d0e2` + startup self-heal), and an **🤖
  Auto-Remediation** card in the Scripts tab (rule builder + recent auto-fixes).
- Verified offline (smoke + unit): an enabled rule fires once on a fresh offline
  alert and queues an APPROVED deployment (version-snapshotted) into the device's
  command queue; a disabled-script rule never fires; cooldown + daily-cap + next-
  day reset all hold; an already-active alert doesn't re-fire; clients can't see
  or create rules (RBAC). Migration up/down/up clean.

## v0.64.0 — Client security scorecard (A–F posture, client-shareable) (June 2026)
- **One graded posture report per client.** Rolls the data Pulse already collects
  into a single **A–F grade** across four domains, each scored 0–100:
  **Endpoints** (% online · % AV/EDR-protected · avg health), **Patching**
  (% fully patched · pending updates), **Identity** (Microsoft 365 Secure Score +
  risky sign-ins), and **Threats** (open security findings, weighted).
- **Fair by design:** a domain with no data (e.g. no M365 tenant linked) is
  *excluded* from the weighting, not scored zero — so a small client isn't
  unfairly graded. The overall is the weighted average of whatever's present,
  with **plain-English recommendations** generated from the gaps.
- **Portfolio view + drill-down.** `GET /api/posture` lists every client graded
  **riskiest-first** (staff); `GET /api/posture/{id}` returns the full breakdown
  (staff, or that client's own users). A **🛡️ Security Scorecards** card in the
  Security tab shows the portfolio with per-domain grades and a click-through
  breakdown, and the **client QBR report + CSV** now carry the posture grade so
  it's client-shareable.
- `services/posture.py` (pure read-only aggregation; reuses `services/security`
  for the threats domain). No schema change.
- Verified offline (smoke + unit): domains score and grade correctly, empty
  domains are excluded, recommendations fire on real gaps, the portfolio sorts
  worst-first, the report/CSV expose the grade, and a client sees only their own
  scorecard — not the portfolio or another client's (RBAC).

## v0.63.0 — Finance cockpit: the money picture in one view (June 2026)
- **A revenue cockpit at the top of Billing.** One call pulls the whole money
  picture together: **collected this month / last 30 days / all-time**,
  **outstanding** and **overdue** A/R, open-invoice count, the **payment-method
  mix** (how clients actually pay — card vs check vs wire vs PayPal…), and the
  **most recent payments**.
- `services/finance_kpis.py` (read-only aggregation over the payment ledger +
  A/R aging), `GET /api/billing/finance` (OWNER/TECH), and a Finance Cockpit card
  with KPI tiles, a method-mix bar breakdown, and a recent-payments list.
- Verified offline (smoke + unit): collected totals sum the ledger, outstanding/
  overdue match A/R, the method mix groups by rail, recent payments surface, and
  it's staff-only (RBAC).

## v0.62.0 — A/R aging + automatic payment reminders (June 2026)
- **See who owes you, by age.** A new **📊 A/R Aging** view buckets every
  outstanding (sent, unpaid) invoice by how overdue it is — **current · 1-30 ·
  31-60 · 61-90 · 90+** — with dollars rolled up per bucket and an overdue total.
  `GET /api/billing/aging` (staff see the whole book or one client; a client sees
  only their own).
- **Get paid without chasing.** Overdue invoices now **email a polite reminder**
  to the client's billing contact (the `Client.email`, else their CLIENT_ADMIN)
  with a link to view + pay — automatically on the scheduler tick, on a **7-day
  cadence** (tracked via `invoices.last_reminded_at`) so it never nags. Plus a
  one-click **✉️ remind** on any sent invoice and an owner **Send due reminders**
  sweep button.
- `services/ar_aging.py` (pure bucketing + an injectable mail sender so reminders
  are testable offline and an undeliverable attempt doesn't mark an invoice
  reminded), wired into `POST /api/automation/run-checks`, `POST
  /api/billing/send-reminders` (OWNER) + `POST /api/invoices/{id}/remind`
  (OWNER/TECH). New `invoices.last_reminded_at` / `reminder_count` columns
  (migration `e5f6a7b8c9d1` + startup self-heal) and an A/R Aging dashboard card.
- Verified offline (smoke + unit): invoices land in the right age buckets (paid +
  draft excluded); a manual remind emails the billing contact; the sweep respects
  the 7-day cadence (a just-reminded invoice is skipped, an un-reminded one
  fires); clients see only their own A/R and can't run the sweep (RBAC). Migration
  up/down/up clean.

## v0.61.0 — Payments & balance tracking: record any payment, auto-reconcile (June 2026)
- **Close the loop on every payment rail.** The offline methods from v0.59 (wire,
  check, Zelle, Cash App, PayPal, cash) have no webhook — so staff can now
  **Record a payment** against any invoice (amount + method + reference/note).
  Card payments via Stripe record themselves through the webhook.
- **Partial payments + live balance.** An invoice's **balance = total − Σ
  payments**; it stays open with a shrinking balance until paid, then
  **auto-marks paid** at zero. The Billing list shows the balance and a **＋
  payment** action; invoices carry `amount_paid` / `balance`.
- **Client pay links bill the *remaining* balance.** PayPal/Venmo/Cash App links
  and the Stripe checkout now charge exactly what's left, and the invoice page
  shows "Paid X of Y · Balance due Z". Once settled, the pay options close out.
- `services/billing_payments.py` (balance math + the single status-reconcile
  path, idempotent on a Stripe object id so webhook retries don't double-count),
  new `payments` table (migration `d4e5f6a7b8c0` + startup self-heal),
  `POST/GET /api/invoices/{id}/payments` (OWNER/TECH record, scoped reads).
- Verified offline (smoke + unit): a partial payment shrinks the balance and
  re-prices the pay links; a second payment auto-reconciles to **paid** and
  closes the options; the Stripe webhook records a card payment **once** (retry
  is a no-op); non-positive amounts and unknown methods are rejected; clients
  can't record payments (RBAC). Migration up/down/up clean.

## v0.60.0 — Power dialer + call coaching (June 2026)
- **Work a call list one click at a time.** A new **📞 Power Dialer** builds a
  queue — numbers typed/pasted in, or pulled straight from CRM contacts (has a
  phone, not do-not-contact, filtered by pipeline status/market) — then **Dial
  next** rings your Dialpad device → the prospect, you log a **disposition**
  (connected / voicemail / callback / not-interested / won / do-not-call / …) +
  notes, and it advances.
- **Live coaching on every call.** Attach a **CallScript** (opening line, talking
  points, and **objection→response cards**) to a session and it's shown beside
  the dialer while you talk. **Live stats** roll up per session: remaining,
  dialed, **connect rate**, and **won**.
- **Writes back to the CRM.** A call against a CRM contact is logged to that
  contact's timeline (with the disposition); a **do-not-call** outcome flips the
  contact's `do_not_contact` flag so campaigns and future pulls skip them.
- `services/power_dialer.py` (pure queue/stat logic; Dialpad HTTP isolated behind
  an injectable `CALLER`), `routes/dialer.py` (sessions, scripts, dial-next,
  disposition, skip, pause/resume/complete — all OWNER/TECH), new `call_scripts`
  / `dial_sessions` / `dial_entries` tables (migration `c3d4e5f6a7b9` + startup
  self-heal), and a full Power Dialer tab in the dashboard.
- Verified offline (smoke + unit): CRM-pull builds the queue (skips no-phone),
  dial-next flips an entry to *calling*, disposition advances + updates live
  stats, a do-not-call result writes DNC back to the CRM contact, bad
  dispositions are rejected, a paused session refuses to dial, and clients are
  locked out (RBAC).

## v0.59.0 — Pay any way: PayPal, Venmo, Cash App, Zelle, wire, check, QuickBooks (June 2026)
- **Hand clients every way to pay, right on the invoice.** Configure each rail
  once in **Settings → Payment Methods** and it renders automatically on every
  invoice the client opens, with the **amount and invoice number pre-filled** into
  each pay link:
  - **PayPal** (PayPal.me deep link, or email instructions), **Venmo**, **Cash App**
    — one-tap deep links to `paypal.me` / `venmo.com` / `cash.app` for the exact total.
  - **Zelle**, **Bank wire / ACH** (beneficiary + routing/account), **Check by mail**
    (payee + address) — clean printed instructions on the invoice.
  - **QuickBooks** pay link/note, plus a fully **custom** rail (label + URL or
    instructions) for anything else (Wise, crypto, …).
  - **Card via Stripe** still shows its secure-checkout button alongside the rest.
- A method only goes **live once its required fields are set**, so clients never
  see a half-configured option. Wire/Zelle/PayPal details are shown (not masked) —
  they're meant for the payer. `services/payment_methods.py` (pure link/instruction
  builders), `GET /api/payments/invoices/{id}/options` (invoice-scoped, same access
  control as the invoice itself), `PUT /api/payments/methods/settings` (OWNER).
- Verified offline (smoke): empty config offers nothing; configuring PayPal/Venmo/
  Cash App/wire lights them up with the **$1,500.00 total + `Invoice INV-…` memo
  pre-filled**; partial saves don't wipe other rails; clients can read their own
  invoice's options but **cannot** configure methods (RBAC).

## v0.58.0 — Recurring auto-invoicing: contracts bill themselves (June 2026)
- **Set it and forget it.** Flag a service contract **Auto-invoice** and Pulse
  generates a **draft invoice** for the contract amount every period (monthly /
  quarterly / annual) on the scheduler tick — no more manual re-keying.
- Deduped via `contracts.last_invoiced_at` (a guard slightly under the nominal
  period) so a contract bills **about once per period, exactly once** even though
  the tick runs continuously. `services/recurring_billing.py` (pure date logic),
  wired into `POST /api/automation/run-checks`, plus a manual **`POST
  /api/contracts/run-recurring`** (OWNER) to bill on demand.
- Verified offline (smoke + unit): only a due contract bills; a contract invoiced
  5 days ago is skipped; an immediate second run creates nothing; a never-billed
  contract bills once and `last_invoiced_at` is stamped; RBAC enforced.

## v0.57.0 — Stripe payments: clients pay invoices online, auto-reconcile (June 2026)
- A **💳 Pay link** on any sent invoice creates a **Stripe Checkout Session** for
  the invoice total; the client pays online and the invoice **auto-marks paid**
  via a **signature-verified webhook** (`POST /api/payments/webhook`, public — the
  HMAC signature is the auth). `services/stripe_pay.py` (injectable HTTP) +
  `routes/payments.py` + a Stripe Settings card (shows the webhook URL to register).
- Verified offline: checkout form (cents/metadata), webhook signature verify
  (valid passes; **tampered + stale rejected**), and end-to-end auto-reconcile
  (a valid `checkout.session.completed` flips the invoice to paid). Masked key,
  RBAC, graceful upstream errors.

## v0.56.0 — One-click OAuth Connect + self-refreshing tokens (June 2026)
- **Authorize once, never paste a token again.** New one-click **Connect** for
  LinkedIn, Google Business Profile, and QuickBooks — built on the existing
  PKCE OAuth framework, with each provider's app credentials read from the vault.
- **Self-refresh forever:** `oauth.get_valid_token()` always hands back a valid
  access token, refreshing on expiry **and persisting the rotated refresh token**
  (critical for QuickBooks, which rotates every refresh) so a connection never
  silently dies. On connect, LinkedIn's person URN is auto-filled from `userinfo`
  and QuickBooks' realm id is captured — nothing left to type.
- `GET /api/oauth/connections` (status + connect URLs), a **🔗 One-click Connect**
  card in Settings (shows the redirect URI to register), and the LinkedIn
  publisher now prefers the auto-refreshed OAuth token. Verified: token
  passthrough/refresh + rotated-refresh persistence, provider registration +
  scopes + LinkedIn no-PKCE, app-config gating, RBAC.

## v0.55.0 — Morning Briefing + scheduled digest email (June 2026)
- A cross-business **"what needs attention" briefing** (`services/briefing.py`):
  active alerts, SLA breaches, failing integrations, offline devices, overdue
  invoices, fresh CRM leads, and contracts expiring within 30 days — one
  glanceable summary. `GET /api/briefing` (staff) + a **📋 Morning Briefing**
  button on the Command Center.
- New automation action **`send_digest`** emails that briefing via M365. Pair it
  with a `schedule` rule and **Pulse emails you a morning briefing every day at
  7am** — the capstone of the automation engine. Skips gracefully if the mailbox
  isn't configured. Verified: briefing aggregation + render, staff-only, action
  graceful-skip.

## v0.54.0 — Documentation & Password Vault (IT Glue / Hudu surface) (June 2026)
- A native **per-client documentation vault**: knowledge articles, network/config
  notes, contacts, license keys, and an **encrypted password vault**. Passwords/
  keys are Fernet-encrypted at rest, never returned by list/read, and revealed
  only via an explicit, **audited** reveal (who saw which credential, when).
- RBAC: staff manage everything; the **client's own users can read their
  non-secret docs but never passwords**, and can't reveal or create. New
  `documents` table (+ migration up/down/up), `routes/docs.py`, and a
  **📚 Docs & Passwords** tab (add/search/reveal-to-clipboard).
- Verified: encrypted secret never leaks in list, audited reveal returns
  plaintext for staff, client sees articles but not passwords and is blocked from
  reveal/create.

## v0.53.0 — Scheduled automations (time-based rules) (June 2026)
- Automation rules can now fire **on a schedule**, not just on events. New
  `schedule` trigger; the schedule lives in the rule's conditions:
  `{"every":"day","at":"08:00","tz":"America/Chicago"}` (also `hour` and
  `week` + `day`). The run-checks tick runs due rules and dedups via the rule's
  last-run, so each schedule fires once per period.
- Combined with the v0.51 cross-integration actions, this means **Pulse can post
  to LinkedIn, send an M365 email, or run any action on a timer itself** — no box
  cron required. `⏰ On a schedule` added to the rule builder with an example.
- Verified: due-detection across day/hour/week with timezones + before-time + the
  next-day reset; run-scheduled fires due rules (with graceful action skips) and
  dedups within the period.

## v0.52.2 — Connector health watchdog runs itself (June 2026)
- The health watchdog is now **automatic**: the `run-checks` cron tick triggers a
  connector-health sweep **at most once per hour** (`integration_health.maybe_sweep`)
  — so an expired token or dead API credit raises an alert on its own, no "Test
  all live" click needed. Throttled off the newest `last_health_at` (no extra
  table); skips entirely when nothing checkable is configured. Verified:
  skip-when-none, run-when-due, throttle-within-hour, re-run-after-interval.

## v0.52.1 — Fix: saved settings read as "not connected" + agent onboarding (June 2026)
- **Root cause of "I saved it but it shows not connected":** schema drift. The
  v0.52 migration adds health columns to `integration_connections`; `deploy.sh`
  runs `alembic upgrade head` best-effort (`|| WARN`) AFTER starting the new code,
  so a failed/late migration left the app querying columns the DB lacked — and
  **every** integration query then errored, making *saved* creds read as absent.
  Fix: **startup now reconciles its own schema** (create missing tables + ADD
  missing columns, idempotent, every boot, all dialects) so the code never
  queries a column the DB lacks. Verified against a simulated old-schema DB: the
  saved mailbox row was intact and read back correctly after self-heal. **No data
  was lost.**
- **Agent onboarding is now paste-proof:** pasting the whole command (or the token
  with quotes/spaces, or at the wrong prompt) is parsed correctly — the JWT token
  and any `--url` are extracted. Fixes the `unknown url type` enrollment failure.
  Agent → v1.5.1.
- **SSO sign-in is vault-driven:** "Sign in with Microsoft/Google" lights up from
  credentials entered in **Settings → Single Sign-On** (Microsoft can reuse the
  M365 mailbox app), not box env vars. New `GET/PUT /api/oauth/sso-settings`
  (shows the redirect URIs to register); providers resolve from the vault on every
  OAuth request. SSO card added to Settings.

## v0.52.0 — Connector health watchdog (June 2026)
- **Pulse now tells you when an integration breaks** instead of failing silently.
  `services/integration_health.py` live-tests each connected provider (M365,
  HubSpot, QuickBooks, GBP, Tactical RMM), records the result on the connection
  (`last_health_ok/at/error`), and **raises a critical notification on each NEW
  failure** (expired token, exhausted credit) — once, no alert storms.
- Network checks run BEFORE any DB write (no transaction held open during slow
  I/O). `POST /api/integrations/health/check` (OWNER/TECH) runs the sweep; the
  **🔌 Integration Hub** gains a **🩺 Test all live** button and per-tile health
  (✓ live / ⚠ error). `integration_connections` health columns (migration
  up/down/up verified).
- Verified: detect-fail → record + notify-once (no storm), skip for unconfigured,
  status carries health, RBAC.

## v0.51.0 — Automation reaches across integrations (June 2026)
- The automation engine gains **outbound-comms actions**: `send_email` (via the
  M365 mailbox) and `linkedin_post` (via the LinkedIn integration) — so a rule can
  now *act*, not just file records. Triggered by the same events (alert opened,
  ticket created, SLA breach). `{hostname}/{message}/{severity}/{subject}`
  placeholders are interpolated from the event.
- Security boundary preserved: actions reach **configured integrations, never a
  device/endpoint**, and **no-op gracefully** (run still succeeds, summary says
  "skipped") when that integration isn't connected. Verified: dispatch with both
  actions unconfigured → graceful skips + green run; interpolation; rule
  validation accepts the new types and still rejects unknown ones.

## v0.50.0 — Integration Hub + safe key updater (June 2026)
- **🔌 Integration Hub** on the Integrations tab — a live board of every platform
  connector (M365 mailbox, LinkedIn, GBP, Dialpad, RMM, prospecting, HubSpot,
  QuickBooks, the website publishers) showing **connected / not-set-up** at a
  glance; click a greyed tile to jump to its setup. `GET /api/integrations/status`
  aggregates vault state per provider. No more silently-dead credentials.
- **`automation/set_key.py`** — idiot-proof, JSON-safe updater for agent.env:
  timestamped backup, atomic write, re-validates, never prints secrets. Run
  `python3 automation/set_key.py anthropic_key "sk-ant-…"` or `--show` to list keys.

## v0.49.1 — Publisher works end-to-end on the JordanPolasek.com site (June 2026)
- Box logs confirmed the JP publish path was structurally wrong for that site:
  posts live at `/<slug>/index.html` (not `blog/<slug>.html`), the skeleton glob
  (`blog/*.html`) found none → bvtech-branded standalone fallback, and the
  clone path nuked the `<h1>`/byline that sit outside the content wrapper.
- `publish_post.py` gains `--skeleton-glob`, `--post-path {blog-file|slug-folder}`,
  `--content-class`; `content_studio` transplants into a known content wrapper
  (preserving a sibling `<h1>`/byline) and honors a `path_style` URL convention.
  `daily_jp_blog.sh` now uses `--skeleton-glob '*/index.html' --post-path
  slug-folder --content-class content`.
- Verified end-to-end: JP clone → folder URL, h1 replaced, byline + site chrome
  preserved, content swapped, **zero bvtech.org leakage**; bvtech.org publishing
  byte-for-byte unchanged. (Note: the daily *generation* itself was failing on
  the box with "Credit balance is too low" — an Anthropic billing issue, separate
  from this publisher fix.)

## v0.49.0 — HubSpot + Google Business Profile connectors (June 2026)
- **HubSpot** — push a Pulse CRM contact to HubSpot (create-or-update by email +
  log a note), one click from the contact (**↗ HubSpot**). `services/hubspot.py`
  (private-app token; injectable so upsert/note mapping is unit-tested offline),
  `routes/hubspot.py`, Settings → HubSpot card with Test.
- **Google Business Profile** — publish a localPost (update + optional CTA) to
  your Google listing for reputation/visibility. `services/gbp.py` (OAuth refresh
  + v4 localPosts; injectable, unit-tested offline), `routes/gbp.py`, Settings →
  GBP card with **Post now**.
- Both staff-only, audited, creds encrypted/masked. Verified: GBP localPost
  payload, HubSpot create+update+note paths, gating + RBAC.

## v0.48.1 — Fix: JordanPolasek.com auto-posts were getting bvtech.org URLs (June 2026)
- **Root cause** of "no JP posts": `content_studio` hardcoded `SITE =
  https://bvtech.org`, so every post published to the JP repo got a **bvtech.org
  canonical/OG/sitemap URL + BVTech branding** — the JP daily run wrote a
  bvtech.org `<loc>` into jordanpolasek.com's sitemap (visible in the live site).
- Threaded **site / org / author_url** through `normalize_post` + `render` +
  schema + the standalone template (defaults unchanged → Content Studio + BVTech
  posts identical). `publish_post.py` gains `--site/--org/--author-url`;
  `daily_jp_blog.sh` now publishes with `--site https://jordanpolasek.com --org
  "Jordan Polasek"`. Verified: JP posts get jordanpolasek.com canonical + sitemap
  entries; BVTech default intact; Content Studio smoke green.

## v0.48.0 — QuickBooks Online: push invoices to accounting (June 2026)
- Connect QuickBooks once (client id/secret + realm id + refresh token, encrypted
  in the vault) and **push a Pulse invoice into QBO** — finds/creates the customer,
  maps line items, creates the invoice. `services/quickbooks.py` (token refresh +
  v3 API over stdlib HTTP; injectable so the customer/invoice mapping is unit-
  tested offline), `routes/quickbooks.py`, Settings → QuickBooks card.
- `POST /api/quickbooks/invoices/{id}/push` (OWNER, audited); sandbox toggle.
  Verified: customer find-or-create, line/amount mapping, sandbox base URL,
  masked creds, gating + RBAC.

## v0.47.0 — Remote desktop: native WebRTC relay (backbone) (June 2026)
- **We are the signaling server** — no third party. New `routes/remote.py` brokers
  a peer-to-peer WebRTC session between an operator (browser) and a device (agent):
  both join `/api/remote/ws/{token}` and Pulse forwards the SDP offer/answer + ICE.
  Media flows P2P; only signaling crosses Pulse.
- Session lifecycle in `remote_sessions` (migration up/down/up verified). Start is
  **OWNER-only + audited**; the operator WS authenticates with the session cookie
  (staff only), the agent WS with the device's enroll-id/agent-key; the token
  scopes the bridge to exactly two peers.
- Branded **viewer page** (`/remote/{token}`) — RTCPeerConnection, renders the
  remote screen, forwards mouse/keyboard over a data channel. **🖥 Remote** button
  on each device. Agent gains a poll (`/api/agent/remote-sessions`) and an optional
  WebRTC add-on (`agent/opspilot_remote.py`: aiortc screen track + pyautogui input)
  that activates when a session is pending and the extras are installed.
- **Verified**: the full signaling relay (operator+agent join, offer/answer/ICE
  both ways, unauthorized operator rejected, session connected→closed) in the
  smoke suite. The agent screen-capture media path needs validation on real
  Windows hardware (next step); the relay/signaling/viewer are done and tested.

## v0.46.0 — Real endpoint RMM: live status, push-command console, endpoint tickets (June 2026)
- **Proved the agent works on both sides** with a live end-to-end harness
  (`scripts/agent_e2e.py`): starts the real server, runs the actual agent process
  → enroll → telemetry → push-command → ticket, asserting the device appears with
  data. (A real-world "installed but no device" is almost always a failed `.exe`
  download or expired token failing silently — the round-trip itself is correct.)
- **Live status**: agent reports `agent_version` + `platform`; check-in cadence
  dropped to **~60s**; `/api/devices` now returns `online`, version, platform, and
  the logged-in user. Devices tab shows an online dot, version, user.
- **Remote console (push commands)**: OWNER can run a command on a device
  (`POST /api/agent/devices/{id}/run-command`) — it becomes an approved job the
  agent runs and reports output back (`/commands`). New ⌨ Console modal on the
  Devices tab. Command execution is now **on by default** in the agent (still only
  ever runs owner-approved jobs; `--no-remote-scripts` to disable).
- **Endpoint tickets**: the person at the PC can file a ticket from the agent
  (`opspilot-agent submit-ticket "…"` → `POST /api/agent/ticket`), tagged with the
  host and SLA-stamped like any ticket. Agent gains `submit-ticket` + `status`.
- Verified end-to-end (live harness) **and** in the smoke suite: version/online,
  endpoint ticket, full push-command loop, OWNER-only gating. Migration up/down/up.

## v0.45.0 — Campaigns: email + SMS outreach to the CRM (June 2026)
- **Email campaigns** via the M365 mailbox and **SMS campaigns** via Dialpad,
  targeting a slice of the CRM pipeline (by status / market / explicit ids).
  Compliance is built in: email skips `do_not_contact` and appends an opt-out
  footer (CAN-SPAM); SMS only reaches `sms_opt_in` numbers (TCPA). `{first}` /
  `{company}` personalization. Every send lands on the contact's timeline.
- `services/campaigns.py` (injected transport → audience/compliance/personalize/
  logging unit-tested offline), `routes/campaigns.py`, a **📣 Campaigns** card on
  the CRM tab with always-available **dry-run preview**. Staff-only + audited.
  Verified: email/SMS audience filtering, dry-run no-op, send+log+footer, failure
  counting, RBAC.

## v0.44.0 — Prospecting: find & score leads into the CRM (June 2026)
- **Lead-gen engine** ported from the Command Center. Google Places discovery of
  real local businesses by market + industry, **MSP-readiness scored 0-100**,
  deduped, and dropped straight into the CRM pipeline as `source=scrape` contacts.
- `services/prospecting.py` (injectable Places client — scoring/dedup unit-tested
  offline with a fake), `routes/prospecting.py`, a **🔎 Find new leads** card on
  the CRM tab, and a Google-key field in Settings (encrypted in the vault).
- Markets: Austin, San Antonio, Houston, El Campo. Staff-only + audited.
  Verified: scoring math, cross-run dedup, market validation, masked key, RBAC.

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
