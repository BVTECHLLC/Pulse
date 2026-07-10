"""v1.20/v1.21 GitLab site publisher — bvtech.org AND jordanpolasek.com, verified.

Both sites are static sites in private GitLab repos, deployed by Cloudflare on
push (NEITHER is WordPress). This service publishes to both and watches the
deploy:

  1. publish(post, site) — clone the newest post's HTML as a skeleton (the
     site's real header/footer/CSS carry over), transplant the new content, and
     commit via the GitLab API. Layouts differ per site:
        bvtech.org         -> blog/<slug>.html        (blog-file)
        jordanpolasek.com  -> <slug>/index.html       (slug-folder)
  2. verify_pending(site) — heartbeat: check the GitLab pipeline (Cloudflare
     Workers Builds reports there) for each commit we pushed; a FAILED build is
     auto-REVERTED (site stays on the last good deploy) + the operator notified.

ZERO-TOUCH TOKEN: the GitLab token resolves through a chain, so the credential
that already lives on the box keeps working with no re-entry:
  site's vault config -> shared vault provider "gitlab" -> env (GITLAB_TOKEN /
  BV_GL_TOKEN) -> /etc/bvtech/publisher.env -> /etc/bvtech/agent.env (JSON,
  same aliases the old cron used). Values are never logged.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Notification
from . import secure_config

DEFAULT_BASE = "https://gitlab.com"

SITES = {
    "jp": {"provider": "jp_site", "name": "JordanPolasek.com Site",
           "default_project": "BVTECHLLC-group/jordanpolasek-website",
           "style": "slug-folder", "site": "https://jordanpolasek.com",
           "org": "Jordan Polasek", "author_url": "https://jordanpolasek.com",
           "content_classes": ("content",),
           # Listing pages that must show the new post (homepage "Writing" +
           # the /blog/ index). Without updating these, a published post is live
           # at its URL but invisible in the site's navigation.
           "index_paths": ("index.html", "blog/index.html")},
    "bvtech": {"provider": "bvtech_site", "name": "BVTech.org Site",
               "default_project": "bvtechllc-group/bvtech-website-new",
               "style": "blog-file", "site": "https://bvtech.org",
               "org": "BVTech LLC", "author_url": "https://bvtech.org",
               "content_classes": None,
               "index_paths": ("blog/index.html", "index.html")},
}

# Alias list matching the old cron's lib_env.sh — the token that already exists
# on the box under any of these names just works.
_TOKEN_ALIASES = ("gitlab_token", "bv_gl_token", "gl_token", "gitlab_deploy_token",
                  "deploy_token", "deploy_token_value", "gitlab_pat")
_BOX_FILES = ("/etc/bvtech/publisher.env", "/etc/bvtech/agent.env")


def _http(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method,
                                 headers={"PRIVATE-TOKEN": token,
                                          "Content-Type": "application/json"})
    data = json.dumps(payload).encode() if payload is not None else None
    with urllib.request.urlopen(req, data=data, timeout=30) as r:
        body = r.read().decode()
    return json.loads(body) if body else {}


# Tests override this to script GitLab responses offline.
_HTTP = _http


def _token_from_box_files() -> str | None:
    """Read the token the old cron used, straight off the box (never logged)."""
    for path in _BOX_FILES:
        try:
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8-sig") as fh:
                raw = fh.read()
            try:      # agent.env is JSON
                d = json.loads(raw)
                low = {str(k).lower(): v for k, v in d.items()
                       if isinstance(v, (str, int, float))}
                for a in _TOKEN_ALIASES:
                    v = str(low.get(a) or "").strip()
                    if v:
                        return v
            except ValueError:   # publisher.env is KEY=VALUE shell
                for line in raw.splitlines():
                    m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)\s*$", line)
                    if not m:
                        continue
                    k, v = m.group(1).lower(), m.group(2).strip().strip("'\"")
                    if k in _TOKEN_ALIASES or k in ("bv_gl_token",):
                        if v:
                            return v
        except Exception:  # noqa: BLE001
            continue
    return None


def _resolve_token(db: Session, cfg_token: str | None) -> str | None:
    if cfg_token:
        return cfg_token
    shared = secure_config.get_platform(db, "gitlab")
    scfg = (shared.config if shared else None) or {}
    tok = secure_config.get_secret(scfg, "token")
    if tok:
        return tok
    for env_key in ("GITLAB_TOKEN", "BV_GL_TOKEN"):
        if os.environ.get(env_key, "").strip():
            return os.environ[env_key].strip()
    return _token_from_box_files()


def verify_token(db: Session) -> dict:
    """Live check: does the resolved GitLab token actually authenticate AND can
    it see both site repos? Returns {ok, detail}. This is what makes the tile's
    green/red mean 'the key works', not just 'a string is stored'."""
    cfg = get_config(db, "jp")
    token = cfg["token"]
    if not token:
        return {"ok": False, "detail": "No GitLab token stored yet."}
    try:
        me = _HTTP("GET", f"{cfg['base']}/api/v4/user", token)
        who = me.get("username") or me.get("name") or "user"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "401" in msg:
            return {"ok": False, "detail": "Token rejected (401) - expired or revoked. Generate a new one (scope: api)."}
        if "403" in msg:
            return {"ok": False, "detail": "Token lacks scope (403) - it needs the 'api' scope."}
        return {"ok": False, "detail": f"Could not reach GitLab: {msg[:120]}"}
    seen = []
    for site in ("bvtech", "jp"):
        sc = get_config(db, site)
        import urllib.parse as _u
        try:
            _HTTP("GET", f"{sc['base']}/api/v4/projects/{_u.quote_plus(sc['project'])}", token)
            seen.append(sc["project"])
        except Exception as e:  # noqa: BLE001
            m = str(e)
            hint = "not found or no access" if ("404" in m or "403" in m) else m[:80]
            return {"ok": False,
                    "detail": f"Authenticated as {who}, but can't reach {sc['project']} ({hint})."}
    return {"ok": True, "detail": f"Verified as {who} - can publish to {' + '.join(seen)}."}


def get_config(db: Session, site: str = "jp") -> dict:
    meta = SITES[site]
    conn = secure_config.get_platform(db, meta["provider"])
    cfg = (conn.config if conn else None) or {}
    token = _resolve_token(db, secure_config.get_secret(cfg, "token"))
    project = cfg.get("project") or meta["default_project"]
    return {
        "base": (cfg.get("base") or DEFAULT_BASE).rstrip("/"),
        "project": project,
        "branch": cfg.get("branch") or "main",
        "token": token,
        "pending": cfg.get("pending") or [],
        "configured": bool(project and token),
        "style": meta["style"], "site": meta["site"], "org": meta["org"],
    }


def save_config(db: Session, *, site: str = "jp", project: str | None = None,
                token: str | None = None, branch: str | None = None,
                base: str | None = None) -> dict:
    meta = SITES[site]
    conn = secure_config.get_platform(db, meta["provider"])
    cfg = dict((conn.config if conn else None) or {})
    if project is not None:
        cfg["project"] = project.strip()
    if token:
        cfg["token"] = token.strip()          # is_secret_key -> encrypted at rest
    if branch is not None:
        cfg["branch"] = branch.strip() or "main"
    if base is not None:
        cfg["base"] = base.strip() or DEFAULT_BASE
    secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing", cfg)
    out = get_config(db, site)
    return {"configured": out["configured"], "project": out["project"], "branch": out["branch"]}


def save_shared_token(db: Session, token: str) -> dict:
    """One paste connects BOTH sites: store the token on the shared 'gitlab'
    provider that every site's resolution chain consults."""
    secure_config.upsert_platform(db, "gitlab", "GitLab", "Publishing",
                                  {"token": token.strip()})
    return {"jp": configured(db, "jp"), "bvtech": configured(db, "bvtech")}


def configured(db: Session, site: str = "jp") -> bool:
    return get_config(db, site)["configured"]


def _proj_url(cfg: dict) -> str:
    return f"{cfg['base']}/api/v4/projects/{urllib.parse.quote_plus(cfg['project'])}"


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "post").lower()).strip("-")
    return s[:70] or "post"


def _fetch_file(cfg: dict, path: str) -> str | None:
    """Return a repo file's text (decoded) or None if it doesn't exist."""
    import base64
    try:
        f = _HTTP("GET", f"{_proj_url(cfg)}/repository/files/"
                  f"{urllib.parse.quote_plus(path)}?ref={cfg['branch']}", cfg["token"])
        return base64.b64decode(f["content"]).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — 404 (no such file) or transient
        return None


def inject_post_into_listing(listing_html: str, *, title: str, url: str,
                             excerpt: str, date_str: str, style: str) -> tuple[str, bool]:
    """Clone the newest post card in a listing page and insert a fresh card for
    `url` at the top of the posts grid. Returns (new_html, changed). Never raises;
    returns (listing_html, False) when the listing already has the post or its
    card structure isn't recognized (so a weird page is left untouched, not
    corrupted — the build-verify + auto-revert is the final safety net)."""
    import html as _html
    h = listing_html
    if f'href="{url}"' in h:                       # already listed (re-publish)
        return h, False
    link_pat = (r'href="[^"]*blog/[a-z0-9\-]+\.html"' if style == "blog-file"
                else r'href="/[a-z0-9\-]{6,}/"')
    # Prefer the standard posts grid (leaves any 'featured' card alone).
    grid = re.search(r'<div[^>]*class="[^"]*\bposts\b[^"]*"[^>]*>', h)
    art_re = re.compile(r'<article\b[^>]*>.*?</article>', re.S | re.I)
    template = None
    if grid:
        for m in art_re.finditer(h, grid.end()):
            if re.search(link_pat, m.group(0)):
                template = m
                break
    if not template:
        for m in art_re.finditer(h):
            if re.search(link_pat, m.group(0)):
                template = m
                break
    if not template:
        return h, False
    card = template.group(0)
    card = re.sub(link_pat, f'href="{url}"', card)                   # post links -> new url
    card = re.sub(r'(<h[1-3][^>]*>\s*<a[^>]*>)(.*?)(</a>)',          # heading -> new title
                  lambda m: m.group(1) + _html.escape(title) + m.group(3),
                  card, count=1, flags=re.S)
    if re.search(r'class="excerpt"', card):                          # excerpt -> new excerpt
        card = re.sub(r'(<p[^>]*class="excerpt"[^>]*>)(.*?)(</p>)',
                      lambda m: m.group(1) + _html.escape(excerpt) + m.group(3),
                      card, count=1, flags=re.S)
    card = re.sub(r'(<span[^>]*>)([A-Z][a-z]+ \d{1,2}, \d{4})(</span>)',  # date -> today
                  lambda m: m.group(1) + date_str + m.group(3), card, count=1)
    pos = grid.end() if (grid and grid.end() <= template.start()) else template.start()
    return h[:pos] + "\n" + card + "\n" + h[pos:], True


def _newest_skeleton(cfg: dict, style: str) -> str | None:
    """Fetch the most recent post's HTML to clone header/footer/CSS from."""
    import base64
    if style == "blog-file":
        tree = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?path=blog&ref={cfg['branch']}&per_page=100",
                     cfg["token"])
        files = sorted([t["path"] for t in tree if t.get("type") == "blob"
                        and t["path"].endswith(".html")], reverse=True)
        for path in files[:5]:
            try:
                f = _HTTP("GET", f"{_proj_url(cfg)}/repository/files/"
                          f"{urllib.parse.quote_plus(path)}?ref={cfg['branch']}", cfg["token"])
                return base64.b64decode(f["content"]).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                continue
        return None
    tree = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?ref={cfg['branch']}&per_page=100",
                 cfg["token"])
    dirs = [t["path"] for t in tree if t.get("type") == "tree"
            and not t["path"].startswith((".", "_", "assets", "static", "css", "js", "img"))]
    for d in sorted(dirs, reverse=True):
        try:
            f = _HTTP("GET", f"{_proj_url(cfg)}/repository/files/"
                      f"{urllib.parse.quote_plus(d + '/index.html')}?ref={cfg['branch']}",
                      cfg["token"])
            return base64.b64decode(f["content"]).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
    return None


def publish(db: Session, post: dict, site: str = "jp") -> dict:
    """Commit the rendered post to the site repo. Returns {ok, sha, url, slug}."""
    meta = SITES[site]
    cfg = get_config(db, site)
    if not cfg["configured"]:
        return {"ok": False, "error": f"{meta['site']} not connected (GitLab token needed)"}
    slug = post.get("slug") or _slugify(post.get("title") or "")
    file_path = (f"blog/{slug}.html" if cfg["style"] == "blog-file"
                 else f"{slug}/index.html")
    public_url = (f"{meta['site']}/blog/{slug}.html" if cfg["style"] == "blog-file"
                  else f"{meta['site']}/{slug}/")
    try:
        skeleton = _newest_skeleton(cfg, cfg["style"])
        from . import content_studio
        rendered = content_studio.render(
            {**post, "slug": slug, "site": meta["site"], "org": meta["org"],
             "author_url": meta["author_url"]},
            skeleton_html=skeleton, content_classes=meta["content_classes"])
        actions = [{"action": "create", "file_path": file_path, "content": rendered}]

        # Add the post to the site's listing pages IN THE SAME COMMIT so it shows
        # up in navigation, not just at its own URL. Best-effort per file: an
        # unrecognized/absent listing is skipped (and reported), never corrupted.
        excerpt = (post.get("description") or content_studio._excerpt_from_html(rendered))[:220]
        date_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")
        listings_updated, listings_skipped = [], []
        for lp in meta.get("index_paths", ()):
            current = _fetch_file(cfg, lp)
            if current is None:
                continue                              # no such listing on this site
            new_html, changed = inject_post_into_listing(
                current, title=post.get("title", slug), url=public_url,
                excerpt=excerpt, date_str=date_str, style=cfg["style"])
            if changed:
                actions.append({"action": "update", "file_path": lp, "content": new_html})
                listings_updated.append(lp)
            else:
                listings_skipped.append(lp)

        commit = _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": f"blog: {post.get('title', slug)[:80]} (via Pulse)",
            "actions": actions,
        })
        sha = commit.get("id")
        conn = secure_config.get_platform(db, meta["provider"])
        raw = dict((conn.config if conn else None) or {})
        pending = list(raw.get("pending") or [])
        pending.append({"sha": sha, "slug": slug,
                        "at": datetime.now(timezone.utc).isoformat(), "checks": 0})
        raw["pending"] = pending[-10:]
        secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing", raw)
        # Purge Cloudflare's edge cache for everything this commit changed so the
        # new post + updated listings are visible IMMEDIATELY (best-effort; a
        # missing token never blocks the publish).
        from . import cloudflare
        purge = cloudflare.purge_urls(db, site, [public_url]
                                      + [f"{meta['site']}/{lp}".replace("/index.html", "/")
                                         for lp in listings_updated])
        return {"ok": True, "sha": sha, "slug": slug, "url": public_url,
                "listings_updated": listings_updated, "listings_skipped": listings_skipped,
                "cache_purged": purge.get("ok"), "cache_detail": purge.get("detail")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


def _list_post_paths(cfg: dict, style: str) -> list[str]:
    """All post files in the repo for this site's layout, newest-ish first."""
    if style == "blog-file":
        tree = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?path=blog&ref={cfg['branch']}&per_page=100",
                     cfg["token"])
        return sorted([t["path"] for t in tree if t.get("type") == "blob"
                       and t["path"].endswith(".html")
                       and not t["path"].endswith("index.html")], reverse=True)
    tree = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?ref={cfg['branch']}&per_page=100",
                 cfg["token"])
    dirs = [t["path"] for t in tree if t.get("type") == "tree"
            and not t["path"].startswith((".", "_", "assets", "static", "css", "js",
                                          "img", "images", "fonts", "blog", "book",
                                          "cdn-cgi", "functions"))]
    return [f"{d}/index.html" for d in sorted(dirs, reverse=True)]


def _post_meta_from_html(page_html: str) -> tuple[str, str]:
    """Pull (title, excerpt) out of a published post page."""
    import html as _h
    t = re.search(r"<title>(.*?)</title>", page_html, re.S)
    title = _h.unescape((t.group(1) if t else "").split("|")[0].strip()) or "Untitled"
    d = re.search(r'<meta\s+name="description"\s+content="(.*?)"', page_html, re.S)
    excerpt = _h.unescape(d.group(1).strip()) if d else ""
    return title[:180], excerpt[:220]


def _post_url_for(meta: dict, path: str, style: str) -> str:
    if style == "blog-file":
        return f"{meta['site']}/{path}"
    return f"{meta['site']}/{path.removesuffix('index.html')}"


def sync_listings(db: Session, site: str, *, limit: int = 15) -> dict:
    """BACKFILL: find published posts that exist in the repo but are missing
    from the blog listing pages (the pre-v1.28 'orphaned post' situation) and
    inject them — one commit per site, then purge the Cloudflare cache. Safe to
    run any time: already-listed posts are untouched, and an unrecognized
    listing is skipped, never corrupted."""
    meta = SITES[site]
    cfg = get_config(db, site)
    if not cfg["configured"]:
        return {"ok": False, "error": f"{meta['site']} not connected (GitLab token needed)"}
    try:
        post_paths = _list_post_paths(cfg, cfg["style"])[:60]
        listings = {lp: _fetch_file(cfg, lp) for lp in meta.get("index_paths", ())}
        listings = {lp: h for lp, h in listings.items() if h is not None}
        if not listings:
            return {"ok": False, "error": "no listing pages found in the repo"}
        date_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")
        added, actions, purge_urls = [], [], []
        for path in post_paths:
            url = _post_url_for(meta, path, cfg["style"])
            rel = url.replace(meta["site"], "")            # href form used in listings
            missing = [lp for lp, h in listings.items()
                       if rel not in h and url not in h]
            if not missing:
                continue
            page = _fetch_file(cfg, path)
            if not page:
                continue
            title, excerpt = _post_meta_from_html(page)
            for lp in missing:
                new_html, changed = inject_post_into_listing(
                    listings[lp], title=title, url=rel, excerpt=excerpt,
                    date_str=date_str, style=cfg["style"])
                if changed:
                    listings[lp] = new_html
            added.append({"path": path, "title": title, "url": url})
            purge_urls.append(url)
            if len(added) >= limit:
                break
        changed_files = []
        for lp, h in listings.items():
            orig = _fetch_file(cfg, lp)
            if orig is not None and h != orig:
                actions.append({"action": "update", "file_path": lp, "content": h})
                changed_files.append(lp)
                purge_urls.append(f"{meta['site']}/{lp}".replace("/index.html", "/"))
        if not actions:
            return {"ok": True, "added": [], "detail": "listings already complete - nothing to sync"}
        commit = _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": f"blog: sync listings - add {len(added)} missing post(s) (via Pulse)",
            "actions": actions,
        })
        from . import cloudflare
        purge = cloudflare.purge_urls(db, site, purge_urls)
        return {"ok": True, "sha": commit.get("id"), "added": added,
                "listings_updated": changed_files,
                "cache_purged": purge.get("ok"), "cache_detail": purge.get("detail")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


def diagnose(db: Session, site: str) -> dict:
    """Publishing Doctor for one site: walk the WHOLE chain and say exactly
    what's healthy and what to fix, in plain English. Read-only."""
    meta = SITES[site]
    cfg = get_config(db, site)
    checks: list[dict] = []

    def _check(name: str, ok: bool, detail: str, fix: str | None = None):
        checks.append({"name": name, "ok": ok, "detail": detail,
                       **({"fix": fix} if (fix and not ok) else {})})

    _check("GitLab token", bool(cfg["token"]),
           "token found" if cfg["token"] else "no token anywhere in the chain",
           "Connection Center -> Websites -> paste a GitLab token (scope: api)")
    if not cfg["token"]:
        return {"site": meta["site"], "checks": checks, "healthy": False}
    try:
        proj = _HTTP("GET", _proj_url(cfg), cfg["token"])
        _check("Repo access", True, f"{proj.get('path_with_namespace') or cfg['project']} reachable")
    except Exception as e:  # noqa: BLE001
        m = str(e)
        _check("Repo access", False,
               "token rejected (401)" if "401" in m else f"can't reach {cfg['project']}: {m[:80]}",
               "regenerate the token with `api` scope / check the project path")
        return {"site": meta["site"], "checks": checks, "healthy": False}
    # Listing pages present + structure our injector understands.
    recognized, missing_posts = [], []
    listings = {}
    for lp in meta.get("index_paths", ()):
        h = _fetch_file(cfg, lp)
        if h is None:
            _check(f"Listing {lp}", False, "file not found in repo",
                   "expected the blog index here - check the repo layout")
            continue
        listings[lp] = h
        _probe, changed = inject_post_into_listing(
            h, title="probe", url="/pulse-doctor-probe/", excerpt="probe",
            date_str="January 1, 2026", style=cfg["style"])
        _check(f"Listing {lp}", changed,
               "structure recognized - new posts will be inserted" if changed
               else "card structure NOT recognized - new posts won't appear here",
               "the listing markup changed; publishing still works but listings need a template tweak")
        if changed:
            recognized.append(lp)
    # Orphaned posts (in repo, absent from every listing).
    try:
        for path in _list_post_paths(cfg, cfg["style"])[:60]:
            url = _post_url_for(meta, path, cfg["style"])
            rel = url.replace(meta["site"], "")
            if listings and all(rel not in h and url not in h for h in listings.values()):
                missing_posts.append(url)
        _check("Orphaned posts", not missing_posts,
               "every published post is in the listings" if not missing_posts
               else f"{len(missing_posts)} post(s) live but NOT listed: "
                    + ", ".join(missing_posts[:3]) + ("..." if len(missing_posts) > 3 else ""),
               "click 'Sync listings' to backfill them in one commit")
    except Exception as e:  # noqa: BLE001
        _check("Orphaned posts", False, f"scan failed: {str(e)[:80]}")
    # Deploy pipeline health for the last commit we pushed.
    pend = cfg.get("pending") or []
    if pend:
        try:
            pipes = _HTTP("GET", f"{_proj_url(cfg)}/pipelines?sha={pend[-1]['sha']}", cfg["token"])
            st = (pipes[0].get("status") if pipes else "none") or "none"
            _check("Cloudflare build", st in ("success", "running", "pending", "created"),
                   f"last publish pipeline: {st}",
                   "the deploy failed - Pulse auto-reverted; re-publish after fixing")
        except Exception:  # noqa: BLE001
            _check("Cloudflare build", True, "no pipeline info (deploy may not report to GitLab)")
    from . import cloudflare
    cf = cloudflare.verify(db) if cloudflare.configured(db) else {
        "ok": False, "detail": "not connected - cached pages update on their own TTL (can look stale for hours)"}
    _check("Cloudflare cache purge", cf["ok"], cf["detail"],
           "Connection Center -> Cloudflare -> paste an API token (Zone:Read + Cache Purge)")
    healthy = all(c["ok"] for c in checks if not c["name"].startswith("Cloudflare cache"))
    return {"site": meta["site"], "checks": checks, "healthy": healthy}


MAX_CHECKS = 20   # ~40 min of heartbeat ticks before we stop waiting


def verify_pending(db: Session, now: datetime | None = None,
                   site: str | None = None) -> list[dict]:
    """Heartbeat: check the deploy pipeline for pending commits on one site (or
    all). FAILED pipeline (the Cloudflare build) -> auto-REVERT + notification."""
    sites = [site] if site else list(SITES)
    results = []
    for sk in sites:
        meta = SITES[sk]
        cfg = get_config(db, sk)
        if not cfg["configured"] or not cfg["pending"]:
            continue
        keep = []
        for p in cfg["pending"]:
            try:
                pipes = _HTTP("GET", f"{_proj_url(cfg)}/pipelines?sha={p['sha']}", cfg["token"])
                status = pipes[0].get("status") if pipes else None
            except Exception:  # noqa: BLE001
                status = None
            if status in ("success",):
                results.append({"site": sk, "sha": p["sha"], "slug": p.get("slug"),
                                "status": "success"})
                continue
            if status in ("failed", "canceled"):
                reverted = False
                try:
                    _HTTP("POST", f"{_proj_url(cfg)}/repository/commits/{p['sha']}/revert",
                          cfg["token"], {"branch": cfg["branch"]})
                    reverted = True
                except Exception:  # noqa: BLE001
                    pass
                try:
                    db.add(Notification(
                        client_id=None, target_user_id=None, kind="content",
                        severity="warning",
                        message=(f"🛑 {meta['site']} deploy FAILED for '{p.get('slug')}' "
                                 f"(commit {str(p['sha'])[:8]}). "
                                 f"{'Commit auto-reverted — the site stays on the last good build. ' if reverted else 'Auto-revert failed — revert manually. '}"
                                 f"Pulse will write a fresh post on the next daily run.")[:1000]))
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
                results.append({"site": sk, "sha": p["sha"], "slug": p.get("slug"),
                                "status": "failed", "reverted": reverted})
                continue
            p = dict(p)
            p["checks"] = int(p.get("checks") or 0) + 1
            if p["checks"] < MAX_CHECKS:
                keep.append(p)
            else:
                results.append({"site": sk, "sha": p["sha"], "slug": p.get("slug"),
                                "status": "unknown"})
        conn = secure_config.get_platform(db, meta["provider"])
        raw = dict((conn.config if conn else None) or {})
        raw["pending"] = keep
        secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing", raw)
    return results
