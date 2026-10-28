"""One-time, hands-off bvtech.org repair (v1.99) — runs itself and emails a report.

Triggered by the heartbeat once per REPAIR_EPOCH (in a background thread, so
publishing is never blocked): nobody has to paste terminal commands.

  1. AI self-test        - exactly why AI writing was failing (or that it works).
  2. Damaged posts       - pages Pulse published by cloning the alphabetically
                           "newest" post kept that post's breadcrumb/date/tags
                           and, when its body had a nested box, the rest of its
                           OLD article. Pulse always inserted the real body
                           after a `<p class="meta">By … · date</p>` marker, so
                           a real HTML parser recovers it exactly; the page is
                           re-rendered clean in the site's own chrome.
                           Hand-written posts (no marker) are never touched.
  3. Listings            - jp_site.listings_self_heal(force=True).
  4. Audit               - site_audit.bvtech_report.
Then: one email to help@bvtech.org + a dashboard notification.
"""
from __future__ import annotations

import html as _html
import os
import re
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

REPAIR_EPOCH = "1.108.0"         # bump to re-run the one-time repair after a future fix
MARKER = '<p class="meta">By '
_PROVIDER = "site_repair"
_lock = threading.Lock()


def _recover(page: str) -> dict | None:
    """Pull the real post back out of a damaged page. None = leave it alone."""
    from .content_studio import element_inner_span
    if MARKER not in page or 'class="pulse-post"' in page:
        return None                               # hand-written, or already clean
    span = element_inner_span(page, marker=MARKER)
    if not span:
        return None
    inner = page[span[0]:span[1]]
    m = re.match(r'\s*<p class="meta">By (.*?) · ([A-Za-z]+ \d{1,2}, \d{4})</p>\s*', inner, re.S)
    if not m:
        return None
    body = inner[m.end():].strip()
    if len(re.sub(r"<[^>]+>", "", body)) < 200:
        return None                               # not confident we found the body
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    t = re.search(r"<title>(.*?)</title>", page, re.S)
    title = _html.unescape(re.sub(r"<[^>]+>", "", (h1 or t).group(1)).strip()) if (h1 or t) else ""
    if not h1 and " | " in title:
        title = title.split(" | ")[0]
    desc = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', page)
    from .jp_site import _date_from_text
    d = _date_from_text(m.group(2))
    return {"title": title, "author": _html.unescape(m.group(1)).strip(),
            "date": d.isoformat() if d else None, "html": body,
            "description": _html.unescape(desc.group(1)) if desc else ""}


def repair_posts(db: Session, site: str = "bvtech", batch: int = 25) -> dict:
    from . import content_studio
    from . import jp_site as J
    meta = J.SITES[site]
    cfg = J.get_config(db, site)
    if not cfg["configured"]:
        return {"ok": False, "error": "not connected"}
    chrome = J._fetch_file(cfg, meta.get("chrome_page", "blog/index.html"))
    if not chrome:
        return {"ok": False, "error": "no chrome page (blog/index.html)"}
    fdir = cfg.get("file_dir", "blog")
    fixed, skipped, files = [], 0, {}
    for path in J._list_post_paths(cfg, cfg["style"]):
        page = J._fetch_file(cfg, path)
        rec = _recover(page or "")
        if not rec:
            skipped += 1
            continue
        slug = J._slug_of(path)
        out = content_studio.render_in_chrome(
            {**rec, "slug": slug, "site": meta["site"], "org": meta["org"],
             "author_url": meta["author_url"],
             "modified": datetime.now(timezone.utc).date().isoformat()}, chrome)
        files[path] = out
        fixed.append(slug)
    commits = 0
    paths = list(files)
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        J._HTTP("POST", f"{J._proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": f"blog: re-render {len(chunk)} damaged post page(s) clean "
                              "in site chrome (via Pulse repair)",
            "actions": [{"action": "update", "file_path": p, "content": files[p]}
                        for p in chunk]})
        commits += 1
    if fixed:
        from . import cloudflare
        cloudflare.purge_urls(db, site, [f"{meta['site']}/{fdir}/{s}.html" for s in fixed[:30]]
                              + [f"{meta['site']}/{fdir}/"])
    return {"ok": True, "repaired": len(fixed), "untouched": skipped, "commits": commits,
            "examples": fixed[:5]}


def _page_title(page: str) -> str:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    if h1:
        return _html.unescape(re.sub(r"<[^>]+>", "", h1.group(1)).strip())
    t = re.search(r"<title>(.*?)</title>", page, re.S)
    return _html.unescape(t.group(1).split(" | ")[0].strip()) if t else ""


def _page_date(page: str):
    from datetime import date
    m = re.search(r'"datePublished":\s*"(\d{4})-(\d{2})-(\d{2})', page)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def regenerate_posts(db: Session, site: str = "bvtech", batch: int = 25) -> dict:
    """v1.100: rebuild pages whose body was NEVER inserted. bvtech.org posts were
    cloned from an April 26 article whose markup had no content wrapper, so the
    new body had nowhere to go: the page kept only the new title over the old
    article - no Pulse marker, nothing to recover. The content is re-derived
    instead, exactly as it was composed:
      news editions (bvtech-news-*) - the deterministic KEV composer over the
        CISA catalog AS OF the edition's own date (kev_as_of);
      other posts - the article Pulse stored when it published (BlogPost by URL,
        then title), else the evergreen library entry with that title.
    Pages Pulse rendered successfully (marker) or already clean, and anything
    whose content can't be re-derived (hand-written posts) are left alone."""
    from . import content_autopilot as CA
    from . import content_studio
    from . import jp_site as J
    from ..models import BlogPost
    meta = J.SITES[site]
    cfg = J.get_config(db, site)
    if not cfg["configured"]:
        return {"ok": False, "error": "not connected"}
    chrome = J._fetch_file(cfg, meta.get("chrome_page", "blog/index.html"))
    if not chrome:
        return {"ok": False, "error": "no chrome page (blog/index.html)"}
    fdir = cfg.get("file_dir", "blog")
    today = datetime.now(timezone.utc).date().isoformat()   # honest dateModified
    feed = None
    evergreen = {t["title"]: t for t in CA._BV_EVERGREEN}
    files, rebuilt, skipped, title_changed = {}, [], 0, []
    for path in J._list_post_paths(cfg, cfg["style"]):
        page = J._fetch_file(cfg, path) or ""
        if not page or MARKER in page or "<!-- pulse:post" in page:
            skipped += 1                          # recoverable elsewhere / already native
            continue
        slug = J._slug_of(path)
        title = _page_title(page)
        if 'class="pulse-post"' in page:          # v1.99/1.100 clean page -> native layout
            from .content_studio import element_inner_span
            sp = element_inner_span(page, cls="pp-body")
            pd = _page_date(page)
            if sp and pd:
                desc = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', page)
                files[path] = content_studio.render_in_chrome(
                    {"title": title, "html": page[sp[0]:sp[1]].strip(),
                     "description": _html.unescape(desc.group(1)) if desc else "",
                     "date": pd.isoformat(), "modified": today, "slug": slug,
                     "site": meta["site"], "org": meta["org"],
                     "author_url": meta["author_url"]}, chrome)
                rebuilt.append(slug)
            else:
                skipped += 1
            continue
        url = f"{meta['site']}/{fdir}/{slug}.html"
        art = None
        if slug.startswith("bvtech-news-"):
            d = J._date_from_text(title)
            if d:
                if feed is None:
                    feed = J._KEV_FEED()
                # The 9:30 CT edition often predates CISA's same-day additions,
                # so "as of D" is usually D-1. The published title records the
                # exact lead vendors: pick the cutoff (D..D-3) that reproduces it.
                from datetime import timedelta
                now_d = datetime(d.year, d.month, d.day, 14, 30, tzinfo=timezone.utc)
                core = lambda t: re.split(r" — [A-Z][a-z]+ \d{1,2}, \d{4}", t or "")[0]
                art = None
                for back in (0, 1, 2, 3):
                    cand = CA._compose_news_deterministic(
                        now_d, J.kev_as_of(feed, d - timedelta(days=back), 6))
                    if cand and core(cand.get("title")) == core(title):
                        art = cand
                        break
                if art is None:
                    art = CA._compose_news_deterministic(
                        now_d, J.kev_as_of(feed, d - timedelta(days=1), 6))
                    if art:
                        title_changed.append(slug)
                if art:
                    art["date"] = d.isoformat()
        else:
            row = (db.query(BlogPost).filter(BlogPost.url == url, BlogPost.html.isnot(None))
                   .order_by(BlogPost.id.desc()).first()
                   or db.query(BlogPost).filter(BlogPost.title == title,
                                                BlogPost.html.isnot(None))
                   .order_by(BlogPost.id.desc()).first())
            pd = _page_date(page)
            if row and len(re.sub(r"<[^>]+>", "", row.html or "")) >= 200:
                art = {"title": title, "html": row.html, "excerpt": row.excerpt or ""}
            elif title in evergreen:
                art = CA._render_evergreen(evergreen[title], byline="BVTech LLC",
                                           cta_html=CA._BV_CTA,
                                           date_str=(pd.isoformat() if pd else ""))
            if art:
                art["date"] = pd.isoformat() if pd else None
        if not art:
            skipped += 1
            continue
        files[path] = content_studio.render_in_chrome(
            {"title": title, "html": art["html"],
             "description": (art.get("excerpt") or "")[:300], "date": art.get("date"),
             "modified": today, "tags": art.get("tags"), "crumb": art.get("crumb"),
             "slug": slug, "site": meta["site"], "org": meta["org"],
             "author_url": meta["author_url"]}, chrome)
        rebuilt.append(slug)
    commits = 0
    paths = list(files)
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        J._HTTP("POST", f"{J._proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": f"blog: rebuild {len(chunk)} post page(s) whose body was "
                              "never inserted (via Pulse repair)",
            "actions": [{"action": "update", "file_path": p, "content": files[p]}
                        for p in chunk]})
        commits += 1
    if rebuilt:
        from . import cloudflare
        cloudflare.purge_urls(db, site, [f"{meta['site']}/{fdir}/{s}.html" for s in rebuilt[:30]]
                              + [f"{meta['site']}/{fdir}/", f"{meta['site']}/news/"])
    return {"ok": True, "rebuilt": len(rebuilt), "left_alone": skipped, "commits": commits,
            "news_not_exact_match": len(title_changed), "examples": rebuilt[:5]}


def backfill_news(db: Session, days: int = 21, cap: int = 15, today=None) -> dict:
    """v1.101.1: restore daily KEV editions that are missing from bvtech.org -
    mostly ones overwritten by a later edition through the truncated-slug
    collision. Each is composed exactly as the 9:30 CT run would have on that
    day (CISA catalog as of D-1) and published under its own dated slug. Days
    with no fresh KEV additions are skipped (no filler posts)."""
    from datetime import timedelta
    from . import content_autopilot as CA
    from . import jp_site as J
    cfg = J.get_config(db, "bvtech_news")
    if not cfg["configured"]:
        return {"ok": False, "error": "not connected"}
    today = today or J.biz_now().date()
    have = set()
    for path in J._list_post_paths(cfg, cfg["style"]):
        if not J._slug_of(path).startswith("bvtech-news-"):
            continue
        d = J._date_from_text(_page_title(J._fetch_file(cfg, path) or ""))
        if d:
            have.add(d)
    feed = J._KEV_FEED()
    restored, skipped_quiet = [], 0
    for back in range(days, 0, -1):
        d = today - timedelta(days=back)
        if d in have or len(restored) >= cap:
            continue
        kev = J.kev_as_of(feed, d - timedelta(days=1), 6)
        if not kev or max(k["added"] for k in kev) < (d - timedelta(days=3)).isoformat():
            skipped_quiet += 1
            continue
        art = CA._compose_news_deterministic(
            datetime(d.year, d.month, d.day, 14, 30, tzinfo=timezone.utc), kev)
        if not art:
            continue
        res = J.publish(db, {**art, "date": d.isoformat(), "author": "Jordan Polasek"},
                        "bvtech_news")
        if res.get("ok"):
            restored.append(f"{d.isoformat()} {res.get('slug')}")
    return {"ok": True, "restored": restored, "quiet_days_skipped": skipped_quiet,
            "already_present": len(have)}


def run_full_repair(db: Session) -> str:
    """All steps; never raises; returns the plain-text report it emails."""
    from . import ai, jp_site, outbound, site_audit
    from ..models import Notification
    started = datetime.now(timezone.utc)
    parts: list[str] = [f"Pulse site repair — started {started:%Y-%m-%d %H:%M} UTC\n"]

    def step(name, fn):
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            res = {"ok": False, "error": str(e)[:300]}
        parts.append(f"== {name}\n{res}\n")
        return res

    st = step("1. AI writing self-test", ai.free_llm_selftest)
    rp = step("2. Damaged post pages (body recovered)", lambda: repair_posts(db, "bvtech"))
    rg = step("2b. Post pages with NO body (rebuilt)", lambda: regenerate_posts(db, "bvtech"))
    from . import feature_articles
    step("2c. Feature article (PHP2Shell, pinned on the homepage + /news/)",
         lambda: feature_articles.publish_php2shell(db))
    step("2d. Missing daily news editions (restored)", lambda: backfill_news(db))
    from . import destination
    step("2e. Destination release (Explore, Lightning Labs, new tools, edge API)",
         lambda: destination.publish(db))
    step("2f. Broken-link + 404 scan", lambda: destination.scan_links(db))
    step("3. Listings self-heal (+ homepage feature, schema, sitemap)",
         lambda: jp_site.listings_self_heal(db, force=True))
    step("4. Audit", lambda: "\n" + site_audit.bvtech_report(db))
    ai_ok = isinstance(st, dict) and st.get("ok")
    headline = (f"AI writing {'WORKS' if ai_ok else 'FAILING: ' + str(st.get('error'))[:120]}; "
                f"{rp.get('repaired', 0) if isinstance(rp, dict) else 0} damaged post page(s) "
                f"re-rendered, {rg.get('rebuilt', 0) if isinstance(rg, dict) else 0} rebuilt.")
    report = headline + "\n\n" + "\n".join(parts)
    try:
        db.add(Notification(client_id=None, target_user_id=None, kind="content",
                            severity="info" if ai_ok else "warning",
                            message=("🛠️ Site repair finished: " + headline)[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    try:
        fn, _ = outbound.resolve_send_fn(db)
        if fn:
            fn("help@bvtech.org", "Pulse — bvtech.org repair report", report[:60000])
    except Exception:  # noqa: BLE001
        pass
    return report


def maybe_start(db: Session) -> dict:
    """Heartbeat hook: start the one-time repair in a background thread once per
    REPAIR_EPOCH. Never blocks the tick; a stale 'running' (>3 h) is retried."""
    from . import jp_site, secure_config
    if os.environ.get("PULSE_DISABLE_SITE_REPAIR"):
        return {"started": False, "reason": "disabled"}
    if not jp_site.get_config(db, "bvtech")["configured"]:
        return {"started": False, "reason": "bvtech.org not connected"}
    conn = secure_config.get_platform(db, _PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    if raw.get("done_for") == REPAIR_EPOCH:
        return {"started": False, "reason": "already done"}
    now = datetime.now(timezone.utc)
    if raw.get("running_since"):
        try:
            if (now - datetime.fromisoformat(raw["running_since"])).total_seconds() < 3 * 3600:
                return {"started": False, "reason": "running"}
        except ValueError:
            pass
    if not _lock.acquire(blocking=False):
        return {"started": False, "reason": "running"}
    secure_config.upsert_platform(db, _PROVIDER, "Site repair", "Publishing",
                                  {"running_since": now.isoformat()})

    def _bg():
        from ..core.db import SessionLocal
        s = SessionLocal()
        try:
            report = run_full_repair(s)
            secure_config.upsert_platform(s, _PROVIDER, "Site repair", "Publishing",
                                          {"done_for": REPAIR_EPOCH, "running_since": "",
                                           "last_report": report[:20000]})
        finally:
            s.close()
            _lock.release()

    threading.Thread(target=_bg, name="pulse-site-repair", daemon=True).start()
    return {"started": True}
