"""v1.20 jordanpolasek.com publisher — in-app, verified, self-healing.

The old pipeline was a box-side cron: Claude writes a post, a script commits it
to the GitLab repo, Cloudflare Workers Builds deploys — and when that external
build FAILS (the red "Pipeline has failed" emails), nothing notices and nothing
recovers. This service brings the whole loop into Pulse:

  1. publish(post)      — clone the newest post's HTML as a skeleton (so the
                          site's real header/footer/CSS carry over), transplant
                          the new content, and commit `<slug>/index.html` via
                          the GitLab API. No box, no cron, no git checkout.
  2. verify_pending()   — heartbeat: check the GitLab pipeline status for each
                          commit we pushed. Cloudflare Workers Builds reports
                          into that pipeline, so a failed deploy is VISIBLE:
                          Pulse auto-REVERTS the commit (site stays green) and
                          raises a notification with the pipeline link.

Config lives in the vault (provider "jp_site"): project path, a GitLab token
(api scope), branch. HTTP is behind a seam (_HTTP) so all logic tests offline.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Notification
from . import secure_config

PROVIDER = "jp_site"
DEFAULT_BASE = "https://gitlab.com"


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


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {
        "base": (cfg.get("base") or DEFAULT_BASE).rstrip("/"),
        "project": cfg.get("project") or "",              # e.g. BVTECHLLC-group/jordanpolasek-website
        "branch": cfg.get("branch") or "main",
        "token": secure_config.get_secret(cfg, "token"),
        "pending": cfg.get("pending") or [],               # commits awaiting build verification
        "configured": bool(cfg.get("project") and secure_config.get_secret(cfg, "token")),
    }


def save_config(db: Session, *, project: str | None = None, token: str | None = None,
                branch: str | None = None, base: str | None = None) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = dict((conn.config if conn else None) or {})
    if project is not None:
        cfg["project"] = project.strip()
    if token:
        cfg["token"] = token.strip()          # is_secret_key -> encrypted at rest
    if branch is not None:
        cfg["branch"] = branch.strip() or "main"
    if base is not None:
        cfg["base"] = base.strip() or DEFAULT_BASE
    secure_config.upsert_platform(db, PROVIDER, "JordanPolasek.com Site", "Publishing", cfg)
    out = get_config(db)
    return {"configured": out["configured"], "project": out["project"], "branch": out["branch"]}


def configured(db: Session) -> bool:
    return get_config(db)["configured"]


def _proj_url(cfg: dict) -> str:
    return f"{cfg['base']}/api/v4/projects/{urllib.parse.quote_plus(cfg['project'])}"


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "post").lower()).strip("-")
    return s[:70] or "post"


def _newest_post_skeleton(cfg: dict) -> str | None:
    """Fetch the most recent post's index.html to clone header/footer/CSS from."""
    tree = _HTTP("GET", f"{_proj_url(cfg)}/repository/tree?ref={cfg['branch']}&per_page=100",
                 cfg["token"])
    dirs = [t["path"] for t in tree if t.get("type") == "tree"
            and not t["path"].startswith((".", "_", "assets", "static", "css", "js", "img"))]
    for d in sorted(dirs, reverse=True):   # newest slug-folders tend to sort late; try each
        try:
            f = _HTTP("GET", f"{_proj_url(cfg)}/repository/files/"
                      f"{urllib.parse.quote_plus(d + '/index.html')}?ref={cfg['branch']}",
                      cfg["token"])
            import base64
            return base64.b64decode(f["content"]).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
    return None


def publish(db: Session, post: dict) -> dict:
    """Commit `<slug>/index.html` to the JP repo. Returns {ok, sha, url, slug}.
    `post` = {title, html (article body), excerpt?}. Raises nothing — errors
    come back as {ok: False, error}."""
    cfg = get_config(db)
    if not cfg["configured"]:
        return {"ok": False, "error": "jp_site not configured (project + token)"}
    slug = post.get("slug") or _slugify(post.get("title") or "")
    try:
        skeleton = _newest_post_skeleton(cfg)
        from . import content_studio
        rendered = content_studio.render(
            {**post, "slug": slug,
             "site": "https://jordanpolasek.com", "org": "Jordan Polasek",
             "author_url": "https://jordanpolasek.com"},
            skeleton_html=skeleton, content_classes=["content"])
        commit = _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": f"blog: {post.get('title', slug)[:80]} (via Pulse)",
            "actions": [{"action": "create", "file_path": f"{slug}/index.html",
                         "content": rendered}],
        })
        sha = commit.get("id")
        # Track for build verification on the next heartbeat ticks.
        conn = secure_config.get_platform(db, PROVIDER)
        raw = dict((conn.config if conn else None) or {})
        pending = list(raw.get("pending") or [])
        pending.append({"sha": sha, "slug": slug, "at": datetime.now(timezone.utc).isoformat(),
                        "checks": 0})
        raw["pending"] = pending[-10:]
        secure_config.upsert_platform(db, PROVIDER, "JordanPolasek.com Site", "Publishing", raw)
        return {"ok": True, "sha": sha, "slug": slug,
                "url": f"https://jordanpolasek.com/{slug}/"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


MAX_CHECKS = 20   # ~40 min of heartbeat ticks before we stop waiting


def verify_pending(db: Session, now: datetime | None = None) -> list[dict]:
    """Heartbeat: check the deploy pipeline for each pending commit. A FAILED
    pipeline (that's the Cloudflare Workers build) triggers an automatic REVERT
    commit + a notification with the reason — the site never sits broken and
    the operator always hears about it."""
    cfg = get_config(db)
    if not cfg["configured"] or not cfg["pending"]:
        return []
    results = []
    keep = []
    for p in cfg["pending"]:
        try:
            pipes = _HTTP("GET", f"{_proj_url(cfg)}/pipelines?sha={p['sha']}", cfg["token"])
            status = pipes[0].get("status") if pipes else None
        except Exception:  # noqa: BLE001
            status = None
        if status in ("success",):
            results.append({"sha": p["sha"], "slug": p.get("slug"), "status": "success"})
            continue   # done — drop from pending
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
                    client_id=None, target_user_id=None, kind="content", severity="warning",
                    message=(f"🛑 jordanpolasek.com deploy FAILED for '{p.get('slug')}' "
                             f"(commit {str(p['sha'])[:8]}). "
                             f"{'Commit auto-reverted — the site stays on the last good build. ' if reverted else 'Auto-revert failed — revert manually. '}"
                             f"Pulse will write a fresh post on the next daily run.")[:1000]))
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            results.append({"sha": p["sha"], "slug": p.get("slug"),
                            "status": "failed", "reverted": reverted})
            continue
        # still running / not visible yet — keep watching (bounded)
        p = dict(p)
        p["checks"] = int(p.get("checks") or 0) + 1
        if p["checks"] < MAX_CHECKS:
            keep.append(p)
        else:
            results.append({"sha": p["sha"], "slug": p.get("slug"), "status": "unknown"})
    conn = secure_config.get_platform(db, PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    raw["pending"] = keep
    secure_config.upsert_platform(db, PROVIDER, "JordanPolasek.com Site", "Publishing", raw)
    return results
