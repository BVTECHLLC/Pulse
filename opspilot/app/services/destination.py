"""Publish the "BVTech as a destination" release to bvtech.org (v1.102):

  * /explore/                    — the Yahoo-style front page (pages_explore)
  * /academy/lightning-labs/     — free interactive labs (pages_labs)
  * /tools/<slug>/               — What's My IP, Speed Test, Is It Down, EV Savings
  * worker-tools/*.js            — the edge API behind all of the above
  * site-wide nav links          — Explore + Lightning Labs, added idempotently
  * tools index cards + sitemap  — so the new pages are found
  * 404 telemetry                — the 404 page reports misses to the Worker

Everything new ships in ONE GitLab commit (so a build never sees pages whose
Worker endpoints haven't landed), then the edge cache is purged. Idempotent and
self-healing: the daily repair re-runs it if any piece goes missing. Pages are
built inside the site's own chrome (head/nav/footer from an existing page), so
they match the site without us hand-writing its markup. Authored under Jordan
Polasek for SEO on his name.
"""
from __future__ import annotations

import html as _html
import re
from pathlib import Path

from sqlalchemy.orm import Session

from . import pages_explore, pages_labs, pages_tools, pages_game

AUTHOR = "Jordan Polasek"
ORG = "BVTech LLC"
SITE = "https://bvtech.org"

# Worker modules that power the new pages (published to worker-tools/ next to the
# existing tool files). Keyed by repo path -> local file in edge_tools/.
_EDGE_DIR = Path(__file__).with_name("edge_tools")
NEW_EDGE = {"worker-tools/feeds.js": "feeds.js",
            "worker-tools/explore.js": "explore.js",
            "worker-tools/netinfo.js": "netinfo.js",
            "worker-tools/labs.js": "labs.js",
            "worker-tools/daily.js": "daily.js",
            "worker-tools/answers.js": "answers.js"}

# Pages to publish: (repo_path, title, description, body, author). Folder-style
# URLs (…/index.html) to match the site's /tools/<slug>/ convention.
EXPLORE_PATH = "explore/index.html"
LABS_PATH = "academy/lightning-labs/index.html"
GAME_PATH = "graveyard-shift/index.html"


def _pages() -> list[dict]:
    out = [
        {"path": EXPLORE_PATH, "url": SITE + "/explore/",
         "title": pages_explore.TITLE, "desc": pages_explore.DESC,
         "body": pages_explore.body()},
        {"path": LABS_PATH, "url": SITE + "/academy/lightning-labs/",
         "title": pages_labs.TITLE, "desc": pages_labs.DESC, "body": pages_labs.body()},
        {"path": GAME_PATH, "url": SITE + "/graveyard-shift/",
         "title": pages_game.TITLE, "desc": pages_game.DESC, "body": pages_game.body()},
    ]
    for t in pages_tools.all_tools():
        out.append({"path": f"tools/{t['slug']}/index.html",
                    "url": f"{SITE}/tools/{t['slug']}/", "title": t["title"],
                    "desc": t["desc"], "body": t["body"]})
    return out


def _schema(p: dict) -> str:
    import json as _json
    data = {"@context": "https://schema.org", "@type": "WebPage", "name": p["title"].split("|")[0].strip(),
            "description": p["desc"], "url": p["url"],
            "author": {"@type": "Person", "name": AUTHOR, "url": SITE},
            "publisher": {"@type": "Organization", "name": ORG, "url": SITE}}
    return '<script type="application/ld+json">' + _json.dumps(data) + "</script>"


def build_page(chrome: str, p: dict) -> str:
    """Put a page body into the site chrome and fix head (title, desc, canonical,
    OG, one fresh schema block). Never touches nav/footer."""
    from . import content_studio
    h = chrome
    t = _html.escape(p["title"]); d = _html.escape(p["desc"], quote=True)
    h = re.sub(r"<title>.*?</title>", f"<title>{t}</title>", h, count=1, flags=re.S | re.I)
    h = re.sub(r'(<meta\s+name="description"\s+content=")[^"]*(")', lambda m: m.group(1) + d + m.group(2),
               h, count=1, flags=re.I)
    for prop, val in (("og:title", t), ("og:description", d), ("og:url", p["url"])):
        h = re.sub(rf'(<meta\s+property="{prop}"\s+content=")[^"]*(")', lambda m, v=val: m.group(1) + v + m.group(2),
                   h, count=1, flags=re.I)
    h = re.sub(r'(<link\s+rel="canonical"\s+href=")[^"]*(")', lambda m: m.group(1) + p["url"] + m.group(2),
               h, count=1, flags=re.I)
    # drop existing page-level ld+json blocks that describe the CLONED page, add ours
    h = re.sub(r'<script type="application/ld\+json">.*?</script>', "", h, flags=re.S)
    h = h.replace("</head>", _schema(p) + "\n</head>", 1)
    return content_studio._swap_main(h, p["body"])


# --------------------------------------------------------------------------- #
# Site-wide nav: add Explore + Lightning Labs. Additive and idempotent — a page
# only changes if it has the anchor AND lacks the new link, and nothing is ever
# removed. Pages whose nav we don't recognize are skipped, never corrupted.
# --------------------------------------------------------------------------- #
NAV_EDITS = [
    # (already-present marker, anchor to insert AFTER, html to insert)
    ('href="/explore/"', '<li><a href="/tools/">🧰 Free Tools (all)</a></li>',
     '\n<li><a href="/explore/">🧭 Explore</a></li>'),
    ('href="/academy/lightning-labs/"', '<li><a href="/academy/labs/">🧪 Hands-On Labs</a></li>',
     '\n<li><a href="/academy/lightning-labs/">⚡ Lightning Labs</a></li>'),
    ('portal.bvtech.org/answers', '<li><a href="/academy/">🎓 Academy Home</a></li>',
     '\n<li><a href="https://portal.bvtech.org/answers">💬 BVTech Answers</a></li>'),
    ('/graveyard-shift/', '<li><a href="/academy/">🎓 Academy Home</a></li>',
     '\n<li><a href="/graveyard-shift/">🧛 Graveyard Shift</a></li>'),
    ('portal.bvtech.org/arena', '<li><a href="/academy/">🎓 Academy Home</a></li>',
     '\n<li><a href="https://portal.bvtech.org/arena/">⚔️ Play Breach Protocol</a></li>'),
]


def apply_nav(h: str) -> tuple[str, bool]:
    changed = False
    for present, anchor, ins in NAV_EDITS:
        if present in h:
            continue                       # already has this link
        i = h.find(anchor)
        if i < 0:
            continue
        at = i + len(anchor)
        h = h[:at] + ins + h[at:]
        changed = True
    return h, changed


# Top-level nav: add an Explore item next to Blog (most visible). Tolerant: only
# where a top-level Blog link exists and Explore isn't already top-level.
# The top-level Explore link carries a small "NEW" badge so visitors notice it.
# Inline-styled so it looks right regardless of the page's own nav CSS.
_NEW_BADGE = ('<span style="display:inline-block;margin-left:5px;padding:1px 6px;border-radius:999px;'
              'background:linear-gradient(135deg,#EB6F24,#F5BE58);color:#0E0D2C;font-size:.6rem;'
              'font-weight:800;letter-spacing:.06em;vertical-align:middle">NEW</span>')
_TOP_EXPLORE = '<li><a href="/explore/">🧭 Explore' + _NEW_BADGE + '</a></li>'
_TOP_EXPLORE_OLD = '<li><a href="/explore/">Explore</a></li>'


def apply_top_nav(h: str) -> tuple[str, bool]:
    # Only skip if the badged TOP-LEVEL item already exists (the dropdown's
    # "🧭 Explore" link must not count, or the most-clickable spot never gets it).
    if _TOP_EXPLORE in h:
        return h, False
    if _TOP_EXPLORE_OLD in h:                      # migrate v1.102 plain link -> badged
        return h.replace(_TOP_EXPLORE_OLD, _TOP_EXPLORE, 1), True
    m = re.search(r'(<li[^>]*>\s*<a href="/blog/"[^>]*>\s*Blog\s*</a>\s*</li>)', h)
    if not m:
        return h, False
    return h[:m.end()] + "\n" + _TOP_EXPLORE + h[m.end():], True


def _tools_index_cards(index_html: str) -> tuple[str, bool]:
    """Add the four new tool cards + an Explore banner to the tools index,
    cloning its own card markup. Idempotent."""
    from . import jp_site
    h = index_html
    changed = False
    for t in pages_tools.all_tools():
        url = f"/tools/{t['slug']}/"
        if url in h:
            continue
        new, ok = jp_site.inject_post_into_listing(
            h, title=f"{t['icon']} {t['card_title']}", url=url, excerpt=t["card_excerpt"],
            date_str="", style="blog-file", file_dir="tools")
        if ok:
            h = new
            changed = True
    if "/explore/" not in h:
        banner = ('<div style="margin:22px auto;max-width:960px;padding:18px 22px;border-radius:14px;'
                  'border:1px solid rgba(245,190,88,.35);background:linear-gradient(135deg,'
                  'rgba(68,64,219,.16),rgba(235,111,36,.12))"><strong style="color:#fff">🧭 New: '
                  'Explore</strong> — the fun side of tech, curated daily by Jordan Polasek. '
                  'Tech, Tesla, space, AI &amp; good news, a NASA photo, rocket launches and a '
                  'daily game. <a href="/explore/" style="font-weight:800;color:#F5BE58">'
                  'Visit Explore →</a></div>')
        for rx in (r"</h1>", r"<main\b[^>]*>", r"</header>"):
            m = re.search(rx, h, re.I)
            if m:
                h = h[:m.end()] + banner + h[m.end():]
                changed = True
                break
    return h, changed


_404_PING = ('<script>/*pulse-404-ping*/(function(){try{fetch("/tools-api/notfound",{method:"POST",'
             'headers:{"Content-Type":"application/json"},body:JSON.stringify({path:location.pathname,'
             'ref:document.referrer||""})});}catch(e){}})();</script>')


def _wire_404(h: str) -> tuple[str, bool]:
    if "pulse-404-ping" in h or "</body>" not in h.lower():
        return h, False
    i = h.lower().rfind("</body>")
    return h[:i] + _404_PING + "\n" + h[i:], True


_SKIP_LINK = re.compile(r"^(#|mailto:|tel:|javascript:|data:|sms:|/cdn-cgi/|/tools-api/)", re.I)
_STATIC_OK = re.compile(r"\.(css|js|png|jpe?g|webp|gif|svg|ico|pdf|woff2?|ttf|xml|txt|json|mp4|webmanifest)$", re.I)


def _repo_index(cfg: dict) -> tuple[set, set]:
    """(all file paths, all directory paths) in the repo, for link resolution."""
    from . import jp_site
    out = []
    for page in range(1, 31):
        batch = jp_site._HTTP("GET", f"{jp_site._proj_url(cfg)}/repository/tree?recursive=true"
                              f"&per_page=100&page={page}&ref={cfg['branch']}", cfg["token"])
        out += batch or []
        if not batch or len(batch) < 100:
            break
    files = {t["path"] for t in out if t.get("type") == "blob"}
    dirs = {t["path"] for t in out if t.get("type") == "tree"}
    return files, dirs


def _exists(target: str, files: set, dirs: set) -> bool:
    t = target.strip("/")
    if t == "":
        return True                                  # site root
    if target.endswith("/"):
        return (t + "/index.html") in files or t in dirs
    last = t.rsplit("/", 1)[-1]
    if "." in last:
        return t in files
    # extensionless: a folder, a pretty page, or a .html file
    return (t + "/index.html") in files or (t + ".html") in files or t in dirs


def scan_links(db: Session, site: str = "bvtech", limit_pages: int = 400) -> dict:
    """Read-only broken-INTERNAL-link scan of the live repo, plus the real 404s
    visitors hit (telemetry). Reports what to fix; changes nothing."""
    from . import jp_site, secure_config
    cfg = jp_site.get_config(db, site)
    if not cfg["configured"]:
        return {"ok": False, "error": "not connected"}
    try:
        files, dirs = _repo_index(cfg)
        htmls = [p for p in files if p.endswith(".html") and not p.startswith("worker-tools/")]
        broken: dict = {}
        checked = 0
        for path in htmls[:limit_pages]:
            h = jp_site._fetch_file(cfg, path)
            if not h:
                continue
            checked += 1
            for m in re.finditer(r'(?:href|src)=["\']([^"\'>]+)["\']', h):
                raw = m.group(1).strip()
                if _SKIP_LINK.match(raw):
                    continue
                link = re.sub(r"^https?://(?:www\.)?bvtech\.org", "", raw, flags=re.I)
                if not link.startswith("/"):
                    continue                          # external or relative anchor
                link = link.split("#")[0].split("?")[0]
                if not link or _SKIP_LINK.match(link):
                    continue
                if not _exists(link, files, dirs):
                    broken.setdefault(link, []).append(path)
        # real-world 404s
        conn = secure_config.get_platform(db, "bvtech_404")
        hits = dict((conn.config if conn else {}).get("hits") or {})
        live404 = sorted(hits.items(), key=lambda kv: kv[1].get("count", 0), reverse=True)[:30]
        return {"ok": True, "pages_scanned": checked, "broken_internal": len(broken),
                "broken": {k: sorted(set(v))[:5] for k, v in sorted(
                    broken.items(), key=lambda kv: -len(kv[1]))[:40]},
                "live_404s": [{"path": k, "count": v.get("count"), "ref": v.get("ref", "")}
                              for k, v in live404]}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"ok": False, "error": str(e)[:300]}


def publish(db: Session) -> dict:
    """Ship the whole destination release to bvtech.org in one commit."""
    from . import cloudflare, content_studio, jp_site
    cfg = jp_site.get_config(db, "bvtech")
    if not cfg["configured"]:
        return {"ok": False, "error": "bvtech.org not connected"}
    try:
        ops = jp_site._repo_ops(cfg)
        chrome = ops["fetch"]("blog/index.html")
        if not chrome:
            return {"ok": False, "error": "no chrome page (blog/index.html)"}
        files: dict = {}
        # 1) worker modules (+ the re-exported worker entry from tools_page)
        from . import tools_page
        for repo_path, local in {**tools_page.EDGE_FILES, **NEW_EDGE}.items():
            files[repo_path] = (_EDGE_DIR / local).read_text()
        files[tools_page.JS_PATH] = tools_page.tool_js()
        # 2) new pages, built into the chrome
        pages = _pages()
        for p in pages:
            files[p["path"]] = build_page(chrome, p)
        # 3) wrangler wiring (idempotent) + .assetsignore for worker-tools/
        wname, wcontent, worker = tools_page.plan_worker(ops)
        if wcontent:
            files[wname] = wcontent
        ignore = ops["fetch"](".assetsignore")
        if ignore is not None and "worker-tools" not in ignore:
            files[".assetsignore"] = ignore.rstrip("\n") + "\nworker-tools/\n"
        # 4) tools index cards + banner
        ti = ops["fetch"]("tools/index.html")
        if ti:
            ni, ch = _tools_index_cards(ti)
            if ch:
                files["tools/index.html"] = ni
        # 5) 404 telemetry
        for p404 in ("404.html", "404/index.html"):
            pg = ops["fetch"](p404)
            if pg:
                np, ch = _wire_404(pg)
                if ch:
                    files[p404] = np
                break
        # 6) site-wide nav links (additive, idempotent) across every repo HTML
        nav_hits = _apply_nav_everywhere(cfg, files)
        # commit everything at once
        jp_site._commit_all = getattr(jp_site, "_commit_all", None)
        _commit(cfg, files, f"destination: Explore hub, Lightning Labs, {len(pages_tools.all_tools())} "
                f"new tools, edge API + nav/sitemap (via Pulse) [{nav_hits} nav pages]")
        # 7) sitemap
        extra = {p["url"]: None for p in pages}
        sm = jp_site.sitemap_sync(db, "bvtech", extra=extra)
        # 8) purge
        purge = [p["url"] for p in pages] + [SITE + "/", SITE + "/tools/", SITE + "/academy/"]
        cloudflare.purge_urls(db, "bvtech", purge)
        return {"ok": True, "pages": [p["url"] for p in pages], "nav_pages": nav_hits,
                "worker": worker, "sitemap": sm, "files": len(files)}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"ok": False, "error": str(e)[:300]}


def _apply_nav_everywhere(cfg: dict, files: dict) -> int:
    """Add the new nav links to every HTML page in the repo (additive). Pages we
    already rebuilt in `files` get edited in memory; the rest are fetched. Bounded
    and best-effort; a page we can't parse is left untouched."""
    from . import jp_site
    hits = 0
    paths = [p for p in jp_site._list_all_html(cfg) if not p.startswith("worker-tools/")]
    for path in paths[:600]:
        base = files.get(path)
        if base is None:
            base = jp_site._fetch_file(cfg, path)
        if not base or 'class="nav' not in base and "<nav" not in base and "/tools/" not in base:
            continue
        h, c1 = apply_nav(base)
        h, c2 = apply_top_nav(h)
        if c1 or c2:
            files[path] = h
            hits += 1
    return hits


def _commit(cfg: dict, files: dict, message: str) -> None:
    from . import jp_site
    if cfg.get("forge") == "github":
        for path, content in files.items():
            jp_site._repo_ops(cfg)["commit"](path, content, message,
                                             jp_site._fetch_file(cfg, path) is not None)
        return
    actions = [{"action": "update" if jp_site._fetch_file(cfg, p) is not None else "create",
                "file_path": p, "content": c} for p, c in files.items()]
    jp_site._HTTP("POST", f"{jp_site._proj_url(cfg)}/repository/commits", cfg["token"],
                  {"branch": cfg["branch"], "commit_message": message, "actions": actions})
