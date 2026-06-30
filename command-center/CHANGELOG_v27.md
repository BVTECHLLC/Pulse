# BVTech MSP Command Center — v27.0 Changelog

**Release: April 2026**
**Codename: SUPER SCRAPER**

## TL;DR

v27 adds the **Super Scraper** — a decision-maker discovery engine that goes
*way* beyond the v26 `info@` email problem. Deep-crawls websites for real
named contacts, finds LinkedIn profiles via search operators, generates and
verifies email patterns (Hunter.io if configured), and auto-pushes named
decision-makers to HubSpot **and** the Dialpad dialer with full job titles.

Everything in v26 still works exactly as before. The old `prospect_scraper.py`
is unchanged and the new module imports from it (same markets, same MSP
scoring base, same cache file — no duplicate work).

## What's New

### 🚀 Super Scraper (`super_scraper.py`) — ~1,160 lines, brand new

A multi-source decision-maker discovery pipeline:

1. **Google Places seed** — reuses your existing `prospect_scraper.py` logic,
   markets, scoring, and cache. Zero re-scraping of known businesses.

2. **Website deep crawl** — for each company, fetches up to 8 pages:
   `/`, `/contact`, `/about`, `/team`, `/leadership`, `/staff`,
   `/our-team`, `/attorneys`, `/providers`, `/agents`, `/partners`,
   `/management`, `/lawyers`, `/physicians`, `/doctors`. Pulls:
   - Real same-domain emails (filters out CDN / image / Wix junk)
   - Obfuscated emails (`name [at] domain dot com`)
   - All phones in any common US format
   - LinkedIn profile URLs
   - LinkedIn company page URL
   - Name + title pairs from rendered text

3. **Hunter.io enrichment** *(optional, requires API key)* — domain search
   for known named contacts + email pattern verification on the top 3
   generated candidates.

4. **LinkedIn discovery** *(deep mode)* — uses `site:linkedin.com/in`
   Google operators to find decision-maker profiles. Tries Google Custom
   Search → Bing → DuckDuckGo HTML in that order. **Free fallback works
   with no extra keys.** This is exactly how Apollo, RocketReach, and
   ZoomInfo do it under the hood — LinkedIn's official `/v2` API does
   not expose people search.

5. **Decision-maker title scoring** — 30+ titles ranked S/A/B/C tier:
   - **S-tier (+30 to +35):** Owner, Founder, CEO, President, Managing Partner, Principal
   - **A-tier (+22 to +27):** COO, Practice Manager, Office Manager, Operations Manager, Administrator, IT Director, CTO
   - **B-tier (+22 to +25):** General Counsel, CFO, Controller, Medical Director, Clinic Manager
   - **C-tier (+12 to +15):** Project Manager, Estimator
   - Word-boundary matching for short acronyms (so "Marketing Coordinator"
     does not false-match as "COO"). Bug caught and fixed during testing.

6. **Email pattern generation** — `first.last@`, `flast@`, `f.last@`,
   `firstlast@`, `first_last@`, `first@`, `last@`. If Hunter is configured,
   verifies the top candidates and only keeps deliverable ones.

7. **Owner-driven industry boost (+5)** — Law Firms, Medical Offices,
   Dental Practices, Accounting/CPA, Insurance, Real Estate, Construction,
   Financial Advisors, Veterinary Clinics. Small shops where the owner
   signs the IT vendor check.

8. **HubSpot sync** — companies + contacts + **associations** + custom
   properties (`msp_score`, `discovery_source`, `linkedin_url`, `jobtitle`
   from decision-maker title).

9. **Dialpad sync** — pushes named humans straight into the dialer with
   first name, last name, job title, company, phone, email. No more
   `info@` placeholders.

### 🎨 New "🚀 SUPER SCRAPER" UI Panel (Scraper tab)

Purple-bordered panel right below the existing scraper. Includes:
- Market checkboxes (Austin / SA / Houston)
- Max prospects + industry dropdown (with "Construction (General Contractors)" added)
- **🔥 DEEP MODE toggle** — enables LinkedIn + max-depth crawl
- **"Only keep prospects with a real decision-maker title"** filter
- Min MSP score, must-have-phone, skip-solo
- HubSpot sync + Dialpad sync checkboxes
- Streaming log output

### ⚙️ Two New Settings Fields

- **🎯 Hunter.io API Key** — optional but recommended. Free tier = 25
  searches/month. Adds named-contact discovery + email verification.
- **🔎 Bing Search API Key** — optional. Improves LinkedIn discovery.
  Falls back to free DuckDuckGo HTML if unset.

The existing `linkedin_access_token` from v26 is reused automatically.

### 🔌 New Flask Route

`GET /api/run/super_scraper` — streams live output from `super_scraper.py`.
Mirrors the existing `/api/run/scraper` interface for consistency.

## Files Changed (vs v26)

| File                  | Status   | Notes                                          |
|-----------------------|----------|------------------------------------------------|
| `super_scraper.py`    | **NEW**  | 1,160 lines. Drop-in module.                   |
| `bvtech_app.py`       | PATCHED  | +UI panel, +route, +settings fields. ~150 new lines. All v26 functionality preserved. |
| `prospect_scraper.py` | UNCHANGED | Super Scraper imports from it.                 |
| `dialpad_integration.py` | UNCHANGED | Super Scraper has its own thin Dialpad client. |
| `power_dialer.py`     | UNCHANGED | Reads `prospects.csv` — unchanged.             |
| `email_campaign.py`   | UNCHANGED | Reads `prospects.csv` — unchanged.             |

## Files Written by Super Scraper

- **`prospects.csv`** — MERGED (not overwritten) with your existing leads.
  Schema is identical to v26. Duplicate `place_id` rows are filtered.
  Verified safe against the v26 200-row prospects.csv during testing —
  zero corruption, zero schema drift. Your dialer + email campaigns read
  this file unchanged.
- **`super_prospects.csv`** — Full enriched record (decision-maker name,
  title, all emails, all phones, LinkedIn URL, crawl page count, discovery
  source). Open in Excel for manual review.
- **`super_raw.json`** — Raw JSON for debugging.
- **`super_scrape_cache.json`** — Separate cache file so it does not
  conflict with the v26 scraper's cache.

## Honest Note on LinkedIn

LinkedIn's official `/v2` API does **not** expose people-search, lead
lookup, or company employee lists. Those endpoints require Sales Navigator
or Marketing Developer Platform partnership which is essentially
impossible to obtain. Every commercial scraper (Apollo, RocketReach,
ZoomInfo) gets LinkedIn data via Google `site:linkedin.com/in` operators —
that is exactly what this module does. Your existing
`linkedin_access_token` is still validated and used for what the official
API actually allows (`/v2/userinfo` profile read).

## Verified Before Shipping

- [x] `super_scraper.py` compiles
- [x] `bvtech_app.py` compiles after all 7 patches
- [x] `prospect_scraper.py` still compiles (untouched)
- [x] Imports cleanly side-by-side with v26 modules
- [x] Title scoring tested (COO/Coordinator substring bug caught & fixed)
- [x] HTML extraction tested (emails, phones, LinkedIn, name+title pairs)
- [x] Email pattern generation tested across 7 patterns
- [x] Phone normalization tested across 5 input formats
- [x] CSV merge tested against the real v26 200-row prospects.csv:
  - 200 existing rows preserved byte-for-byte
  - Duplicate place_ids filtered correctly
  - Schema unchanged
  - 0 corruption

## Recommended First Run

```
Tab:        Scraper
Panel:      🚀 SUPER SCRAPER (purple, below the regular scraper)
Markets:    Austin only (start small)
Max:        25 prospects
Industry:   Law Firms
DEEP MODE:  ON
Titles only: OFF (you'll see what gets filtered)
HubSpot:    ON
Dialpad:    ON
Min score:  60
```

Runtime ~3-5 minutes. ~50 Google Places API calls (~$1.25 if you exceed
the free tier — the $200/month free credit usually covers it). ~25
website crawls. ~25 LinkedIn lookups. Output: named decision-makers
pushed straight into HubSpot + Dialpad ready to call.

## CLI Usage (Standalone)

```
python super_scraper.py --market austin --industry "law firm" --deep --sync --dialer --titles-only --max 50
```

Flags: `--deep`, `--titles-only`, `--sync`, `--dialer`, `--require-phone`,
`--skip-solo`, `--min-score N`, `--market {austin,san_antonio,houston}`,
`--industry KEYWORD`, `--max N`.

## Upgrade Path from v26

1. Stop the BVTech app.
2. Unzip `BVTech_MSP_CommandCenter_v27_FINAL.zip` over your v26 folder
   (or to a fresh location — your `bvtech_config.json`, `prospects.csv`,
   and `scrape_cache.json` are preserved).
3. Restart with `Start-BVTech.bat`.
4. Open the Scraper tab — the new purple panel is below the old one.
5. (Optional) Add a Hunter.io API key in Settings for verified emails.

No database migration. No config changes required. v26 features all work
exactly as before.
