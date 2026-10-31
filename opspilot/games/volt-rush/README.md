# VOLT RUSH v2 — original multiplayer 3D kart racing

**BVTech portal game at `https://portal.bvtech.org/kart/`** (FastAPI static mount + WebSocket proxy to independent Node service). **Not** the Cloudflare Workers static website at `bvtech.org`.

This is a *source-code overhaul and repo integration patch*, not a verified live deployment. See [`PORTAL_INTEGRATION.md`](./PORTAL_INTEGRATION.md) for the required Git -> `main` -> API cron -> separate `volt-rush` container workflow and production verification steps.

## Gameplay

- Three original, widened 22–24 unit circuits with beginner-friendly steering and shoulder assist.
- Six custom procedural drivers/karts; vivid scenery, spectators, signs and animated hologram item crates.
- Three laps, AI fill to eight, private multiplayer rooms, server-authoritative racing, boost/pulse/shield/oil power-ups, synthesized sounds, drift particles and finish confetti.
- Keyboard: **W / ↑** accelerate, **S / ↓** brake, **A / ←** steer left, **D / →** steer right, **SPACE** drift, **SHIFT** use power-up, **E** camera, **M** mute.
- Touch: dedicated steering, GO, BRAKE, DRIFT, and power-up controls. Landscape recommended for phones.

## Local development (Node ≥20)

```bash
npm ci                # use the EXISTING repository package-lock.json
npm test              # includes steering, AI and track physics
npm run build         # Vite base=/kart/ ; check in generated dist/
npm start             # Node game service on 0.0.0.0:3108
# In a second terminal:
npm run smoke         # complete real-time two-human-client 3-lap race
```

For hot reload: `npm run dev` (Vite on 5173 and websocket/health proxy to Node 3108). To screenshot basic desktop/touch UI, with Vite running: `python deploy/browser_check.py` (Python Playwright + Chromium required).

## License and deployment boundaries

All game art/model/audio generation in this revision is original; see [`LICENSES.md`](./LICENSES.md). Engine and libraries use their own software licenses. **Never replace the whole OpsPilot compose setup or give `api` a dependency on `volt-rush`.** New Node builds require `docker compose up -d --build volt-rush` on the Linode machine after the Git/API auto-deploy.
