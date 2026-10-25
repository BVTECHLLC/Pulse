# SIGNAL 199X — v3.0 / THE POLYGON FREQUENCY

An original family-friendly-leaning (currently **13+ only**) browser multiplayer retro-tech RPG. Real-time shared overworld, 3D low-poly WebGL2 renderer with **automatic 2D fallback**, persistent accounts and equipment, co-op adventures, server-side loot, cozy housing, friendly opt-in PvP, and arcade diversions. Art and story are original: **no EarthBound, Pokémon, Warcraft, or other games' characters/maps/audio were copied.**

> **Release status: PLAYABLE ALPHA.** This is a substantial prototype and source-code base, not a production-certified public MMO and not a recreation of the feature depth or graphics of a commercial title. Three.js is not needed; the WebGL2 scene is built with included original code. The 3D renderer has static-code checks but **was not verified in the restricted browser environment** (headless Chromium would not grant WebGL2, and navigation was blocked). Always run through a real browser before publishing.

## FASTEST START

Requires Node.js **22.13+** (Node 24 recommended for a deployment), current Chrome/Edge/Firefox, and a computer with WebGL2 for 3D. No `npm install` and no remote CDN needed.

- Windows: extract ZIP, run `START-WINDOWS.bat`.
- Linux/macOS: run `sh START-LINUX-MAC.sh`.
- Visit `http://localhost:3000`, confirm you are at least 13, create a character or select unsaved guest mode.
- For friends: deploy the same Node service behind HTTPS/WSS using the included `deploy/` scripts. Do **not** expose HTTP or WebSockets publicly without TLS.

**Controls:** WASD/arrow keys = move; left mouse drag on world = orbit 3D camera; mouse wheel = zoom; Space = attack; F = Echo Burst; R = Heartwave team heal; E = interact; H = healing drink; I = bag; M = map; O = settings; 1–4 = friendly emotes; Q = field guide. Mobile touch controls remain available. Set Graphics Mode = 2D in Settings for low-end devices.

## PLAYABLE CONTENT

**Shared world:** Six connected districts (Pinebell, Moonberry Grove, Soda Shore, Neon Boardwalk, Spark Yard, Cassette Commons). Other logged-in players in the same overworld share one server-side map and receive positional updates, not separate per-user world copies. Separate private party instances exist for dungeons and solo survival only. The reference site's enormous open world isn't reproduced; the six regions are a cohesive small world. Simultaneous connections are capped at 80 by the current WebSocket implementation; load-test and scale before advertising a larger server.

**Activities:**

1. Lost Mixtape story: tune any 3 of 6 radio towers. No mandatory fighting.
2. Main-world enemies, Hushling boss, loot tiers, one-time treasure chests, 3 character classes and gear upgrades.
3. Three private co-op Rift dungeons (solo or up to 4-person party), each with themed challenge, enemies and boss rewards.
4. Static Storm: a **private 90-second survival game**, with automatically triggered attacks, wave spawning, server-scored kills, one capped reward per day, and best score stored in SQLite.
5. Circuit Sprint: 2–4 teammates follow 3 real map checkpoints in order; server validates proximity and order. Hourly reward cooldown.
6. Signal Relay: 2–4 teammates split up across 3 far-flung radio towers to complete a cooperative objective in 7 minutes. Hourly reward cooldown.
7. Duo Rhythm Jam: join a second player at the Boardwalk jukebox within 9 seconds; server verifies location and participation. Capped rewards.
8. Co-op Broadcast Beacon: synchronized team activity, with server-enforced proximity and cooldowns.
9. Memory Jam and Pixel Fishing: interactive sequence-memory minigames, prizes capped per day. **Limitation:** sequences must be delivered to the browser, so a modified client can automate solving them; they should not become a high-value competitive economy until redesigned with cheat-resistant gameplay.
10. Friendly opt-in PvP in a marked arena, normalized damage, no player-loot loss.
11. Four purchasable house plots; persistent cosmetic color and furniture configurations (the interior preview remains a UI panel; not yet a walk-in 3D interior).
12. Buy and equip five purely cosmetic companions (Bot-01, Byte Frog, Cassette Cat, Hologram Moth, Moon Snail). Cosmetic companions grant zero PvP/combat advantage.
13. Leaderboards, party invitations, quick chat, block and report tools, game rules, privacy and terms pages.

## WHAT CHANGED IN v3

- Truly 3D client view, not fake perspective: WebGL2 shaders, depth-tested 3D geometry, atmospheric distance fog, lit low-poly houses, natural trees, lamps, neon arcade cabinets, radio towers, treasure chests, creatures, NPCs and characters. Stylized original title illustration optimized as `public/media/signal-world-cover.webp`.
- 3D camera rotation, zoom, local graphics options, visual day/night grading, name tags, fullscreen, 2D fallback, separate sound effect toggle and master volume.
- Solo Static Storm survival mode, co-op Signal Relay, timed party Circuit Sprint, rhythm-duo activity, five cosmetic pets, extra collectibles and more visual region landmarks.
- Server-side SQLite columns for personal survival best and activity reward cooldowns; no client-provided score, gold, XP, wave, or position is accepted.
- Existing v2 accounts and items remain compatible because migrations are additive. **Back up `data/game.sqlite*` files before upgrading v2; use a maintenance window.**

## QUICK TESTS

`npm test` runs the Node integration tests. The test harness boots a temporary server and checks account handling, authoritative movement, persistence, co-op party/rift isolation, moderation, housing, survival scoreboard and two-player jam verification. The WebGL2 visual output **must** additionally be inspected manually on your own Chrome/Firefox GPU environment; the restricted build environment rejected WebGL2 contexts and page navigation.

## SECURITY AND PUBLIC HOSTING

Read `OPERATOR.md`, `SAFETY.md`, `deploy/nginx.conf`, `deploy/signal199x.service`, and `deploy/backup.sh` **before** going public. The app defaults to listen on `127.0.0.1:3000`; proxy over Nginx HTTPS, disable public ports 3000, set environment/permissions, rotate secret material, have human moderation, and review child protection and privacy obligations. Age 13+ checkbox is self-attestation, not age verification. Quick chat is on; free-text chat is disabled by default. No payment processor or purchases in v3.

Game can run at `game.bvtech.org`; **it is NOT integrated** with `portal.bvtech.org` account identities. Reusing the portal's login would need a properly designed, server-side SSO/auth integration (not shared passwords or browser local-storage tokens).

## FILES

- `server.mjs` authoritative game server / SQLite / HTTP / WebSockets / rewards.
- `world.mjs` world, creatures, loot tables and spawns.
- `survival.mjs`, `dungeons.mjs` instanced challenge generators.
- `moderation.mjs` quick chat, usernames, optional filtering.
- `public/engine3d.js` original WebGL2 3D renderer without external dependencies.
- `public/game.js`, `public/index.html`, `public/style.css` client HUD, actions, UI and 2D fallback.
- `LICENSE-ASSETS.md` asset provenance and verified optional CC0 libraries.
- `tests/smoke.mjs` integration test suite.

## IMPORTANT LIMITATIONS

No in-game freeform co-creation, cross-server shards, guild economy, item trading, voice chat, global auction, walk-in houses, 3D character animations/rigs, procedural multilevel buildings, or fully automatic public moderation. The game's 3D assets are procedural low-poly rather than photorealistic. Multiplayer is a **single-process** game server, not a horizontally scalable MMO backend. These are appropriate next engineering milestones, not advertised as completed.
