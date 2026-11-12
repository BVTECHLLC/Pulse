"""Hidden easter-egg page — "How to Survive the AI Apocalypse" — a complete,
self-contained page published to bvtech.org/survive-the-ai-apocalypse/ by the
destination pipeline.

Funny on the outside, real cybersecurity on the inside (MFA, code words vs
deepfakes, 3-2-1 backups, patching). Deliberately NOT in the site nav or the
sitemap (noindex) — it's a secret page you reach only by direct link, just like
the threat map. The HTML lives beside this module as a data file; publish()
writes it verbatim AFTER the site-wide nav sweep, so it always ships pristine.
"""
from __future__ import annotations

from pathlib import Path

PATH = "survive-the-ai-apocalypse/index.html"      # repo path on the bvtech.org site
URL = "https://bvtech.org/survive-the-ai-apocalypse/"
_FILE = Path(__file__).parent / "static_pages" / "survive-ai.html"


def html() -> str:
    return _FILE.read_text(encoding="utf-8")
