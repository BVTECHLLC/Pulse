# BVTech MSP Command Center — v32.0 Changelog

**Release: April 2026**
**Codename: POLISH — CHANNEL REWRITES + STAGGERED SCHEDULER**

## TL;DR

v32 is the "actually finish the deferred list" release. Closes out
nearly everything that's been on the backlog since v30:

1. **Channel-specific content rewrites** — the master article for
   "All 4 Channels" is now rewritten by Claude into 4 distinct
   voices (BVTech corporate, JP first-person, LinkedIn hook-driven,
   GBP 300-char) instead of being posted verbatim to all four. This
   was the single biggest SEO win on the deferred list.

2. **Staggered per-channel scheduler** — 4 new weekly tasks (Mon/
   Wed/Fri/Sat) that each publish ONE channel from a local post
   queue, so all four channels never see the same content land at
   the same moment.

3. **Retroactive backlinks CLI** — standalone script that walks
   your existing local blog folder and injects "Related Posts"
   blocks into old posts. Idempotent, dry-run by default, makes
   backups.

4. **Draft & Track email flow** — safer alternative to building a
   full SMTP relay. Builds a `mailto:` URL with HubSpot BCC
   pre-injected, opens your default mail client, and pre-logs the
   contact in HubSpot via the v3 Engagements API.

5. **Polish pass round 2** — strips ~30 more pieces of version
   graffiti, removes orphan tabs, hides deprecated tabs, removes
   runtime junk files from the zip, rewrites README and INSTALL.bat
   to actually reflect what's in the box.

Nothing from v28-v31 was removed. Cross-linking, CF Direct Upload,
GBP OAuth, HubSpot tracking, Local Automation, all still work.

---

## What's new in detail

### 1. `channel_rewriter.py` — new module (~380 lines)

Handles per-channel content rewrites via second-pass Claude calls.

**`CHANNEL_CONFIGS`** dict defines the 4 channel personas:
- `bvtech` — passthrough (the master IS the BVTech voice)
- `jp` — first-person, conversational, "I", "my team", "we've seen"
- `linkedin` — ≤1200 chars, hook-driven, 3-5 short paragraphs,
  ends with engagement question
- `gbp` — ≤300 chars, sentence + value + soft pitch (no links in
  body — GBP has its own CTA button)

**`rewrite_for_channel()`** — main entry point. Builds a
channel-specific prompt, makes one Anthropic API call, post-
processes the output (strips code fences, strips quotes, hard-
enforces length limits), returns `(text, error)`.

**`rewrite_all_channels()`** — convenience wrapper that calls
`rewrite_for_channel` for all 4 channels in sequence with a
small inter-call delay. Returns a dict keyed by channel.

**Safe fallbacks** — if the API call fails (no key, rate limit,
network error), each channel returns a sensible fallback rather
than crashing the whole post:
- `bvtech` and `jp` → return the master article unchanged
- `linkedin` → first sentence of meta description + canonical link
- `gbp` → meta description truncated to 280 chars

This means Super Posting keeps working even if Claude is
unreachable or rate-limited.

**Output post-processing** — strips ```code fences```, strips
surrounding quotes, hard-enforces `max_output_chars` for short
channels by trimming at the last sentence boundary before the
limit (or hard-truncating with `...` if no sentence break).

**6 unit tests passing** including `rewrite_all_channels` end-to-
end with no API key (all fallbacks fire correctly).

### 2. `post_queue.py` — new module (~200 lines)

Thread-safe JSON-backed queue for the staggered scheduler.

**`PostQueue`** class with:
- `add(title, topic, tone, length, custom_instructions)` — append
  a new pending item, returns the auto-generated id
- `remove(item_id)` — drop an item from the queue
- `next_pending_for_channel(channel)` — find the oldest pending
  item that hasn't been published to `channel` yet
- `mark_channel_done(item_id, channel, url)` — record success;
  if all 4 channels are now done, flip the item's overall status
  to `done`
- `mark_channel_failed(item_id, channel, error)` — record failure;
  if all 4 channels failed with no successes, flip overall status
  to `failed`
- `stats()` — `{total, pending, in_progress, done, failed}`

**State machine:** `pending` → `in_progress` (after first success)
→ `done` (when all 4 channels done) | `failed` (when all 4 errored
with no successes).

**Storage:** `post_queue.json` in the app directory. Thread-safe
via `threading.Lock()`. Last-write-wins on concurrent updates.

**8 unit tests passing** including persistence across reloads,
multi-channel state tracking, and the "next pending" picker
correctly walking through items when bvtech is done but jp isn't.

### 3. `retroactive_backlinks.py` — new standalone CLI (~310 lines)

Unlike the runtime enrichment in `posts_index.py` (which only adds
backlinks to NEW posts going forward), this script retroactively
mutates EXISTING blog files. That's why it's a standalone CLI tool
instead of being baked into the main app:

- Runs ONCE, when you decide you want old posts to link to newer
  content
- `--dry-run` BY DEFAULT — you have to explicitly pass `--commit`
  to actually write
- **Idempotent** — posts that already have a `data-bvtech-related`
  marker are skipped, so re-running does nothing
- Commits per-file, so a crash mid-run leaves the already-modified
  files valid
- Writes backups to `<site-root>/.bvtech_backups/<slug>.html.bak`
  before each modification (skip with `--no-backup`)
- **Never touches `blog/index.html`** — same protection as the
  v29 deployer

```cmd
:: Dry run
python retroactive_backlinks.py --site bvtech \
    --site-root "C:\BVTech2\Website\bvtech.org"

:: Commit
python retroactive_backlinks.py --site bvtech \
    --site-root "C:\BVTech2\Website\bvtech.org" --commit

:: Test on first 3 files only
python retroactive_backlinks.py --site bvtech \
    --site-root "C:\BVTech2\Website\bvtech.org" --limit 3 --commit
```

Marker: `data-bvtech-retro="v32"` (alongside the existing v30
`data-bvtech-related="v30"`), so you can identify retro-injected
blocks vs forward-injected ones if you ever need to.

**Full end-to-end test against the real bvtech.org folder passed:**
- Dry run reports correctly, writes nothing
- Commit run writes 5 files with proper retro markers
- `blog/index.html` is byte-identical (never touched)
- Backups created in `.bvtech_backups/`
- **Re-run is idempotent** — already-enriched files are skipped

### 4. Staggered scheduler (4 new tasks)

Added to `local_automation.py`'s `build_default_tasks()`. All 4
are **disabled by default** so they don't start firing the moment
you launch the app — you opt in from the Automation tab.

| Task | Day | Time | Channel |
|---|---|---|---|
| `staggered_monday_bvtech` | Monday | 10am | BVTech.org |
| `staggered_wednesday_jp` | Wednesday | 10am | JordanPolasek.com |
| `staggered_friday_linkedin` | Friday | 10am | LinkedIn |
| `staggered_saturday_gbp` | Saturday | 10am | Google Business Profile |

Each task calls a `_staggered_publish(channel)` helper that:
1. Loads `PostQueue`
2. Calls `next_pending_for_channel(channel)` to get the next item
3. Calls `_BVTECH_GENERATE_POST(...)` (exposed via `builtins`) with
   the right per-channel target
4. On success → `mark_channel_done` with the published URL
5. On failure → `mark_channel_failed` with the error
6. Returns a status string that gets logged to the event log

**Critical hookup:** `_generate_one_post` is exposed via
`builtins._BVTECH_GENERATE_POST` at startup AND in the `--run-task`
CLI path so the staggered tasks work both when the Flask app is
running AND when fired via Windows Task Scheduler.

### 5. Post Queue UI panel (Super Posting tab)

New card at the bottom of the Super Posting tab with:
- Title input (required)
- Topic / focus keyword input
- Tone selector (personal_authority / thought_leadership / how_to / case_study)
- Length selector (short / medium / long / pillar)
- Custom instructions textarea
- "Add to Queue" button
- Refresh button
- "Go to Automation Tab" link (for enabling the staggered tasks)
- Live stats bar (total / pending / in_progress / done / failed)
- Item list with per-channel status dots (✓ done / ✗ failed / ○ pending)
  + Remove button per item
- Inline help explaining the staggered workflow

Auto-loads when you switch to the Super Posting tab.

### 6. Draft & Track button (HS Track tab)

New green button on the HS Track form, next to "Log to HubSpot".

When clicked:
1. Builds a `mailto:` URL with the recipient, subject, body, and
   the configured HubSpot BCC address all pre-injected as URL
   params
2. Opens the user's default mail client (Gmail, Outlook, Mail.app,
   Thunderbird, whatever)
3. **Pre-logs** the contact + subject + body to HubSpot via
   `/api/hubspot/track-email` so there's a breadcrumb in the
   contact's timeline even if you abandon the draft

The reasoning: building a full SMTP relay with DKIM/SPF/Gmail
Send-As alias handling is the kind of feature that ships broken
and you don't notice for weeks because emails silently land in
spam. Draft & Track gives you 90% of the value (HubSpot logging
+ auto-BCC) using the user's existing trusted mail client.

### 7. New API routes (3 v32, on top of v31's 13)

- `GET /api/queue/list` — full post queue + stats
- `POST /api/queue/add` — add an item, body: `{title, topic?, tone?, length?, custom_instructions?}`
- `POST /api/queue/remove/<item_id>` — drop an item

### 8. Tab bar reorganization

The 21 tabs were in roughly chronological order of when they were
added (which is why HS Track and Automation were sandwiched
between CRM and Super Posting). v32 reorganizes them into logical
workflow groups:

**Core workflow:** Dashboard → Scraper → Super Posting → HS Track → Automation
**Outreach:** Email → SMS → Dialer → Phone → Coaching
**CRM/Ops:** Inbox → CRM → Pipeline → Revenue
**Infrastructure:** TRMM → Cloudflare → CyberAudit → News
**Advanced:** Claude AI → WARMODE → Settings

### 9. Polish pass

- Deleted the orphan **Guardz tab content div** (47 lines) — there
  was no button in the tab bar to reach it; it was dead code from
  a removed feature
- **Hid the WordPress tab** from the bar (kept the tab-content div
  in place because `_get_jp_publisher` still has a WordPress
  fallback path that some users may rely on)
- **Removed the WordPress badge** from the header strip
- **Stripped 30+ version graffiti strings** that survived v31's
  polish pass: "v17 ANTI-SPAM (Still Active)", "v18 KEY FIXES",
  "v20.0 BVTECH", "v23 deprecation note", "v25 BVTECH",
  "v29 walks this folder", "Auto Scheduler v17", "ORM POST
  CREATED (v17)", and similar
- **Removed all "NEW" badges** from News, Inbox, Revenue, HS Track,
  Automation tabs (they've been there across 3+ releases — not new
  anymore)
- **Removed 7 runtime junk files** that had been shipping in zips
  since v27: `prospects.csv`, `campaign_state.json`, `sent_log.csv`,
  `test_prospects.csv`, `raw_places_data.json`, `scrape_cache.json`,
  `sms_prospects.csv`. These were YOUR working data, not
  distributables, and they had been bundled by accident every
  release for ~5 versions
- `APP_VERSION` bumped 31.0 → 32.0
- Header badge bumped to v32.0 FINAL
- What's New modal data updated with v32 highlights + v31/v30/v29/v28 history
- localStorage version check updated so the modal auto-shows on
  first launch after upgrading

### 10. Documentation overhaul

- **`READ ME FIRST.txt`** — completely rewritten. The old one
  still said "v27.0 SUPER SCRAPER" from 5 releases ago. New version
  documents all 21 tabs, the 9 built-in tasks, the 5-min HubSpot
  setup, the GBP gated-API caveat, and v32's new features
- **`README.md`** — completely rewritten. The old one still said
  "v24.0 DUAL-SITE CLOUDFLARE PAGES + BVTECH NEWS". New version
  has architecture overview, file layout, all 21 tabs grouped,
  scheduled task table, API setup quick reference
- **`INSTALL.bat`** — completely rewritten. The old one was stuck
  on v19 and missing `--hidden-import` directives for everything
  added since (cloudflare_pages_deploy, google_business_profile,
  posts_index, hubspot_tracker, local_automation, channel_rewriter,
  post_queue, super_scraper). PyInstaller would have failed to
  bundle the new modules. New version explicitly imports all 18
  helper modules and adds them as data files for subprocess
  fallbacks. Also auto-migrates `posts_index.json` and
  `local_events.db` from previous versions
- **`CHANGELOG_v32.md`** — this file

---

## Channel rewriter wiring inside `_generate_one_post`

When `target == "all_four"`, the post generator now does this:

```python
# v32: Rewrite once, before any channel publishes
if target == "all_four" and rewrite_all_channels is not None:
    channel_variants = rewrite_all_channels(
        master_html=blog["content"],
        master_title=title,
        api_key=load_config().get("anthropic_key", ""),
        master_focus_keyword=blog.get("focus_keyword", ""),
        master_meta_description=blog.get("meta_description", ""),
    )

def _content_for(site_key):
    """Return the rewritten variant for a site, or the master as fallback."""
    if site_key in channel_variants:
        v = channel_variants[site_key]
        if v.get("text"):
            return v["text"]
    return blog["content"]

# Each publish branch then uses _content_for():
jp_html = _content_for("jp")        # JP first-person variant
bv_html = _content_for("bvtech")    # BVTech master (passthrough)
li_text = channel_variants.get("linkedin", {}).get("text") or _adapt_for_linkedin(...)
gbp_text = channel_variants.get("gbp", {}).get("text") or fallback_gbp_truncation
```

Each variant then goes through the v30 cross-linker (`_enrich`)
before being deployed, so each site gets its own voice AND its own
related-post block.

The legacy `_adapt_for_linkedin()` function is kept as a fallback
for when channel rewriting isn't used (e.g. target is `linkedin`
only, not `all_four`) so nothing regresses.

---

## Files changed in v32

- **NEW:** `channel_rewriter.py` (~380 lines)
- **NEW:** `post_queue.py` (~200 lines)
- **NEW:** `retroactive_backlinks.py` (~310 lines, standalone CLI)
- **NEW:** `CHANGELOG_v32.md` (this file)
- **REWRITTEN:** `READ ME FIRST.txt`
- **REWRITTEN:** `README.md`
- **REWRITTEN:** `INSTALL.bat`
- `bvtech_app.py`:
  - `APP_VERSION` bumped 31.0 → 32.0
  - `_generate_one_post()` rewired to call `rewrite_all_channels`
    before publishing for `all_four` target
  - All 4 publish branches use `_content_for(site)` to pick the
    right variant
  - `builtins._BVTECH_GENERATE_POST` exposed for staggered tasks
  - 3 new API routes for post queue (`/api/queue/list`, `/add`,
    `/remove/<item_id>`)
  - New Post Queue panel inserted at end of Super Posting tab
  - Draft & Track button added to HS Track form
  - `~170 lines of new JS` for queue + draft & track + queue auto-load
  - Tab bar reorganized into workflow groupings
  - Orphan Guardz tab content deleted (47 lines)
  - WordPress tab hidden from the bar
  - `_V31_WHATS_NEW` data updated to v32 highlights
  - localStorage version check bumped 31.0 → 32.0
  - 30+ version graffiti strings stripped
- `local_automation.py`:
  - `build_default_tasks()` extended with 4 new staggered publish
    tasks
  - New `_staggered_publish(channel)` helper that bridges to
    `_generate_one_post` via `builtins._BVTECH_GENERATE_POST`

Everything else (the 14 other helper modules) is byte-identical
to v31.

---

## Test results

Before packaging:

- ✅ All 18 Python files parse clean (`ast.parse`)
- ✅ 161 Flask routes registered, **0 broken** (param names match
  route variables)
- ✅ All 16 v31+v32 routes verified present
- ✅ `channel_rewriter` 6 tests pass: bvtech passthrough, jp
  fallback, linkedin fallback (≤1200 chars), gbp fallback (≤300
  chars), code fence stripping, quote stripping, length cap,
  `rewrite_all_channels` end-to-end
- ✅ `post_queue` 8 tests pass: add, find_next_for_channel walking
  through items, mark_done state transitions, mark_failed,
  persistence across reloads, remove
- ✅ `retroactive_backlinks` end-to-end against real bvtech.org
  folder: dry-run writes nothing, commit writes 5 files with retro
  markers, `blog/index.html` byte-identical, backups created,
  re-run is idempotent
- ✅ `local_automation` 9 default tasks register with correct
  next-run times (5 enabled + 4 staggered disabled)
- ✅ `compute_next_run` correct for new weekday math: Monday=0,
  Wednesday=2, Friday=4, Saturday=5
- ✅ All v28/v29/v30/v31 functionality preserved — CF Direct Upload,
  GBP OAuth, posts_index cross-linking, HubSpot tracking, Local
  Automation engine, Windows Task Scheduler integration

v32 is ready to ship.
