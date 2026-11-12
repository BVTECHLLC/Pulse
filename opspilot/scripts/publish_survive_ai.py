"""One-shot publisher for the hidden "Surviving the AI Apocalypse" easter-egg
page -> bvtech.org/survive-the-ai-apocalypse/.

Commits the single self-contained page to the bvtech.org repo (same GitLab/
Cloudflare-Pages pipeline the destination release uses) and purges its edge
cache, so it goes live immediately instead of waiting for the next full
destination sweep.

Run on the box (pipes the freshly-pulled file into the running api container,
so it works right away with no image rebuild):

    cd /opt/bvtech-portal/opspilot && git pull origin main && \
      docker compose exec -T api python - < scripts/publish_survive_ai.py
"""
import os
import sys

sys.path.insert(0, os.getcwd())
from app.core.db import SessionLocal                               # noqa: E402
from app.core.config import get_settings                          # noqa: E402
from app.services import destination, jp_site, cloudflare         # noqa: E402
from app.services import pages_survive_ai as sa                   # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        print("=" * 60)
        print("  BVTech hidden page publisher — Survive the AI Apocalypse")
        print("=" * 60)
        print("running APP_VERSION :", get_settings().APP_VERSION)
        cfg = jp_site.get_config(db, "bvtech")
        if not cfg.get("configured"):
            print("bvtech.org connected: False  <-- paste a GitLab token in "
                  "Settings, then rerun. Nothing published.")
            return 1
        print("bvtech.org connected: True")
        print("publishing to       :", sa.PATH)

        files = {sa.PATH: sa.html()}
        destination._commit(cfg, files,
                            "easter-egg: How to Survive the AI Apocalypse (hidden page)")
        try:
            cloudflare.purge_urls(db, "bvtech", [sa.URL])
        except Exception as e:  # noqa: BLE001 — cache will expire on its own
            print("  (cache purge note:", e, ")")
        print("-" * 60)
        print("PUBLISHED ✓")
        print("LIVE URL:", sa.URL)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
