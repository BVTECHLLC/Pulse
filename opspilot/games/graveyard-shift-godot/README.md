# Graveyard Shift

An original **BVTech** third-person 3D action-RPG with Vampire-Survivors-style
waves. Built in **Godot 4.3 + GDScript**. Everything here is code-driven and
fully editable — open the folder in Godot and press play.

## Run / edit

1. Install **Godot 4.3** (standard, not .NET) — https://godotengine.org/download
2. Open Godot → **Import** → select this folder's `project.godot`.
3. Press **F5** (Play). First launch reimports the art (a few seconds).

The game also runs/validates headless for CI:

```bash
# compile + import (surfaces any GDScript parse errors)
godot --headless --path . --import

# quick runtime smoke (builds the scene, runs 150 frames, quits)
godot --headless --path . --quit-after 150

# render a screenshot under software GL (Xvfb + mesa llvmpipe)
LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -s "-screen 0 1280x720x24" \
  godot --path . --rendering-driver opengl3 -- --shot
# -> saves graveyard_shift_shot.png into the user data dir (path printed on quit)
```

## Controls

| Action | Key |
| --- | --- |
| Move | **W A S D** / arrow keys |
| Rotate camera | **Mouse** |
| Dodge (brief i-frames) | **Space** |
| Attack | **automatic** — your weapons fire on their own |

## How it plays

Vampire-survivors style: you only **move and dodge** — every weapon fires on its
own at nearby foes. Kill husks, they drop **soul-shard gems** that you vacuum up
for XP. On level-up, **pick one of three** perks: a new auto-weapon, an upgrade
to one you carry, or a passive boost. Survive until **dawn (7:00)** to win. Soul-
shards bank between runs for a small permanent head-start.

Weapons: **Silver Bolt** (homing-ish bolts), **Bone Spear** (piercing lance),
**Reaper Scythe** (sweeping ring), **Holy Nova** (big burst), **Chain Smite**
(lightning that leaps between foes), **Grave Aura** (constant damage field).

## Project layout

```
project.godot          # Godot 4.3 project (GL Compatibility renderer, 1280x720)
scenes/Main.tscn       # entry scene -> scripts/game.gd
scripts/
  game.gd              # world, camera rig, waves, gems, timer, win/lose, meta, FX
  player.gd            # movement + dodge, run stats, weapon list, XP/leveling
  weapons.gd           # Weapon class: the six auto-firing weapons + scaling
  projectile.gd        # generic physics-free projectile (bolts, spears)
  enemy.gd             # husk: chase, contact attack, take damage, die (animated)
  upgrades.gd          # level-up pick-a-perk: new weapons / upgrades / passives
  hud.gd               # timer, kills, level, weapons list, HP + XP bars
assets/forest/         # Kenney Mini-Forest (CC0): rigged archer, bow, trees, rocks
assets/pirate/         # Kenney Pirate Kit (CC0): barrels, crates, chests, tower...
```

## Roadmap

- [x] Milestone 1: playable slice — movement, animated enemies, follow camera,
      combat, damage numbers, particles, lighting, HUD, XP.
- [x] Moonlit graveyard atmosphere (ghost ship, crypt, tombstones, torches).
- [x] Milestone 2: true survivors loop — auto-firing weapons, XP gems, pick-a-perk
      level-ups (weapons + passives), survive-to-dawn timer, win/lose, dodge,
      persistent soul-shards. Web export + live hosting.
- [ ] Main menu: pick a class (Rogue / Warrior / Healer) + difficulty (3 levels).
- [ ] Deeper meta-progression: spend soul-shards to unlock weapons/perks/classes.
- [ ] Music + SFX.
- [ ] More weapons / active spells, more enemy types + bosses, more maps.
- [ ] Multiplayer (authoritative server) — later phase.

## Credits / license

Game code, lore, characters and mechanics are **original** © BVTech LLC.

3D art is **CC0** from [Kenney](https://kenney.nl):
Mini-Forest and Pirate Kit. See `assets/forest/License.txt` and
`assets/pirate/License.txt`. CC0 means no attribution is required, but we credit
Kenney gladly.
