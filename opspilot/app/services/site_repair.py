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

REPAIR_EPOCH = "1.99.0"          # bump to re-run the one-time repair after a future fix
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
             "author_url": meta["author_url"]}, chrome)
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


def run_full_repair(db: Session) -> str:
    """All four steps; never raises; returns the plain-text report it emails."""
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
    rp = step("2. Damaged post pages", lambda: repair_posts(db, "bvtech"))
    step("3. Listings self-heal", lambda: jp_site.listings_self_heal(db, force=True))
    step("4. Audit", lambda: "\n" + site_audit.bvtech_report(db))
    ai_ok = isinstance(st, dict) and st.get("ok")
    headline = (f"AI writing {'WORKS' if ai_ok else 'FAILING: ' + str(st.get('error'))[:120]}; "
                f"{rp.get('repaired', 0) if isinstance(rp, dict) else 0} damaged post page(s) re-rendered.")
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
