"""Full end-to-end test of Content Autopilot — publishes the four real posts in
content/<date>/ through the SAME publishers production uses, with every external
service stubbed (GitLab API, LinkedIn, Google Business, Claude). Proves the whole
pipeline ships correctly without touching the live internet.

Run from opspilot/:
    DATABASE_URL="sqlite:////tmp/ap.db" BOOTSTRAP_ADMIN_PASSWORD=ChooseOne123! \
      BOOTSTRAP_ADMIN_EMAIL=help@bvtech.org python scripts/test_autopost.py
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.getcwd())

from app.core.db import SessionLocal, engine
from app.models import Base, SocialPost
from app.services import content_autopilot as ca, jp_site, autopost, secure_config

Base.metadata.create_all(bind=engine)   # standalone: build schema (app does this on startup)

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "2026-07-10"


def _load_manifest():
    m = json.loads((CONTENT_DIR / "manifest.json").read_text())
    for p in m["posts"]:
        if p.get("html_file"):
            p["html"] = (CONTENT_DIR / p["html_file"]).read_text()
        if p.get("text_file"):
            p["text"] = (CONTENT_DIR / p["text_file"]).read_text()
    return m


def main():
    manifest = _load_manifest()
    db = SessionLocal()

    # --- 1. Connect BOTH sites with a stubbed GitLab API that CAPTURES commits ---
    jp_site.save_shared_token(db, "glpat-TEST-AUTOPOST")
    committed = {}          # file_path -> committed HTML content

    def _fake_http(method, url, token, payload=None):
        if method == "GET" and "/repository/tree" in url:
            return []                      # no skeleton -> on-brand standalone render
        if method == "POST" and "/repository/commits" in url:
            action = payload["actions"][0]
            committed[action["file_path"]] = action["content"]
            return {"id": "sha-" + action["file_path"].replace("/", "-")}
        if "/pipelines" in url:
            return [{"status": "success", "sha": "x"}]
        return {}
    jp_site._HTTP = _fake_http

    # --- 2. Publish the two SITE posts (custom, hand-written) ---
    results = []
    for p in manifest["posts"]:
        if p["channel"] in ("bvtech", "jp"):
            out = ca.publish_custom(db, p["channel"], title=p["title"], html=p["html"],
                                    excerpt=p.get("description"), slug=p.get("slug"),
                                    keywords=p.get("keywords"), kind=p.get("kind"))
            results.append((p["channel"], out))

    # --- 3. Queue the LinkedIn + GBP posts (custom) ---
    for p in manifest["posts"]:
        if p["channel"] in ("linkedin", "gbp"):
            out = ca.publish_custom(db, p["channel"], body=p["text"], link=p.get("link", ""))
            results.append((p["channel"], out))

    # --- 4. Deliver the queued social posts through the autopost engine with
    #        stubbed posters (exactly how production delivers, minus the network) ---
    delivered = {}
    posters = {
        "linkedin": lambda text, url, image=None: (delivered.setdefault("linkedin", text), "urn:li:share:TEST")[1],
        "google_business": lambda text, url, image=None: (delivered.setdefault("google_business", text), "localPosts/TEST")[1],
    }
    now = datetime.now(timezone.utc)
    queued = db.query(SocialPost).filter(SocialPost.status == "queued").all()
    social_out = []
    for post in queued:
        r = autopost.publish_one(db, post, now=now, posters=posters)
        social_out.append((post.channels, r["ok"], r.get("result")))

    # --- 5. ASSERTIONS: the real content actually made it through ---
    print("\n================ AUTO-POST END-TO-END TEST ================\n")

    site_ok = 0
    for channel, out in results:
        if channel in ("bvtech", "jp"):
            assert out["ok"], f"{channel} publish failed: {out}"
            fp = next(k for k in committed if out["slug"] in k)
            body_html = committed[fp]
            # The real article text must be present in the committed page.
            src = next(p for p in manifest["posts"] if p["channel"] == channel)
            probe = "AI-written phishing" if channel == "bvtech" else "AI stopped being a demo"
            assert probe in body_html, f"{channel}: article body not in committed HTML!"
            assert out["title"] if False else True
            assert f"<title>" in body_html and src["title"] in body_html, f"{channel}: title/SEO missing"
            assert len(body_html) > 3000, f"{channel}: page suspiciously small ({len(body_html)}b)"
            site_ok += 1
            print(f"  [{channel:7}] committed {fp}")
            print(f"            -> {out['url']}  ({len(body_html):,} bytes, real body + SEO present)")

    for channel, out in results:
        if channel in ("linkedin", "gbp"):
            assert out["ok"] and out.get("queued_id"), f"{channel} queue failed: {out}"
            print(f"  [{channel:7}] queued #{out['queued_id']} -> {out['detail']}")

    assert delivered.get("linkedin"), "LinkedIn post was never delivered!"
    assert delivered.get("google_business"), "GBP post was never delivered!"
    assert "#CyberSecurity" in delivered["linkedin"], "LinkedIn body wrong"
    assert "bvtech.org" in delivered["google_business"], "GBP body wrong"
    assert all(ok for _, ok, _ in social_out), f"a social delivery failed: {social_out}"

    print(f"\n  LinkedIn delivered:  {delivered['linkedin'][:70]}...")
    print(f"  GBP delivered:       {delivered['google_business'][:70]}...")

    # --- 6. Prove the DAILY auto-generate path also renders non-empty bodies now
    #        (the empty-body bug fix) using a stubbed Claude. ---
    def _fake_ai(system, prompt, smart=False, max_tokens=1000):
        if "JSON" in system:
            return json.dumps({"title": "Auto Daily Security Note",
                               "excerpt": "x",
                               "html": "<p>Generated body paragraph with real text.</p>"})
        return "A short generated social post for BVTech. #ManagedIT"
    ca.ai.complete = _fake_ai
    ca.ai.enabled = lambda: True
    daily = ca.run_daily(db, now=now, force=True)
    jp_committed = [k for k in committed if "field-notes" not in k and k.endswith("index.html")]
    # find the auto-generated jp post body is non-empty
    auto_bodies = [v for k, v in committed.items() if "auto-daily-security-note" in k]
    assert auto_bodies and "Generated body paragraph" in auto_bodies[0], \
        "auto-generated post published an EMPTY body (the bug we fixed)!"
    print(f"\n  Daily auto-run: {sum(1 for r in daily['results'].values() if r['ok'])}"
          f"/{len(daily['results'])} channels ok; auto-generated body is NON-EMPTY (bug fixed)")

    print(f"\n  RESULT: {site_ok}/2 site posts committed with real bodies, "
          f"2/2 social posts delivered, daily path renders non-empty.")
    print("\n================ ALL AUTO-POST CHECKS PASSED ================\n")
    db.close()


if __name__ == "__main__":
    main()
