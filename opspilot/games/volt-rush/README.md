# VOLT RUSH V3 DELUXE — original-art browser kart racer

A visually richer continuation of the previous V3 authoritative multiplayer racing game, intended to be merged into `opspilot/games/volt-rush/` in the `bvtechllc/pulse` repository and served from `https://portal.bvtech.org/kart/`.

### Original art shipped

| Asset family | Desktop | Mobile |
|---|---|---|
| Fully modeled karts and chibi pilots | 6 GLBs, 8–9k triangles each | 6 GLBs, reduced poly count |
| Six unique road themes | 6 × 1024px WebP | 6 × 512px WebP |
| Driver selection portraits | 6 × WebP | Same compressed portraits |
| Track selection illustrations | 6 × WebP | Same compressed thumbnails |

Models have individualized helmet/headpieces, eye/face parts, chassis details, colored body panels, 4 independent animated wheel assemblies and per-player custom paint. Loading falls back to the old procedural vehicles when assets are unavailable. All tracks retain their distinct original gameplay layout and power-ups.

### Quality settings

`AUTO`: reduced mobile detail / full desktop detail. `ECO`: low track prop detail and reduced resolution. `ULTRA`: high props / textures, with desktop shadows and bloom when available. A rolling FPS check automatically reduces rendering pixel ratio when necessary. These are performance strategies, **not measured 60 FPS claims**.

### Commands

Run from this directory with Node 20+ and network package registry access:

```bash
npm install
npm test
npm run build
node server/index.js
```

Run `npm run smoke` while Node is serving, and use a separate Vite server for `deploy/browser_check.py` / `deploy/browser_multiplayer.py`. The `dist/` directory must be built and committed before Linode deployment. See `START_HERE.md` for real repo and server requirements.

### Licensing

All bundled art, models and sound design are authored for this game. No Nintendo content or copied game art. See `LICENSES.md`.
