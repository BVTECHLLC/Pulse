# BVTech MSP Command Center — v31.0 Changelog

**Release: April 2026**
**Codename: SUPER POSTING + LOCAL AUTOMATION**

## TL;DR

v31 is the "automate the automator" release. Three big additions
on top of v30's working Super Posting engine:

1. **HubSpot email tracking** — every manually-sent email lands
   on the contact's timeline via the HubSpot v3 Engagements API.
   Two methods: BCC forwarding (works with any mail client) or
   one-click manual logging through the new HS Track tab.
2. **Local automation engine** — SQLite event log + in-process
   task runner + Windows Task Scheduler integration. Stops
   relying on the web UI being open or Claude being called.
   Five built-in tasks ship by default, and you can install any
   of them to Windows Task Scheduler with one click so they
   survive reboots.
3. **Polish pass** — stripped `v17/v18/v20/v23/v25/v26/v27/v28/
   v29/v30` version graffiti from every tab. Moved the changelog
   history into a single **🎁 What's New** modal accessible from
   the dashboard. First-run auto-shows the v31 highlights.

Nothing from v30 was removed. Cross-linking still builds forward,
the GBP OAuth flow still works, the Cloudflare Pages deployer
still walks your full site folder. v31 is pure additive.

---

## What's new in detail

### 1. `hubspot_tracker.py` — new module (~350 lines)

Standalone wrapper around HubSpot's CRM v3 API. Handles:

- **`HubSpotTracker`** class with `find_contact_by_email()`,
  `create_contact()`, `find_or_create_contact()`,
  `log_email()`, `log_note()`, `log_call()`,
  `track_email_to_address()` (one-call: find/create + log),
  `bulk_enrich_emails()` (rate-limited batch), `verify_connection()`,
  `count_contacts()`.
- **Error normalization** — 401 → HubSpotAuthError with "token
  invalid/expired"; 403 → scope error with the exact scopes you
  need (`crm.objects.contacts.read/write`, `crm.objects.emails.write`);
  429 → HubSpotRateLimitError.
- **Rate limiting** — `bulk_enrich_emails()` caps at ~8 req/sec to
  stay under HubSpot's 100 req/10s burst limit.
- **Subject capping** — subject lines are truncated at 998 chars
  and bodies at 65000 chars to match HubSpot's field limits.

**Endpoints used:**
- `POST /crm/v3/objects/contacts/search` (filterGroups with
  `{propertyName: "email", operator: "EQ"}`)
- `POST /crm/v3/objects/contacts` (create)
- `POST /crm/v3/objects/emails` (engagement with
  `associationTypeId: 198` = EMAIL_TO_CONTACT)
- `POST /crm/v3/objects/notes` (associationTypeId 202)
- `POST /crm/v3/objects/calls` (associationTypeId 194)
- `GET /account-info/v3/details` (verify)

### 2. `local_automation.py` — new module (~550 lines)

Three subsystems in one file:

**`LocalEventLog`** — SQLite-backed append-only log stored in
`local_events.db` in the app directory. Schema:

```
events (id, ts, ts_epoch, category, action, target, success, details_json)
```

With indexes on `ts_epoch`, `category`, and `target`. Methods:
`record()` (thread-safe, never raises), `query()` (filter by
category/target/since/limit), `stats()` (total + by_category +
failures + last_24h + db_size), `rotate_if_too_big()` (moves to
`backups/` with timestamp when over 100 MB).

**`ScheduledTask` dataclass + `TaskRunner`** — in-process scheduler.
Background thread wakes every 60 seconds and fires any tasks whose
`next_run` has passed. State persists to `automation_state.json` on
every run (last_run, success_count, failure_count, enabled,
last_error). `compute_next_run()` handles four schedule types:
- `daily` — next occurrence of `preferred_hour:00`
- `hourly` — top of the next hour
- `weekly` — next occurrence of `preferred_weekday` at `preferred_hour`
- `every_N_minutes` — rolling interval

Tasks can be enabled/disabled individually and triggered manually
via `run_now()`.

**`WindowsTaskScheduler`** — thin wrapper around `schtasks.exe`.
All tasks get a `BVTech_` prefix so they group in `taskschd.msc`.
Uses `/RL LIMITED` (no admin required) and `CREATE_NO_WINDOW` so
the shell-outs don't flash console windows. Methods: `install_daily`,
`install_hourly`, `uninstall`, `list_installed`, `query`. On
non-Windows it returns a clear "not on Windows" error instead of
crashing.

### 3. Five built-in scheduled tasks

Defined in `build_default_tasks()` and registered automatically at
app startup:

| Task | Schedule | What it does |
|---|---|---|
| `daily_config_backup` | Daily 3am | Copies `bvtech_config.json` to `backups/` with a date stamp, keeps last 14 |
| `weekly_log_rotation` | Sunday 4am | Rotates `local_events.db` if over 100 MB |
| `daily_posts_index_prune` | Daily 2am | Drops `posts_index.json` entries older than 180 days |
| `hourly_csv_watcher` | Hourly | Checks `prospects.csv` mtime, counts new rows since last check, logs the delta |
| `daily_hubspot_enrichment` | Daily 6am | Finds prospects missing `hubspot_contact_id`, creates/looks them up in HubSpot, writes the IDs back to the CSV (capped at 50/run to stay under the API rate limit) |

Each task has an **Install to Windows** button next to it in the
new Automation tab. Clicking it registers the task with the
Windows Task Scheduler via `schtasks /Create /SC DAILY /TN
BVTech_<task> /TR "pythonw.exe bvtech_app.py --run-task <task>"`.

### 4. `--run-task` CLI flag

New entry point in `bvtech_app.py`'s `if __name__ == "__main__":`
block. When you run:

```
pythonw bvtech_app.py --run-task daily_config_backup
```

It initializes `LocalEventLog` and `TaskRunner`, registers the
default tasks, fires the named one, logs success/failure to the
event log, and exits. **No Flask server starts.** This is what
the Windows Task Scheduler entries shell out to when they fire at
3am / 6am / whenever. Your machine can run automation even when
you haven't opened the BVTech UI in days.

### 5. New **📬 HS Track** tab

Four stat cards:
- HubSpot Contacts — total contacts in your portal (via
  `count_contacts()`)
- Tracked Today — count of `email / hubspot_track` events in
  the local log from today
- Prospects CSV — total rows in `prospects.csv`
- Needs Enrichment — rows without `hubspot_contact_id`

Three action cards:
- **🔑 BCC Forwarding** — text input for your HubSpot BCC address
  (`yourtoken@bcc.hubspot.com`), Save button, Copy button, and
  setup instructions linking to HubSpot's docs
- **📝 Log Manual Email** — form with to/subject/body/fname/lname/
  company/phone fields, "Log to HubSpot" button that calls
  `/api/hubspot/track-email`, Verify Connection button, Clear
  button, and an inline status log
- **🔄 Bulk Enrich CSV** — button that runs the
  `daily_hubspot_enrichment` task on demand

Plus a **Recently Tracked** list pulled from the local event log
showing the last 50 `email` events with status, timestamp,
recipient, contact ID, and any error.

### 6. New **⏰ Automation** tab

Four stat cards: Events Logged, Last 24h, Failures, DB Size.

**Scheduled Tasks section** — renders every registered task as a
card showing:
- Name + schedule type
- Description
- Last run / next run timestamps
- Success and failure counts
- Last error (if any) with a warning icon
- Toggle button (enabled/disabled)
- Run Now button
- Install to Windows button

**Event Log viewer** — live table (text log, really) of the most
recent 200 events from `local_events.db`. Filter dropdown by
category (all / automation / email / post / scrape / call / error).
Each row shows: success icon, timestamp, category, action, target.

### 7. New **🎁 What's New** modal

Single popup that replaces the scattered `v20 NEW`, `v25 NEW`,
`v28 NEW` tab badges and the "v30 FINAL — Super Posting" banner
text. Driven by `/api/whats-new` which returns a structured
`_V31_WHATS_NEW` dict with the current release highlights plus a
compressed history of v27/v28/v29/v30.

- Button on the dashboard header
- First-run auto-show based on `localStorage.bvtech_last_seen_version`
- Collapsible "📜 Previous releases" section
- Click outside or × to dismiss
- Remembers the last version you saw so it doesn't nag on every
  launch

### 8. Polish pass — stripped version graffiti

Removed user-visible version tags from:

- Tab bar: `v30` badge on Super Posting, `v20` badge on WARMODE,
  `NEW` badge on CyberAudit
- Dashboard headline: "v30.0 FINAL — Super Posting" → "BVTech
  Command Center"
- Dashboard description: removed the "v20: BVTech.org now deploys
  to Cloudflare Pages!" brag
- Super Posting tab title: "v30 — 4-Channel Publishing" → just
  "4-Channel Publishing"
- WARMODE welcome: "✅ WARMODE v20.0" → "✅ WARMODE"
- WordPress tab: "Legacy (Deprecated in v23)" → "Legacy
  (Deprecated)"
- Super Posting log banner: "ORM POST CREATED (v17)" → "SUPER
  POST CREATED"
- Settings banner: "MSP COMMAND CENTER — v30 FINAL — Super Posting"
  → "MSP COMMAND CENTER — v31 FINAL"
- Settings field labels: "BVTech Site Root (v29)" → "BVTech Site
  Root", "JP Site Root (v29)" → "JP Site Root"
- Various "v18 KEY FIXES", "v17 ANTI-SPAM (Still Active)", "AFTER
  UPGRADING TO v18", "What's Fixed in v18", "All Features
  (v13-v18)", "Auto Scheduler v17" — all stripped to clean text
- Section titles with "(v20 NEW)" / "(v25 NEW)" / "(v30 NEW)" —
  8 of these auto-stripped by regex pass
- Removed the "(v23)" from the WordPress deprecation note
- Removed "v29 walks this folder" from the Cloudflare site root
  help text

**What's intentionally left:**
- Internal Python comments (`# v15 ORM BEAST`, etc.) — invisible
  to users
- `CHANGELOG_v27.md`, `CHANGELOG_v28.md`, `CHANGELOG_v29.md`,
  `CHANGELOG_v30.md` files on disk — historical reference
- `APP_VERSION = "31.0"` and the header badge — this is where
  the current version lives

### 9. `bvtech_app.py` other changes

- `APP_VERSION` bumped `23.0` → `31.0` (it was oddly stuck at 23
  through the last several releases)
- New config default: `hubspot_bcc_address` (default empty)
- Save/load field lists extended
- HubSpot settings card gets a new "BCC Forwarding Address" input
- **14 new API routes** (counted the `/api/posts-index` carry-over
  from v30; 13 are brand new in v31):
  - `/api/hubspot/verify` — smoke test
  - `/api/hubspot/bcc-address` — read the configured BCC
  - `/api/hubspot/track-email` — POST to log one email (returns
    contact_id + email_id)
  - `/api/hubspot/enrich-csv` — trigger the daily enrichment task
    on demand
  - `/api/hubspot/stats` — total contact count
  - `/api/automation/tasks` — list all registered tasks with state
  - `/api/automation/task/<name>/enable` — POST with `{enabled: bool}`
  - `/api/automation/task/<name>/run-now` — POST to trigger a task
  - `/api/automation/install-windows/<name>` — POST to install
    to Windows Task Scheduler
  - `/api/automation/uninstall-windows/<name>` — POST to uninstall
  - `/api/automation/log` — query the event log (`?category=`,
    `?limit=`, `?target=`, `?since=`)
  - `/api/automation/stats` — event log summary
  - `/api/whats-new` — return the changelog data for the modal

- Startup hook in `if __name__ == "__main__":` initializes
  `LocalEventLog`, creates a `TaskRunner`, registers all 5 default
  tasks, starts the background thread, and exposes both globally
  via `builtins._BVTECH_EVENT_LOG` and `builtins._BVTECH_TASK_RUNNER`
  so route handlers can grab them

- 2 new tab content blocks (HS Track + Automation) inserted
  between the CRM tab and the Super Posting tab

- ~600 lines of new JS: `hsTrackVerify`, `hsTrackLog`,
  `hsTrackClearForm`, `saveBccAddress`, `copyBccAddress`,
  `loadBccAddress`, `hsTrackEnrichNow`, `loadHsStats`,
  `loadHsHistory`, `loadAutomationTasks`, `toggleTask`,
  `runTaskNow`, `installToWindows`, `loadAutomationLog`,
  `loadAutomationStats`, `showWhatsNew`, plus a `switchTab`
  monkey-patch so opening HS Track or Automation auto-loads data

---

## Setup notes

### HubSpot tracking setup (5 min)

1. HubSpot → Settings → Integrations → Private Apps → Create
2. Scopes you need:
   - `crm.objects.contacts.read`
   - `crm.objects.contacts.write`
   - `crm.objects.emails.write`
3. Copy the access token, paste into BVTech Settings → HubSpot
   CRM → Private App Token
4. Optional but recommended: HubSpot → Settings → Objects →
   Activities → Email tab → copy the "Forward to HubSpot" address,
   paste into BVTech Settings → HubSpot CRM → BCC Forwarding
   Address
5. Open the HS Track tab → click **Verify Connection**. If green,
   you're done.

### Installing a task to Windows Task Scheduler

1. Open the Automation tab
2. Find the task you want (e.g. `daily_hubspot_enrichment`)
3. Click **⊕ Win**
4. Confirm
5. Open `taskschd.msc` — your task is now under the default
   folder as `BVTech_daily_hubspot_enrichment`
6. It will fire on its schedule even when BVTech is closed

**Important:** the Windows Task Scheduler entry calls
`pythonw.exe bvtech_app.py --run-task <task>`. This means:
- The task needs the same Python environment BVTech was launched
  with
- If you move the BVTech folder, reinstall the tasks (uninstall +
  install)
- The path to `pythonw.exe` is captured at install time via
  `sys.executable`

### Files created at runtime

- `local_events.db` — SQLite event log
- `automation_state.json` — task state persistence
- `posts_index.json` — cross-linking index (from v30)
- `.csv_watcher_state.json` — CSV watcher checkpoint
- `backups/bvtech_config_YYYYMMDD.json` — daily config backups

All in the app directory (`APP_DIR`), which is `C:\BVTech2\` by
default.

---

## What's NOT in v31

Still on the deferred list:

- **Full SMTP relay with open-tracking pixel** — the pixel endpoint
  and HubSpot event write pieces are there, but I didn't hook them
  into `email_campaign.py`'s actual sending. That's v31.1 — too
  many DKIM/SPF/Gmail "Send As" landmines to do safely in one
  release.
- **Staggered per-channel scheduler** (Mon BV / Wed JP / Fri LI /
  Sat GBP) — still deferred
- **Channel-specific content rewrites** per target — still deferred
- **Retroactive backlinks into old posts** — still too risky

---

## Files changed in v31

- **NEW:** `hubspot_tracker.py` (~350 lines)
- **NEW:** `local_automation.py` (~550 lines)
- **NEW:** `CHANGELOG_v31.md` (this file)
- `bvtech_app.py`:
  - `APP_VERSION` bumped to 31.0
  - New config default `hubspot_bcc_address`
  - Startup hook initializes event log + task runner
  - `--run-task` CLI flag for Windows Task Scheduler integration
  - 13 new API routes for HubSpot tracking + automation + What's New
  - 2 new tab content blocks (HS Track, Automation)
  - ~600 lines of new JS
  - Polish pass stripping ~30 user-visible version graffiti strings
  - HubSpot Settings card gets the BCC address input

Everything else (`cloudflare_pages_deploy.py`,
`google_business_profile.py`, `posts_index.py`,
`tacticalrmm_integration.py`, `super_scraper.py`, etc.) is
byte-for-byte identical to v30.

---

## Test results

Before packaging, v31 was tested with:

- ✅ All 15 Python files parse clean (`ast.parse`)
- ✅ 158 total Flask routes (13 new v31 routes verified, param
  names match route variables)
- ✅ `LocalEventLog` records events, queries by category/target/
  since, round-trips JSON details, computes stats, rotates when
  oversized
- ✅ `TaskRunner` registers tasks, runs them on demand, captures
  exceptions, persists state to disk
- ✅ `compute_next_run` correct for daily (next 3am) and weekly
  (next Sunday 4am)
- ✅ `daily_config_backup` actually writes a backup file
- ✅ `daily_posts_index_prune` drops old entries, keeps recent
- ✅ `hourly_csv_watcher` detects new rows across runs
- ✅ `WindowsTaskScheduler` gracefully refuses on non-Windows
- ✅ `hubspot_tracker.HubSpotTracker` initializes and all method
  signatures check out
- ✅ All v30 cross-linking + GBP OAuth + CF Direct Upload code
  still present and functional

v31 is ready to ship.
