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

# BVTech is a Texas business, so every human-facing date must read in Central
# time — NOT the box's UTC. Without this a post published at, say, 9pm Central
# gets stamped with tomorrow's UTC date ("posting the future"). tzdata (in
# requirements) makes ZoneInfo work on the slim image; we fall back to UTC only
# if the zone is somehow unavailable.
BIZ_TZ = "America/Chicago"


def biz_now(now: datetime | None = None) -> datetime:
    """`now` (UTC) as Central time, for datelines and date-based slugs."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo(BIZ_TZ))
    except Exception:  # noqa: BLE001 — missing tzdata: degrade to UTC, never crash
        return now

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
           "index_paths": ("index.html", "blog/index.html"),
           # v1.43: the HOMEPAGE is a PREVIEW — newest N cards only. The full
           # archive lives on /blog/. Without a cap the homepage section grew a
           # card for every post ever published (the "100 writings" flood).
           "preview_caps": {"index.html": 6}},
    "bvtech": {"provider": "bvtech_site", "name": "BVTech.org Site",
               "default_project": "BVTECHLLC-group/bvtech-website-new",
               "style": "blog-file", "site": "https://bvtech.org",
               "org": "BVTech LLC", "author_url": "https://bvtech.org",
               "content_classes": None,
               "index_paths": ("blog/index.html", "index.html"),
               "preview_caps": {"index.html": 6}},
    # bvtech.org's SEPARATE news section ("This Week in Cybersecurity" KEV
    # briefings live at /news/, not /blog/). Same repo/token, own folder+index.
    # The /news/ page is a LISTING whose cards link to /blog/ files (the
    # Splunk edition lives at /blog/jordan-polasek-june-20-...). So news
    # editions publish as BLOG files and their card lands on news/index.html.
    # sweep=False: the hourly sweep must never sync ALL blog posts onto the
    # news page - the bvtech site entry already guards the blog dir itself.
    "bvtech_news": {"provider": "bvtech_site", "name": "BVTech.org News",
                    "default_project": "BVTECHLLC-group/bvtech-website-new",
                    "style": "blog-file", "file_dir": "blog", "backfill": False,
                    "site": "https://bvtech.org", "org": "BVTech LLC",
                    "author_url": "https://bvtech.org", "content_classes": None,
                    "index_paths": ("news/index.html", "blog/index.html", "index.html")},
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
    # v1.37 added an optional GitHub forge; v1.38 makes it strictly OPT-IN.
    # The live bvtech.org repo is on GitLab (BVTECHLLC-group/bvtech-website-new),
    # so GitLab stays authoritative unless a GitHub token is stored AND the
    # switch hasn't been turned off. Setting github_active to "no" (or clearing
    # the token) always falls straight back to GitLab.
    gh_token = secure_config.get_secret(cfg, "gh_token")
    gh_active = str(cfg.get("github_active", "yes")).strip().lower()
    if site == "bvtech" and gh_token and gh_active not in ("no", "false", "0", "off"):
        return {
            "forge": "github",
            "base": GITHUB_API,
            "project": cfg.get("github_repo") or DEFAULT_GITHUB_REPO,
            "branch": cfg.get("github_branch") or cfg.get("branch") or "main",
            "token": gh_token,
            "pending": cfg.get("pending") or [],
            "configured": True,
            "style": meta["style"], "site": meta["site"], "org": meta["org"],
        }
    token = _resolve_token(db, secure_config.get_secret(cfg, "token"))
    project = cfg.get("project") or meta["default_project"]
    return {
        "forge": "gitlab",
        "base": (cfg.get("base") or DEFAULT_BASE).rstrip("/"),
        "project": project,
        "branch": cfg.get("branch") or "main",
        "token": token,
        "pending": cfg.get("pending") or [],
        "configured": bool(project and token),
        "style": meta["style"], "site": meta["site"], "org": meta["org"],
        "file_dir": meta.get("file_dir", "blog"),
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

    # v1.44.1: a post's link can appear OUTSIDE its card first (JSON-LD blocks,
    # raw head links) — try every occurrence until one is inside a real card,
    # instead of giving up on the first non-card hit.
    for _m in list(_re.finditer(link_pat, html_text))[:20]:
        span = _find_card_at(html_text, _m.start())
        if span:
            return span
    return None


def _find_card_at(html_text: str, link_pos: int) -> tuple[int, int] | None:
    from html.parser import HTMLParser

    lines = html_text.split("\n")
    line_off = [0]
    for ln in lines:
        line_off.append(line_off[-1] + len(ln) + 1)

    class _P(HTMLParser):
        # v1.39: <a> counts as a container too — modern card grids often make
        # the whole card ONE anchor (<a class="card"><h3>...</h3>...</a>), so
        # the smallest element wrapping the link+heading IS the link itself.
        CONTAINERS = ("article", "li", "section", "div", "a")

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
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.headings.append(self._off())
            elif tag in ("div", "span", "p", "strong", "b"):
                # Heading-less cards: a class named *title* is the headline.
                cls = next((v for k, v in attrs if k == "class" and v), "")
                if "title" in cls.lower():
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
    card, n_head = _re.subn(r"(<h[1-6][^>]*>\s*(?:<a[^>]*>)?)(.*?)((?:</a>\s*)?</h[1-6]>)",
                            lambda m: m.group(1) + _html.escape(title) + m.group(3),
                            card, count=1, flags=_re.S)
    if not n_head:
        # Heading-less cards: rewrite the first element whose class says "title".
        card = _re.sub(r'(<(\w+)[^>]*class="[^"]*[Tt]itle[^"]*"[^>]*>)(.*?)(</\2>)',
                       lambda m: m.group(1) + _html.escape(title) + m.group(4),
                       card, count=1, flags=_re.S)
    # v1.47.6: the fresh excerpt goes in as a SENTINEL until the date swaps are
    # done. The no-year date swap used to hit month-day mentions INSIDE the new
    # excerpt text ("...the rest of the June 9 KEV additions" turned into "the
    # rest of the April 5 KEV additions") - prose must never be date-swapped.
    _SENT = "\x00PULSE-EXCERPT\x00"
    if _re.search(r'class="excerpt"', card):
        card = _re.sub(r'(<p[^>]*class="excerpt"[^>]*>)(.*?)(</p>)',
                       lambda m: m.group(1) + _SENT + m.group(3),
                       card, count=1, flags=_re.S)
    elif excerpt:
        # v1.40: cards without class="excerpt" kept the CLONED post's summary —
        # every card on bvtech.org showed the same stale text. The first
        # substantial paragraph (>=40 chars of plain text) is the summary.
        card = _re.sub(r"(<p[^>]*>)([^<]{40,}?)(</p>)",
                       lambda m: m.group(1) + _SENT + m.group(3),
                       card, count=1)
    if date_str:      # v1.41: empty date_str means "leave the card's date alone"
        n_dated = 0
        card, _n = _re.subn(r"(>)([A-Z][a-z]+ \d{1,2}, \d{4})(<)",
                            lambda m: m.group(1) + date_str + m.group(3), card, count=1)
        n_dated += _n
        card, _n = _re.subn(r"(>)([A-Z][a-z]+ \d{1,2}, \d{4})(\s*\u00b7)",
                            lambda m: m.group(1) + date_str + m.group(3), card, count=1)
        n_dated += _n
        card, _n = _re.subn(r"(>)(\d{4}-\d{2}-\d{2})(<)",
                            lambda m: m.group(1) + date_str + m.group(3), card, count=1)
        n_dated += _n
        card, _n = _re.subn(r"(\u00b7\s*)([A-Z][a-z]+ \d{1,2}, \d{4})",
                            lambda m: m.group(1) + date_str, card, count=1)
        n_dated += _n
        # v1.40: badge-style dates without a year ("NEW · JUNE 22 WEEKLY REPORT",
        # "June 22") also cloned verbatim — swap month+day, keep the badge text.
        # v1.47.6: only when NO full date matched above - a card that already
        # shows a full date has no year-less badge, so this loose pattern could
        # only ever hit innocent prose (a month-day inside a title or caption).
        if not n_dated:
            _md = date_str.rsplit(",", 1)[0]          # "July 14, 2026" -> "July 14"
            card = _re.sub(r"\b(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|"
                           r"OCTOBER|NOVEMBER|DECEMBER) \d{1,2}\b(?!, \d{4})",
                           _md.upper(), card, count=1)
            card = _re.sub(r"\b(January|February|March|April|May|June|July|August|September|"
                           r"October|November|December) \d{1,2}\b(?!, \d{4})",
                           _md, card, count=1)
    return card.replace(_SENT, _html.escape(excerpt))


def inject_post_into_listing(listing_html: str, *, title: str, url: str,
                             excerpt: str, date_str: str, style: str,
                             file_dir: str = "blog") -> tuple[str, bool]:
    """Clone the newest post card in a listing page and insert a fresh card for
    `url` at the top of the posts grid. Returns (new_html, changed). Never raises;
    returns (listing_html, False) when the listing already has the post or its
    card structure isn't recognized (so a weird page is left untouched, not
    corrupted — the build-verify + auto-revert is the final safety net)."""
    import html as _html
    h = listing_html
    # Already listed under ANY href form (absolute/relative) -> never re-inject.
    if f'href="{url}"' in h or _slug_listed(h, _slug_of(url)):
        return h, False
    link_pat = _link_pat_for(style, file_dir)
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


def _link_pat_for(style: str, file_dir: str = "blog") -> str:
    return (r'href="[^"]*' + re.escape(file_dir) + r'/[a-z0-9\-]+\.html"'
            if style == "blog-file" else r'href="/[a-z0-9\-]{6,}/"')


def _ai_inject_listing(html_text: str, *, title: str, url: str, excerpt: str,
                       date_str: str, link_pat: str) -> tuple[str, bool]:
    """v1.39 last resort: when the deterministic card-finder can't parse the
    page's markup, have Claude clone the page's OWN newest card for the new
    post. The model only AUTHORS the card + names an anchor; the splice itself
    is deterministic and validated hard (the anchor must exist verbatim near
    the first post link, the card must link the new URL and carry its title) —
    a wrong answer changes NOTHING, exactly like an unrecognized listing today."""
    import html as _html
    import re as _re
    from . import ai as ai_svc
    if not ai_svc.enabled():
        return html_text, False
    m = _re.search(link_pat, html_text)
    if not m:
        return html_text, False
    frag = html_text[max(0, m.start() - 4000): m.start() + 4000]
    system = (
        "You are an exact HTML templating engine for a static blog listing page. "
        "Clone the existing post-card markup for a NEW post: same tags, same class "
        "names, same attribute style, same indentation. Never invent classes or "
        "restructure anything. Reply in EXACTLY this format (nothing else):\n"
        "ANCHOR: <the first 60-120 characters of the newest existing post card, copied "
        "VERBATIM from the fragment starting at its opening tag; the new card will be "
        "inserted immediately before this text>\n"
        "CARD_START\n<the new card's html>\nCARD_END")
    user = (f"New post to insert:\nTITLE: {title}\nURL: {url}\nDATE: {date_str}\n"
            f"EXCERPT: {excerpt}\n\nListing page fragment:\n{frag}")
    try:
        raw = ai_svc.complete(system, user, max_tokens=1600)
    except Exception:  # noqa: BLE001 — AI down: behave like "not recognized"
        return html_text, False
    am = _re.search(r"ANCHOR:[ \t]*(.+)", raw)
    cm = _re.search(r"CARD_START\s*\n(.*?)\nCARD_END", raw, _re.S)
    if not am or not cm:
        return html_text, False
    anchor = am.group(1).strip()[:200]
    card = cm.group(1).strip()
    idx = html_text.find(anchor)
    # Validation gauntlet — every miss returns the page untouched.
    if (len(anchor) < 20 or idx < 0 or not card or len(card) > 4000
            or f'href="{url}"' not in card
            or (title[:40] not in card and _html.escape(title)[:40] not in card)
            or "<html" in card.lower() or "<body" in card.lower()
            or abs(idx - m.start()) > 8000):
        return html_text, False
    return html_text[:idx] + card + "\n" + html_text[idx:], True


def _inject_listing(html_text: str, *, title: str, url: str, excerpt: str,
                    date_str: str, style: str, allow_ai: bool = True,
                    file_dir: str = "blog") -> tuple[str, bool]:
    """Deterministic injection first; AI card-clone fallback when the markup
    isn't recognized (and Claude is connected). This is what publish and
    sync_listings actually call."""
    new_html, changed = inject_post_into_listing(
        html_text, title=title, url=url, excerpt=excerpt,
        date_str=date_str, style=style, file_dir=file_dir)
    if changed or f'href="{url}"' in html_text or not allow_ai:
        return new_html, changed
    return _ai_inject_listing(html_text, title=title, url=url, excerpt=excerpt,
                              date_str=date_str,
                              link_pat=_link_pat_for(style, file_dir))


def _newest_skeleton(cfg: dict, style: str) -> str | None:
    """Fetch the most recent post's HTML to clone header/footer/CSS from."""
    import base64
    if style == "blog-file":
        _fd = cfg.get("file_dir", "blog")
        tree = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?path={_fd}&ref={cfg['branch']}&per_page=100",
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
    fdir = meta.get("file_dir", "blog")
    file_path = (f"{fdir}/{slug}.html" if cfg["style"] == "blog-file"
                 else f"{slug}/index.html")
    public_url = (f"{meta['site']}/{fdir}/{slug}.html" if cfg["style"] == "blog-file"
                  else f"{meta['site']}/{slug}/")
    try:
        from . import content_studio
        # Adaptive: a generated site (Astro/Next/Hugo/...) only ships what its
        # build produces — publish MARKDOWN into its content folder, cloned from
        # its own newest post. The generator then builds the page AND all its
        # listing/index pages for us.
        layout = detect_layout(cfg)
        if layout["format"] == "markdown":
            ops = _repo_ops(cfg)
            excerpt_md = (post.get("description")
                          or content_studio._excerpt_from_html(post.get("html") or ""))[:220]
            sample = ops["fetch"](layout["sample_path"]) or "---\ntitle: x\n---\n"
            ext = layout["sample_path"].rsplit(".", 1)[-1]
            md_path = f"{layout['content_dir']}/{slug}.{ext}"
            md_url = f"{meta['site']}/blog/{slug}/"
            exists_md = ops["fetch"](md_path) is not None
            sha = ops["commit"](md_path, _markdown_for(post, slug, sample, excerpt_md),
                                f"blog: {post.get('title', slug)[:80]} (via Pulse)",
                                exists_md)
            conn = secure_config.get_platform(db, meta["provider"])
            raw = dict((conn.config if conn else None) or {})
            # GitLab pipelines report the Cloudflare build (verify+auto-revert);
            # GitHub-forge commits deploy via Cloudflare's GitHub integration,
            # which doesn't report back here — skip the pending watch for those.
            if cfg.get("forge") != "github":
                pending = list(raw.get("pending") or [])
                pending.append({"sha": sha, "slug": slug,
                                "at": datetime.now(timezone.utc).isoformat(), "checks": 0})
                raw["pending"] = pending[-10:]
                secure_config.upsert_platform(db, meta["provider"], meta["name"],
                                              "Publishing", raw)
            from . import cloudflare
            purge = cloudflare.purge_urls(db, site, [md_url, f"{meta['site']}/blog/",
                                                     f"{meta['site']}/"])
            return {"ok": True, "sha": sha, "slug": slug, "url": md_url,
                    "listings_updated": [], "listings_skipped": [],
                    "listing_generated": True, "engine": layout["engine_file"],
                    "forge": cfg.get("forge", "gitlab"),
                    "content_path": md_path,
                    "cache_purged": purge.get("ok"), "cache_detail": purge.get("detail")}

        skeleton = _newest_skeleton(cfg, cfg["style"])
        rendered = content_studio.render(
            {**post, "slug": slug, "site": meta["site"], "org": meta["org"],
             "author_url": meta["author_url"]},
            skeleton_html=skeleton, content_classes=meta["content_classes"])
        # v1.41: the cloned skeleton carries the ORIGINAL post's visible date —
        # swap that exact stale date for today's so the page tells the truth.
        rendered = _refresh_cloned_date(rendered, skeleton)
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
        date_str = biz_now().strftime("%B %-d, %Y")
        listings_updated, listings_skipped = [], []
        for lp in meta.get("index_paths", ()):
            current = _fetch_file(cfg, lp)
            if current is None:
                continue                              # no such listing on this site
            new_html, changed = _inject_listing(
                current, title=post.get("title", slug), url=public_url,
                excerpt=excerpt, date_str=date_str, style=cfg["style"],
                file_dir=cfg.get("file_dir", "blog"))
            cap = (meta.get("preview_caps") or {}).get(lp)
            if cap:                                   # homepage = preview only
                new_html, trimmed = _trim_listing(new_html, cfg["style"], cap)
                changed = changed or bool(trimmed)
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
# v1.37 GitHub forge support (OPTIONAL) — kept for sites whose repo lives on
# GitHub. The live bvtech.org repo is confirmed on GitLab
# (BVTECHLLC-group/bvtech-website-new), so this path only activates when the
# operator explicitly connects a GitHub token AND leaves github_active on.
# When active, publishing goes through the GitHub Contents API with the same
# adaptive (markdown/frontmatter-clone) pipeline.
# --------------------------------------------------------------------------- #
GITHUB_API = "https://api.github.com"
DEFAULT_GITHUB_REPO = "BVTECHLLC/bvtech-website-new"


def _gh_http(method: str, url: str, token: str, payload: dict | None = None) -> dict | list:
    req = urllib.request.Request(url, method=method,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28",
                                          "User-Agent": "BVTech-OpsPilot"})
    data = json.dumps(payload).encode() if payload is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            raw = e.read().decode()[:300]
            detail = str(json.loads(raw).get("message", raw))[:200]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"GitHub {e.code}: {detail or e.reason}") from e
    return json.loads(body) if body else {}


_GH = _gh_http   # test seam


def _repo_ops(cfg: dict) -> dict:
    """Forge-agnostic repo operations so detect_layout/publish work identically
    against GitLab (API v4) and GitHub (Contents API):
      tree(path)  -> [{"path": str, "type": "blob"|"tree"}]
      fetch(path) -> str | None
      commit(path, content, message, update) -> sha
    """
    import base64
    if cfg.get("forge") == "github":
        repo, branch, token = cfg["project"], cfg["branch"], cfg["token"]

        def tree(path: str = ""):
            try:
                out = _GH("GET", f"{GITHUB_API}/repos/{repo}/contents/"
                          f"{urllib.parse.quote(path)}?ref={branch}", token)
            except Exception:  # noqa: BLE001
                return []
            if isinstance(out, dict):
                out = [out]
            return [{"path": it.get("path"),
                     "type": "tree" if it.get("type") == "dir" else "blob"}
                    for it in out]

        def fetch(path: str):
            try:
                out = _GH("GET", f"{GITHUB_API}/repos/{repo}/contents/"
                          f"{urllib.parse.quote(path)}?ref={branch}", token)
                return base64.b64decode(out["content"]).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                return None

        def commit(path: str, content: str, message: str, update: bool):
            payload = {"message": message, "branch": branch,
                       "content": base64.b64encode(content.encode()).decode()}
            if update:
                cur = _GH("GET", f"{GITHUB_API}/repos/{repo}/contents/"
                          f"{urllib.parse.quote(path)}?ref={branch}", token)
                payload["sha"] = cur.get("sha")
            out = _GH("PUT", f"{GITHUB_API}/repos/{repo}/contents/"
                      f"{urllib.parse.quote(path)}", token, payload)
            return (out.get("commit") or {}).get("sha")
        return {"tree": tree, "fetch": fetch, "commit": commit}

    def tree(path: str = ""):
        q = f"&path={urllib.parse.quote_plus(path)}" if path else ""
        try:
            return _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?ref={cfg['branch']}"
                         f"&per_page=100{q}", cfg["token"]) or []
        except Exception:  # noqa: BLE001
            return []

    def fetch(path: str):
        return _fetch_file(cfg, path)

    def commit(path: str, content: str, message: str, update: bool):
        out = _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"], "commit_message": message,
            "actions": [{"action": "update" if update else "create",
                         "file_path": path, "content": content}]})
        return out.get("id")
    return {"tree": tree, "fetch": fetch, "commit": commit}


def gh_verify(db: Session) -> dict:
    """Live check of the bvtech GitHub connection: token + repo reachability."""
    cfg = get_config(db, "bvtech")
    if cfg.get("forge") != "github":
        return {"ok": False, "detail": "No GitHub token stored yet (paste a fine-grained "
                                       "PAT with Contents read/write)."}
    try:
        me = _GH("GET", f"{GITHUB_API}/user", cfg["token"])
        repo = _GH("GET", f"{GITHUB_API}/repos/{cfg['project']}", cfg["token"])
        perm = (repo.get("permissions") or {})
        if not (perm.get("push") or perm.get("admin") or perm.get("maintain")):
            return {"ok": False,
                    "detail": f"Token sees {cfg['project']} but can't WRITE - grant "
                              "Contents: Read and write on the fine-grained token."}
        return {"ok": True, "detail": f"Verified as {me.get('login', '?')} - can publish "
                                      f"to {cfg['project']} (branch {cfg['branch']})."}
    except Exception as e:  # noqa: BLE001
        m = str(e)
        if "401" in m:
            return {"ok": False, "detail": "GitHub rejected the token (401) - generate a "
                                           "new fine-grained PAT."}
        if "404" in m:
            return {"ok": False, "detail": f"Token can't see {cfg['project']} (404) - on the "
                                           "fine-grained token, set Repository access to "
                                           "include it."}
        return {"ok": False, "detail": f"GitHub check failed: {m[:140]}"}


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
        "engine_file": str|None} — one root-tree call + a few cheap dir probes.
    Forge-agnostic (GitLab or GitHub) via _repo_ops."""
    ops = _repo_ops(cfg)
    root = ops["tree"]("")
    if not root:
        return {"format": "html", "content_dir": None, "sample_path": None, "engine_file": None}
    names = {t.get("path") for t in root if t.get("type") == "blob"}
    engine = next((f for f in _ENGINE_FILES if f in names), None)
    if not engine:
        return {"format": "html", "content_dir": None, "sample_path": None, "engine_file": None}
    for d in _CONTENT_DIRS:
        tree = ops["tree"](d)
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
    today = biz_now().strftime("%Y-%m-%d")
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
        _fd = cfg.get("file_dir", "blog")
        tree = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?path={_fd}&ref={cfg['branch']}&per_page=100",
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
    if len(excerpt) > 220:
        # v1.47.6: cut on a word boundary — the hard [:220] slice left cards
        # ending mid-word ("...and the rest of the June 9 KEV additio").
        excerpt = excerpt[:220].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return title[:180], excerpt


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
    if cfg.get("forge") == "github":
        return {"ok": False, "error": "GitHub site with an unrecognized layout - run the "
                                      "Doctor for details"}
    try:
        post_paths = _list_post_paths(cfg, cfg["style"])[:60]
        listings = {lp: _fetch_file(cfg, lp) for lp in meta.get("index_paths", ())}
        listings = {lp: h for lp, h in listings.items() if h is not None}
        if not listings:
            return {"ok": False, "error": "no listing pages found in the repo"}
        date_str = biz_now().strftime("%B %-d, %Y")
        added, actions, purge_urls = [], [], []
        ai_misses: dict[str, int] = {}
        for path in (post_paths if meta.get("backfill", True) else []):
            url = _post_url_for(meta, path, cfg["style"])
            rel = url.replace(meta["site"], "")            # href form used in listings
            slug = _slug_of(path)
            # v1.42: listed-detection by SLUG across any href form — exact-string
            # matching re-injected "already listed" posts on every sync (the
            # duplicate-card spam on bvtech.org's blog page).
            caps = meta.get("preview_caps") or {}
            missing = [lp for lp, h in listings.items()
                       if lp not in caps and not _slug_listed(h, slug)]
            if not missing:
                continue
            page = _fetch_file(cfg, path)
            if not page:
                continue
            title, excerpt = _post_meta_from_html(page)
            # v1.46: date the backfilled card by the POST'S own date — stamping
            # TODAY on every backfilled card made whole batches look same-day
            # published (the "multi post per day" spam look). v1.47.6: page
            # date first, first-commit fallback (see _post_date_label).
            post_date = _post_date_label(cfg, path, page) or date_str
            any_change = False
            for lp in missing:
                # AI fallback is capped per listing page: after 2 misses the
                # page clearly isn't AI-fixable either — stop burning calls.
                use_ai = ai_misses.get(lp, 0) < 2
                new_html, changed = _inject_listing(
                    listings[lp], title=title, url=rel, excerpt=excerpt,
                    date_str=post_date, style=cfg["style"], allow_ai=use_ai,
                    file_dir=cfg.get("file_dir", "blog"))
                if changed:
                    listings[lp] = new_html
                    any_change = True
                elif use_ai:
                    ai_misses[lp] = ai_misses.get(lp, 0) + 1
            if not any_change:
                continue                    # nothing injectable for this post
            added.append({"path": path, "title": title, "url": url})
            purge_urls.append(url)
            if len(added) >= limit:
                break
        # v1.40 REPAIR: cards whose text was CLONED from another post (the
        # "every card shows the same stale excerpt/date badge" bug) get rebuilt
        # from their own post's metadata. Deterministic span replace only.
        import html as _html40
        repaired = []
        for path in post_paths[:40]:
            slug_root = (path.rsplit("/", 1)[-1] if cfg["style"] == "blog-file"
                         else path.split("/")[0])
            if any(slug_root.startswith(pfx) for pfx in _PAGE_SLUGS):
                continue
            url = _post_url_for(meta, path, cfg["style"])
            rel = url.replace(meta["site"], "")
            page = title = excerpt = None
            date_lbl = date_str
            for lp in list(listings):
                h = listings[lp]
                pat = _slug_href_pat(_slug_of(path))     # any href form (v1.42)
                if not re.search(pat, h):
                    continue
                span = _find_generic_card(h, pat)
                if not span:
                    continue
                if page is None:
                    page = _fetch_file(cfg, path) or ""
                    title, excerpt = _post_meta_from_html(page)
                    # v1.47.6: page date first, first-commit fallback — git
                    # "first commit" follows renames on GitLab and stamped
                    # months-early dates on repaired cards. Unknown -> leave
                    # the card's date untouched ("" = no date swap).
                    date_lbl = _post_date_label(cfg, path, page)
                card = h[span[0]:span[1]]
                ex_ok = (not excerpt or excerpt[:60] in card
                         or _html40.escape(excerpt)[:60] in card)
                # v1.44: a card can have the RIGHT excerpt but the WRONG date
                # (every JP card said "July 14" after the flood era) — repair
                # whenever the visible date disagrees with the commit date too.
                date_ok = (not date_lbl or date_lbl in card
                           or not re.search(r"(>|\u00b7\s*)[A-Z][a-z]+ \d{1,2}, \d{4}",
                                            card))
                if ex_ok and date_ok:
                    continue              # card already tells the truth
                new_card = _rewrite_card(card, title=title, url=rel, excerpt=excerpt,
                                         date_str=date_lbl, link_pat=pat)
                if new_card != card:
                    listings[lp] = h[:span[0]] + new_card + h[span[1]:]
                    repaired.append(f"{lp}: {rel}")
                    purge_urls.append(f"{meta['site']}/{lp}".replace("/index.html", "/"))
        # v1.43: homepage sections are PREVIEWS — newest N cards only.
        for lp, cap in (meta.get("preview_caps") or {}).items():
            if lp in listings:
                new_h, n = _trim_listing(listings[lp], cfg["style"], cap)
                if n:
                    listings[lp] = new_h
                    repaired.append(f"{lp}: trimmed {n} extra preview card(s)")
        # v1.47.8: the featured briefing follows the newest news edition.
        if 'class="intel-featured"' in (listings.get("index.html") or ""):
            _best48 = None
            for _p48 in [p for p in post_paths
                         if p.rsplit("/", 1)[-1].startswith("bvtech-news-")][:15]:
                _pg48 = _fetch_file(cfg, _p48)
                if not _pg48:
                    continue
                _d48 = _post_date_from_html(_pg48)
                if _d48 and (_best48 is None or _d48 > _best48[0]):
                    _best48 = (_d48, _p48, _pg48)
            if _best48:
                _d48, _p48, _pg48 = _best48
                _t48, _ex48 = _post_meta_from_html(_pg48)
                _t48 = re.sub(r"^BVTech News\s*[—-]+\s*", "", _t48)
                _t48 = re.sub(r"\s*[—-]+\s*[A-Z][a-z]+ \d{1,2}, \d{4}$", "", _t48)
                _lbl48 = f"{_MONTH_NAMES[_d48.month - 1]} {_d48.day}"
                _nh48, _ch48 = _promote_featured(
                    listings["index.html"],
                    url=_post_url_for(meta, _p48, cfg["style"]).replace(meta["site"], ""),
                    title=_t48, date_lbl=f"{_lbl48} \u00b7 daily briefing \u00b7 KEV alert",
                    excerpt=_ex48)
                if _ch48:
                    listings["index.html"] = _nh48
                    repaired.append("index.html: featured -> newest news edition")
        # v1.55.2: keep the homepage "This Week in Cybersecurity" trio (the cards
        # under the LIVE KEV ticker) pointed at the 3 NEWEST posts — and REBUILD
        # the block if the duplicate-sweeper stripped it (its intel-mini cards
        # mirror the main grid by design, so the de-spam pass used to delete them
        # and leave the section empty). Source: the /blog/ listing (newest-first).
        _home_ir = listings.get("index.html") or ""
        _blog_ls = listings.get("blog/index.html") or _fetch_file(cfg, "blog/index.html") or ""
        if '<div class="intel-grid">' in _home_ir and _blog_ls:
            _hrefs = re.findall(r'<a href="(/blog/[^"]+\.html)"[^>]*class="blog-card"',
                                _blog_ls)[:3]
            _ir_cards = []
            for _href in _hrefs:
                _pg_ir = _fetch_file(cfg, _href.lstrip("/"))
                if not _pg_ir:
                    continue
                _d_ir = _post_date_from_html(_pg_ir)
                _t_ir, _ex_ir = _post_meta_from_html(_pg_ir)
                _t_ir = re.sub(r"^BVTech News\s*[—-]+\s*", "", _t_ir).strip()
                _lbl_ir = (f"{_MONTH_NAMES[_d_ir.month - 1]} {_d_ir.day}"
                           if _d_ir else "Latest")
                _ir_cards.append(_intel_mini_card(_href, _lbl_ir, _t_ir, _ex_ir))
            if len(_ir_cards) == 3:
                _newrec = ('<div class="intel-recent">\n' + "\n".join(_ir_cards)
                           + "\n</div>")
                if '<div class="intel-recent">' in _home_ir:      # replace in place
                    _nhr = re.sub(r'<div class="intel-recent">.*?</a>\s*</div>',
                                  lambda _m: _newrec, _home_ir, count=1, flags=re.S)
                elif '<!-- Three recent cards -->' in _home_ir:   # rebuild after marker
                    _nhr = _home_ir.replace('<!-- Three recent cards -->',
                                            '<!-- Three recent cards -->\n' + _newrec, 1)
                else:                                              # rebuild into grid
                    _nhr = _home_ir.replace('<div class="intel-grid">',
                                            '<div class="intel-grid">\n' + _newrec, 1)
                if _nhr != _home_ir:
                    listings["index.html"] = _nhr
                    repaired.append("index.html: rebuilt/refreshed intel-recent -> 3 newest posts")
        for lp in list(listings):
            new_h, _n45 = _strip_empty_shells(listings[lp])
            if _n45:
                listings[lp] = new_h
                repaired.append(f"{lp}: removed {_n45} empty card shell(s)")
        changed_files = []
        for lp, h in listings.items():
            orig = _fetch_file(cfg, lp)
            if orig is not None and h != orig:
                actions.append({"action": "update", "file_path": lp, "content": h})
                changed_files.append(lp)
                purge_urls.append(f"{meta['site']}/{lp}".replace("/index.html", "/"))
        if not actions:
            if ai_misses:
                return {"ok": False,
                        "error": "listing card markup not recognized (deterministic + AI "
                                 "fallback both missed) - run the Doctor; the listing "
                                 "template needs a tweak"}
            return {"ok": True, "added": [], "detail": "listings already complete - nothing to sync"}
        commit = _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": (f"blog: sync listings - add {len(added)} missing, "
                               f"repair {len(repaired)} stale card(s) (via Pulse)"),
            "actions": actions,
        })
        conn46 = secure_config.get_platform(db, meta["provider"])
        raw46 = dict((conn46.config if conn46 else None) or {})
        _pend = list(raw46.get("pending") or [])
        _pend.append({"sha": commit.get("id"), "slug": "sync-listings",
                      "at": datetime.now(timezone.utc).isoformat(), "checks": 0})
        raw46["pending"] = _pend[-10:]
        secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing", raw46)
        from . import cloudflare
        purge = cloudflare.purge_urls(db, site, purge_urls)
        return {"ok": True, "sha": commit.get("id"), "added": added,
                "repaired": repaired, "listings_updated": changed_files,
                "cache_purged": purge.get("ok"), "cache_detail": purge.get("detail")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December")
# Slug prefixes that are PAGES, never blog posts — the duplicate sweeper must
# never consider (let alone delete) these.
_PAGE_SLUGS = ("about", "contact", "certification", "service", "pricing", "portfolio",
               "resume", "privacy", "terms", "book", "review", "case-stud", "academy")


def _intel_mini_card(url: str, date_lbl: str, title: str, excerpt: str) -> str:
    """One card for the homepage 'intel-recent' trio (under the KEV ticker)."""
    import html as _h
    ex = excerpt[:190].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…" if len(excerpt) > 190 else excerpt
    return ('<a href="' + url + '" class="intel-mini">\n'
            '<div class="intel-mini-date">' + _h.escape(date_lbl) + ' · latest</div>\n'
            '<h4>' + _h.escape(title) + '</h4>\n'
            '<p>' + _h.escape(ex) + '</p>\n</a>')


def _promote_featured(home: str, *, url: str, title: str, date_lbl: str,
                      excerpt: str) -> tuple[str, bool]:
    """Deterministically point the homepage intel-featured card at the newest
    news edition (href, headline, dateline, excerpt, generic tags). v1.47.8:
    the capped homepage no longer takes backfill, so nothing else updates it."""
    import html as _h
    m = re.search(r'<a href="([^"]*)" class="intel-featured".*?</a>', home, re.S)
    if not m:
        return home, False
    if _slug_of(url.strip("/")) == _slug_of(m.group(1).strip("/")):
        return home, False                       # already promoted
    f = m.group(0)
    f = re.sub(r'^<a href="[^"]*"', f'<a href="{url}"', f, count=1)
    f = re.sub(r"(<h3[^>]*>).*?(</h3>)",
               lambda mm: mm.group(1) + _h.escape(title) + mm.group(2),
               f, count=1, flags=re.S)
    f = re.sub(r'(intel-featured-date"[^>]*>)[^<]*(<)',
               lambda mm: mm.group(1) + date_lbl + mm.group(2), f, count=1)
    f = re.sub(r"(<p[^>]*>)[^<]{40,}?(</p>)",
               lambda mm: mm.group(1) + _h.escape(excerpt) + mm.group(2), f, count=1)
    f = re.sub(r'(<div class="intel-tags">).*?(</div>)',
               r"\1<span>CISA KEV</span><span>daily briefing</span>\2",
               f, count=1, flags=re.S)
    return home[:m.start()] + f + home[m.end():], True


def _post_date_from_html(page_html: str):
    """Best-effort publish date of a post page -> datetime.date | None."""
    from datetime import date as _date
    m = re.search(r'datetime="(\d{4})-(\d{2})-(\d{2})', page_html)
    if m:
        try:
            return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r">([A-Z][a-z]+) (\d{1,2}), (\d{4})<", page_html)
    if m and m.group(1) in _MONTH_NAMES:
        try:
            return _date(int(m.group(3)), _MONTH_NAMES.index(m.group(1)) + 1,
                         int(m.group(2)))
        except ValueError:
            return None
    return None


def _post_date_label(cfg: dict, path: str, page_html: str) -> str:
    """Truth hierarchy for a post's DISPLAY date -> "July 14, 2026" or "".
    v1.47.6: the page's own machine date (datetime attr / datePublished — the
    publisher refreshes these on every publish since v1.44) now outranks git.
    GitLab's commits-by-path API follows renames, so a June post that resembles
    a bulk-uploaded file 'first appeared' in April — every repaired card got
    stamped with a date months before the post existed. Fall back to the
    first-commit date only when the page itself carries no parseable date."""
    d = _post_date_from_html(page_html or "")
    if d is None:
        ts = _first_commit_iso(cfg, path)
        if ts:
            try:
                d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            except ValueError:
                d = None
    if d is None:
        return ""
    return f"{_MONTH_NAMES[d.month - 1]} {d.day}, {d.year}"


def _commit_span(cfg: dict, path: str) -> tuple[str | None, str | None]:
    """(oldest_iso, newest_iso) commit timestamps for `path` in ONE API call.
    v1.47.8: cleanup needs both — the oldest is rename-follow poisoned (GitLab
    matches new posts to old lookalikes), the newest says whether the file was
    touched recently at all."""
    try:
        commits = _HTTP("GET", f"{_proj_url(cfg)}/repository/commits?path="
                        f"{urllib.parse.quote_plus(path)}&ref_name={cfg['branch']}"
                        "&per_page=100", cfg["token"])
        if not commits:
            _first_commit_iso.last_error = "empty commit list"   # type: ignore[attr-defined]
            return (None, None)
        return (commits[-1].get("created_at"), commits[0].get("created_at"))
    except Exception as e:  # noqa: BLE001
        _first_commit_iso.last_error = str(e)[:200]       # type: ignore[attr-defined]
        return (None, None)


def _first_commit_iso(cfg: dict, path: str) -> str | None:
    """ISO timestamp of the FIRST commit that touched `path` — its true creation
    time. (Page-visible dates lie: skeleton-cloned pages carry the ORIGINAL
    post's date, which is exactly how the July flood hid from the sweeper.)"""
    try:
        commits = _HTTP("GET", f"{_proj_url(cfg)}/repository/commits?path="
                        f"{urllib.parse.quote_plus(path)}&ref_name={cfg['branch']}"
                        "&per_page=100", cfg["token"])
        if not commits:
            _first_commit_iso.last_error = "empty commit list"   # type: ignore[attr-defined]
            return None
        return commits[-1].get("created_at") or None      # API lists newest first
    except Exception as e:  # noqa: BLE001
        _first_commit_iso.last_error = str(e)[:200]       # type: ignore[attr-defined]
        return None


def _refresh_cloned_date(rendered: str, skeleton: str | None,
                         now: datetime | None = None) -> str:
    """The skeleton clone carries the ORIGINAL post's visible date — a post
    published July 14 rendered saying 'June 30'. Swap every copy of that EXACT
    stale date (text + datetime attrs + ISO) for today's. Exact-match only, so
    dates the new article's own prose mentions are untouched."""
    now = now or datetime.now(timezone.utc)
    old = _post_date_from_html(skeleton or "")
    if not old or old == now.date():
        return rendered
    old_txt = f"{_MONTH_NAMES[old.month - 1]} {old.day}, {old.year}"
    today_txt = f"{_MONTH_NAMES[now.month - 1]} {now.day}, {now.year}"
    rendered = rendered.replace(old_txt, today_txt)
    rendered = rendered.replace(old.isoformat(), now.date().isoformat())
    return rendered


def _slug_href_pat(slug: str) -> str:
    """Match a post link by SLUG in ANY href form — relative ("/slug/"),
    absolute ("https://site/slug/"), or blog-file ("blog/slug.html"). Listings
    accumulated MIXED forms over time, and exact-string matching is exactly how
    duplicate cards multiplied (a post 'already listed' under another form was
    re-injected on every sync)."""
    return r'href="[^"]*/' + re.escape(slug) + r'(?:/|\.html)?"'


def _slug_of(url_or_path: str) -> str:
    """Trailing slug of a post URL or repo path — "…/slug/", "…/slug.html",
    AND the slug-folder repo form "slug/index.html" (the index file is the
    page, the FOLDER is the slug)."""
    s = url_or_path.rstrip("/")
    if s.endswith("/index.html"):
        s = s[: -len("/index.html")]
    s = s.rsplit("/", 1)[-1]
    return s[:-5] if s.endswith(".html") else s


def _slug_listed(h: str, slug: str) -> bool:
    return bool(re.search(_slug_href_pat(slug), h))


def _remove_card(h: str, slug: str) -> tuple[str, bool]:
    """Delete EVERY card linking to `slug` from a listing page — matching any
    href form (relative or absolute)."""
    changed = False
    pat = _slug_href_pat(slug)
    for _ in range(30):                   # flood-duplicated cards: remove all
        if not re.search(pat, h):
            break
        span = _find_generic_card(h, pat)
        if not span:
            break
        h = h[:span[0]] + h[span[1]:]
        changed = True
    return h, changed


def _all_card_spans(h: str, link_pat: str) -> list[tuple[int, int]]:
    """Source spans of every post card on a listing page, in page order."""
    spans: list[tuple[int, int]] = []
    off = 0
    for _ in range(400):
        seg = h[off:]
        m = re.search(link_pat, seg)
        if not m:
            break
        # v1.43.1: nav/menu/page links match the post pattern but are NOT
        # cards — SKIP them and keep scanning. Breaking on the first one made
        # the homepage trim silently see zero cards (the wall stayed).
        slug = _slug_of(m.group(0)[6:-1])
        if slug == "index" or any(slug.startswith(p) for p in _PAGE_SLUGS):
            off += m.end()
            continue
        span = _find_generic_card(seg, link_pat)
        if not span:
            off += m.end()
            continue
        spans.append((off + span[0], off + span[1]))
        off += span[1]
    return spans


def _trim_listing(h: str, style: str, keep: int, file_dir: str = "blog") -> tuple[str, int]:
    """v1.43: PREVIEW listings (the homepage blog section) keep only the newest
    `keep` cards — the full archive lives on /blog/. Cards are newest-first, so
    everything after the first `keep` is removed. Returns (html, n_removed)."""
    spans = _all_card_spans(h, _link_pat_for(style, file_dir))
    if len(spans) <= keep:
        return h, 0
    # v1.47.4: SECTION-AWARE - the homepage has multiple card sections (a small
    # featured strip + the big archive wall). Cluster cards by proximity and
    # trim ONLY the largest cluster; small featured sections are never touched
    # (the cap once ate the This Week in Cybersecurity feature - never again).
    clusters: list[list[tuple[int, int]]] = [[spans[0]]]
    for sp in spans[1:]:
        if sp[0] - clusters[-1][-1][1] < 2500:
            clusters[-1].append(sp)
        else:
            clusters.append([sp])
    big = max(clusters, key=len)
    if len(big) <= keep:
        return h, 0
    for s, e in reversed(big[keep:]):
        h = h[:s] + h[e:]
    return h, len(big) - keep


def _strip_empty_shells(h: str) -> tuple[str, int]:
    """v1.45: card removal can leave HOLLOW WRAPPERS behind (empty divs/
    articles/li that render as bare divider lines down the page). Remove
    elements with no text and no children, iterating until stable. Elements
    with an id= are spared (functional placeholders)."""
    n = 0
    pat = re.compile(r"<(div|article|li|section|span|p)\b(?![^>]*\bid=)[^>]*>(?:\s|&nbsp;)*</\1>")
    for _ in range(30):
        h2, k = pat.subn("", h)
        if not k:
            break
        h, n = h2, n + k
    return h, n


def _dedupe_cards(h: str, slug: str) -> tuple[str, int]:
    """Keep the FIRST card linking to `slug`; remove every later duplicate card
    (the 'same card repeated down the whole page' spam). Returns (html, n)."""
    pat = _slug_href_pat(slug)
    first = _find_generic_card(h, pat)
    if not first:
        return h, 0
    removed = 0
    for _ in range(30):
        tail = h[first[1]:]
        if not re.search(pat, tail):
            break
        span = _find_generic_card(tail, pat)
        if not span:
            break
        h = h[:first[1] + span[0]] + h[first[1] + span[1]:]
        removed += 1
    return h, removed


def cleanup_duplicate_posts(db: Session, site: str, *, days: int = 3,
                            now: datetime | None = None, debug: bool = False) -> dict:
    """v1.40 FLOOD REPAIR: enforce ONE post per calendar day on the live site.
    Same-day extras (beyond the earliest-committed post) are deleted from the
    repo AND their cards removed from the listings — one commit, cache purged.
    Pages (about/contact/...) are never candidates. Idempotent: with no
    duplicates it changes nothing."""
    meta = SITES[site]
    cfg = get_config(db, site)
    if not cfg["configured"]:
        return {"ok": False, "error": f"{meta['site']} not connected"}
    if cfg.get("forge") == "github" or detect_layout(cfg)["format"] == "markdown":
        return {"ok": True, "removed": [],
                "detail": "generated/GitHub site - the build owns its listings"}
    now = now or datetime.now(timezone.utc)
    try:
        from datetime import timedelta
        window = {now.date() - timedelta(days=i) for i in range(days)}
        # v1.47.8: a post's "day" is its OWN page date first (the publisher
        # refreshes it on every publish since v1.44), first-commit only as a
        # fallback — GitLab's commits-by-path follows renames, so a brand-new
        # post can "first appear" on an old lookalike's date. That poisoned
        # grouping deleted a freshly published JP post two minutes after it
        # went live. News editions (bvtech-news-*) are their OWN channel: a
        # briefing and a blog post legally share a day, never dedupe across.
        by_day: dict = {}
        stamps: dict = {}
        scan: list[str] = []                     # debug: per-path dating evidence
        for path in _list_post_paths(cfg, cfg["style"])[:80]:
            slug_root = (path.rsplit("/", 1)[-1] if cfg["style"] == "blog-file"
                         else path.split("/")[0])
            if any(slug_root.startswith(p) for p in _PAGE_SLUGS):
                continue
            _first_commit_iso.last_error = ""    # type: ignore[attr-defined]
            first_ts, last_ts = _commit_span(cfg, path)
            if not first_ts:
                scan.append(f"{path} -> NO-DATE "
                            f"({getattr(_first_commit_iso, 'last_error', '')})")
                continue
            try:
                first_d = datetime.fromisoformat(first_ts.replace("Z", "+00:00")).date()
                last_d = datetime.fromisoformat((last_ts or first_ts).replace("Z", "+00:00")).date()
            except ValueError:
                scan.append(f"{path} -> UNPARSEABLE ({first_ts[:32]})")
                continue
            if first_d not in window and last_d not in window:
                scan.append(f"{path} -> {first_d.isoformat()} (untouched, outside window)")
                continue                      # floods are recent; skip the page fetch
            page = _fetch_file(cfg, path) or ""
            pd = _post_date_from_html(page)
            d = pd or first_d
            scan.append(f"{path} -> {d.isoformat()}"
                        + (" (page date)" if pd else " (commit date)")
                        + ("" if d in window else " (outside window)"))
            if d not in window:
                continue
            stamps[path] = first_ts
            channel = "news" if slug_root.startswith("bvtech-news") else "post"
            by_day.setdefault((channel, d), []).append(path)
        removed, actions, purge_urls = [], [], []
        listings = {lp: _fetch_file(cfg, lp) for lp in meta.get("index_paths", ())}
        listings = {lp: h for lp, h in listings.items() if h is not None}
        # v1.55.2 SHIELD: the homepage "This Week in Cybersecurity" trio (the
        # intel-mini cards under the KEV ticker) POINT AT the same 3 newest posts
        # the main archive wall shows — by design. The de-spam/dedupe passes below
        # treat that as "the same card repeated down the page" and delete the whole
        # intel-recent block, freezing the section. Stash it out of every listing
        # before the sweep and stitch it back verbatim afterwards; the sync pass
        # (rebuild-if-missing) owns keeping its contents current.
        _shielded: dict = {}
        for _lp_sh in list(listings):
            _m_sh = re.search(r'<div class="intel-recent">.*?</a>\s*</div>',
                              listings[_lp_sh], re.S)
            if _m_sh:
                _tok_sh = f"<!--PULSE_INTEL_SHIELD_{_lp_sh}-->"
                _shielded[_lp_sh] = (_tok_sh, _m_sh.group(0))
                listings[_lp_sh] = (listings[_lp_sh][:_m_sh.start()] + _tok_sh
                                    + listings[_lp_sh][_m_sh.end():])
        for (_ch48, d), paths in sorted(by_day.items()):
            if len(paths) <= 1:
                continue
            # Keep the day's EARLIEST-committed post; everything after is flood.
            paths.sort(key=lambda p: stamps[p])
            for p in paths[1:]:
                actions.append({"action": "delete", "file_path": p})
                url = _post_url_for(meta, p, cfg["style"])
                for lp in list(listings):
                    new_h, ch = _remove_card(listings[lp], _slug_of(p))
                    if ch:
                        listings[lp] = new_h
                removed.append(url)
                purge_urls.append(url)
        # v1.42: DE-SPAM pass — a post gets at most ONE card per listing. (The
        # old exact-string listed-check re-injected posts whose existing card
        # used a different href form, repeating the same card down the page.)
        cards_deduped = 0
        for path in _list_post_paths(cfg, cfg["style"])[:80]:
            for lp in list(listings):
                new_h, n = _dedupe_cards(listings[lp], _slug_of(path))
                if n:
                    listings[lp] = new_h
                    cards_deduped += n
        # v1.43: GHOST cards — cards whose post no longer exists in the repo
        # (deleted flood files whose cards survived under another href form)
        # link straight to 404s; remove them everywhere. Own-site links only,
        # never pages/nav.
        site_host = meta["site"].split("//", 1)[1]
        if cfg["style"] == "blog-file":
            ghost_rx = (r'href="[^"]*/' + re.escape(cfg.get("file_dir", "blog"))
                        + r'/([a-z0-9\-]+)\.html"')
        else:
            ghost_rx = (r'href="(?:https?://' + re.escape(site_host)
                        + r')?/([a-z0-9\-]{6,})/"')
        repo_slugs = {_slug_of(p) for p in _list_post_paths(cfg, cfg["style"])}
        ghost_cards = 0
        for lp in list(listings):
            h = listings[lp]
            for gslug in set(re.findall(ghost_rx, h)):
                if (gslug in repo_slugs or gslug == "index"
                        or any(gslug.startswith(pfx) for pfx in _PAGE_SLUGS)):
                    continue
                new_h, ch = _remove_card(h, gslug)
                if ch:
                    h = new_h
                    ghost_cards += 1
            listings[lp] = h
        # v1.43: PREVIEW cap — the homepage blog section keeps only the newest
        # N cards (the full archive lives on /blog/). This shrinks the
        # "100 writings on the main page" flood in the same commit.
        for lp, cap in (meta.get("preview_caps") or {}).items():
            if lp in listings:
                new_h, n = _trim_listing(listings[lp], cfg["style"], cap)
                if n:
                    listings[lp] = new_h
                    cards_deduped += n
        for lp in list(listings):
            new_h, n = _strip_empty_shells(listings[lp])
            if n:
                listings[lp] = new_h
                cards_deduped += n
        # v1.55.2 SHIELD (restore): stitch the intel-recent trio back in exactly
        # where it was, now that the dedupe/ghost/trim passes are done.
        for _lp_sh, (_tok_sh, _blk_sh) in _shielded.items():
            if _lp_sh in listings and _tok_sh in listings[_lp_sh]:
                listings[_lp_sh] = listings[_lp_sh].replace(_tok_sh, _blk_sh, 1)
        if not removed and not cards_deduped and not ghost_cards:
            out = {"ok": True, "removed": [], "cards_deduped": 0,
                   "detail": "no same-day duplicates found"}
            if debug:
                out["scan"] = scan
            return out
        for lp, h in listings.items():
            orig = _fetch_file(cfg, lp)
            if orig is not None and h != orig:
                actions.append({"action": "update", "file_path": lp, "content": h})
                purge_urls.append(f"{meta['site']}/{lp}".replace("/index.html", "/"))
        if not actions:
            return {"ok": True, "removed": [], "cards_deduped": 0,
                    "detail": "no changes needed"}
        commit = _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": (f"blog: remove {len(removed)} duplicate post(s), "
                               f"{cards_deduped} duplicate/extra card(s), "
                               f"{ghost_cards} ghost card(s) "
                               "(1-post-per-day flood guard, via Pulse)"),
            "actions": actions,
        })
        conn46 = secure_config.get_platform(db, meta["provider"])
        raw46 = dict((conn46.config if conn46 else None) or {})
        _pend = list(raw46.get("pending") or [])
        _pend.append({"sha": commit.get("id"), "slug": "flood-cleanup",
                      "at": datetime.now(timezone.utc).isoformat(), "checks": 0})
        raw46["pending"] = _pend[-10:]
        secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing", raw46)
        from . import cloudflare
        purge = cloudflare.purge_urls(db, site, purge_urls or [f"{meta['site']}/"])
        try:
            db.add(Notification(
                client_id=None, target_user_id=None, kind="content", severity="info",
                message=(f"🧹 Flood guard: {meta['site']} — removed {len(removed)} same-day "
                         f"duplicate post(s) (first of each day kept), {cards_deduped} "
                         f"repeated/extra listing card(s) and {ghost_cards} dead-link "
                         "card(s). Cache purged.")[:1000]))
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        out = {"ok": True, "sha": commit.get("id"), "removed": removed,
               "cards_deduped": cards_deduped, "ghost_cards": ghost_cards,
               "cache_purged": purge.get("ok")}
        if debug:
            out["scan"] = scan
        return out
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


def sweep_duplicates(db: Session, now: datetime | None = None) -> dict:
    """Heartbeat hook: self-healing content hygiene for both sites, at most
    once per hour per site — (1) delete same-day duplicate posts, then
    (2) sync the listings (backfill unlisted posts + repair stale cloned
    cards). Idempotent no-ops when the sites are clean; zero clicks ever."""
    from ..core.config import get_settings
    ver = get_settings().APP_VERSION
    now = now or datetime.now(timezone.utc)
    out: dict = {}
    for sk, meta in SITES.items():
        if not meta.get("sweep", True):
            continue                      # listing-only pseudo-sites: never sync
        conn = secure_config.get_platform(db, meta["provider"])
        raw = (conn.config if conn else None) or {}
        if not configured(db, sk):
            continue
        # v1.41.1: a NEW DEPLOY busts the hourly cooldown — a fixed sweeper must
        # act on its first tick, not sit out a stamp its broken predecessor left.
        last = raw.get("last_dupe_sweep")
        if raw.get("last_sweep_version") == ver:
            try:
                if last and (now - datetime.fromisoformat(last)).total_seconds() < 3600:
                    continue
            except ValueError:
                pass
        res = {"cleanup": cleanup_duplicate_posts(db, sk, now=now),
               "sync": sync_listings(db, sk)}
        out[sk] = res
        for step, r in res.items():
            if isinstance(r, dict) and r.get("ok") is False:
                try:
                    db.add(Notification(
                        client_id=None, target_user_id=None, kind="content",
                        severity="warning",
                        message=(f"🧹 Flood-guard {step} hit a problem on {meta['site']}: "
                                 f"{str(r.get('error'))[:200]} - will retry next hour.")[:1000]))
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
        secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing",
                                      {"last_dupe_sweep": now.isoformat(),
                                       "last_sweep_version": ver})
    return out


def diagnose(db: Session, site: str) -> dict:
    """Publishing Doctor for one site: walk the WHOLE chain and say exactly
    what's healthy and what to fix, in plain English. Read-only."""
    meta = SITES[site]
    cfg = get_config(db, site)
    checks: list[dict] = []

    def _check(name: str, ok: bool, detail: str, fix: str | None = None):
        checks.append({"name": name, "ok": ok, "detail": detail,
                       **({"fix": fix} if (fix and not ok) else {})})

    if cfg.get("forge") == "github":
        # v1.37: this site publishes through GitHub (where Cloudflare actually
        # builds from). Token -> repo write -> engine, then done.
        v = gh_verify(db)
        _check("GitHub connection", v["ok"], v["detail"],
               "Connection Center -> bvtech.org (GitHub) -> paste a fine-grained PAT "
               "with Contents: Read and write on the site repo")
        if not v["ok"]:
            return {"site": meta["site"], "checks": checks, "healthy": False}
        layout = detect_layout(cfg)
        if layout["format"] == "markdown":
            _check("Site engine", True,
                   f"generated site ({layout['engine_file']}) - publishing markdown to "
                   f"{layout['content_dir']}/ (frontmatter cloned from "
                   f"{layout['sample_path'].rsplit('/', 1)[-1]}); the build creates the "
                   "post page AND the blog index automatically")
        else:
            _check("Site engine", False,
                   "no recognizable content folder found in the GitHub repo",
                   "expected something like src/content/blog/*.md - check the repo layout")
        from . import cloudflare
        cf = cloudflare.verify(db) if cloudflare.configured(db) else {
            "ok": False,
            "detail": "not connected - cached pages update on their own TTL (can look stale for hours)"}
        _check("Cloudflare cache purge", cf["ok"], cf["detail"],
               "Connection Center -> Cloudflare -> paste an API token (Zone:Read + Cache Purge)")
        healthy = all(c["ok"] for c in checks if not c["name"].startswith("Cloudflare cache"))
        return {"site": meta["site"], "checks": checks, "healthy": healthy}

    # v1.38 clarity: say exactly which repo this site publishes through, and —
    # if a GitHub token is stored but switched off — that GitLab is in charge.
    conn = secure_config.get_platform(db, meta["provider"])
    raw_cfg = (conn.config if conn else None) or {}
    route = f"publishing via GitLab -> {cfg['project']} (branch {cfg['branch']})"
    if secure_config.get_secret(raw_cfg, "gh_token"):
        route += "; a GitHub token is stored but github_active=no, so it is ignored"
    _check("Publish route", True, route)
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
        if changed:
            _check(f"Listing {lp}", True, "structure recognized - new posts will be inserted")
            recognized.append(lp)
        else:
            # v1.39: not deterministically parseable, but Claude clones the
            # page's own card at publish/Sync time — that's a working state.
            from . import ai as _ai_svc
            if _ai_svc.enabled():
                _check(f"Listing {lp}", True,
                       "custom card markup - Claude clones this page's own card at "
                       "publish/Sync time (validated splice; a bad answer changes nothing)")
            else:
                _check(f"Listing {lp}", False,
                       "card structure NOT recognized - new posts won't appear here",
                       "connect Claude (Connection Center) to enable AI card cloning, or "
                       "the listing template needs a tweak")
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
            if st == "none":
                # v1.39: Cloudflare can deploy a repo without reporting a GitLab
                # pipeline at all — "no pipeline" is NOT a failure. The posts
                # being live at their URLs is the real signal.
                _check("Cloudflare build", True,
                       "no pipeline reported for the last publish (Cloudflare can deploy "
                       "without one) - the post URLs being live is the real check")
            else:
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


# --------------------------------------------------------------------------- #
# v1.44 LIVE CISA-KEV ticker — bvtech.org's homepage marquee gets TODAY's real
# exploited-vulnerability entries, once per day. Data straight from CISA's
# public KEV feed; the markup edit is Claude-templated and hard-validated
# (anchor must exist, new block must carry the real CVE ids, sane size) — a
# bad answer changes nothing.
# --------------------------------------------------------------------------- #
KEV_FEED_URL = ("https://www.cisa.gov/sites/default/files/feeds/"
                "known_exploited_vulnerabilities.json")


def _fetch_kev(limit: int = 5) -> list[dict]:
    req = urllib.request.Request(KEV_FEED_URL, headers={"User-Agent": "BVTech-OpsPilot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    vulns = sorted(data.get("vulnerabilities", []),
                   key=lambda v: v.get("dateAdded", ""), reverse=True)
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=15)).isoformat()
    recent = [v for v in vulns if (v.get("dateAdded") or "") >= cutoff]
    vulns = (recent or vulns)[:max(limit, len(recent[:10]))]
    return [{"cve": v.get("cveID"), "name": v.get("vulnerabilityName"),
             "vendor": v.get("vendorProject"), "product": v.get("product"),
             "added": v.get("dateAdded"), "due": v.get("dueDate")} for v in vulns]


_KEV_FETCH = _fetch_kev   # test seam



def _notify_ticker(db: Session, raw: dict, now: datetime, msg: str) -> None:
    """One ticker status notification per day (success or failure) - the
    marquee can never fail silently again."""
    try:
        if raw.get("last_kev_note") == now.date().isoformat():
            return
        raw["last_kev_note"] = now.date().isoformat()
        secure_config.upsert_platform(db, SITES["bvtech"]["provider"],
                                      SITES["bvtech"]["name"], "Publishing", raw)
        db.add(Notification(client_id=None, target_user_id=None, kind="content",
                            severity="info", message=msg[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

def update_kev_ticker(db: Session, now: datetime | None = None) -> dict:
    """Refresh the homepage 'LIVE - CISA KEV FEED' marquee with the last 15
    days of real KEV entries. DETERMINISTIC (v1.47.5): the ticker's markup is
    known exactly (<div class="intel-ticker-scroll"> of tk-item/tk-sep spans,
    duplicated for the seamless scroll) - both tracks are rebuilt in place.
    Once per day, stamped; every failure notifies."""
    now = now or datetime.now(timezone.utc)
    meta = SITES["bvtech"]
    cfg = get_config(db, "bvtech")
    if not cfg["configured"]:
        return {"ok": False, "error": "bvtech.org not connected"}
    conn = secure_config.get_platform(db, meta["provider"])
    raw = dict((conn.config if conn else None) or {})
    if raw.get("last_kev_ticker") == now.date().isoformat():
        return {"ok": True, "detail": "ticker already updated today"}
    try:
        kev = _KEV_FETCH(12)
        if not kev:
            return {"ok": False, "error": "CISA KEV feed returned nothing"}
        home = _fetch_file(cfg, "index.html")
        if not home:
            return {"ok": False, "error": "index.html not found"}
        tracks = list(re.finditer(r'(<div class="intel-ticker-scroll"[^>]*>)(.*?)(</div>)',
                                  home, re.S))
        if not tracks:
            _notify_ticker(db, raw, now, "\u26a0\ufe0f KEV marquee: intel-ticker-scroll div not found")
            return {"ok": False, "error": "intel-ticker-scroll not found on homepage"}
        mons = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        items = []
        for v in kev:
            try:
                _y, _m, _d = (v.get("added") or "").split("-")
                lbl = f"{mons[int(_m) - 1]} {int(_d)}"
            except Exception:  # noqa: BLE001
                lbl = ""
            prod = f"{v.get('vendor', '')} {v.get('product', '')}".strip()[:40]
            name = (v.get("name") or "").replace(v.get("vendor") or "", "").replace(
                v.get("product") or "", "").strip(" -")[:42]
            items.append(f'<span class="tk-item tk-crit">{lbl} \u00b7 <strong>{v["cve"]}</strong> '
                         f"{prod} \u2014 {name} \u00b7 <em>CISA KEV</em></span>")
        body = ("\n          "
                + '\n          <span class="tk-sep">\u25cf</span>\n          '.join(items)
                + "\n        ")
        for m in reversed(tracks):
            home = home[:m.start(2)] + body + home[m.end(2):]
        _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": f"homepage: refresh LIVE CISA KEV ticker ({kev[0]['cve']}, via Pulse)",
            "actions": [{"action": "update", "file_path": "index.html", "content": home}]})
        from . import cloudflare
        cloudflare.purge_urls(db, "bvtech", [f"{meta['site']}/"])
        raw["last_kev_ticker"] = now.date().isoformat()
        secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing", raw)
        _notify_ticker(db, raw, now, f"\u2705 KEV marquee updated: {', '.join(k['cve'] for k in kev[:3])}\u2026")
        return {"ok": True, "cves": [k["cve"] for k in kev]}
    except Exception as e:  # noqa: BLE001
        _notify_ticker(db, raw, now, f"\u26a0\ufe0f KEV marquee update FAILED: {str(e)[:180]} - retrying every 2 min")
        return {"ok": False, "error": str(e)[:300]}
