# Content pack — 2026-07-10

Four ready-to-publish posts written for BVTech, plus a manifest that ties each
file to its channel. Publish them through the portal (they go out via the same
publishers the daily Content Autopilot uses).

| File | Channel | What it is |
|------|---------|-----------|
| `bvtech-blog.html` | bvtech.org | Mid-year 2026 threat report (SEO advisory, Jordan Polasek) |
| `jordanpolasek.com` → `jordanpolasek-blog.html` | jordanpolasek.com | Founder "field notes" on 2026 IT trends |
| `linkedin.txt` | LinkedIn | Recent cyber threats + how BVTech protects you |
| `gbp.txt` | Google Business | Local security-review CTA |
| `manifest.json` | — | Maps each file to its channel + SEO metadata |

## How to publish

Each post ships to one channel via `POST /api/content-autopilot/publish-custom`
(OWNER-only). The site posts (`bvtech`, `jp`) are committed to the site's GitLab
repo and verified by the Cloudflare build; the `linkedin` / `gbp` posts are queued
to the autopost engine (retries + brand guard + dedupe).

Example payloads:

```jsonc
// bvtech.org blog
{ "channel": "bvtech", "kind": "advisory",
  "title": "BVTech Mid-Year 2026 Threat Report: The 5 Attacks Actually Hitting Texas Small Businesses",
  "slug": "2026-mid-year-threat-report-texas-small-business",
  "keywords": "small business cybersecurity 2026, Texas managed IT security, ransomware Houston",
  "html": "<contents of bvtech-blog.html>" }

// LinkedIn
{ "channel": "linkedin", "body": "<contents of linkedin.txt>", "link": "https://bvtech.org/book/" }
```

Prerequisite: connect the credentials in the portal's **Connection Center** —
a GitLab token (one connects both sites), a LinkedIn connection, and a Google
Business Profile. Any channel that isn't connected reports that clearly instead
of failing silently.
