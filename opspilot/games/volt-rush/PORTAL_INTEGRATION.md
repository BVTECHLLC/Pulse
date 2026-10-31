# VOLT RUSH v2 — OpsPilot / Linode integration for external build agent

**This package is source code, not a live deployment. It was prepared against the previous VOLT RUSH source snapshot.** The actual `bvtechllc/pulse` repository could have newer work; compare before overwriting. Source syntax and `npm test` pass locally; npm packages were unavailable in this environment, so Vite build, 2-human WebSocket smoke, Playwright and live Linode checks **have not been executed here**. Do not report CI, iPhone 60 FPS, or live deployment as passing until verified.

## Safest integration flow

1. In your checkout of `bvtechllc/pulse`, branch from the latest `main` and review the included `VOLT_RUSH_V2.patch`. Run `git apply --check VOLT_RUSH_V2.patch` from the **repo root**. If it fails due to newer repo changes, merge selectively from the included `opspilot/games/volt-rush/` source files; do not blanket replace newer server/proxy files.
2. Apply the patch (or merge relevant files) and inspect the diff. Changes are restricted to **the VOLT RUSH game subtree**; no FastAPI/Caddy/Cloudflare/Workers files need replacing. Do not deploy this to `bvtech.org` (Workers/static site).
3. Inside `opspilot/games/volt-rush`, use Node >=20: `npm ci`, `npm test`, `VITE_BASE_PATH=/kart/ npm run build`. **Commit the generated `dist/` alongside source.** If the repo has no package lock, generate and commit it with `npm install`; do not use an unverified handcrafted lock.
4. Start server locally and run `npm run smoke`. This now exercises **two genuine WebSocket clients through an entire race** (not just the lobby). If the server is already running, restart it after modifying `server/` or `src/shared/`.
5. With local Vite and server up, run optional `python deploy/browser_check.py` (requires Python Playwright/Chromium). Test actual iPhone Safari **portrait and landscape** manually; monitor frame rate and memory. The new bloom pass is desktop-only and can disable itself when frame time is too slow.
6. Follow repo's REQUIRED commit-message trailers (co-author + session). Push feature branch `claude/pulse-rmm-msp-features-c4ug25`, then fast-forward/push `main` only after tests. Update `opspilot/app/core/config.py` `APP_VERSION` and the pinned smoke-test asserts in `opspilot/scripts/smoke_test.py` **as appropriate to the latest repo policy**; keep CI green.
7. Existing cron `/opt/bvtech-portal/opspilot/deploy.sh` resets to origin/main every ~2 minutes and rebuilds **only** `api`. To deploy **server or shared-sim** changes, an authorized SSH-enabled agent must also run:

   ```bash
   cd /opt/bvtech-portal/opspilot
   docker compose up -d --build volt-rush
   docker compose ps api volt-rush
   docker compose logs --tail=80 volt-rush
   ```

8. Ensure the Node server listens on `0.0.0.0:3108` in its container; v2's `server/index.js` uses `process.env.HOST || '0.0.0.0'`. **Never add `depends_on: [volt-rush]` to `api`**. Keep the existing FastAPI `/kart/ws` WebSocket proxy and `/kart/health` handler graceful (503/502/close) when Node is stopped.
9. Test in the API container:

   ```bash
   docker compose exec -T api python -c "import urllib.request as u;print(u.urlopen('http://127.0.0.1:8000/kart/health').read())"
   ```

10. Open `https://portal.bvtech.org/kart/` on a PC and iPhone, host and join from two physical devices, finish a full 3-lap race, test right/left, touch, all items and mute. Cloudflare edge caching may require a purge via the existing `app/services/cloudflare.py` helper. Do not treat cloud-host curl 403/404 challenges as reliable proof of app downtime.

## Safety + compatibility notes

- `src/shared/sim.js` and `src/shared/tracks.js` are authoritative **shared** by server and client. Rebuild Node and client together; avoid schema drift and stale cached client bundles.
- Nothing in this patch modifies the FastAPI `api` container's dependency graph or the Cloudflare Workers marketing site. Preserve all existing `/arena`, `/signal`, `/graveyard-shift`, `/tools-api/*` handlers.
- `base: '/kart/'` in Vite is unchanged.
- Mobile uses Pointer Events and touch-safe buttons; real-device touch/multi-touch and frame-rate validation remains required.
- Do **not** publish a "production ready / live / 60 FPS verified" claim before CI, local browser tests, socket smoke, and physical phone verification.
- Full race smoke lasts at real race speed and may take up to ~165 seconds, unlike the earlier lobby-only smoke.
- The UI pickup appearance is decorative: the **server** randomly awards boost, shield, pulse or oil. Clients do not choose item results or send coordinates.

## What changed

**Controls/physics:** corrected camera-relative steering sign and AI inverse steering; eased high-speed steering, progressive input, gentle edge assist and rubberized boundary correction; 22–24 unit roads with sweeping corners.

**Graphics:** brighter track palette and light, procedural spectator stands and banners, rotating multi-layer holographic energy crates, redesigned kart silhouette kits, shield rings, particles, burst impacts and confetti, optional desktop-only postprocessing bloom.

**Audio:** new original synthesized sounds for each item, boost noise whoosh and celebration; existing sound toggle retained.

**Testing:** new keyboard+touch direction tests, complete 3-lap AI verification, full 2-player websocket smoke test, optional desktop/mobile Playwright screenshots.
