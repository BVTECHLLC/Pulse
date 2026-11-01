# VOLT RUSH V3 DELUXE — asset rights and provenance

**All original game models, art, textures, 2D character portraits, and track illustrations are generated specifically for this VOLT RUSH project.** No art, likenesses, sound recordings, music, models, files or other material from Nintendo, Mario Kart, or third-party game packs is bundled.

The asset construction files are included and reproducible:

- `tools/generate_original_art.py` creates **12 original GLB models** (six desktop + six mobile), **12 road surface WebP textures** (6 themes × 2 resolutions), **6 original pilot portraits**, and an original track accent texture atlas.
- `tools/generate_track_cards.py` creates **6 original track illustrations**.
- `src/game/hero-assets.js` loads the GLB meshes, safely reuses geometry, and recolors each player's kart paint.
- `src/game/world.js` creates the 3D racetracks, props, pickup sculptures, signage, spectators, lighting and other procedural scenery.
- `src/game/fx.js` and `src/game/audio.js` create effects and all audio procedurally using Three.js and Web Audio; no music recordings or sound packs are included.

**Font information:** PNG/WebP track-card letters are rasterized from the locally installed DejaVu Sans Bold font, a permissively licensed Bitstream Vera derivative; used only as rendered text, not redistributed as a font file. The existing UI requests Barlow Condensed and DM Sans through Google Fonts, distributed under the SIL Open Font License; external font loading is not required for gameplay because system fallbacks are present. All game art is original, and these fonts are explicitly permitted for commercial use.

**Non-art runtime dependencies:** Three.js (MIT), ws (MIT), Vite (MIT) and dependencies under their respective package licenses. No third-party asset models used. Check npm installed LICENSE files after installation.

Asset generation uses Pillow, NumPy and trimesh as **development-time** tools only. They are not loaded by the game browser and are not needed to deploy already generated assets. No font files are bundled.
