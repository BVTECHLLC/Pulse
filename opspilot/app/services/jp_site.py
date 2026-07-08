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
           "content_classes": ("content",)},
    "bvtech": {"provider": "bvtech_site", "name": "BVTech.org Site",
               "default_project": "bvtechllc-group/bvtech-website-new",
               "style": "blog-file", "site": "https://bvtech.org",
               "org": "BVTech LLC", "author_url": "https://bvtech.org",
               "content_classes": None},
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
        commit = _HTTP("POST", f"{_proj_url(cfg)}/repository/commits", cfg["token"], {
            "branch": cfg["branch"],
            "commit_message": f"blog: {post.get('title', slug)[:80]} (via Pulse)",
            "actions": [{"action": "create", "file_path": file_path,
                         "content": rendered}],
        })
        sha = commit.get("id")
        conn = secure_config.get_platform(db, meta["provider"])
        raw = dict((conn.config if conn else None) or {})
        pending = list(raw.get("pending") or [])
        pending.append({"sha": sha, "slug": slug,
                        "at": datetime.now(timezone.utc).isoformat(), "checks": 0})
        raw["pending"] = pending[-10:]
        secure_config.upsert_platform(db, meta["provider"], meta["name"], "Publishing", raw)
        return {"ok": True, "sha": sha, "slug": slug, "url": public_url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


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
