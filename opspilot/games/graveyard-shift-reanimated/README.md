# Graveyard Shift: NIGHTFALL V3 — Sound & World Overhaul

An original browser-based 3D survival roguelite. Built with Three.js, JavaScript and Vite. **V3 prototype source, not an independently playtested release.** No deployment to your live portal has been performed.

## Play locally

```sh
npm install
npm run dev
```

Open the Vite URL printed in your terminal. Node 20+ required. To check source and game logic:

```sh
npm test
npm run build
```

**Controls:** WASD/arrows move, Space jump/climb, Q dash, E selected relic, F loot chest/activate altar, Escape pause. Weapons auto-fire. Graphics, sound, and music adjustable in Settings.

## V3 gameplay additions

- Perspective/height-aware 3D camera and solid collision volumes for trees, ruins, rocks, boulders and buildings. Platforms, ramps and climbable/jumpable rocks.
- 26 auto-firing weapons, 20 weapon evolution recipes, 12 active relic spells, 16 survivor classes, eight skin palettes (128 character/class/skin combinations) and 12 passive abilities.
- Dynamic treasure chests throughout runs, with rare drops, healing, cash, weapon upgrades and bonuses.
- Weapon-specific projectile shapes (crossbow bolts, discs, shards, fiery cones, homing spirits), AoE knockback, slows, bosses, timed blood moons and objectives.
- Optimized enemy batching, effects/projectile budgets and scalable graphics presets to help avoid the oversized spawn/freezing bug from V2.
- Two **original composed looping soundtracks** (menu and combat) plus 22 unique synthesized sound cues. The sound mixer throttles attacks to at most one cue per ~520 ms, limits simultaneous SFX voices to four, and supports separate volume sliders.
- Local save for XP, coins and progress. **Authenticated Linode sync is not included**; do not trust local saves for server-side rewards.

## Asset packs

The runtime uses optimized GLB / glTF exports from supplied KayKit, Fantasy Props, Universal Base Characters, Nature, sci-fi, adventurer and dungeon model packs. Extra models are imported into `public/assets/models/kaykit/`, `public/assets/models/fantasy/`, and `public/assets/library/universal/` for later placement; **the full asset library is not drawn in every scene** (that would cause long loads and FPS problems). Some supplied FBX-only Halloween content remains source-only pending conversion to web GLB. See `docs/ASSET_PROVENANCE.md` for licensing.

## Give this to Claude Code without any attachment-size limit

Best option: extract the full ZIP on **your Windows computer**, open a terminal in `graveyard-shift-reanimated`, then start `claude` there. Claude Code reads your working directory rather than relying on the ChatGPT/Claude message upload UI.

Alternatively transfer the extracted full folder to your **Linode staging directory** using the PowerShell / Bash scripts in `../transfer-tools/`, SSH to the Linode, `cd` to the folder and run `claude`. See `../transfer-tools/LINODE_STAGING_SETUP.md` for safe, reversible steps. **Do not overwrite `/var/www` or your existing user database until staging has been tested.**

## Important limits

Tests are static/logic tests; installing npm deps and interactive WebGL playtesting were not possible in the creation environment. Before deployment Claude should execute `npm install`, `npm test`, `npm run build`, then manual browser/WebGL performance tests on Desktop + mobile. No authentication backend is asserted to be working. All 3D assets used must be audited for permissions before public redistribution.
