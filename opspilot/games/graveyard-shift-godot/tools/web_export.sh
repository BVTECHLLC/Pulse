#!/usr/bin/env bash
# Export Graveyard Shift to the web, cache-bust the pack, and publish it to the
# bind-mounted hosting dir (games/graveyard-3d) that the portal serves at
# /graveyard-shift.
#
# Usage:  GODOT=/path/to/Godot_v4.3-stable_linux.x86_64 bash tools/web_export.sh
#
# Why cache-bust: the engine wasm/js are identical template files across builds;
# only index.pck (our code + scenes) changes. Browsers and the CDN key on the
# URL, so without a version token a refresh can keep serving a stale pack. We
# point the loader at index.pck?v=<hash> so a new build always fetches fresh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # the Godot project dir
GODOT="${GODOT:-godot}"
cd "$HERE"

"$GODOT" --headless --path . --import
"$GODOT" --headless --path . --export-release "Web" build/index.html

HASH="$(md5sum build/index.pck | cut -c1-8)"
sed -i "s/\"executable\":\"index\"/\"executable\":\"index\",\"mainPack\":\"index.pck?v=$HASH\"/" build/index.html

DEST="$HERE/../graveyard-3d"
rm -rf "$DEST"
cp -r build "$DEST"
rm -f "$DEST"/*.import

echo "exported + cache-busted (v=$HASH) -> $DEST"
