"""v0.70 Auto-posting — keep the feed alive on autopilot.

The MSP queues a handful of posts; the scheduler publishes the **oldest due**
one about once a day to its channels (LinkedIn today, via the configured
publisher). A vault entry ("autopost") holds the on/off switch and the minimum
gap between posts, so it never double-posts even though the tick runs often.

The actual publish is injectable (`poster`) so the queue/cadence logic is
unit-testable offline, and an un-configured channel never burns a queued post.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import SocialPost
from . import secure_config

PROVIDER = "autopost"
_DEFAULT_GAP_HOURS = 20


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"enabled": str(cfg.get("enabled", "")).lower() in ("1", "true", "yes", "on"),
            "gap_hours": int(cfg.get("gap_hours") or _DEFAULT_GAP_HOURS),
            "default_channels": cfg.get("default_channels") or ["linkedin"]}


def save_config(db: Session, *, enabled: bool, gap_hours: int) -> dict:
    secure_config.upsert_platform(db, PROVIDER, "Auto-posting", "Marketing",
                                  {"enabled": "true" if enabled else "false",
                                   "gap_hours": str(max(1, gap_hours))})
    return get_config(db)


def _linkedin_poster(db: Session):
    """Default poster: publish to LinkedIn using the vault credentials. Returns a
    callable(text, url) -> ref, or None if LinkedIn isn't configured."""
    from . import publishers
    conn = secure_config.get_platform(db, "pub_linkedin")
    cfg = (conn.config if conn else None) or {}
    token = secure_config.get_secret(cfg, "access_token")
    urn = secure_config.get_secret(cfg, "person_urn") or cfg.get("person_urn")
    if not (token and urn):
        return None
    return lambda text, url: publishers.post_linkedin(str(token), str(urn), text, url or "")


def _last_posted_at(db: Session) -> datetime | None:
    row = (db.query(SocialPost).filter(SocialPost.status == "posted")
           .order_by(SocialPost.posted_at.desc()).first())
    return _aware(row.posted_at) if row and row.posted_at else None


def next_due(db: Session, now: datetime) -> SocialPost | None:
    """Oldest queued post whose scheduled_for (if any) has arrived."""
    q = db.query(SocialPost).filter(SocialPost.status == "queued")
    rows = q.order_by(SocialPost.created_at.asc()).all()
    for p in rows:
        sf = _aware(p.scheduled_for)
        if sf is None or sf <= now:
            return p
    return None


def publish_one(db: Session, post: SocialPost, now: datetime | None = None, *,
                poster=None) -> dict:
    """Publish a single post now. Marks posted/failed. Commits. `poster` defaults
    to the LinkedIn publisher; pass one in tests."""
    now = now or datetime.now(timezone.utc)
    fn = poster if poster is not None else _linkedin_poster(db)
    if fn is None:
        return {"ok": False, "reason": "LinkedIn not configured — connect it in Settings → Publishers."}
    try:
        ref = fn(post.body, post.link or "")
        post.status = "posted"
        post.posted_at = now
        post.result = str(ref)[:400]
        db.commit()
        return {"ok": True, "post_id": post.id, "result": post.result}
    except Exception as e:  # noqa: BLE001 — record + surface, never crash the tick
        post.status = "failed"
        post.result = f"error: {e}"[:400]
        db.commit()
        return {"ok": False, "post_id": post.id, "reason": post.result}


def publish_due(db: Session, now: datetime | None = None, *, poster=None) -> list[dict]:
    """Scheduler entrypoint: if enabled and the gap has elapsed, publish the next
    due post. At most one per call. Returns a summary list (empty if nothing)."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    if not cfg["enabled"]:
        return []
    last = _last_posted_at(db)
    if last and (now - last) < timedelta(hours=cfg["gap_hours"]):
        return []
    post = next_due(db, now)
    if not post:
        return []
    # If the channel isn't ready, leave the post queued (don't fail it) so it
    # publishes once credentials are added.
    fn = poster if poster is not None else _linkedin_poster(db)
    if fn is None:
        return []
    res = publish_one(db, post, now, poster=fn)
    return [res] if res.get("ok") else [res]
