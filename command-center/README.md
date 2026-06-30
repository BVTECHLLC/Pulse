# BVTech MSP Command Center v32.0

**Codename: POLISH**
**Built by Jordan Polasek for BVTech LLC, El Campo TX**

A unified Windows desktop dashboard for running an MSP business out of one window. Prospect scraping, multi-channel content publishing, HubSpot CRM sync + email tracking, security audits, M365 inbox, DialPad calling, and a local automation engine that runs scheduled tasks even when the UI is closed.

Everything runs locally. No SaaS, no monthly subscriptions beyond the APIs you already pay for.

## Quick start

```cmd
INSTALL.bat        :: first time only
Start-BVTech.bat   :: every time after that
```

Browser opens at `http://localhost:5678`. The "What's New" popup auto-shows on first launch.

## What's in v32

### The big three

1. **Channel-specific content rewrites** — when you publish to "All 4 Channels" (BVTech.org + JordanPolasek.com + LinkedIn + Google Business Profile), the master article gets rewritten by Claude into 4 distinct voices instead of being posted verbatim everywhere. BVTech gets corporate authority, JP gets first-person personal, LinkedIn gets a hook-driven 1200-char post, GBP gets a 300-char local-search blurb. Stops Google's de-dup filter from penalizing duplicate content.

2. **Staggered scheduler** — four new weekly tasks (disabled by default) publish ONE channel per day instead of all four at once. Mon BVTech → Wed JP → Fri LinkedIn → Sat GBP. Pulls from a local post queue. Enable them on the Automation tab once you've populated the queue from Super Posting.

3. **Retroactive backlinks CLI** — `retroactive_backlinks.py` walks your existing local blog folder and injects "Related Posts" blocks into old posts using the `posts_index.json` data. Idempotent (re-running does nothing), `--dry-run` by default, makes backups before writing.

### Everything else

- **Post queue manager** on the Super Posting tab — pre-generate ideas, drop them in the queue, let the scheduler drip them out
- **Draft & Track** button on HS Track — opens default mail client with your HubSpot BCC pre-injected, and pre-logs the contact to HubSpot
- **Tab bar reorganized** by workflow groupings (core / outreach / ops / infra / advanced)
- **30+ pieces of version graffiti stripped** from tab content
- **Orphan Guardz tab deleted** (was unreachable from the bar)
- **WordPress tab hidden** from the bar (legacy fallback still works in the publisher code)
- **7 runtime junk files removed** from the zip (`prospects.csv`, `scrape_cache.json`, `sent_log.csv`, etc. — these had been shipping in zips since v27 because nobody cleaned them up)
- **Installer + README rewritten** to actually reflect what's in the box

## Architecture (one paragraph)

`bvtech_app.py` is the main Flask app, ~12,200 lines, exposes ~161 routes, renders the entire UI as a single SPA-style HTML page with vanilla JS. The 18 helper modules (`channel_rewriter.py`, `post_queue.py`, `retroactive_backlinks.py`, `hubspot_tracker.py`, `local_automation.py`, `posts_index.py`, `google_business_profile.py`, `cloudflare_pages_deploy.py`, `super_scraper.py`, `prospect_scraper.py`, `email_campaign.py`, `sms_campaign.py`, `power_dialer.py`, `dialpad_integration.py`, `tacticalrmm_integration.py`, `autopilot.py`, `autoclaude.py`, `generate_prospects.py`) are imported lazily by the routes that need them. State lives in `bvtech_config.json` (settings), `posts_index.json` (cross-link graph), `post_queue.json` (staggered queue), `local_events.db` (SQLite event log), and `automation_state.json` (task runner state).

## The 21 tabs

### Core workflow
- **Dashboard** — stats from every connected tool in one view
- **Scraper** — find prospects via Google Places + Hunter.io
- **Super Posting** — generate and publish blog posts to 4 channels
- **HS Track** — track manually-sent emails in HubSpot (BCC + manual log + Draft & Track)
- **Automation** — local SQLite event log + scheduled tasks

### Outreach
- **Email** — M365 email campaigns
- **SMS** — DialPad SMS campaigns
- **Dialer** — power dialer for prospect lists
- **Phone** — DialPad AI phone integration
- **Coaching** — AI-driven call coaching

### CRM / Operations
- **Inbox** — M365 unified inbox
- **CRM** — HubSpot prospect sync
- **Pipeline** — HubSpot deal tracker
- **Revenue** — MRR / pipeline rollup

### Infrastructure
- **TRMM** — Tactical RMM dashboard
- **Cloudflare** — Pages deploy + DNS
- **CyberAudit** — Security audit + pen test reports
- **News** — Vulnerability intel feed

### Advanced
- **Claude AI** — brain panel
- **WARMODE** — aggressive auto-builder
- **Settings** — API keys + integrations

## Built-in scheduled tasks (9 total)

Automatically registered at startup. Visible in the Automation tab. Each one can be enabled/disabled, run on demand, or installed to Windows Task Scheduler.

| Task | Schedule | Default |
|---|---|---|
| `daily_config_backup` | Daily 3am | ON |
| `weekly_log_rotation` | Sunday 4am | ON |
| `daily_posts_index_prune` | Daily 2am | ON |
| `hourly_csv_watcher` | Hourly | ON |
| `daily_hubspot_enrichment` | Daily 6am | ON |
| `staggered_monday_bvtech` | Monday 10am | OFF |
| `staggered_wednesday_jp` | Wednesday 10am | OFF |
| `staggered_friday_linkedin` | Friday 10am | OFF |
| `staggered_saturday_gbp` | Saturday 10am | OFF |

The 4 staggered tasks are off by default so they don't start firing the moment you launch the app. Enable them after you've added items to the post queue from the Super Posting tab.

## API setup quick reference

### HubSpot (5 min)
1. HubSpot → Settings → Integrations → Private Apps → Create
2. Scopes: `crm.objects.contacts.read/write`, `crm.objects.emails.write`
3. Paste token into Settings → HubSpot CRM → Private App Token
4. (Optional) Paste BCC forwarding address into HS Track → BCC field

### Google Business Profile (gated, 1-2 day wait)
1. console.cloud.google.com → enable 3 GBP APIs
2. Apply for API access at support.google.com/business/contact/api_default
3. Wait for approval email
4. Create OAuth 2.0 web client with redirect URI `http://localhost:5678/api/gbp/oauth/callback`
5. Paste Client ID + Secret into Settings → Google Business Profile

### Cloudflare Pages
1. Create CF API token with Pages:Edit permission
2. Settings → Cloudflare → API token + account ID + project name
3. Set `bvtech_site_root` to your local bvtech.org folder
4. Click **Test Deploy** on the Super Posting tab to dry-run

## File layout

```
BVTech_MSP_CommandCenter_v32_FINAL/
├── bvtech_app.py                    Main app
├── channel_rewriter.py              [v32 NEW]
├── post_queue.py                    [v32 NEW]
├── retroactive_backlinks.py         [v32 NEW] standalone CLI
├── hubspot_tracker.py               [v31]
├── local_automation.py              [v31] (extended in v32)
├── posts_index.py                   [v30]
├── google_business_profile.py       [v30]
├── cloudflare_pages_deploy.py       [v29]
├── super_scraper.py                 [v27]
├── prospect_scraper.py              [v25]
├── tacticalrmm_integration.py
├── email_campaign.py
├── sms_campaign.py
├── power_dialer.py
├── dialpad_integration.py
├── autopilot.py
├── autoclaude.py
├── generate_prospects.py
├── bvtech.ico
├── favicon.png
├── INSTALL.bat                      [v32 rewritten]
├── Start-BVTech.bat
├── build_exe.bat
├── READ ME FIRST.txt                [v32 rewritten]
├── README.md                        [v32 rewritten] (this file)
├── CHANGELOG_v32.md
├── CHANGELOG_v31.md
├── CHANGELOG_v30.md
├── CHANGELOG_v29.md
├── CHANGELOG_v28.md
├── CHANGELOG_v27.md
├── CHANGELOG_v25.md
└── CF_DIRECT_SETUP_GUIDE.md
```

## Upgrading from v31 or earlier

```cmd
:: 1. Unzip v32 to a NEW folder
:: 2. Run INSTALL.bat — it auto-migrates these files from your previous version:
::      bvtech_config.json    (your API keys + settings)
::      posts_index.json      (cross-linking history)
::      local_events.db       (v31+ event log)
:: 3. Done. Old folder is untouched, keep it as a backup.
```

If migration didn't happen automatically, manually copy those three files from your old version folder.

## What's NOT in v32 (still deferred)

**Full SMTP relay with open-tracking pixel.** v32 ships "Draft & Track" instead, which gives you 90% of the value (auto-BCC, pre-log to HubSpot, opens default mail client) without the DKIM/SPF/Gmail-Send-As rabbit hole. If you want the full SMTP relay later, that's a v32.1 follow-up.

## Troubleshooting

- **App won't start** → check `crash.log` in the app folder
- **Port 5678 in use** → installer kills previous instances, but if it persists, run `netstat -aon | findstr :5678` to find the PID and kill it
- **Module import errors** → run `python -m pip install flask requests` manually
- **HubSpot 401** → token expired or wrong scopes — regenerate the Private App and re-paste
- **GBP 403 on post** → API access not granted yet, fill out the Google access request form
- **Cloudflare Direct Upload fails** → run **Test Deploy** first to dry-run; usually a missing `bvtech_site_root` config

## License

Internal tool, BVTech LLC. Use as you like inside the company.
