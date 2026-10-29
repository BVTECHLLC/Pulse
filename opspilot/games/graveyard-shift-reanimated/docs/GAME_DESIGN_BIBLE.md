# Graveyard Shift: Reanimated — Game Design Bible

## Identity

**Genre:** isometric 3D auto-combat survival roguelite, with optional active tactical abilities. **Theme:** cyber-gothic horror at the boundary of supernatural curses and malfunctioning technology. **Tagline:** "Survive the night. Own the dawn." **Platform:** browser, desktop-first with mobile touch support. **Session:** 12 minutes in Classic. No copyrighted Vampire Survivors characters, visual assets, music, or proprietary code.

## Fantasy and moment-to-moment loop

Choose a survivor and cosmetic set → choose location + optional challenge modifier → enter a wave-based horde arena → kite enemies and position carefully → auto-attack and dodge threats → collect crystalline XP → choose 1 of 3 weapons/passives on level up → assemble combinations to evolve weapons → survive bosses at 3/6/9 minutes → reach dawn or die → permanently bank earned account XP, coins, and souls → unlock cosmetics, characters, harder maps and account upgrades → replay with different builds.

**The game should feel great within 30 seconds.** An interesting enemy should appear within 5 seconds, the first level-up by ~40 seconds, an elite by ~90 seconds, and the first boss at 3 minutes. These timings need playtesting; adjust XP/drop rates rather than simply cutting content.

## Character identity

| Survivor | Role | Weapon | Permanent talent |
|---|---|---|---|
| The Warden | durable all-rounder | Bone Blades | -12% incoming damage |
| Hex Weaver | magic burst | Ember Wand | +12% XP/spell damage |
| Night Ranger | rapid-fire precision | Grave Scattergun | -15% attack cooldown |
| The Shade | fast assassin | Void Lance | +15% movement speed |
| Gravedigger | high-HP cleaver | Spectral Scythe | +25% maximum HP |
| Plague Doctor | AoE/DOT scientist | Plague Spores | +18% area/poison damage |
| Ghost Protocol | tech summoner | Sentry Drone | +15% projectile speed |
| Dawnbringer | sustain + radiant AoE | Solar Nova | +0.35 health/sec |
| The Reaper | soul farmer | Reaper Halo | +15% souls |
| Stormcaller | chain DPS | Arc Coil | +1 chained target |

**Implementation status:** All 10 are selectable with unique starting weapons; some listed talents are still represented approximately and need trait-by-trait validation. Six distinct KayKit meshes are repurposed across ten classes, not ten different sculpted character models.

## Player progression

**In a run:** XP gems collected → local run level → 3-way draft (up to six weapons and six passives) → max-level weapon + specified passive + boss chest = evolved weapon. Combat stats and upgrades reset when run ends.

**Across runs:** permanent account XP, account level, earnable coins, souls (reserved for future cosmetic/crafting system), purchased permanent upgrades, achievements, unlocked classes and skins, best scores. All must move to Linode after auth integration. Cosmetic purchases must not offer competitive advantages.

**Meta currency split:** Coins: permanent stat upgrades, rerolls, future cosmetics. Souls: character-specific mastery, occult cosmetics, future recipes. Soul-spending systems not implemented yet: design carefully so they have a real purpose.

**Meta upgrade price curve:** base × (current_rank+1)^1.6; max rank 10, no pay-to-win. Balance after telemetry.

## Enemy readability

Enemy "silhouette language": gray walkers = slow pressure; teal skitters = fast low HP; red brutes = slow tank; violet ghosts = phasing; yellow/green infected = DOT; orange hollows = rushing attackers. Boss should be unmissable with name, HP bar, arrival sting, attack telegraph and worthwhile loot. The prototype currently uses colored primitive-based enemy meshes and optional Quaternius drone; replacing common-enemy shapes with strong 3D silhouettes and animation is a major polish task.

## Recommended encounter schedule

| Clock | Event |
|---|---|
| 0:00 | Spawn basic walker pairs; reveal basic controls |
| 0:40 | Skitter pack; encourage first level-up |
| 1:30 | First elite and health/coin pickup |
| 3:00 | Boss 1: Bell Warden; chest reward |
| 4:30 | New archetype and density surge |
| 6:00 | Boss 2: Plague Vessel; chest reward |
| 7:30 | Map modifier or side objective |
| 9:00 | Boss 3: Rift Keeper; chest reward |
| 10:30 | Blood moon, density spike, rising music |
| 12:00 | Dawn victory, results and persistent progression |

The initial engine has a 3-minute boss interval and 12-minute victory, but not individual authored bosses or final dramatic cues yet.

## Weapon family and effect quality

- **Projectile:** Bone Blades, Ember Wand, Void Lance, Blood Pact (homing, pierce, debuff, lifesteal).
- **Ranged cone:** Grave Scattergun (spread, lots of sparks, directional reward).
- **Orbit:** Reaper Halo (persistent visible orbiters; upgrade count and radius).
- **Area pulse:** Scythe, Plague Spores, Solar Nova, Frozen Heart.
- **Chain:** Arc Coil (visible lightning lines between targets).
- **Summon/traps:** Sentry Drone, Raven Swarm, Soul Mines.

Fix mathematical damage consistency, add real DOT ticks for poison, visual chain paths, persistent drone entities and better weapon silhouettes in future polishing. The prototype approximates some special mechanics (e.g., "Sentry Drone" fires as homing projectiles rather than a persistent 3D pet).

## Cosmetic system future shape

Eight palette skins for each of ten classes now. Expand to helmet, body, gloves, weapon glow, trail, companion, victory pose and aura slots with inspectable preview. Add lore collection and mastery unlocks, not endless randomly generated color names. Build a curated set of 160+ meaningful looks with original mesh variation, not just multiplying palette counts in marketing.

## Retention without pressure

- Discoverable synergies and evolution codex, not overwhelming menus.
- Achievements and character mastery offer clear optional goals.
- 3–12 minute runs fit casual play; 20+ minute Endless is optional.
- Daily challenges and map affixes rotate without locking paid content.
- Persistent XP and currency are a reward, not a grind substitute for fun.
- All earnable cosmetic, no gambling, no dark patterns or required daily login.

## Accessibility + account safety

No player-generated chat in initial game. If introduced, add server moderation and reporting. Reduced motion, color-blind mode, readable HP, scalable HUD, remappable keyboard/gamepad controls, optional reduced effects, touch access. All saves need atomic server persistence; no client can grant itself banked XP, leaderboards, or cosmetics by editing localStorage.
