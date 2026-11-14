"""v1.152 BVTech Threat Map — a complete, self-contained page published to
bvtech.org/cyber-range/threat-map/ by the destination pipeline, wired to Pulse's
own /api/public-tools/threat-feed (real honeypot/404/edge telemetry, self-healing).

Replaces the old page whose external Cloudflare-Worker feed silently died and left
every counter at zero. This one is fed by infrastructure we control, so it can't
go dark the same way. The HTML lives beside this module as a data file so there is
no fragile inlining; publish() writes it verbatim AFTER the site-wide nav sweep,
so the page always ships pristine."""
from __future__ import annotations

from pathlib import Path

PATH = "cyber-range/threat-map/index.html"      # repo path on the bvtech.org site
URL = "https://bvtech.org/cyber-range/threat-map/"
WORLD_PATH = "cyber-range/world-110m.js"        # self-hosted D3 world geometry
_FILE = Path(__file__).parent / "static_pages" / "threat-map.html"
_WORLD = Path(__file__).parent / "static_pages" / "world-110m.js"


def html() -> str:
    return _FILE.read_text(encoding="utf-8")


def world_js() -> str:
    """The world-110m topojson, wrapped as window.__WORLD__ — served same-origin
    so the map's country geometry loads without a cross-origin fetch."""
    return _WORLD.read_text(encoding="utf-8")
