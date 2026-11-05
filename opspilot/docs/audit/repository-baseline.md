# BVTech Platform — Repository Baseline (Phase 0)

_Generated as the Phase 0 "Repository Discovery" deliverable of the Comprehensive
Digital Audit & Overhaul Plan. This records the **actual** architecture so later
phases build on reality, not assumptions. (The source plan was written from the
public site and assumed a Node/React SPA; the real stack is documented below.)_

## 1. What this repository is

A single Python monorepo, **OpsPilot** (an MSP command center), that powers **two
public surfaces** from one codebase:

| Surface | URL | How it is served |
| --- | --- | --- |
| **The Portal** | `portal.bvtech.org` | FastAPI app (`app/`) in a Docker container on Linode, behind Cloudflare. Serves the staff/client/academy web app + all `/api/*` + the public Academy + certificate pages + the free-tool lead API. |
| **The Public Site** | `bvtech.org` | A **Cloudflare Workers static-assets site**. Its HTML lives in a separate **GitLab** repo; Cloudflare Workers Builds rebuilds it on each commit. OpsPilot **publishes** to that repo over the GitLab API (`destination.publish()` → `jp_site`). Dynamic widgets are Cloudflare edge functions (`app/services/edge_tools/*.js`). |

> **Key architectural fact:** there is no Node/React web app for the marketing
> site. "Templates" for `bvtech.org` are Python functions that return HTML
> strings, injected into a cloned site chrome. The only Node pieces are the
> VOLT RUSH game (Vite build under `games/volt-rush/`) and the edge-worker JS.

## 2. Stack

- **Language/runtime:** Python 3.11.
- **Web framework:** FastAPI (+ Starlette), Uvicorn. Routers in `app/api/routes/*.py`, wired in `app/main.py`.
- **Templating:** Jinja2 for portal pages (`app/templates/*.html`). Public-site pages are built by `app/services/pages_*.py` (functions returning HTML) and placed into the GitLab chrome via `content_studio._swap_main` + `destination.build_page`.
- **CSS / design system:** No central token system. Portal uses `app/static/css/pulse.css`. Each public page ships **scoped inline CSS** that reuses the chrome's CSS custom properties (`--white`, `--text`, `--o`, `--o2`, `--card`, `--border`, `--fh`, `--fb`, …). _(Conflict with plan Phase 2, which assumes design tokens + a shared React shell — see roadmap.)_
- **Database:** PostgreSQL in production via SQLAlchemy; SQLite in CI/dev. Migrations via Alembic (`migrations/`).
- **Package manager:** `pip` (`opspilot/requirements.txt`). Node only for `games/volt-rush` (Vite) and edge workers.
- **Auth:** session cookies, password hashing, MFA (TOTP), OAuth connectors. Roles: `OWNER`, `TECH`, `CLIENT_ADMIN`, `CLIENT_VIEWER`, plus Academy learners provisioned into an **isolated Academy tenant**.
- **Background work:** in-process scheduler (`app/services/scheduler.py`) + `heartbeat.run_all` (news digest, email filter, SEO autopilot, site repair, cache purge-on-deploy, etc.). No external cron except the deploy poller.

## 3. Deployment

- **Portal (api):** `deploy.sh` runs via cron every 2 min on the Linode box; it fast-forwards the checkout to `origin/main`, rebuilds only the `api` service, runs Alembic, restarts, and (v1.124+) full-zone-purges Cloudflare on a version change. A FastAPI startup hook also purges once per `APP_VERSION`.
- **Public site:** `destination.publish(db)` commits all built pages + edge workers to the GitLab site repo in **one commit**; Cloudflare Workers Builds deploys it; the publish then purges. Daily self-heal re-runs publish via `site_repair`.
- **CI:** `.github/workflows/ci.yml` — SQLite, Alembic up/down/up, then `scripts/smoke_test.py` (a large FastAPI `TestClient` integration suite). _(No `npm test` for the site — it is Python. Conflict with plan Phase 17's npm pipeline — see roadmap.)_

## 4. Routes (inventory)

See `docs/migration/routes-before.csv` (generated from the live app).

- **501 portal routes** (`/` pages + `/api/*`). Public page routes: `/`, `/login`, `/join`, `/signup`, `/academy`, `/academy/certificate/{code}`, `/answers`, `/status`, `/developers`, `/report/{client_id}`, `/human.js`, plus `/invoice/{id}`, `/remote/{token}`.
- **13 published static pages** on `bvtech.org`: `/explore/`, `/academy/lightning-labs/`, `/graveyard-shift/`, 7× `/tools/<slug>/`, and 3× `/managed-it-{houston,austin,san-antonio}/`. (Additional `bvtech.org` pages — homepage, `/services/`, `/pricing/`, `/blog/`, `/about/`, `/reviews/`, `/es/`, `/academy/`, `/academy/labs/`, `/cyber-range/` — live in the **external GitLab site repo**, not this codebase; OpsPilot sweeps them for nav + captcha + viewport but does not own their markup.)

## 5. Academy (learning platform) — current state

- **Content** (`app/services/academy.py`, ~3.1k lines): 5 modules / 20 lessons, 2 games, ~63 Cyber Range CTF labs (Easy/Medium/Hard), plus Code Dojo (`dojo.py`) and the emulated shell "The Grid" (`shell_range.py`). Public **Lightning Labs** (3, edge-graded via `edge_tools/labs.js`).
- **Progress/rewards:** `AcademyProfile` (xp, streak_days, badges JSON) + `AcademyCompletion` (one row per user×item; **XP awarded once**, retakes re-grade at 0). Levels from XP (10 tiers), 18 badges, tenant-isolated leaderboard, training-compliance rollups for client reports. **Grading is server-side; answers never ship to the browser.**
- **Certificates (new this session):** derived from completions, **HMAC-signed and verifiable** at `/academy/certificate/<code>` (a forged/incomplete code 404s). Per-module + a full Graduate certificate. Shown in the Academy "Me" tab; API at `/api/academy/certificates`.

## 6. SEO / schema / analytics (current state)

- **Schema:** `destination._schema` emits a JSON-LD `@graph` (`WebPage` + `WebSite` + shared `ProfessionalService`/`Organization` with Texas `areaServed`, + `FAQPage` when a page supplies `faqs`). `build_page` rewrites title/description/canonical/OG and guarantees a mobile viewport (v1.126).
- **Sitemap/robots/llms:** `jp_site.sitemap_sync` + `seo_boost` (`llms.txt`, `robots.txt`, IndexNow key + ping). City pages carry `LocalBusiness`/`FAQPage`.
- **Analytics:** Google Tag Manager is present in the public chrome. There is **no typed event-contract layer yet** (plan Phase 15 — backlog).

## 7. Security (current state)

- Session cookies (HttpOnly/SameSite), MFA, per-IP rate limiting on public intake, moderation engine, in-house proof-of-work + honeypot CAPTCHA on public forms (lead, signup, academy register) with disposable-email blocking, audit logging, encrypted secret vault (`secure_config`).
- **Gaps vs plan Phase 14 (OWASP ASVS):** no explicit CSP-with-nonces / HSTS / `Permissions-Policy` / `Referrer-Policy` headers asserted from the app layer yet; dependency/secret scanning not in CI. (Backlog.)

## 8. Known duplication / debt (matches the plan's audit)

- Academy marketing copy historically over-claimed "certificates" (now true as of this session) and lesson counts drift from live labs.
- Public-site nav is dense; nav/captcha/viewport are swept across the GitLab repo but the chrome itself is externally maintained.
- `/es/` Spanish page is partial (no full hreflang parity).

## 9. How to run the test suite (verified)

```bash
cd opspilot
python -m venv /tmp/pvenv && /tmp/pvenv/bin/pip install -r requirements.txt httpx
ENV=development SECRET_KEY=... AGENT_ENROLL_SECRET=... COOKIE_SECURE=false \
  BOOTSTRAP_ADMIN_EMAIL=admin@bvtech.org BOOTSTRAP_ADMIN_PASSWORD='ChooseOne123!' \
  DATABASE_URL="sqlite:///./ci.db" \
  python scripts/smoke_test.py
```

_Note: the smoke suite writes a SQLite file; never run two copies against the same
`DATABASE_URL` concurrently (they corrupt each other). Use a unique DB path per run._
