# BVTech MSP Command Center → Pulse — Porting Status

This directory is the **archived source** of the standalone *BVTech MSP Command
Center* (desktop/Flask suite, v32.1). It is kept here as the reference
implementation while its capabilities are ported into the **Pulse** web platform
(`/opspilot`) as proper multi-tenant, RBAC-scoped, encrypted-at-rest features.

Nothing in this directory runs as part of Pulse. It is source-of-truth for the
port only. All modules load credentials from environment variables (no secrets
are committed).

## Module inventory & port status

| Module | What it does | Pulse port |
|---|---|---|
| `tacticalrmm_integration.py` | **Tactical RMM** REST client (agents, alerts, clients, scripts, services, updates), WordPress REST, Guardz, M365 inbox | RMM client → **`opspilot/app/services/tacticalrmm.py`** + `routes/rmm.py` + RMM tab ✅ |
| `hubspot_tracker.py` | HubSpot CRM v3 — contacts, log emails/calls/notes | Planned: `services/hubspot.py` + CRM tab |
| `prospect_scraper.py` | Google Places lead discovery + MSP scoring | Planned: `services/leadgen.py` |
| `super_scraper.py` | Deep decision-maker discovery (site crawl + search) | Planned: leadgen (SSRF-guarded crawler) |
| `generate_prospects.py` | Sample prospect generator | Reference only |
| `email_campaign.py` | M365 drip email + HubSpot sync (CAN-SPAM) | Planned: `services/campaigns.py` (reuses M365 mailbox) |
| `sms_campaign.py` | Dialpad SMS (TCPA-gated) | Planned: campaigns (reuses Dialpad creds) |
| `dialpad_integration.py` | Dialpad calls + AI call coaching + CRM automation | Partly done (click-to-call ✅); coaching planned |
| `power_dialer.py` | Sequential power-dialer over a prospect list | Planned: dialer queue UI |
| `google_business_profile.py` | GBP OAuth + localPost publishing | Planned: add to Publishers |
| `channel_rewriter.py` | Per-channel article rewrite (bvtech/jp/linkedin/gbp) | Planned: Content Studio enhancement |
| `post_queue.py`, `posts_index.py` | Staggered post scheduling + index | Partly covered by Content Studio / publishers |
| `cloudflare_pages_deploy.py` | Cloudflare Pages Direct Upload deploy | Box-side automation (kept) |
| `retroactive_backlinks.py` | Internal-link/backlink builder for SEO | Planned: Content Studio SEO |
| `autopilot.py` | Multi-thread self-building daemon (WARMODE) | Not ported (desktop daemon; Pulse uses scheduled jobs) |
| `autoclaude.py` | Self-modifying AI brain (writes its own code) | **Not ported** — unsafe in a production web app |
| `local_automation.py` | Local SQLite dedup/scheduler glue | Superseded by Pulse DB/automation engine |
| `bvtech_app.py` | 652KB Flask/desktop GUI monolith | Reference only — features re-implemented natively in Pulse |

## Porting principles
1. **Secure by construction.** Credentials go through the Pulse secure vault
   (`services/secure_config.py`, Fernet-encrypted), never hardcoded.
2. **Multi-tenant + RBAC.** Every ported feature is staff-scoped; mutating/RMM
   actions are OWNER-only and audited.
3. **SSRF-guarded.** Any user-supplied URL (RMM endpoint, scraper target) is
   resolved and blocked from private/loopback/metadata ranges
   (`services/netdiag.py` guard).
4. **stdlib HTTP.** Pulse uses `urllib` (no `requests` dependency) to match the
   existing M365 client.
