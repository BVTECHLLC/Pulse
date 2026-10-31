"""Autumn Polasek memorial — public candle + memory-wall API (cross-origin).

autumnpolasek.com is a Cloudflare Workers static site; its "light a candle" and
"share a memory" features were cosmetic (a browser-only counter and a form that
discarded submissions). These endpoints give them a real home on the portal so
that every candle is counted for everyone and every memory is SAVED and reaches
Jordan to review before it appears on the wall.

Mirrors the public_tools pattern: unauthenticated public writes, CORS pinned to
the memorial site, per-IP rate limiting, moderation on free text, and lightweight
storage in secure_config (no new table). Staff review approves/hides memories.
"""
from __future__ import annotations

import re
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response

from ...core.db import SessionLocal
from ...core.deps import current_user
from ...models import Notification, User
from ...services import moderation, secure_config

router = APIRouter(prefix="/api/memorial", tags=["memorial"])

PROVIDER = "autumn_memorial"
_ALLOWED_ORIGINS = {"https://autumnpolasek.com", "https://www.autumnpolasek.com"}
_READ_RATE: dict = {}      # ip -> [window_start, count]
_READ_MAX = 40             # candle lights / reads per minute per ip
_SUBMIT_RATE: dict = {}
_SUBMIT_MAX = 5            # memory submissions / 10 min / ip
_MAX_STORED = 500          # bound the secure_config blob


def _cors(request: Request, resp: Response) -> None:
    origin = request.headers.get("origin", "")
    if origin in _ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"


def _ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or (request.client.host if request.client else "?"))


def _limited(bucket: dict, request: Request, maxn: int, window: int) -> bool:
    ip = _ip(request)
    now = time.time()
    win = bucket.get(ip)
    if not win or now - win[0] > window:
        bucket[ip] = [now, 1]
        if len(bucket) > 10000:
            bucket.clear()
        return False
    win[1] += 1
    return win[1] > maxn


def _load(db) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    return dict((conn.config if conn else None) or {})


def _save(db, cfg: dict) -> None:
    secure_config.upsert_platform(db, PROVIDER, "Autumn Memorial", "Memorial", cfg)


def _public_card(m: dict) -> dict:
    return {"id": m.get("id"), "name": m.get("name", ""), "message": m.get("message", ""),
            "relationship": m.get("relationship", ""), "location": m.get("location", ""),
            "at": m.get("at")}


@router.options("/{rest:path}", include_in_schema=False)
def _preflight(rest: str, request: Request, resp: Response):
    _cors(request, resp)
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "content-type"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return {}


@router.get("/state")
def state(request: Request, resp: Response):
    """Public: the shared candle count + approved memories for the wall."""
    _cors(request, resp)
    db = SessionLocal()
    try:
        cfg = _load(db)
        memories = [_public_card(m) for m in (cfg.get("memories") or [])
                    if m.get("status") == "approved"]
        count = int(cfg.get("candles") or 0)
        recent = [c.get("who") for c in (cfg.get("recent_candles") or [])[:12] if c.get("who")]
    finally:
        db.close()
    resp.headers["Cache-Control"] = "public, max-age=30"
    return {"candles": count, "recent_candles": recent, "memories": memories[:500]}


@router.post("/candle")
async def light_candle(request: Request, resp: Response):
    """Public: light a candle for Autumn. Increments the shared count. Optional
    `who` name is kept (moderated) for the 'recently lit by' line."""
    _cors(request, resp)
    db = SessionLocal()
    try:
        cfg = _load(db)
        if _limited(_READ_RATE, request, _READ_MAX, 60):
            return {"ok": True, "count": int(cfg.get("candles") or 0)}  # don't punish, just no-op
        cfg["candles"] = int(cfg.get("candles") or 0) + 1
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        who = re.sub(r"[<>]", "", str(body.get("who") or "").strip())[:40]
        if who and moderation.check(who, kind="comment", max_urls=0)["ok"]:
            recent = list(cfg.get("recent_candles") or [])
            recent.insert(0, {"who": who, "at": datetime.now(timezone.utc).isoformat()})
            cfg["recent_candles"] = recent[:50]
        _save(db, cfg)
        db.commit()
        return {"ok": True, "count": cfg["candles"]}
    except Exception:  # noqa: BLE001
        db.rollback()
        return {"ok": False, "count": 0}
    finally:
        db.close()


@router.post("/memory")
async def submit_memory(request: Request, resp: Response):
    """Public: leave a name + memory of Autumn. Saved as PENDING, moderated, and
    Jordan is notified to review before it appears on the wall."""
    _cors(request, resp)
    if _limited(_SUBMIT_RATE, request, _SUBMIT_MAX, 600):
        return {"ok": False, "error": "You've shared a few already — thank you. "
                                       "Please try again in a little while."}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    name = re.sub(r"[<>]", "", str(body.get("name") or "").strip())[:60]
    message = str(body.get("message") or "").strip()[:2000]
    relationship = re.sub(r"[<>]", "", str(body.get("relationship") or "").strip())[:40]
    howmet = re.sub(r"[<>]", "", str(body.get("howmet") or "").strip())[:60]
    location = re.sub(r"[<>]", "", str(body.get("location") or "").strip())[:80]
    consent = bool(body.get("consent"))
    if not name or not message:
        return {"ok": False, "error": "Please add your name and a memory of her."}
    if not consent:
        return {"ok": False, "error": "Please check the box so your memory can appear "
                                       "on Autumn's wall after review."}
    mod = moderation.check(message, kind="comment", max_urls=0)
    nmod = moderation.check(name, kind="comment", max_urls=0)
    if not (mod["ok"] and nmod["ok"]):
        reason = (mod.get("reasons") or nmod.get("reasons") or ["Please reword and try again."])[0]
        return {"ok": False, "error": reason}
    db = SessionLocal()
    try:
        cfg = _load(db)
        items = list(cfg.get("memories") or [])
        mid = secrets.token_urlsafe(8)
        items.insert(0, {"id": mid, "name": name, "message": message,
                         "relationship": relationship, "howmet": howmet,
                         "location": location, "status": "pending",
                         "at": datetime.now(timezone.utc).isoformat(),
                         "ip": _ip(request)[:60]})
        cfg["memories"] = items[:_MAX_STORED]
        _save(db, cfg)
        try:
            db.add(Notification(
                client_id=None, target_user_id=None, kind="content", severity="info",
                message=(f"🕯️ A new memory of Autumn from {name}"
                         + (f" ({relationship})" if relationship else "")
                         + " is waiting for your review on the memorial wall.")[:1000]))
        except Exception:  # noqa: BLE001
            pass
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        return {"ok": False, "error": "Something went wrong saving that — please try again."}
    finally:
        db.close()
    return {"ok": True, "message": "Thank you. Your memory of Autumn has been received and "
                                   "will appear after Jordan reviews it. It means more than you know."}


# --------------------------------------------------------------------------- #
# Staff review (authenticated portal user) — approve / hide submitted memories.
# --------------------------------------------------------------------------- #
@router.get("/review/pending")
def review_pending(user: User = Depends(current_user)):
    db = SessionLocal()
    try:
        cfg = _load(db)
        mem = cfg.get("memories") or []
        return {"pending": [m for m in mem if m.get("status") == "pending"],
                "approved": sum(1 for m in mem if m.get("status") == "approved"),
                "candles": int(cfg.get("candles") or 0)}
    finally:
        db.close()


@router.post("/review/{mid}/{action}")
def review_action(mid: str, action: str, user: User = Depends(current_user)):
    if action not in ("approve", "reject"):
        return {"ok": False, "error": "unknown action"}
    db = SessionLocal()
    try:
        cfg = _load(db)
        found = False
        for m in (cfg.get("memories") or []):
            if m.get("id") == mid:
                m["status"] = "approved" if action == "approve" else "rejected"
                found = True
                break
        if found:
            _save(db, cfg)
            db.commit()
        return {"ok": found}
    finally:
        db.close()
