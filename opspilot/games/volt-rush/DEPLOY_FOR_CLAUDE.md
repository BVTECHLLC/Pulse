# VOLT RUSH V3 DELUXE — one-pass graphics + mobile upgrade

**Source origin:** Existing V3 game at `opspilot/games/volt-rush/`, on `bvtechllc/pulse`.
**Target:** `https://portal.bvtech.org/kart/` — OpsPilot FastAPI on Linode behind Cloudflare Tunnel. Never deploy this multiplayer game to the separate Workers site `bvtech.org`.

## What has already been built

- 12 **original GLB kart/driver models**: six distinct chibi-style racers, with independent 3D components, molded kart bodies and animated wheels. Six higher-detail desktop GLBs and six reduced-mesh mobile GLBs.
- Road surface artwork for six circuits at desktop 1024px and mobile 512px. Separate assets for each environment; **lazy-loaded only for the active track**.
- Six original racer portraits and six illustrated track cards for the menu.
- `hero-assets.js` asynchronous GLTFLoader with an original fallback racer if any GLB fails; per-player kart paint and shared mesh geometry to reduce device memory.
- Mobile performance pass: draw-call reduction using instanced rails/dashes, reduced scenery on low-quality setting, mobile pixel ratio 1.25 at start, resolution floor .75 under sustained frame-rate drops, optional eco/auto/ultra quality button, desktop-only bloom/shadows by default. Device-specific models picked via coarse-pointer/low-memory check.
- Preserved the existing V3 6-track, 8-item, collision and authoritative multiplayer gameplay. **This is an artwork upgrade, not a new network protocol.**

## Integrate safely

1. On the latest `main` of `bvtechllc/pulse`, branch/rebase `claude/pulse-rmm-msp-features-c4ug25` as prescribed. Compare this overlay's `opspilot/games/volt-rush/` with the current tree and merge the source and **all `public/art/**` assets**. Avoid overwriting newer server/shared logic if the actual repo is ahead. In particular preserve OpsPilot `app/main.py`, `app/api/routes/kart.py`, Compose and all other games.
2. In `opspilot/games/volt-rush/`, run `npm ci` if the actual repository has a lockfile, otherwise `npm install` and commit a generated `package-lock.json`. Then run `npm test` (17 tests in supplied source) and `npm run build` (Vite configured with `base: '/kart/'`). Check `dist/art/models/*.glb`, `dist/art/textures/*.webp`, `dist/art/tracks/*.webp`, and `dist/art/portraits/*.webp` are present. **Commit `dist/`** with the source and art.
3. Run a local Node game server (`node server/index.js`) and the test Vite server (`npx vite --host 0.0.0.0`), then `npm run smoke`, `python deploy/browser_check.py`, and `python deploy/browser_multiplayer.py`. Verify that no missing-asset requests, JS exceptions, WebGL errors or network snapshot NaNs occur. Inspect browser console for `[VOLT RUSH] 6/6 original 3D racers loaded`; confirm avatars/personalized kart colors display.
4. Measure FPS and GPU memory on an actual iPhone Safari and desktop Chrome; test `AUTO` and `ECO` and forced landscape. A synthetic mobile Chromium viewport is **not** a physical iPhone performance test. Profile and tune GPU draw calls if < 60 FPS; do not describe 60 FPS as verified until measured.
5. Connect two real clients through `https://portal.bvtech.org/kart/ws` via the existing FastAPI proxy: host, join, start, drive, collide, collect an item and finish together. Confirm no start-of-race freeze. Multiplayer must remain authoritative—client never sends trusted positions. Ensure portal fails gracefully if Node is stopped.
6. Bump `APP_VERSION` and hard-pinned assertions in `scripts/smoke_test.py` when needed for this portal repo's cron process. Check GitHub Actions green; preserve required co-author/session message trailers; fast-forward and push `main` per your existing workflow.
7. **Deployment difference:** If the live Node/shared simulation is already V3 and only these client/art files change, the existing Node container normally needs no rebuild. If upgrading from V2 or the agent changes `server/` or `src/shared/`, an authorized SSH agent must run `cd /opt/bvtech-portal/opspilot && docker compose up -d --build volt-rush`. The cron only rebuilds `api`. Never add `depends_on: volt-rush` to `api`.
8. Verify inside the API container `docker compose exec -T api python -c "import urllib.request as u;print(u.urlopen('http://127.0.0.1:8000/kart/health').read())"`, then the actual public browser path. Handle Cloudflare caches if stale.

## Verification done during package creation

- **17/17 Node unit/regression tests passing**, including complete eight-bot races on all six circuits, collisions, pickups, network interpolation and GLB/asset metadata/LOD checks.
- All JS files pass `node --check`; generated GLBs checked for glTF v2 structure and named PBR materials; all images checked as WebP.
- Could not install npm packages in this environment (DNS EAI_AGAIN), so the **Vite production build, actual rendering, full two-player WS race, GitHub CI, physical iPhone FPS and live deployment remain unverified**. This package includes source and assets, **not** a rebuilt `dist/` folder. Claude/SSH agent must perform the steps above.

## Important

Never replace live game code without comparing it with latest source. Keep unrelated FastAPI routes, other games, and credentials unchanged. The art pack contains no external copyrighted models or sounds. Generated art can be recreated by executing `python tools/generate_original_art.py && python tools/generate_track_cards.py` in a Python environment with numpy, Pillow, trimesh, but this step is unnecessary for deployment.
