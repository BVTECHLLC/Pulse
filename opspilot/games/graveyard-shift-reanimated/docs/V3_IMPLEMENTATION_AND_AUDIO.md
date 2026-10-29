# NIGHTFALL V3: implementation + audio handoff

**Built in this package:** `src/terrain.js`, `src/world-v3.js` (solid tree/rock/ruin geometry, ramps/perches), `src/v3-content.js` (new weapons, relic/chest data), updated `src/data.js`, `src/engine.js` (physics, perspective camera, chests, weapon styles, spells), `src/main.js` (UI/HUD/input/audio events), `src/audio.js` (audio mix throttling), and 24 OGG files under `public/assets/audio/`.

## Original sound design

Soundtracks: `nightfall_menu.ogg`, `nightfall_battle.ogg`, original 108 BPM minor-key loops. SFX: `ui_select`, `levelup`, `evolve`, `chest_spawn`, `chest_open`, `boss_warning`, `boss_defeat`, `blood_moon`, `hit`, `dash`, `spell`, `swing`, `bow`, `magic`, `flame`, `quake`, `pickup`, `altar`, `victory`, `defeat`, `jump`, `rush_end`. They were synthesized specifically for the game; no outside copyrighted audio samples were used. The supplied asset archives contained meshes/textures but no compatible music/SFX files.

The audio is isolated in a single reusable `GraveAudio` class, with per-event cooldowns, global voice budget and particularly strict weapon-attack throttling. Menu and battle audio are two separate looping tracks. Music starts only after user gesture; paused games suspend music. Music and SFX sliders map directly to the existing saved settings. Browser visibility and mobile audio behavior should be verified.

## World/gameplay notes

3D depth comes from a perspective camera and Y-axis terrain. Physical obstacles should match the meshes; collision tests ensure circles, walls, ramps, and perches work. Chest interaction via F is not automatic; rewards are part of the active run and enemy defeats. AI enemy batching and particle budgets must stay bounded. `npm test` contains terrain/combat catalog/audio checks.

## Remaining production tasks for Claude

1. Install deps/build and run automated + manual browser tests on Windows Chromium/Firefox, Safari and Android.
2. Improve animation rig retargeting for six original adventurer models, tune the world to retain 60 FPS on mid-range hardware, and create hit VFX based on recorded performance.
3. Develop secure, server-authoritative session-backed progression using the *existing* BVTech Linode auth system. The packaged HTTP contract and SQL schema are examples; inspect the live data model before migrating.
4. Verify external asset license/redistribution rights; provenance information is stored beside the assets. Full source FBX / OBJ archives are not embedded in the portable runtime package.
5. Implement staging release, rollback and monitoring before production cutover.

No remote deployment has occurred. The 24 automated logic tests do NOT establish visually verified browser playability. The user has final cutover authority.
