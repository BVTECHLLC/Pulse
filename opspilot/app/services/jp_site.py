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
import urllib.error
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
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        # Surface GitLab's ACTUAL message ("A file with this name already
        # exists", "branch not found", ...) instead of a bare "HTTP Error 400"
        # that tells the operator nothing.
        detail = ""
        try:
            raw = e.read().decode()[:300]
            detail = str(json.loads(raw).get("message", raw))[:200]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"GitLab {e.code}: {detail or e.reason}") from e
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


def _find_generic_card(html_text: str, link_pat: str) -> tuple[int, int] | None:
    """Universal fallback: locate the source span of the SMALLEST container
    element (article/li/section/div) that wraps the first post link together
    with a heading. Uses the stdlib HTML parser with real source positions, so
    it works on ANY card markup — no assumptions about class names. This is
    what lets bvtech.org's custom blog cards get injected, not just <article>s."""
    import re as _re
    from html.parser import HTMLParser

    m = _re.search(link_pat, html_text)
    if not m:
        return None
    link_pos = m.start()
    lines = html_text.split("\n")
    line_off = [0]
    for ln in lines:
        line_off.append(line_off[-1] + len(ln) + 1)

    class _P(HTMLParser):
        CONTAINERS = ("article", "li", "section", "div")

        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.stack: list[tuple[str, int]] = []
            self.headings: list[int] = []
            self.best: tuple[int, int] | None = None

        def _off(self) -> int:
            ln, col = self.getpos()
            return line_off[ln - 1] + col

        def handle_starttag(self, tag, attrs):
            if tag in self.CONTAINERS:
                self.stack.append((tag, self._off()))
            elif tag in ("h1", "h2", "h3", "h4"):
                self.headings.append(self._off())

        def handle_endtag(self, tag):
            if tag not in self.CONTAINERS:
                return
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    start = self.stack[i][1]
                    end = self._off() + len(tag) + 3          # '</tag>'
                    del self.stack[i:]
                    span = end - start
                    if (start <= link_pos < end and span < 6000
                            and any(start <= h < end for h in self.headings)):
                        if self.best is None or span < (self.best[1] - self.best[0]):
                            self.best = (start, end)
                    break

    p = _P()
    try:
        p.feed(html_text)
        p.close()
    except Exception:  # noqa: BLE001 — malformed HTML: give up, never corrupt
        return None
    return p.best


def _rewrite_card(card: str, *, title: str, url: str, excerpt: str,
                  date_str: str, link_pat: str) -> str:
    """Turn a cloned card into the new post's card (links, heading, excerpt, date)."""
    import html as _html
    import re as _re
    card = _re.sub(link_pat, f'href="{url}"', card)
    card = _re.sub(r"(<h[1-4][^>]*>\s*(?:<a[^>]*>)?)(.*?)((?:</a>\s*)?</h[1-4]>)",
                   lambda m: m.group(1) + _html.escape(title) + m.group(3),
                   card, count=1, flags=_re.S)
    if _re.search(r'class="excerpt"', card):
        card = _re.sub(r'(<p[^>]*class="excerpt"[^>]*>)(.*?)(</p>)',
                       lambda m: m.group(1) + _html.escape(excerpt) + m.group(3),
                       card, count=1, flags=_re.S)
    card = _re.sub(r"(>)([A-Z][a-z]+ \d{1,2}, \d{4})(<)",
                   lambda m: m.group(1) + date_str + m.group(3), card, count=1)
    return card


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
    if template:
        card = _rewrite_card(template.group(0), title=title, url=url, excerpt=excerpt,
                             date_str=date_str, link_pat=link_pat)
        pos = grid.end() if (grid and grid.end() <= template.start()) else template.start()
        return h[:pos] + "\n" + card + "\n" + h[pos:], True
    # Strategy 2 — universal: any container element (div/li/section) that wraps
    # a post link + heading, found with a real parser. Handles custom card
    # markup (bvtech.org's blog index) with zero class-name assumptions.
    span = _find_generic_card(h, link_pat)
    if not span:
        return h, False
    card = _rewrite_card(h[span[0]:span[1]], title=title, url=url, excerpt=excerpt,
                         date_str=date_str, link_pat=link_pat)
    return h[:span[0]] + card + "\n" + h[span[0]:], True


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
        from . import content_studio
        # Adaptive: a generated site (Astro/Next/Hugo/...) only ships what its
        # build produces — publish MARKDOWN into its content folder, cloned from
        # its own newest post. The generator then builds the page AND all its
        # listing/index pages for us.
        layout = detect_layout(cfg)
        if layout["format"] == "markdown":
            excerpt_md = (post.get("description")
                          or content_studio._excerpt_from_html(post.get("html") or ""))[:220]
            sample = _fetch_file(cfg, layout["sample_path"]) or "---\ntitle: x\n---\n"
            ext = layout["sample_path"].rsplit(".", 1)[-1]
            md_path = f"{layout['content_dir']}/{slug}.{ext}"
            md_url = f"{meta['site']}/blog/{slug}/"
            exists_md = _fetch_file(cfg, md_path) is not None
            commit = _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
                "branch": cfg["branch"],
                "commit_message": f"blog: {post.get('title', slug)[:80]} (via Pulse)",
                "actions": [{"action": "update" if exists_md else "create",
                             "file_path": md_path,
                             "content": _markdown_for(post, slug, sample, excerpt_md)}],
            })
            sha = commit.get("id")
            conn = secure_config.get_platform(db, meta["provider"])
            raw = dict((conn.config if conn else None) or {})
            pending = list(raw.get("pending") or [])
            pending.append({"sha": sha, "slug": slug,
                            "at": datetime.now(timezone.utc).isoformat(), "checks": 0})
            raw["pending"] = pending[-10:]
            secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing", raw)
            from . import cloudflare
            purge = cloudflare.purge_urls(db, site, [md_url, f"{meta['site']}/blog/",
                                                     f"{meta['site']}/"])
            return {"ok": True, "sha": sha, "slug": slug, "url": md_url,
                    "listings_updated": [], "listings_skipped": [],
                    "listing_generated": True, "engine": layout["engine_file"],
                    "content_path": md_path,
                    "cache_purged": purge.get("ok"), "cache_detail": purge.get("detail")}

        skeleton = _newest_skeleton(cfg, cfg["style"])
        rendered = content_studio.render(
            {**post, "slug": slug, "site": meta["site"], "org": meta["org"],
             "author_url": meta["author_url"]},
            skeleton_html=skeleton, content_classes=meta["content_classes"])
        # Idempotent: if this slug was already published (same-day re-run, retry
        # after a partial failure, deliberate re-publish), OVERWRITE it instead
        # of letting GitLab reject the commit with "file already exists".
        exists = _fetch_file(cfg, file_path) is not None
        actions = [{"action": "update" if exists else "create",
                    "file_path": file_path, "content": rendered}]

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


# --------------------------------------------------------------------------- #
# v1.36 Adaptive publishing — detect what KIND of site each repo is and publish
# the format that will actually ship. jordanpolasek.com is plain HTML (commit ->
# live). A generated site (Astro/Next/Hugo/Eleventy) only ships what its BUILD
# produces from its content folder — raw HTML committed into blog/ never appears
# (or breaks the build and gets auto-reverted). That is exactly "Pulse says
# posted but the site never changes." For generated repos we clone the newest
# real post's frontmatter and commit MARKDOWN into the content folder instead.
# --------------------------------------------------------------------------- #
_ENGINE_FILES = ("package.json", "astro.config.mjs", "astro.config.ts", "next.config.js",
                 "next.config.mjs", "hugo.toml", "config.toml", ".eleventy.js",
                 "eleventy.config.js", "gatsby-config.js", "svelte.config.js")
_CONTENT_DIRS = ("src/content/blog", "src/content/posts", "content/blog", "content/posts",
                 "src/posts", "_posts", "posts", "src/pages/blog", "blog")


def detect_layout(cfg: dict) -> dict:
    """{"format": "html"|"markdown", "content_dir": str|None, "sample_path": str|None,
        "engine_file": str|None} — one root-tree call + a few cheap dir probes."""
    try:
        root = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?ref={cfg['branch']}&per_page=100",
                     cfg["token"])
    except Exception:  # noqa: BLE001
        return {"format": "html", "content_dir": None, "sample_path": None, "engine_file": None}
    names = {t.get("path") for t in root if t.get("type") == "blob"}
    engine = next((f for f in _ENGINE_FILES if f in names), None)
    if not engine:
        return {"format": "html", "content_dir": None, "sample_path": None, "engine_file": None}
    for d in _CONTENT_DIRS:
        try:
            tree = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?path={urllib.parse.quote_plus(d)}"
                         f"&ref={cfg['branch']}&per_page=100", cfg["token"])
        except Exception:  # noqa: BLE001
            continue
        md = sorted([t["path"] for t in tree if t.get("type") == "blob"
                     and t["path"].rsplit(".", 1)[-1] in ("md", "mdx", "markdown")],
                    reverse=True)
        if md:
            return {"format": "markdown", "content_dir": d, "sample_path": md[0],
                    "engine_file": engine}
    # Generated site but no recognizable content dir: fall back to HTML (and the
    # Doctor will say so) rather than guessing blindly.
    return {"format": "html", "content_dir": None, "sample_path": None, "engine_file": engine}


def _markdown_for(post: dict, slug: str, sample_md: str, excerpt: str) -> str:
    """Clone the sample post's frontmatter line-by-line, swapping the values that
    identify the post (title/description/date/slug/draft) and copying everything
    else verbatim — the same 'mimic the site's own newest post' philosophy the
    HTML skeleton cloning uses. Body: the article HTML (all major generators
    render embedded HTML inside markdown)."""
    import json as _json
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title_q = _json.dumps((post.get("title") or slug)[:180])
    desc_q = _json.dumps((excerpt or "")[:220])
    fm_lines, body_start = [], 0
    lines = sample_md.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i
                break
            fm_lines.append(lines[i])
    out, seen = ["---"], set()
    def put(key: str, val: str):
        out.append(f"{key}: {val}")
        seen.add(key.lower())
    for ln in fm_lines:
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:", ln)
        if not m:
            out.append(ln)                      # nested/list lines: copy verbatim
            continue
        key, lk = m.group(1), m.group(1).lower()
        if lk == "title":
            put(key, title_q)
        elif lk in ("description", "excerpt", "summary", "subtitle"):
            put(key, desc_q)
        elif lk in ("date", "pubdate", "publishdate", "published", "publish_date",
                    "created", "updateddate", "updated"):
            put(key, today)
        elif lk == "slug":
            put(key, slug)
        elif lk == "draft":
            put(key, "false")
        else:
            out.append(ln)                      # keep the site's own metadata as-is
            seen.add(lk)
    if "title" not in seen:
        put("title", title_q)
    if "description" not in seen:
        put("description", desc_q)
    if "date" not in seen and "pubdate" not in seen:
        put("date", today)
    out.append("---")
    body = post.get("html") or post.get("body") or ""
    return "\n".join(out) + "\n\n" + body + "\n"


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
    if detect_layout(cfg)["format"] == "markdown":
        return {"ok": True, "added": [],
                "detail": "generated site - the build produces its own blog index; nothing to sync"}
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
    # Site engine: what kind of site is this, and are we publishing the format
    # that will actually SHIP? (Generated sites ignore raw HTML commits — the
    # silent "posted but never appears" trap.)
    layout = detect_layout(cfg)
    if layout["format"] == "markdown":
        _check("Site engine", True,
               f"generated site ({layout['engine_file']}) - publishing markdown to "
               f"{layout['content_dir']}/ (frontmatter cloned from "
               f"{layout['sample_path'].rsplit('/', 1)[-1]}); the build creates the "
               "post page AND the blog index automatically")
        from . import cloudflare
        cf = cloudflare.verify(db) if cloudflare.configured(db) else {
            "ok": False,
            "detail": "not connected - cached pages update on their own TTL (can look stale for hours)"}
        _check("Cloudflare cache purge", cf["ok"], cf["detail"],
               "Connection Center -> Cloudflare -> paste an API token (Zone:Read + Cache Purge)")
        healthy = all(c["ok"] for c in checks if not c["name"].startswith("Cloudflare cache"))
        return {"site": meta["site"], "checks": checks, "healthy": healthy}
    if layout["engine_file"]:
        _check("Site engine", False,
               f"generated site ({layout['engine_file']}) but no recognizable content "
               "folder found - committed HTML may never appear on the site",
               "tell Pulse where the posts live (expected something like src/content/blog/*.md)")
    else:
        _check("Site engine", True, "static HTML site - direct publish + listing injection")
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
