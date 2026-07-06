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


def _truthy(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    kws = [k.strip() for k in (cfg.get("keywords") or "").split(",") if k.strip()]
    chans = [c.strip() for c in (cfg.get("gen_channels") or "linkedin").split(",") if c.strip()]
    return {"enabled": _truthy(cfg.get("enabled")),
            "gap_hours": int(cfg.get("gap_hours") or _DEFAULT_GAP_HOURS),
            # Auto-generate ("runs itself"): brand profile used to top up the queue.
            "auto_generate": _truthy(cfg.get("auto_generate")),
            "min_queue": int(cfg.get("min_queue") or 3),
            "city": cfg.get("city") or "",
            "cities": [c.strip() for c in (cfg.get("city") or "").split(",") if c.strip()],
            "voice": cfg.get("voice") or "",
            "keywords": kws,
            "cta_url": cfg.get("cta_url") or "",
            "image_url": cfg.get("image_url") or "",
            "gen_channels": [c for c in chans if c in CHANNELS] or ["linkedin"],
            "default_channels": ["linkedin"]}


def save_config(db: Session, **fields) -> dict:
    """Persist any subset of the auto-post settings (partial update)."""
    payload = {}
    if "enabled" in fields:
        payload["enabled"] = "true" if fields["enabled"] else "false"
    if "gap_hours" in fields and fields["gap_hours"] is not None:
        payload["gap_hours"] = str(max(1, int(fields["gap_hours"])))
    if "auto_generate" in fields:
        payload["auto_generate"] = "true" if fields["auto_generate"] else "false"
    if "min_queue" in fields and fields["min_queue"] is not None:
        payload["min_queue"] = str(max(1, min(int(fields["min_queue"]), 20)))
    if "city" in fields and fields["city"] is not None:
        payload["city"] = str(fields["city"])[:200]   # comma-separated target metros
    if "voice" in fields and fields["voice"] is not None:
        payload["voice"] = str(fields["voice"])[:400]
    if "keywords" in fields and fields["keywords"] is not None:
        kws = fields["keywords"]
        payload["keywords"] = ",".join(kws) if isinstance(kws, list) else str(kws)
    if "cta_url" in fields and fields["cta_url"] is not None:
        payload["cta_url"] = str(fields["cta_url"])[:500]
    if "image_url" in fields and fields["image_url"] is not None:
        payload["image_url"] = str(fields["image_url"])[:800]
    if "gen_channels" in fields and fields["gen_channels"] is not None:
        ch = fields["gen_channels"]
        payload["gen_channels"] = ",".join(ch) if isinstance(ch, list) else str(ch)
    secure_config.upsert_platform(db, PROVIDER, "Auto-posting", "Marketing", payload)
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


MAX_ATTEMPTS = 3   # transient API errors retry on later ticks, then fail loudly

# Documented brand rule: BVTech targets Sugar Land / Houston / Austin / San
# Antonio — never El Campo. Enforced at PUBLISH time so no path (AI, template,
# or manual) can ship an off-brand post.
_BANNED_PHRASES = ("el campo",)


def _publish_guard(post: SocialPost) -> str | None:
    """Return a rejection reason if this post must not go out, else None."""
    body = (post.body or "").strip()
    if not body:
        return "rejected: empty body"
    for phrase in _BANNED_PHRASES:
        if phrase in body.lower():
            return f"rejected: off-brand content ('{phrase}' is excluded by brand rules)"
    return None


def _claim(db: Session, post: SocialPost) -> bool:
    """Atomically move queued -> publishing so two overlapping ticks (or a tick
    racing the post-now button) can never publish the same post twice."""
    n = (db.query(SocialPost)
         .filter(SocialPost.id == post.id, SocialPost.status == "queued")
         .update({"status": "publishing"}, synchronize_session=False))
    db.commit()
    db.refresh(post)
    return bool(n)


def _notify_failure(db: Session, post: SocialPost) -> None:
    try:
        from . import notifications
        from ..models import Notification
        msg = (f"Auto-post #{post.id} failed {MAX_ATTEMPTS}x and needs attention: "
               f"{(post.result or '')[:200]} — review it in Content Studio → Auto-poster.")
        db.add(Notification(client_id=None, target_user_id=None, kind="autopost",
                            severity="warning", message=msg[:1000]))
        db.commit()
        notifications.fanout(db, message=msg, severity="warning", client_id=None)
    except Exception:  # noqa: BLE001
        pass


def publish_one(db: Session, post: SocialPost, now: datetime | None = None, *,
                posters: dict | None = None) -> dict:
    """Publish a post to each of its channels. Marks posted if ANY channel
    succeeds. On an all-channel error the post goes BACK to queued for a later
    tick (up to MAX_ATTEMPTS), then is marked failed + staff are notified — a
    transient LinkedIn/GBP blip never silently kills a post. Posts with every
    channel skipped stay queued untouched (publish once creds are added). Commits.
    `posters` is a {channel: callable(text,url,image)} override for tests."""
    now = now or datetime.now(timezone.utc)

    guard = _publish_guard(post)
    if guard:
        post.status, post.result = "failed", guard[:400]
        db.commit()
        return {"ok": False, "ready": True, "post_id": post.id,
                "result": post.result, "channels": {}, "reason": guard}

    if not _claim(db, post):
        return {"ok": False, "ready": False, "post_id": post.id, "skipped": True,
                "result": post.result, "channels": {},
                "reason": "already being published by another worker"}

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
        post.attempts = (post.attempts or 0) + 1
        if post.attempts >= MAX_ATTEMPTS:
            post.status = "failed"
        else:
            post.status = "queued"   # retry on a later tick
            post.result = (f"retry {post.attempts}/{MAX_ATTEMPTS} — " + (post.result or ""))[:400]
    else:
        post.status = "queued"   # nothing configured -> don't burn it
    db.commit()
    if post.status == "failed":
        _notify_failure(db, post)
    return {"ok": any_ok, "ready": any_ready, "post_id": post.id,
            "result": post.result, "channels": results,
            "reason": (None if any_ok else
                       ("No channel configured — connect LinkedIn / Google Business in Settings."
                        if not any_ready else post.result))}


def requeue(db: Session, post_id: int) -> SocialPost | None:
    """Give a failed post a fresh set of attempts (the UI 'Retry' button)."""
    post = db.get(SocialPost, post_id)
    if not post or post.status != "failed":
        return None
    post.status, post.attempts, post.result = "queued", 0, None
    db.commit()
    return post


def generate_and_queue(db: Session, count: int, *, city: str = "", keywords=None,
                       cta_url: str = "", image_url: str = "", channels=None,
                       biz: str = "BVTech", voice: str = "", use_ai: bool = False) -> list[dict]:
    """Generate `count` drafts and add them to the queue. `use_ai=True` writes them
    with Claude (falling back to templates). `city` may be comma-separated metros —
    the generator rotates across them. Rotation continues from the current post
    count so re-runs don't repeat."""
    from . import post_generator
    channels = [c for c in (channels or ["linkedin"]) if c in CHANNELS] or ["linkedin"]
    start = db.query(SocialPost).count()
    if use_ai:
        drafts = post_generator.generate_ai_drafts(count, city=city, keywords=keywords,
                    biz=biz, cta_url=cta_url, voice=voice, start=start)
    else:
        drafts = post_generator.generate_drafts(count, city=city, keywords=keywords,
                    biz=biz, cta_url=cta_url, start=start)
    created = []
    for d in drafts:
        p = SocialPost(body=d["body"], link=d.get("link"), image_url=(image_url or None),
                       channels=list(channels), status="queued")
        db.add(p)
        db.flush()
        created.append({"id": p.id})
    if created:
        db.commit()
    return created


def maybe_refill(db: Session, now: datetime | None = None) -> list[dict]:
    """If auto-generate is on and the queue is running low, top it back up so the
    feed never runs dry. Returns the drafts created."""
    cfg = get_config(db)
    if not cfg["auto_generate"]:
        return []
    queued = db.query(SocialPost).filter(SocialPost.status == "queued").count()
    if queued >= cfg["min_queue"]:
        return []
    need = cfg["min_queue"] - queued
    # Auto-refill writes with Claude when connected (matching tone/SEO), and
    # transparently falls back to the on-brand template engine when it isn't.
    return generate_and_queue(db, need, city=cfg["city"], keywords=cfg["keywords"],
                              cta_url=cfg["cta_url"], image_url=cfg["image_url"],
                              channels=cfg["gen_channels"], voice=cfg["voice"], use_ai=True)


def publish_due(db: Session, now: datetime | None = None, *, posters: dict | None = None) -> list[dict]:
    """Scheduler entrypoint: if enabled and the gap has elapsed, publish the next
    due post (at most one). Skips entirely if no channel for that post is ready,
    so the cadence gap is only consumed by a real publish."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    if not cfg["enabled"]:
        return []
    # Keep the queue stocked (auto-generate) so it never runs dry.
    try:
        maybe_refill(db, now)
    except Exception:
        pass
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
