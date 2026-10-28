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
| Move | **W A S D** |
| Look | **Mouse** |
| Jump | **Space** |
| Fire bow | **Hold Left Mouse** |
| Free cursor / re-capture | click in window |

## How it plays

Survive endless waves of **husks**. Each kill grants XP; every level auto-grants
an upgrade (more HP, faster fire, more damage) and every 8 kills raises the wave,
which spawns tougher, faster husks. (A pick-your-upgrade screen, classes, and
meta-progression are the next milestone — see below.)

## Project layout

```
project.godot          # Godot 4.3 project (GL Compatibility renderer, 1280x720)
scenes/Main.tscn       # entry scene -> scripts/game.gd
scripts/
  game.gd              # world build, waves, XP, damage numbers, death FX, HUD
  player.gd            # third-person archer: movement, camera, jump, bow, anims
  enemy.gd             # husk: chase, contact attack, take damage, die (animated)
  arrow.gd             # bow projectile (physics-free, distance hit)
  hud.gd               # health + XP bars, wave/kills/level, crosshair
assets/forest/         # Kenney Mini-Forest (CC0): rigged archer, bow, trees, rocks
assets/pirate/         # Kenney Pirate Kit (CC0): barrels, crates, chests, tower...
```

## Roadmap

- [x] Milestone 1: playable slice — third-person movement, animated enemies,
      follow camera, bow combat, damage numbers, particles, lighting, HUD, XP.
- [ ] Upgrade-choice screen (pick 1 of 3 on level-up).
- [ ] Classes: Rogue / Warrior / Healer, each with unique starting skill.
- [ ] Meta-progression: XP/currency carries across runs, unlock tree.
- [ ] Pause + settings menu, main menu, game-over screen.
- [ ] Music + SFX.
- [ ] More weapons / abilities.
- [ ] Web export + host online.
- [ ] Multiplayer (authoritative server) — later phase.

## Credits / license

Game code, lore, characters and mechanics are **original** © BVTech LLC.

3D art is **CC0** from [Kenney](https://kenney.nl):
Mini-Forest and Pirate Kit. See `assets/forest/License.txt` and
`assets/pirate/License.txt`. CC0 means no attribution is required, but we credit
Kenney gladly.
