# VOLT RUSH V5 — original-art browser kart racer

A visually richer continuation of the previous authoritative multiplayer racing game, intended to be merged into `opspilot/games/volt-rush/` in the `bvtechllc/pulse` repository and served from `https://portal.bvtech.org/kart/`.

## What's new in V5

V5 is the biggest content-and-feel update since launch. Everything the game already did now looks and plays better, and there is a lot more of it.

**Three brand-new tracks (6 → 9 worlds).** *Sunset Dunes* is a wide coastal sprint under a burnt-orange sky, *Glacier Rift* is a tight icy technical circuit, and *Pulse Speedway* is a fast neon oval built for overtakes. New circuits with no illustration yet render a clean gradient card generated from each track's own sky and surface colors, so the menu never shows a broken thumbnail.

**Two new power-ups (8 → 10).** *Lightning* (🗲) zaps every rival ahead of you for a jolt of chaos plus a small personal boost, and *Warp* (🌀) grants a short burst of speed, brief invulnerability and a forward blink through the pack. Both are weighted to show up more often when you're behind, so a bad lap has a real comeback button. New synthesized sound effects and particle colors were authored for each.

**Original race music.** A rolling synthesized bassline and arpeggio over a short minor-key loop — written note-by-note in the Web Audio API, no samples or licenses — plays through races and can be toggled independently of sound effects.

**Rebuilt mobile controls.** The old touch pad is replaced with an analog steering joystick (drag-to-steer with adjustable sensitivity) *or* classic left/right buttons — the player's choice. The action buttons (item, drift, brake, GO) were regrouped so nothing is crowded on phones or in landscape, and a new **Options** panel exposes steering scheme, sensitivity, music, sound, graphics and camera in one place.

**Multiplayer lobby & smooth rematch.** After a race, everyone can return to a shared lobby; the host can start a rematch and non-hosts are taken back cleanly, with the network protocol bumped so stale clients are refreshed automatically.

**Better graphics on everything that was already there.** Richer power-up particle effects and new FX palettes across the board, plus the V5 stamp throughout the UI.

See `games/volt-rush/LICENSES.md` — all new sound, music and effects are original and license-free.

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
