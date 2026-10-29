# GRAVEYARD SHIFT: NIGHTFALL v0.9.1 — Gameplay-first handoff

## User-reported problem

User found huge monsters spawned and froze the game, and visuals/combat were unpolished. Fix the real performance bottlenecks first; do not make bigger monsters, particle storms or massive non-instanced horde scenes.

## Done in this code snapshot

- Fixed-scale Grave Titan, health balanced for first boss at 120s, then every 120s.
- Instanced enemy silhouettes via `src/enemy-batch.js`. Model data is decoupled from visible Three.js nodes.
- CPU/GPU safety limits via `src/balance.js`; frame rate adaptive enemy cap.
- 6 active relics selected in Add-ons; active E cooldown differs by relic. Q dash has shorter cooldown.
- 4 interactable altars (F keyboard/touch), healing, currency, temporary blessing.
- Blood Moon waves, streak-based XP combos, 3 kill contracts per run, extra rewards.
- 3 graphics quality profiles with actual draw budgets and pixel ratio limits.
- 13 passing syntax/data/balance tests; original v1 browser save schema still supported.
- New mature dark-fantasy CSS (`src/v2-polish.css`) and HUD signals.

## Mandatory immediate Claude tasks

1. **Install and execute:** `npm install`, `npm test`, `npm run build`, `npm run dev`; fix all runtime errors before touching live production. This environment could not install npm dependencies, so end-to-end browser verification is outstanding.
2. **Playtest:** early-game visibility, enemy behavior, relic selections, altar F interaction, first boss at 2:00, XP level-up, enemy cap after 6:00, run end, save reload. Test resize and mobile.
3. **GPU profile:** use browser Performance/Memory panel. Examine `enemy-batch.js` draw counts, CPU collision, tree model cost and WebGL context memory. Preserve capped effects. At 1080p target 50–60 FPS on mainstream laptops at Balanced; Low quality for weak GPUs.
4. **Art pass:** keep drawn enemy types distinctive, add compatible legal high-quality animation and attack timing for heroes, improve environment depth with modular tombs and foliage without raising batches dangerously. Prefer instanced glTF geometry and texture atlases. Do not simply spawn 300+ clones.
5. **Gameplay pass:** add enemy telegraph, distinct enemy attacks, meaningful boss attack phases (well signaled), damage readability, sound design, and more curated terrain. Preserve fun build synergies, 6 relics and permanent unlocks.
6. **Database integration:** preserve and reuse live authentication on the Linode server. The frontend guest save is local-only; server-side run rewards must be validated. No trusting arbitrary client XP, souls or coins. Back up, stage, verify migration and rollback before production.

## Safety and deployment

- **Do not overwrite** `/graveyard-shift/` before a working staging build and DB snapshot.
- `VITE_BASE_PATH=/graveyard-shift/ npm run build` builds the production subdirectory assets.
- Browser profile key remains `bvtech.graveyard-shift.reanimated.profile.v1`; retain it across versions.
- Avoid bundling unused source asset libraries or copyrighted Vampire Survivors media. Supplied third-party asset license files remain under `public/assets/models/*/LICENSE.txt`; inspect before repackaging.
- Feature limitations remain: real server-account XP not connected, original soundtrack not included, and fully authored AAA animations/audio/biomes require further production work.

## Important performance invariants

| Preset | Enemies | Projectiles | Pickups | FX | DPR | Trees |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Low | 95 | 65 | 70 | 24 | 1.0 | 8 |
| Balanced | 145 | 90 | 90 | 36 | 1.35 | 12 |
| High | 185 | 120 | 110 | 48 | 1.6 | 17 |

Note: tree and prop assets are user-supplied, and model sizes are normalized using bounding boxes. Avoid double scaling parent containers.
