"""v1.4 WordPress publisher — Pulse posts straight to bvtech.org.

Uses the WordPress REST API with an Application Password (Users → Profile →
Application Passwords in wp-admin), stored encrypted in the vault under the
`wp_site` provider:
    base_url      https://bvtech.org
    username      the wp-admin user the app password belongs to
    app_password  xxxx xxxx xxxx xxxx (spaces okay — normalized here)

Everything is stdlib; `_urlopen` is the seam tests stub. Errors surface as
WPError with the server's own reason (status + message), never swallowed.
"""
from __future__ import annotations

import base64
import json
from urllib import error, request

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "wp_site"

_urlopen = request.urlopen   # tests override


class WPError(Exception):
    pass


def _creds(db: Session) -> tuple[str, str, str]:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    user = (cfg.get("username") or "").strip()
    pw = (secure_config.get_secret(cfg, "app_password") or "").replace(" ", "").strip()
    return base, user, pw


def configured(db: Session) -> bool:
    base, user, pw = _creds(db)
    return bool(base and user and pw)


def _call(base: str, user: str, pw: str, path: str, *,
          method: str = "GET", payload: dict | None = None) -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req = request.Request(
        f"{base}/wp-json/wp/v2{path}",
        data=(json.dumps(payload).encode() if payload is not None else None),
        method=method,
        headers={"Authorization": f"Basic {token}",
                 "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "BVTech-OpsPilot"})
    try:
        with _urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403):
            raise WPError(f"WordPress auth failed (HTTP {e.code}) — check the username and "
                          f"Application Password in Settings. {detail}")
        raise WPError(f"WordPress HTTP {e.code}: {detail}")
    except WPError:
        raise
    except Exception as e:  # noqa: BLE001
        raise WPError(f"WordPress request failed: {e}")


def test_connection(db: Session) -> dict:
    """Live check: who does WordPress think we are? Cheap, side-effect-free."""
    base, user, pw = _creds(db)
    if not (base and user and pw):
        raise WPError("WordPress is not configured — set site URL, username and "
                      "Application Password in Settings → Website.")
    me = _call(base, user, pw, "/users/me?context=edit")
    return {"ok": True, "site": base, "user": me.get("name") or me.get("slug"),
            "roles": me.get("roles", [])}


def publish_post(db: Session, *, title: str, content_html: str, excerpt: str = "",
                 status: str = "publish", tags_csv: str = "") -> dict:
    """Create a post on the connected WordPress site. Returns {id, link}."""
    base, user, pw = _creds(db)
    if not (base and user and pw):
        raise WPError("WordPress is not configured — set site URL, username and "
                      "Application Password in Settings → Website.")
    if not (title or "").strip() or not (content_html or "").strip():
        raise WPError("Refusing to publish an empty post (title and body required).")
    payload = {
        "title": title.strip()[:200],
        "content": content_html,
        "excerpt": (excerpt or "").strip()[:400],
        "status": status if status in ("publish", "draft", "pending") else "draft",
    }
    out = _call(base, user, pw, "/posts", method="POST", payload=payload)
    return {"id": out.get("id"), "link": out.get("link"),
            "status": out.get("status")}
