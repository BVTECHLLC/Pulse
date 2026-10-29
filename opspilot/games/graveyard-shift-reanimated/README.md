# ☠ GRAVEYARD SHIFT: REANIMATED

**A playable, original 3D browser horde-survival roguelite starter for the BVTech portal.**

Version `0.8.0-prototype` · built using assets supplied by the game owner · frontend only

## Get it running

```bash
# Node.js 20+ required
npm install
npm run dev
# Open http://localhost:5173/
```

**Production build under existing BVTech portal subdirectory:**

```bash
VITE_BASE_PATH=/graveyard-shift/ npm run build
# Contents of dist/ should be served at https://portal.bvtech.org/graveyard-shift/
```

Do not deploy this blindly to production. Back up the existing game and account database. The remaster is a standalone frontend prototype; the live portal's source was not provided. It does not update or reuse current user accounts yet.

## What's already playable

- Original 3D arena with 6 provided KayKit character models, low-poly enemy crowds, interactive pickups, cinematic lighting, a procedurally detailed ground, and a follow camera.
- 10 survivor **classes** built from 6 core character models, 8 colorway skins per class (**80 class/skin combinations**), unlocks linked to permanent account XP.
- 3 map themes, 14 automatic weapons, 12 passive perks, 8 weapon evolutions, up to 6 weapons and 6 passives per run.
- Scaling enemy waves, 3-minute boss spawns, boss chests, critical hits, knockback, healing, auto-fired attacks, a 12-minute victory condition, 3-card upgrade drafts, run-end stats.
- 4 add-on challenge mutators including Nightmare and Glass Cannon.
- Persistent local XP, coins, souls, permanent upgrade tree, best scores, achievements, and save export/import.
- Responsive desktop/mobile interface, WASD and arrow controls, touch joystick, pause, settings, minimal original synthesized audio cues.
- Content/consistency tests.

## Important prototype limitations

**Server persistence is not yet connected**: the supplied build persists locally with `localStorage` and exposes a read-only `/api/graveyard-shift/v1/me` integration probe. Claude Code should integrate with the existing Linode Linux server and existing identity system. Server must be authoritative over currency/XP and verify run submissions; **never blindly trust client-provided scores.**

This is an integrated first build, not a verified production release. A full end-to-end 3D browser test and production integration are still needed, followed by animations, effects, balancing, proper sound/music, accessibility, and stronger performance optimization. See `docs/CLAUDE_CODE_HANDOFF.md`.

The optional music slider is a placeholder for the future original soundtrack. Rendering effects toggles are UI preferences and not yet fully applied to the engine.

## Controls

| Input | Action |
| --- | --- |
| WASD / arrow keys | Move relative to camera |
| Mouse / touch | Use menus; movement touch joystick on mobile |
| 1, 2, 3 | Pick corresponding level-up |
| Q / E | Shadow Dash / Nightfall Burst (active skills, cooldowns) |
| Escape | Pause / resume |
| Auto-fire | Weapons shoot automatically at nearby enemies |
| Boss chest | Obtain coins/health or evolve a max-level weapon with its prerequisite passive |

## Project layout

```text
index.html
src/
  data.js          Content tables and balance numbers
  engine.js        Three.js scene, combat, wave AI, loot, camera
  main.js          Menus, HUD, events, interactions
  profile.js       Browser save and Linode API probe
  style.css        Full game UI styles
public/assets/models/     Curated subset of original uploaded CC0 asset packs
server-example/            Design/reference for Linode integration
scripts/                   Reserved for asset processing
stats/
docs/
  CLAUDE_CODE_HANDOFF.md   START HERE for Claude Code
  ASSET_PROVENANCE.md      Source and license notes
  GAME_DESIGN_BIBLE.md    Next-phase scope and detailed mechanics
  ADDON_SPEC.md           Data-only add-on safety spec
```

## Licensing

Code in this remaster is original, and you can modify and use it for your BVTech game. The included **asset models belong to their respective creators** and come from the user's uploads. Quaternius, KayKit, and Kenney CC0 licenses are preserved in each asset subdirectory. The Quaternius Bestiary QAL-licensed pack was intentionally not included to avoid redistributing that pack's raw assets. Retain embedded attribution/license files. No Vampire Survivors assets or source code are included.
