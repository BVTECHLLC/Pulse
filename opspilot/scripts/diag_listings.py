"""Read-only diagnosis: why are jp/txplants/bvtech blog listings frozen?
Fetches each live listing page via the GitLab API (same token the publisher
uses) and reports, per page: is the newest repo post listed? does the
DETERMINISTIC injector recognize the card markup? does the AI/free-LLM
fallback? Plus a dump of the first post-card markup so the structure is visible.
Nothing is written to any repo."""
from app.core.db import SessionLocal
from app.services import jp_site as J
from app.services import ai as A
import re

print("=== ENGINES ===")
print("ai.enabled (Anthropic key present):", A.enabled())
print("free_llm_enabled (Groq etc.):     ", A.free_llm_enabled())
try:
    from app.core.config import get_settings
    print("FREE_LLM_ONLY:", get_settings().FREE_LLM_ONLY)
except Exception as e:
    print("settings:", e)

db = SessionLocal()
TEST = {"title": "Diagnostic Probe Post", "excerpt": "Probe excerpt for injection test.",
        "date": "October 19, 2026"}

for site in ("jp", "txplants", "bvtech"):
    print("\n" + "=" * 70)
    print("SITE:", site)
    cfg = J.get_config(db, site)
    if not cfg.get("configured"):
        print("  NOT CONFIGURED:", cfg.get("error") or cfg)
        continue
    meta = J.SITES[site]
    style = cfg["style"]
    fdir = cfg.get("file_dir", "blog")
    link_pat = J._link_pat_for(style, fdir)
    print("  style=%s file_dir=%s" % (style, fdir))
    print("  link_pat=%s" % link_pat)
    # newest post in the repo
    try:
        paths = J._list_post_paths(cfg, style)[:5]
    except Exception as e:
        paths = []
        print("  _list_post_paths error:", e)
    print("  newest repo post paths:", paths[:3])
    newest_slug = J._slug_of(paths[0]) if paths else None
    newest_url = J._post_url_for(meta, paths[0], style) if paths else "https://x/probe-post"
    rel = newest_url.replace(meta["site"], "") if paths else "/probe-post/"
    print("  newest_slug=%s  rel=%s" % (newest_slug, rel))

    for lp in meta.get("index_paths", ()):
        print("  --- listing page: %s ---" % lp)
        h = J._fetch_file(cfg, lp)
        if h is None:
            print("     (page not found in repo)")
            continue
        print("     length=%d bytes" % len(h))
        if newest_slug:
            print("     newest post already listed? ", J._slug_listed(h, newest_slug))
        # count recognizable cards deterministically
        spans = J._all_card_spans(h, link_pat)
        print("     deterministic card spans found: %d" % len(spans))
        # try a deterministic-only injection of the newest post
        _, det = J.inject_post_into_listing(h, title=TEST["title"], url=rel,
                                             excerpt=TEST["excerpt"], date_str=TEST["date"],
                                             style=style, file_dir=fdir)
        print("     deterministic inject changed? ", det)
        # does ANY link matching the post pattern appear at all?
        ms = list(re.finditer(link_pat, h))
        print("     raw link_pat matches on page: %d" % len(ms))
        if ms:
            first = ms[0]
            frag = h[max(0, first.start() - 400): first.start() + 500]
            print("     >>> markup around FIRST matching link:")
            print("     " + frag.replace("\n", "\n     "))
        else:
            # no link matched the pattern — show the first <a href> in the body
            am = re.search(r'<a\b[^>]*href="[^"]*"', h[h.find("<body"):] if "<body" in h else h)
            print("     NO link matched link_pat. First <a href> in body:",
                  am.group(0) if am else "(none)")
            # show first heading region to reveal card structure
            hm = re.search(r"<h[1-3]\b", h)
            if hm:
                frag = h[max(0, hm.start() - 300): hm.start() + 600]
                print("     >>> markup around first heading:")
                print("     " + frag.replace("\n", "\n     "))

db.close()
print("\n=== END DIAGNOSTIC ===")
