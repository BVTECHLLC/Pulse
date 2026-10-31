# VOLT RUSH — BVTech Arcade

Original 3D browser kart racing game for iPhone/iPad Safari and desktop Chrome/Edge/Firefox/Safari. This is a **feature-rich playable v1**, not a Nintendo game, a photorealistic production title, or a guarantee that every browser/server has been tested. All characters, kart models and world geometry are procedural/original (no game art pack needed).

## What is included

- Fully navigable 3D kart circuits: **Solar Coast**, **Emerald Run**, and **Neon Metropolis**.
- Six original pilots, six kart paint finishes, individual 3D karts, rotating wheels, helmets, spoilers and effects.
- Solo 3-lap racing with seven AI racers; online rooms for **2–8 real players**, AI fills empty positions.
- Server-authoritative kart movement, lap times and rankings, bump collisions, race countdown/results/rematches.
- Corner drifting and drift-charge turbo; collectible boost, pulse, shield and oil slick power-ups.
- Original synthesized sound effects, engine sound, three camera modes, HUD, minimap, responsive PC/mobile controls.
- Five-character shareable multiplayer room codes; no account needed; no open text chat, simple restricted names.
- Installs next to an existing site under **https://portal.bvtech.org/kart/** (does NOT replace your portal).
- Three.js/WebGL frontend + Vite; Node 20+ HTTP/WebSocket server; Nginx and systemd examples.

## Quick local setup

Requires **Node.js 20.19+ or 22.12+**, npm, and an internet connection for installing packages.

```bash
unzip volt-rush.zip -d volt-rush   # if starting from ZIP (skip if already unpacked)
cd volt-rush
npm install
npm test
npm run dev
```

Then visit **http://localhost:5173/kart/**. The dev command starts both the game server (`3108`) and the Vite frontend (`5173`). For a standalone production run:

```bash
npm run build
npm start
```

Visit `http://127.0.0.1:3108/kart/` for a production preview. Only local development runs over HTTP; deploy public iPhone multiplayer over HTTPS/WSS.

> If testing from another device on your LAN, Vite listens on all interfaces, but the local WebSocket proxy needs a compatible Host/Origin. For a real phone test, deploy behind HTTPS or use a secure development tunnel.

## Controls

| Action | Desktop | iPhone/iPad |
|---|---|---|
| Accelerate | W or ↑ | GO |
| Steer | A/D or ←/→ | ◀ / ▶ |
| Brake / reverse | S or ↓ | BRAKE |
| Drift / charge turbo | SPACE + steer | Hold DRIFT while steering |
| Use power-up | SHIFT | ⚡ |
| Camera | E | Camera icon |
| Sound | M | Music icon |
| Leave race | ESC | EXIT RACE |

Landscape orientation offers the best iPhone/iPad driving layout. You can add the site to the iPhone Home Screen in Safari using Share → Add to Home Screen.

## Gameplay notes

- Collect a glowing item diamond while your power-up slot is empty.
- Boost provides acceleration, pulse strikes a nearby rival, shield absorbs a hit, and oil creates a hazard behind you.
- Drifting while turning charges a bonus turbo released when you straighten up.
- Each race is 3 laps; after the first racer finishes, everyone has 24 more seconds to finish.
- Rooms currently live in server memory and disappear when the last connected person leaves. There is no persistent public matchmaking, tournament account system, or ranking database in this version.

## Production deployment

Read **`DEPLOY_FOR_CLAUDE.md`** for Linode and Claude instructions. The only external runtime dependencies are the audited npm ecosystem libraries declared in `package.json`; no Nintendo copyrighted media is included. Review the package list and security rules before making a public game broadly accessible.

## Testing and limitations

Shared simulation/physics tests: `npm test`. After a production build and starting the server, run `npm run smoke` to test the health endpoint and two WebSocket clients. `npm run build` validates browser bundling. Manual Safari, Android Chrome and desktop testing is still strongly recommended before launch.

The initial package was authored without direct access to your Linode portal or browser/device fleet. Dependencies could not be installed in the packaging environment because npm registry DNS was unavailable; source syntax and physics tests were checked, but the final Vite build and live multiplayer smoke test must be run after installation on the server. This is a solid playable v1 implementation, not a promise of AAA-level physics, graphics, security hardening, fault tolerance or uninterrupted performance.

## Directories

- `src/main.js` — responsive HUD, menus, controls, client prediction, race UI.
- `src/game/world.js` — 3D tracks, lights, terrain and scenery.
- `src/game/karts.js` — procedural racer and kart geometry.
- `src/game/audio.js` — original synthesized effects.
- `src/shared/` — circuits and deterministic game mechanics.
- `server/index.js` — standalone Node HTTP/WebSocket multiplayer host.
- `deploy/` — Nginx/systemd and real multiplayer smoke test.

## Art and licensing

All source-created game worlds, racer designs, and sounds are original to this project. The runtime uses Three.js (MIT) and ws (MIT); development uses Vite and concurrently. CSS optionally loads Google Fonts (`Barlow Condensed` and `DM Sans`) from their public service. To fully self-host, replace the Google Fonts CSS import with system fonts or locally licensed versions; no font files are included in this distribution.
