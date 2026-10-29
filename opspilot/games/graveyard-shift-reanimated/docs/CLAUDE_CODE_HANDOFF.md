# CLAUDE CODE — MASTER REMASTER HANDOFF

## Your mission

You are the lead gameplay engineer, technical artist, and production integrator for **Graveyard Shift: Reanimated**. The owner wants a polished, original Vampire-Survivors-*style* 3D browser horde-survival game hosted at `https://portal.bvtech.org/graveyard-shift/`, with long-term persistence on their existing Linode Linux VPS and account login. You are receiving a **playable prototype**, not a blank prompt.

**FIRST: Inspect this repository, run the tests/build, launch it locally, and play the first 3 minutes.** Use the existing code and asset pipeline. Improve and preserve what works; do not throw away core gameplay or replace the project with a static mockup. Fix defects before adding broad new systems.

The former live site's canvas application could not be inspected through the crawler, and no original source or server credentials were supplied. Do not make assumptions about existing server folders, frameworks, databases, or auth providers. Inspect them with owner-provided authorized access. **Before any deployment, back up the current game and database; create a staging subdirectory and a rollback plan.**

## Current deliverables in this repository

- Vite + Three.js browser game, CSS-based game shell, 3D arena and models
- 10 classes / 6 distinct hero 3D source models / 8 palettes = 80 combinations
- 3 environments, 14 weapons, 12 passives, 8 evolutions, 4 challenge mutators
- Dynamic enemy waves, 3-minute bosses, 12-minute runs, level-up drafts and persistent local metaprogression
- 6 permanent stats, achievements, gameover summary, mobile virtual stick, two basic active abilities (Q dash / E burst)
- Curated CC0 asset subsets and retained licenses
- Simple automated content tests

## Phase 0 — Verify, benchmark, and fix bugs BEFORE shipping

1. Install dependencies, run `npm test`, `npm run build`, start game in Chromium/Firefox + mobile emulation. Check JS console and network. Confirm **all 3D files load** correctly from both `/` and `/graveyard-shift/` using `VITE_BASE_PATH`.
2. Verify 60 FPS on a midrange gaming laptop and stable 30 FPS on typical mobile; avoid expensive per-entity draw calls and new object allocations per frame. Use InstancedMesh or ECS/spatial grid for 200–500 enemies, pooled bullets/loot/effects.
3. Playtest character select, every class starting weapon, run combat, XP/level selection, weapon cap, health/death, boss chest/evolution, run results, permanent XP/coins, upgrades, unlocks, export/import, all 4 modes, and audio preference.
4. Confirm the Three.js camera/WASD alignment feels intuitive, mobile joystick doesn't interfere with menus, and no resources leak after 10 consecutive runs.
5. Repair and/or redesign any bugs or placeholder-feeling art **before** calling this ready. Add a Playwright E2E smoke test to run the game for 30–60 seconds with mocked time and deterministic RNG.
6. Enable currently prototype-only graphics settings, local SFX sliders, reduced-motion options; add proper animations on the rigged KayKit GLBs.

**Acceptance:** game loads fast on staging, plays without console exceptions, menus work, loot/upgrades genuinely affect play, game over persists legitimate local progress, no regressions when replayed.

## Phase 1 — Premium-feeling gameplay and presentation

- Design a distinct 'cyber-gothic graveyard' art direction: Victorian cemetery + haunted neon + restrained sci-fi horror; atmospheric fog, grave lights, color-coded threats, terrain decals, layered depth, no default primitive-looking heroes.
- Hero rigs: use animations and weapon attachment points: idle/run/attack/struck/death, pivot, squashing, particles, glow shader outlines. Ensure 3D actors are camera-visible at player scale.
- Enemy families: basic undead, skeleton pack, skitter swarms, ghost phases, charging brutes, bombers, leech, summoner, elite, bosses; each visibly telegraphs damage or ability. Implement loot tables by family, proper hit VFX/SFX, HP bars for elites.
- Physics: consistent collision volumes, spatial hashing, anti-stuck, knockback decay, reliable projectiles, fair invincibility frames, attack indicators, synergy/tuning.
- Camera: tight and stable isometric view, screen-safe margins, subtle zoom for bosses, optional shake and flash that honor accessibility preferences.
- Feedback: weapon trails, crit pulses, floating XP/coin numbers, colored drops, death bursts, transition screen, satisfying upgrade cards, a short original audio identity (no copyrighted soundtrack).
- Distinct map geometry: Haunted Cemetery (tombs, twisted trees), Forsaken Village (user's medieval meshes), Sector 13 (user's sci-fi kit), each with handcrafted landmarks, obstacles, enemy mix, waves, map-specific bosses, and color palette.
- Graphics settings: Low/Medium/High; pixel ratio, shadows, particles, culling and texture quality; lazy load per-map models to keep TTI good.

## Phase 2 — Expand and balance gameplay without fake content

### Survivors

- Deliver **at least 20 genuinely different classes**, not just renamed skins. Each needs unique passive, starting weapon, skill animation, and playstyle; six initial source meshes may be modified/recolored first. Unlocks are earned; add 3–5 real silhouette differences via attachments for each base model.
- Build **160+ equipable cosmetic looks** across colorways, armor mesh parts, hats, capes, trails, footprints and weapons. Preview in 3D, show locked/unlocked, save per class to DB. Ensure all cosmetics are earnable without purchases.
- Add a character mastery path (0–100 levels each) with cosmetic rewards and small sidegrade options; separate from global account level.

### Arsenal

- Expand from **14 to 30 real weapons**, **12 to 18 passives**, **8 to 20 evolutions**. Each weapon must be testable, produce visible attacks, have minimum six meaningful upgrades, and unique risk/reward. Limit to 6 weapons + 6 passives as a strategic constraint.
- Active skills: the prototype has generic `Q` dash / `E` burst; expand to distinct selectable skills (ward, blink, temporary overclock, sacrifice, crowd control), each with cooldowns and class identity. Keep keyboard `Q`/`E` plus touch icons.
- Level-up drafts: weighted rarity, reroll/banish/skip, persistent selection history, synergies, luck bonuses, full inventory UI, non-repeating options.
- Boss chests: 3D animated open, guaranteed evolution if recipe eligible, sensible reward if none, and informative recipe codex.
- Add summon archetypes, damage-over-time, status effects, freeze resist, life steal, shields, crits, chain logic, and boss immunity rules; centralize combat modifiers to prevent accidental multiplicative exploits.

### Game modes

- Classic 12-minute survival, Endless with difficulty scaling, 5-minute Rush, challenge dailies, Glass Cannon, Nightmare, Turbo, and a training room with no progression rewards.
- Maps: add procedural encounter variations with fixed readable landmarks; boss every three minutes; chest, elites, optional encounters, random side objectives and limited revive.
- Never copy names, sprites, portraits, music, or proprietary UI art from Vampire Survivors or other published games; genre mechanics are fine, use original expression.

## Phase 3 — Linode account integration: IMPORTANT

First inspect the existing identity system and database. Reuse existing login/session and cookie scope. DO NOT make a second password store, expose SSH keys, or copy secrets into browser code. Integrate using `docs` API contract below.

### Expected server behavior

- Authenticated read `GET /api/graveyard-shift/v1/me` returns server-held profile, cosmetics, character mastery, currencies, upgrade ranks, stats, entitlements, high scores.
- `POST /sessions` starts a run and issues server-generated short-lived run ID bound to user/version/seed/mutator; enforce rate limits and concurrent run policy.
- `POST /sessions/:id/events` optional bounded telemetry/checkpoints; validate elapsed times, activity and plausible max kills / drops.
- `POST /sessions/:id/finish` accepts user events/summary for evaluation, not direct balances. Recalculate payouts on server from validated run events/signed checkpoints or server-authoritative deterministic simulation, not from trusting self-reported JSON. Reject replayed/expired IDs, invalid builds, impossible scores.
- `POST /upgrades/:upgradeId` atomic currency decrement and rank increment in DB transaction, max 10; ensure concurrent double spend cannot happen.
- Cosmetic equip, unlock, daily quests, high scores, purchases (earned in-game currency only), map, and class selection are idempotent authenticated API calls.
- Profile migration from browser `localStorage`: show the player an explicit **review & import** option; enforce reasonableness checks and one-time migration. Never silently replace their current server account with local values.
- Anonymous mode is allowed as a guest, but show clear local-only indicator; never claim it is cloud-synced until server ACK.

### Infrastructure

- Linux Linode VPS behind existing HTTPS/Nginx. Reuse the existing Node app or existing stack; check compatibility first.
- PostgreSQL preferred for structured durability (use existing DB if appropriate); deploy through current service manager/systemd/containers as appropriate. No new public DB ports.
- HTTP-only + Secure + SameSite cookies, CSRF protection for state-changing cookie-auth routes, HTTPS, authorization on every endpoint, input schemas with max request sizes and limits, strict CORS same-origin. Session/seed signed server side, and replay protection.
- SQL migrations are additive and reversible, do not drop old game tables or change old user IDs. Daily backup with restore drill, migrations in staging first, logs without sensitive tokens.
- Static files under `/graveyard-shift/`, API under `/api/graveyard-shift/v1/` without reverse proxy path collisions. Add cache headers + fingerprinted bundles; no-cache HTML, history route fallback, security headers without breaking WebGL.
- Separate leaderboards for Classic vs each modifier; reject unvalidated runs from ranked leaderboards. Add leaderboard pagination and privacy settings (show alias, not email).

**Important:** Server-side account verification is essential: no client browser game can be tamper-proof by itself. Do not pretend client-side encryption, checksums, or hidden keys prevent cheats.

## Phase 4 — Long-term engagement and safety

- Account level + per-character mastery + achievements + equipment/cosmetic unlocks with a truthful progression UI. XP and currency survive death and logouts.
- Daily/weekly challenges, rotating map affixes, collection gallery, boss codex, milestone trophies, rare palettes, seasonal theme (avoid FOMO pressure and pay-to-win).
- Optional browser multiplayer later: co-op with capped parties, private room codes, reporting, rate limiting, account privacy, server-sided gameplay, and moderation if chat is ever added. No chat or multiplayer exists in this prototype.
- Age-inclusive mode: no text chat initially, no user uploads, optional reduced blood/gore, no real-money loot boxes, accessible controls and screen-reader descriptions for menus.

## Required code hygiene and deliverables

- Data-driven content registries and schema tests; avoid monolithic engine growth; separate simulation state, rendering, entity systems, input, and UI.
- Deterministic time advancement and fixed-step simulation to prevent different FPS changing damage or XP output.
- Add unit/visual/E2E tests, CI build, type checking (TypeScript recommended), error boundaries, structured logs, profiling report.
- `docs/DEPLOYMENT.md` with precise verified commands for *this* Linode instance only after actual inspection; include safe backup, staging, smoke test, upgrade, rollback.
- Maintain `docs/CHANGELOG.md` listing what's **actually implemented**, what is mocked, and known bugs. Don't claim production readiness based on code existing.
- Implement, test, show screenshots, and report measured results. Don't stop at planning or give the owner another prompt to run.

## Working style for Claude Code

Work incrementally with commits. Verify each phase via the browser. Prioritize actual playability, responsiveness, art coherence, performance, account security, and future maintainability. If asset licenses conflict, keep the game playable with CC0 alternatives and note the restriction. If you can't inspect production, keep all destructive operations disabled and produce a staging bundle and a deployment checklist.

**Definition of Done:** a returning user logs in, chooses a fully modeled survivor and skin, survives enjoyable 3D horde combat, collects XP/levels/evolutions, dies or wins, receives verified persistent XP/currency, buys a permanent upgrade, logs out and back in, and sees the exact same legitimate progression. Everything works on modern desktop and touch devices without breaking the existing portal.

## NIGHTFALL V3 ADDENDUM (latest; takes precedence over V2)
Read `docs/V3_IMPLEMENTATION_AND_AUDIO.md` and `START_HERE_CLAUDE.txt`. 3D terrain obstacles, chests and 26 weapons are already coded. Music + SFX are original OGG sound files under `public/assets/audio` and loaded with `src/audio.js`, not WebAudio oscillator beeps. Check runtime behavior. This is a prototype, not a certified deployed release.
