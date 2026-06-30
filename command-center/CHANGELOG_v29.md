# BVTech MSP Command Center — v29.0 Changelog

**Release: April 2026**
**Codename: SITE-ROOT WALK**

## TL;DR

v29 is the real fix for ORM auto-posting. It replaces the broken
Cloudflare Pages Direct Upload path with a full site-root-walk
deployer that correctly implements the 5-step protocol wrangler
uses under the hood. v28 was the "don't let it burn your house
down" release; v29 is the "actually works" release.

**Before you enable ORM auto-posting: use the new Test Deploy button
in the ORM tab. It walks your local site folder, computes hashes, and
asks Cloudflare what it would upload — without actually deploying.
Run it before you ever click Publish All.**

---

## What's new

### 1. `cloudflare_pages_deploy.py` — new module (~450 lines)

A standalone Cloudflare Pages Direct Upload client that implements the
full protocol correctly. It's usable on its own from the command line
or imported by the ORM publisher.

**The 5-step protocol (what wrangler actually does):**

1. `GET /accounts/{acct}/pages/projects/{proj}/upload-token` — get a
   short-lived JWT valid for 1 hour.
2. `POST /pages/assets/check-missing` with the list of file hashes —
   Cloudflare returns the subset it does NOT already have cached. On
   the first deploy this will be everything; on subsequent deploys it
   will just be the new blog post plus anything else that changed.
3. `POST /pages/assets/upload?base64=true` in batches of ≤15 MB with
   base64-encoded file contents. Retries on 429/5xx with exponential
   backoff.
4. `POST /pages/assets/upsert-hashes` to confirm the full hash set.
5. `POST /accounts/{acct}/pages/projects/{proj}/deployments` as a
   multipart form with a `manifest` field mapping every URL path to
   its content hash. Every file on the site MUST be in this manifest
   — anything not in the manifest stops existing, which is the bug
   v25-v27 had.

**Hash format:** SHA-256 of file bytes, truncated to 32 hex chars.
This matches what wrangler does and what check-missing expects.

**Safety rails baked in:**

- Refuses to deploy if `site_root` doesn't exist or isn't a directory.
- Refuses to deploy if `site_root` has no top-level `index.html`
  (sanity check — prevents pointing at an empty folder or the wrong
  drive and nuking the site).
- Refuses to deploy any file over 25 MiB (Cloudflare's per-asset limit).
- Refuses to deploy more than 20,000 files (free plan limit).
- Skips `.git`, `node_modules`, `__pycache__`, `.DS_Store`, `Thumbs.db`,
  `.wrangler/*`, and similar junk automatically.
- Defensively sanitizes blog post slugs — alphanumeric + dashes only,
  no path traversal.

**Dry run mode:** `deploy_folder(..., dry_run=True)` does steps 0, 1,
and 2 (verify project, walk folder, ask check-missing) but stops
before uploading or deploying. Returns the same shape with a report
of what it would have done. This is what the Test Deploy button
calls.

**First-deploy vs. subsequent-deploy behavior:** The first deploy
uploads every file on the site (~19 MiB / 186 files for bvtech.org).
Every deploy after that only uploads the new blog post and any other
changed files — Cloudflare's check-missing endpoint handles the
dedup automatically. This is why it's cheap to deploy once per post.

**Flat-file blog layout:** The deployer writes new posts as
`/blog/{slug}.html` to match your existing bvtech.org convention, not
the subfolder style (`/blog/{slug}/index.html`). This preserves all
existing links in your 35 KB handcrafted `blog/index.html`.

**blog/index.html protection:** By default, `regenerate_index=False`
because your existing `blog/index.html` is a handcrafted listing
page. The auto-regenerator will only run if you explicitly set
`regenerate_index=True` AND the existing file has a
`data-blog-index="auto"` marker in it. No marker = no touch. Your
site's design is safe.

### 2. `tacticalrmm_integration.py` — `_deploy_cf_direct()` rewritten

The v28 safety-hold stub is replaced with a real implementation that
reads `bvtech_site_root` or `jp_site_root` from config and calls into
the new `cloudflare_pages_deploy.write_blog_post_and_deploy()`. Picks
the right site root based on whether the client is serving BVTech or
JP, honors `cf_deploy_branch` from config (defaults to `main`), and
bubbles the full deploy log up to the caller.

A new `test_cf_deploy(dry_run=True)` method is added to the same
class, which is what the new API routes call.

The old nuke-your-site code is kept only as
`_deploy_cf_direct_UNSAFE_v27_ORIGINAL` for historical reference.
Never called.

### 3. `bvtech_app.py` — publishers, routes, config, UI

**Publishers fixed (again):** `get_bvtech_publisher()` and
`_get_jp_publisher()` no longer return `disabled_v28_hold`. They now
return:

- `"cloudflare"` — CF Direct Upload ready, site_root configured
- `"needs_site_root"` — CF creds present but `site_root` not set
  (clear actionable error, not a silent failure)
- `"github"` — GitHub API path
- `"wordpress"` — legacy WP relay fallback

`_generate_one_post()` handles all four modes and returns a
user-friendly error message if `site_root` is missing.

**New API routes:**

- `POST /api/orm/cf-test-deploy/<site>` — dry-run a deployment for
  'bvtech' or 'jp'. Walks the folder, verifies the project, calls
  check-missing, stops. Returns a JSON report. This is what the
  Test Deploy buttons call.
- `POST /api/orm/cf-deploy-live/<site>` — REAL deployment of the
  current site folder as-is. For pushing local edits to CF without
  generating a new blog post. Backed by the same safety rails.
- `GET /api/orm/site-root-check/<site>` — sanity check for the
  status dots in the UI. Returns `{ok: true, file_count, size_mb}`
  or `{ok: false, reason, message}`.

**New config fields (with defaults):**

- `bvtech_site_root` = `C:\BVTech2\Website\bvtech.org`
- `jp_site_root` = `C:\BVTech2\Website\jordanpolasek.com`
- `cf_deploy_branch` = `main`

These are persisted through `saveSettings()` along with everything
else. Existing configs will get the defaults on first load.

**Settings tab — new fields:**

The Cloudflare settings section now has a **BVTech Site Root** input
field highlighted with a green star. Below the JP section there's a
matching **JP Site Root** field. Both default to the `C:\BVTech2\...`
paths but can be pointed anywhere.

**ORM tab — new banner + Test Deploy controls:**

The v28 red safety-hold banner is replaced with a green v29-ready
banner that has:

- 🧪 Test Deploy — BVTech.org (blue button)
- 🧪 Test Deploy — JordanPolasek.com (pink button)
- 📁 Check Site Folders (verifies both site_roots exist)
- Two status dots showing file count + size for each configured site
- An output log that streams the dry-run report inline

The buttons call the new API routes and render a human-readable
report:

```
✅ Test Deploy OK — bvtech
───────────────────────────────────────
Project:         bvtech-website
Site root:       C:\BVTech2\Website\bvtech.org
Files walked:    186
Would upload:    186  (new/changed)
Already cached:  0
Total size:      18.51 MiB
Elapsed:         0.9s

Sample of files that would upload:
  • /CHANGELOG_v33.md
  • /CHANGELOG_v34.md
  ...

───────────────────────────────────────
DRY RUN — nothing was actually deployed.

⚠  First deploys upload everything. That's expected.
    Second run should show very few files to upload.
```

### 4. Content quality upgrades to `_build_orm_prompt()`

Doubled the word count defaults (short=800, medium=1500, long=2200,
pillar=3000+) and added a universal v29 SEO quality block that applies
on top of all five existing templates:

- **Structure:** H1 with focus keyword, H2 per section (3-5 of them),
  H3 sub-points, 2-4 sentence paragraphs max, at least one `<ul>` or
  `<ol>` list, bolded key phrases for scanners.
- **Readability:** Flesch 60+, varied sentence lengths, concrete
  examples with real numbers/tool names/dollar amounts, no corporate
  jargon ("solutions," "leverage," "synergy," "robust").
- **FAQ section:** Every post gets an `<h2>Frequently Asked Questions</h2>`
  near the end with 3-4 real questions and schema.org FAQPage
  microdata — this targets featured snippets and rich results.
- **Author byline:** Every post ends with a styled
  `<div class="author-byline">` containing Jordan Polasek's
  credentials, BVTech service area, phone number, and a link back to
  bvtech.org. This is the "use my name for SEO" part.
- **Internal links:** 1-2 contextual links to bvtech.org pages
  (services, locations, contact) — no more, no less.
- **Meta fields:** 140-155 char meta description that reads like a
  human wrote it, plus JSON-LD BlogPosting schema.

The five rotating templates (thought leadership, how-to, case study,
analysis, Q&A) are untouched — they still randomize to avoid
Google's template-fingerprint detection.

---

## What's NOT in v29 (coming in v29.1)

I split the original ask in two to ship the critical CF deployer
clean and tested. These pieces are the next turn's work:

1. **Google Business Profile auto-posting.** Needs its own OAuth2
   dance with `business.manage` scope and the Business Profile API's
   `localPosts` endpoint. Will be a separate "Connect Google
   Business" button in Settings plus a target option in the ORM tab.

2. **LinkedIn sharing after BVTech/JP deploys.** The LinkedIn client
   already exists in `tacticalrmm_integration.py`. The wiring into
   the new `target="all_three"` flow needs one more pass to grab the
   BVTech URL after the deploy completes and share it as an article.

3. **Scheduler rewrite for staggered per-channel posting.** Your ask
   was "one post per week per channel, on different days" —
   something like BVTech Mon 10am, JP Wed 2pm, LinkedIn Fri 9am, GBP
   Sat 11am. The existing scheduler does total-posts-per-week; v29.1
   will add per-channel day/time locks.

---

## How to test v29 safely

First-time setup checklist, in order:

1. **Drop the v29 zip in a new folder and run `Start-BVTech.bat`.**
   Your existing `bvtech_config.json` carries over. You'll see the
   green v29 banner at the top of the ORM tab.

2. **Extract `CompletedBVTechWebsite_V38__2_.zip` to
   `C:\BVTech2\Website\bvtech.org`** (or wherever — just make sure
   the path has `index.html` directly inside it).

3. **Go to Settings → Cloudflare → BVTech.org.** Paste your
   Cloudflare API token in the CF API Token field. The account ID
   and project name are pre-filled. Confirm the **BVTech Site Root**
   field matches wherever you extracted the site. Click Save.

4. **Go to the ORM tab.** The two status dots in the green banner
   should now show `BVTech: ● 186 files, 18.51 MiB` and `JP: ● 20
   files, 0.25 MiB` (or whatever your folders contain).

5. **Click 🧪 Test Deploy — BVTech.org.** First run output should be
   "186 files walked, 186 would upload, 0 cached, DRY RUN — nothing
   was actually deployed." If you see any errors, fix them before
   doing a real deploy. The most likely errors are:

   - `401 Unauthorized` — API token doesn't have Pages:Edit permission
   - `404 Not Found` — project name doesn't match what's in Cloudflare
   - `No index.html found at top of <path>` — site_root is pointing
     at the wrong folder
   - `File too large for Cloudflare Pages` — you have a file over 25 MiB

6. **Once Test Deploy is clean, you can do a real first deploy** via
   `POST /api/orm/cf-deploy-live/bvtech` (or the "Deploy Site As-Is"
   button when I add it to the UI). This uploads the whole site
   fresh. Takes 30-90 seconds on a decent connection.

7. **Verify bvtech.org still looks right** in a browser. Hard-refresh
   to make sure you're not seeing cache.

8. **Then and only then** generate an ORM post and click Publish
   Next. It'll write `/blog/{slug}.html` into your local folder,
   call the deployer, and CF will only upload the new file plus
   whatever changed (usually just the one file). Verify it works
   before touching the scheduler.

---

## Files changed in v29

- **NEW:** `cloudflare_pages_deploy.py` — the new deployer module
- **NEW:** `CHANGELOG_v29.md` — this file
- `bvtech_app.py` — publishers rewritten, 3 new API routes, new
  config defaults, new Settings fields, new ORM banner, new JS for
  Test Deploy, content quality upgrades to `_build_orm_prompt`
- `tacticalrmm_integration.py` — `_deploy_cf_direct` rewritten,
  `test_cf_deploy` method added

Everything else (`super_scraper.py`, `prospect_scraper.py`,
`power_dialer.py`, `email_campaign.py`, `sms_campaign.py`,
`dialpad_integration.py`, `autopilot.py`, etc.) is byte-for-byte
identical to v28.

---

## What v29 does NOT fix

- The Super Scraper fix from v28 is still in place and still works.
- The v28 version string bump is still in place (but bumped again
  to v29 in every user-visible spot).
- GitHub API publishing still works if you have it configured — it's
  a legacy path but not removed.
- WordPress relay publishing still works as a last-resort fallback.
- None of the existing Dialpad / HubSpot / M365 / TRMM integrations
  are touched.
