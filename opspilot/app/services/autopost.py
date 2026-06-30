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


CHANNELS = ("linkedin", "google_business")


def _linkedin_poster(db: Session):
    """LinkedIn poster: callable(text, url, image) -> ref, or None if unconfigured.
    (LinkedIn image upload isn't wired yet, so the image arg is accepted+ignored.)"""
    from . import publishers
    conn = secure_config.get_platform(db, "pub_linkedin")
    cfg = (conn.config if conn else None) or {}
    token = secure_config.get_secret(cfg, "access_token")
    urn = secure_config.get_secret(cfg, "person_urn") or cfg.get("person_urn")
    if not (token and urn):
        return None
    return lambda text, url, image=None: publishers.post_linkedin(str(token), str(urn), text, url or "")


def _gbp_poster(db: Session):
    """Google Business poster: callable(text, url, image) -> ref, or None if the
    GBP connection isn't fully configured. Publishes a localPost (with photo)."""
    from . import gbp
    conn = secure_config.get_platform(db, "gbp")
    cfg = (conn.config if conn else None) or {}
    req = ("client_id", "client_secret", "refresh_token", "account_name", "location_name")
    if not secure_config.configured(cfg, req):
        return None
    client = gbp.GBPClient(
        str(secure_config.get_secret(cfg, "client_id") or cfg.get("client_id")),
        str(secure_config.get_secret(cfg, "client_secret")),
        str(secure_config.get_secret(cfg, "refresh_token")),
        str(cfg.get("account_name")), str(cfg.get("location_name")))

    def _post(text, url, image=None):
        res = client.create_post(text, url or None, image_url=(image or None))
        return res.get("name") or "localPost"
    return _post


def _poster_for(db: Session, channel: str):
    if channel == "linkedin":
        return _linkedin_poster(db)
    if channel == "google_business":
        return _gbp_poster(db)
    return None


def channel_readiness(db: Session) -> dict:
    return {ch: (_poster_for(db, ch) is not None) for ch in CHANNELS}


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
                posters: dict | None = None) -> dict:
    """Publish a post to each of its channels. Marks posted if ANY channel
    succeeds, failed if all attempted channels errored, and leaves it queued if no
    channel is configured yet (so it publishes once creds are added). Commits.
    `posters` is a {channel: callable(text,url,image)} override for tests."""
    now = now or datetime.now(timezone.utc)
    channels = [c for c in (post.channels or ["linkedin"]) if c in CHANNELS] or ["linkedin"]
    results, any_ok, any_err, any_ready = {}, False, False, False
    for ch in channels:
        fn = (posters or {}).get(ch) if posters is not None else _poster_for(db, ch)
        if fn is None:
            results[ch] = "skipped (not configured)"
            continue
        any_ready = True
        try:
            ref = fn(post.body, post.link or "", post.image_url or None)
            results[ch] = str(ref)[:160]
            any_ok = True
        except Exception as e:  # noqa: BLE001 — record + surface, never crash the tick
            results[ch] = f"error: {e}"[:160]
            any_err = True
    post.result = ("; ".join(f"{k}={v}" for k, v in results.items()))[:400]
    if any_ok:
        post.status, post.posted_at = "posted", now
    elif any_err:
        post.status = "failed"
    # else: nothing configured -> leave it 'queued' (don't burn it)
    db.commit()
    return {"ok": any_ok, "ready": any_ready, "post_id": post.id,
            "result": post.result, "channels": results,
            "reason": (None if any_ok else
                       ("No channel configured — connect LinkedIn / Google Business in Settings."
                        if not any_ready else post.result))}


def publish_due(db: Session, now: datetime | None = None, *, posters: dict | None = None) -> list[dict]:
    """Scheduler entrypoint: if enabled and the gap has elapsed, publish the next
    due post (at most one). Skips entirely if no channel for that post is ready,
    so the cadence gap is only consumed by a real publish."""
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
    chans = [c for c in (post.channels or ["linkedin"]) if c in CHANNELS] or ["linkedin"]
    built = {ch: ((posters or {}).get(ch) if posters is not None else _poster_for(db, ch)) for ch in chans}
    if not any(v is not None for v in built.values()):
        return []   # nothing ready for this post — wait, don't consume the gap
    return [publish_one(db, post, now, posters=built)]
