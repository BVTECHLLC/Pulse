# BVTech MSP Command Center — v30.0 Changelog

**Release: April 2026**
**Codename: SUPER POSTING**

## TL;DR

v30 rebrands ORM Beast as **Super Posting** and adds two big things
on top of v29's working Cloudflare deployer:

1. **Google Business Profile auto-posting** (OAuth2 + localPosts API),
   with a new "All 4 Channels" target that publishes to BVTech.org +
   JordanPolasek.com + LinkedIn + Google Business Profile in one
   click.
2. **Forward-only cross-linking** — every new post automatically
   injects a "Related from BVTech.org" block with 2-3 relevant older
   posts (scored by keyword overlap), plus an "Also on Jordan
   Polasek" cross-site link. The internal link graph builds itself
   as you post.

Nothing from v29 was removed. The Cloudflare Pages Direct Upload
deployer still walks your full site folder, the Super Scraper fix
from v28 is still in place, and the v29 `blog/index.html` safety
protection is untouched.

**Quick test path:**
1. Unzip, run `Start-BVTech.bat`.
2. Super Posting tab → verify v30 green banner + Test Deploy buttons
   still work (v29 stuff is all there).
3. Settings → scroll to the new Google Business Profile card → set
   up OAuth (see instructions in the card itself).
4. When ready, pick "All 4 Channels" in the Super Posting target
   dropdown and generate a post.

---

## What's new

### 1. `google_business_profile.py` — new module (~290 lines)

Standalone Google Business Profile API client. Implements:

- **OAuth2 flow helpers:** `build_authorize_url()`,
  `exchange_code_for_tokens()`, `refresh_access_token()`. Uses scope
  `https://www.googleapis.com/auth/business.manage` with
  `access_type=offline` and `prompt=consent` so the refresh token
  is always returned.
- **`GoogleBusinessProfileClient`** class with `list_accounts()`,
  `list_locations()`, `create_local_post()`, `verify_connection()`.
  Lazily refreshes the access token on each call.
- **`post_to_gbp()`** high-level helper that reads config, builds a
  client, and creates one local post with a call-to-action button.
  Called from `_generate_one_post()` when the target includes GBP.
- **Clear 403 handling** pointing at Google's API access request
  form (because GBP API access is gated — see the GBP ACCESS
  section below).

**API endpoints used** (Google split this across three base URLs):
- Accounts: `https://mybusinessaccountmanagement.googleapis.com/v1`
- Locations: `https://mybusinessbusinessinformation.googleapis.com/v1`
- LocalPosts: `https://mybusiness.googleapis.com/v4`
  (still on legacy v4 — Google hasn't migrated localPosts yet)

### 2. `posts_index.py` — new module (~270 lines)

Forward-only link graph. Maintains `posts_index.json` in the app
directory with every post that's been successfully published. On
each new publish:

1. Load the index.
2. Score existing posts on the same site by keyword/title overlap
   with the new post's focus keyword.
3. Pick the top 3 and build a "Related from BVTech.org" HTML block.
4. Also pick the most recent post from the *other* site and build
   an "Also on Jordan Polasek" cross-site block.
5. Inject both blocks into the new post's HTML **before** the
   `author-byline` div (or before `</body>` as a fallback).
6. After the deploy succeeds, record the new post in the index so
   it becomes a candidate for all future posts.

**Why forward-only** — the original ask was "make all posts
backlink to each other so SEO sees one uniform thing." The safe way
to do that is to link forward: new posts link to old ones, never
rewrite old HTML. After 10-20 posts every post has inbound links
from newer content, which is what Google actually rewards, and
nothing ever breaks because we never touched old files.

**Scoring algorithm:** simple keyword intersection. New post's
title + focus_keyword → token set → overlap count with each
candidate's title + focus_keyword. Ties broken by recency. Top 3
wins. No external ML dependency.

**Block HTML** has `data-bvtech-related="v30"` and
`data-bvtech-cross="v30"` markers so you can style them site-wide
or find them later for bulk updates.

### 3. `bvtech_app.py` — Super Posting wiring

**ORM → Super Posting rename.** All user-visible strings updated:
tab label now reads "Super Posting", the section title is "🚀 Super
Posting v30 — 4-Channel Publishing", the header badge says "SUPER
POSTING", the welcome dashboard listing mentions BVTech + JP +
LinkedIn + GBP. Internal variable names (`_orm_queue`,
`_orm_history`, `/api/orm/*`, tab id `orm`) are unchanged to avoid
breaking existing `bvtech_config.json` and queued state files.

**`_generate_one_post()` upgraded** to:
- Lazily import `posts_index.enrich_post_html` and
  `posts_index.record_post` so the core keeps working even if the
  module were somehow missing.
- Call `_enrich(html, site)` before each site publish, which runs
  the HTML through the cross-linker and returns enriched HTML plus
  an info dict with `related_count`, `related_titles`,
  `cross_count`, `cross_title`.
- Call `record_post()` after each successful deploy so the link
  graph grows.
- Add GBP publish branch: when `target in ("gbp", "all_four")`,
  builds a 280-char summary from the meta description, points the
  call-to-action URL at the just-published BVTech post (or JP as
  fallback), and calls `post_to_gbp()`. Errors are captured and
  returned as normal post failures.
- Add LinkedIn to the `all_four` target so one click posts to all
  four channels.

**7 new API routes:**

- `GET /api/gbp/oauth/start` — returns the Google OAuth authorize
  URL. The UI opens this in a new window.
- `GET /api/gbp/oauth/callback` — the redirect target. Exchanges
  the `?code=` for tokens, saves the refresh token to config, shows
  a success page that auto-closes.
- `GET /api/gbp/test` — calls `list_accounts` as a smoke test.
  Returns the list of accounts visible to the user, or a clear error
  if the token is stale / API access not granted.
- `GET /api/gbp/accounts` — full accounts list for the picker.
- `GET /api/gbp/locations?account=accounts/X` — locations under one
  account, for the picker.
- `POST /api/gbp/disconnect` — clears the refresh token + account
  + location from config.
- `GET /api/posts-index` — returns the cross-linking index
  (`{total, bvtech_count, jp_count, posts[]}`) so the UI can show
  how many posts are in the link graph.

**New Settings section — Google Business Profile:**

A new card in Settings with inputs for OAuth client ID, client
secret, redirect URI, refresh token (read-only, auto-filled), and
account/location names (read-only, auto-filled by the picker). Has
six action buttons:

- **📍 Connect Google Business** — opens Google consent window
- **🏢 Pick Location** — loads accounts, loads locations, auto-saves
  the pick (if there's only one location it auto-picks; otherwise
  it prompts)
- **🔌 Test Connection** — smoke test, shows account list inline
- **🔌 Disconnect** — clears credentials after confirm
- **GBP Dashboard ↗** — opens business.google.com
- **Request API Access ↗** — opens Google's access request form

The card has detailed inline setup instructions explaining the
7-step process (create GCP project → enable APIs → request access →
create OAuth credentials → paste ID+secret → Connect → Pick
Location).

**New target dropdown option:** Super Posting's target selector now
has `🚀 All 4 Channels (BV + JP + LI + GBP) — v30` as the top
option. The existing options (3-Way Rotate, Both, JP Only, BV Only,
LinkedIn Only, etc.) are all still there. New: "Google Business
Profile Only" for targeted GBP-only posts.

---

## GBP ACCESS — READ THIS FIRST

Unlike most Google APIs, the Business Profile APIs are **gated**.
Creating an OAuth client in Google Cloud Console is not enough —
your project also needs approval from Google's Business Profile
team. Without approval, `localPosts.create` returns HTTP 403 with
a "permission denied" error.

**Required one-time steps:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or pick a project
3. Enable these three APIs from the API Library:
   - My Business Account Management API
   - My Business Business Information API
   - Google My Business API
4. **Fill out the access request form:**
   https://support.google.com/business/contact/api_default
5. Wait 1-2 business days for approval email
6. Create OAuth 2.0 credentials (Web application type) with
   redirect URI: `http://localhost:5678/api/gbp/oauth/callback`
7. Paste client ID + secret into Settings → Google Business Profile

If you skip step 4 and try to post anyway, the v30 client will show
you a clear error message with a link directly to the form. It won't
silently fail.

**OAuth listing works before API access approval.** You can click
Connect Google Business, complete consent, Pick Location, and see
the Test Connection smoke test succeed — because listing accounts
uses a less-restricted endpoint. Only `localPosts.create` is gated.

---

## Cross-linking details (`posts_index.json`)

The index file gets created the first time you publish a post
through Super Posting. Its shape:

```json
{
  "posts": [
    {
      "slug": "how-msps-help-texas-smbs",
      "title": "How MSPs Help Texas SMBs Stay Secure",
      "site": "bvtech",
      "url": "https://bvtech.org/blog/how-msps-help-texas-smbs.html",
      "published_at": "2026-04-09T14:32:11",
      "focus_keyword": "managed it services",
      "summary": "Three ways a managed IT provider..."
    }
  ]
}
```

**What gets injected into new posts** (right before the
`<div class="author-byline">` marker):

```html
<div class="bvtech-related-posts" data-bvtech-related="v30"
     style="...purple-left-border card...">
  <h3>Related from BVTech.org</h3>
  <ul>
    <li><a href="/blog/slug-a.html">Title A</a></li>
    <li><a href="/blog/slug-b.html">Title B</a></li>
    <li><a href="/blog/slug-c.html">Title C</a></li>
  </ul>
</div>

<div class="bvtech-cross-site" data-bvtech-cross="v30"
     style="...yellow accent...">
  <p><strong>Also on Jordan Polasek:</strong>
     <a href="https://jordanpolasek.com/blog/slug.html">Title</a></p>
</div>
```

**You can restyle these** site-wide via CSS using the
`data-bvtech-related` and `data-bvtech-cross` attribute selectors
without touching any post HTML.

**Graph growth pattern** (assuming you post 3x/week):

- Week 1: first post has 0 related, 0 cross (nothing to link to)
- Week 2: posts have 1-3 related, 0-1 cross
- Week 3+: every post has 3 related + 1 cross, total posts start
  having dozens of inbound links from newer content
- Month 3: Google's crawler starts seeing a dense topical cluster,
  which is exactly the signal it rewards

**Deleting the index resets the graph** — just delete
`posts_index.json` from the app directory. Future posts will start
fresh. Old posts already on your site keep their existing
(historical) backlinks since v30 never rewrote them.

---

## What's NOT in v30 (coming later)

Same split as v29 had. These still need a follow-up:

- **Channel-specific content rewrites.** Right now all 4 channels
  get the same HTML body. The Claude prompt was supposed to do a
  second-pass rewrite for LinkedIn-short-form and GBP-300-char
  variants. That got deferred — the existing `_adapt_for_linkedin`
  function still runs for LinkedIn (so it's at least trimmed and
  hook-rewritten), and the GBP publisher auto-truncates the meta
  description to 280 chars, so nothing's broken — but the "four
  different voices" idea is v30.1.
- **Scheduler rewrite for staggered per-channel day/time locks**
  (Mon BVTech / Wed JP / Fri LinkedIn / Sat GBP). Current
  scheduler still works, you just manually trigger "All 4 Channels"
  for now.
- **Channel-specific rewrites of old posts to add backlinks
  retroactively.** Still too risky — forward-only graph growth is
  the safer default.

---

## Files changed in v30

- **NEW:** `google_business_profile.py` (~290 lines)
- **NEW:** `posts_index.py` (~270 lines)
- **NEW:** `CHANGELOG_v30.md` (this file)
- `bvtech_app.py`:
  - 6 new config defaults for GBP
  - Save/load field lists extended
  - `_generate_one_post()` wired for cross-linking + GBP + all_four
  - 7 new API routes for GBP OAuth, test, accounts, locations,
    disconnect, and posts-index
  - New GBP Settings card with 6 action buttons
  - 4 new JS functions: `connectGoogleBusiness`, `testGBP`,
    `gbpPickLocation`, `disconnectGBP`
  - New "All 4 Channels" option in the target dropdown
  - ORM → Super Posting rename on all user-visible strings
  - Version strings bumped v29 → v30

Everything else (`cloudflare_pages_deploy.py`,
`tacticalrmm_integration.py`, `super_scraper.py`,
`prospect_scraper.py`, `power_dialer.py`, `email_campaign.py`,
`sms_campaign.py`, `dialpad_integration.py`, `autopilot.py`, etc.)
is byte-for-byte identical to v29. The v29 fixes all still apply.

---

## End-to-end smoke test results

Before packaging, v30 was tested against a scratch copy of
bvtech.org (187 files, 18.5 MiB). Results:

- ✅ All 6 modules parse clean (`ast.parse`)
- ✅ 145 total Flask routes, 7 new v30 routes verified present
- ✅ Cross-linking picks topically-relevant posts (seeded "ransomware
  defense" post → correctly picked as top match for a new
  cybersecurity article)
- ✅ Related block injected BEFORE `author-byline` marker
- ✅ Cross-site block picks the other site's most recent post
- ✅ Enriched HTML written to disk (post file 1578 chars, up from
  706 after enrichment) — related blocks intact
- ✅ `blog/index.html` byte-identical to original after deploy
  (v29 safety preserved)
- ✅ Second new post correctly picks up the FIRST new post as a
  candidate — link graph grows forward
- ✅ CF Direct Upload dry run: 187 files walked, only 1 would upload
  (the new enriched post) — efficient deploy behavior confirmed
- ✅ GBP authorize URL contains `business.manage` scope,
  `access_type=offline`, and `prompt=consent`
- ✅ GBP 403 error classifier correctly points user at the API
  access request form

v30 is ready to ship.
