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
# v1.144 PER-CHANNEL CADENCE. The user's hard rule: "google only likes once a
# week so never ever spam there — the rest one a day is fine." So the default
# gap is DAILY (24h) for LinkedIn and every non-Google channel, and Google
# Business has its OWN weekly gap (168h). Each is overridable in Settings.
_DEFAULT_GAP_HOURS = 24           # LinkedIn + default: one post per day
_DEFAULT_GBP_GAP_HOURS = 168      # Google Business: at most one post per WEEK


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
    # Default to BOTH channels so a weekly post hits LinkedIn and Google Business;
    # an unconnected channel is skipped gracefully at publish time.
    chans = [c.strip() for c in (cfg.get("gen_channels") or "linkedin,google_business").split(",") if c.strip()]
    return {"enabled": _truthy(cfg.get("enabled")),
            "gap_hours": int(cfg.get("gap_hours") or _DEFAULT_GAP_HOURS),
            # Google Business gets its own (much longer) gap so it is NEVER
            # spammed: at most one GBP post per gbp_gap_hours (default weekly).
            "gbp_gap_hours": int(cfg.get("gbp_gap_hours") or _DEFAULT_GBP_GAP_HOURS),
            # Auto-generate ("runs itself"): brand profile used to top up the queue.
            "auto_generate": _truthy(cfg.get("auto_generate")),
            "min_queue": int(cfg.get("min_queue") or 3),
            "city": cfg.get("city") or "",
            "cities": [c.strip() for c in (cfg.get("city") or "").split(",") if c.strip()],
            "voice": cfg.get("voice") or "",
            "keywords": kws,
            "cta_url": cfg.get("cta_url") or "",
            "image_url": cfg.get("image_url") or "",
            "gen_channels": [c for c in chans if c in CHANNELS] or ["linkedin", "google_business"],
            "default_channels": ["linkedin", "google_business"]}


def save_config(db: Session, **fields) -> dict:
    """Persist any subset of the auto-post settings (partial update)."""
    payload = {}
    if "enabled" in fields:
        payload["enabled"] = "true" if fields["enabled"] else "false"
    if "gap_hours" in fields and fields["gap_hours"] is not None:
        payload["gap_hours"] = str(max(1, int(fields["gap_hours"])))
    if "gbp_gap_hours" in fields and fields["gbp_gap_hours"] is not None:
        # Floor the Google gap at 24h so it can never be turned into a spammer,
        # even by a mis-click in Settings.
        payload["gbp_gap_hours"] = str(max(24, int(fields["gbp_gap_hours"])))
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


CHANNELS = ("linkedin", "google_business", "google_business_personal")


def _linkedin_poster(db: Session):
    """LinkedIn poster: callable(text, url, image) -> ref, or None if unconfigured.
    Prefers the one-click OAuth token (self-refreshing) and only falls back to a
    manually-pasted token — previously delivery ONLY used the manual token, so a
    stale paste kept failing 401 even when a fresh OAuth connection existed.
    (LinkedIn image upload isn't wired yet, so the image arg is accepted+ignored.)"""
    from . import oauth as _oauth, publishers
    conn = secure_config.get_platform(db, "pub_linkedin")
    cfg = (conn.config if conn else None) or {}
    token = None
    try:
        token = _oauth.get_valid_token(db, "linkedin")
    except Exception:  # noqa: BLE001 — refresh hiccup: fall back to manual token
        token = None
    token = token or secure_config.get_secret(cfg, "access_token")
    urn = secure_config.get_secret(cfg, "person_urn") or cfg.get("person_urn")
    if not (token and urn):
        return None
    return lambda text, url, image=None: publishers.post_linkedin(str(token), str(urn), text, url or "")


def _gbp_poster_from(db: Session, vault_key: str):
    """Google Business poster for a given vault entry ("gbp" = business listing,
    "gbp_personal" = personal listing): callable(text, url, image) -> ref, or
    None if that connection isn't fully configured. Publishes a localPost."""
    from . import gbp
    conn = secure_config.get_platform(db, vault_key)
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


def _gbp_poster(db: Session):
    return _gbp_poster_from(db, "gbp")


def _gbp_personal_poster(db: Session):
    return _gbp_poster_from(db, "gbp_personal")


def _poster_for(db: Session, channel: str):
    if channel == "linkedin":
        return _linkedin_poster(db)
    if channel == "google_business":
        return _gbp_poster(db)
    if channel == "google_business_personal":
        return _gbp_personal_poster(db)
    return None


# --------------------------------------------------------------------------- #
# v1.36 Re-auth circuit breaker — dead tokens pause a channel cleanly instead
# of burning retries forever. When delivery fails with an AUTH error
# (invalid_grant / invalid_client / 401 / expired), the channel is marked
# "needs re-connect": posts stay safely queued, no attempts are consumed, the
# UI/Doctor say exactly which button to click, and the moment a new credential
# is saved or a one-click Connect completes, the queue drains automatically.
# --------------------------------------------------------------------------- #
_REAUTH_PROVIDER = {"linkedin": "pub_linkedin", "google_business": "gbp",
                    "google_business_personal": "gbp_personal"}
_AUTH_HINTS = ("invalid_grant", "invalid_client", "http 401", "(401", "401)",
               "unauthorized", "expired or revoked", "token is likely expired")


def _is_auth_error(msg: str) -> bool:
    low = str(msg or "").lower()
    return any(h in low for h in _AUTH_HINTS)


def _reauth_message(channel: str, raw: str) -> str:
    low = str(raw or "").lower()
    if channel in ("google_business", "google_business_personal"):
        which = "Google Business (Personal)" if channel == "google_business_personal" else "Google Business"
        base = (f"Google needs a one-click re-connect: Settings -> One-click Connect -> "
                f"{which}. Your posts are safe in the queue and send automatically "
                f"after you reconnect.")
        if "invalid_grant" in low:
            base += (" (If this happens again in ~a week: your Google OAuth consent screen "
                     "is in 'Testing' mode - Google expires Testing tokens after 7 days. "
                     "Set it to 'In production' in Google Cloud -> OAuth consent screen.)")
        return base
    if channel == "linkedin":
        return ("LinkedIn needs a one-click re-connect: Settings -> One-click Connect -> "
                "LinkedIn. Your posts are safe in the queue and send automatically after "
                "you reconnect.")
    return f"{channel} needs re-authorization; posts stay queued until reconnected."


def get_reauth(db: Session, channel: str) -> dict | None:
    prov = _REAUTH_PROVIDER.get(channel)
    if not prov:
        return None
    conn = secure_config.get_platform(db, prov)
    return ((conn.config if conn else None) or {}).get("needs_reauth") or None


def set_reauth(db: Session, channel: str, reason: str) -> None:
    prov = _REAUTH_PROVIDER.get(channel)
    if not prov:
        return
    names = {"pub_linkedin": ("LinkedIn Publisher", "Marketing"), "gbp": ("GBP", "Publishing")}
    nm, cat = names.get(prov, (prov, "Publishing"))
    secure_config.upsert_platform(db, prov, nm, cat, {
        "needs_reauth": {"reason": reason[:400],
                         "at": datetime.now(timezone.utc).isoformat()}})


def clear_reauth(db: Session, provider_key: str) -> bool:
    """Called when a fresh credential lands (one-click Connect callback, a
    connector save, or a successful delivery). Returns True if a pause was
    lifted — the queued posts then send on the next tick."""
    conn = secure_config.get_platform(db, provider_key)
    cfg = dict((conn.config if conn else None) or {})
    if conn and cfg.pop("needs_reauth", None) is not None:
        conn.config = cfg
        db.commit()
        return True
    return False


def channel_readiness(db: Session) -> dict:
    return {ch: (_poster_for(db, ch) is not None) for ch in CHANNELS}


def _last_posted_at(db: Session) -> datetime | None:
    row = (db.query(SocialPost).filter(SocialPost.status == "posted")
           .order_by(SocialPost.posted_at.desc()).first())
    return _aware(row.posted_at) if row and row.posted_at else None


# --------------------------------------------------------------------------- #
# v1.144 PER-CHANNEL cadence state. We record the moment a channel ACTUALLY
# delivers (not merely when a post that *listed* the channel went out) in the
# autopost vault as `last_post_<channel>`. This is what lets LinkedIn run daily
# while Google Business is gated to weekly: a both-channels post that only
# reached LinkedIn on a non-Google day must NOT reset Google's weekly clock.
# These keys aren't secret-looking, so they store + read back as plain ISO text.
# --------------------------------------------------------------------------- #
def _mark_channel_posted(db: Session, channel: str, when: datetime) -> None:
    secure_config.upsert_platform(db, PROVIDER, "Auto-posting", "Marketing",
                                  {f"last_post_{channel}": when.isoformat()})


def _last_posted_channel(db: Session, channel: str) -> datetime | None:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    raw = cfg.get(f"last_post_{channel}")
    if raw:
        try:
            return _aware(datetime.fromisoformat(str(raw)))
        except Exception:
            pass
    # Back-compat: before per-channel tracking existed, fall back to the newest
    # posted row that listed this channel (approximate, but only used once until
    # the first real per-channel delivery stamps the vault).
    rows = (db.query(SocialPost).filter(SocialPost.status == "posted")
            .order_by(SocialPost.posted_at.desc()).limit(50).all())
    for r in rows:
        if channel in (r.channels or []) and r.posted_at:
            return _aware(r.posted_at)
    return None


def _channel_gap_hours(cfg: dict, channel: str) -> int:
    # Both Google listings (business + personal) are weekly-gated so neither is
    # ever spammed; everything else (LinkedIn) is daily.
    if channel in ("google_business", "google_business_personal"):
        return cfg["gbp_gap_hours"]
    return cfg["gap_hours"]


def _due_channels(db: Session, cfg: dict, now: datetime) -> list[str]:
    """Channels whose cadence gap has elapsed, so a post may go there now.
    LinkedIn (and any non-Google channel) = daily; Google Business = weekly."""
    due = []
    for ch in CHANNELS:
        last = _last_posted_channel(db, ch)
        if last is None or (now - last) >= timedelta(hours=_channel_gap_hours(cfg, ch)):
            due.append(ch)
    return due


def _next_due_for_channels(db: Session, now: datetime, channels: list[str]) -> SocialPost | None:
    """Oldest queued, schedule-ready post that targets at least one due channel.
    Skips a post whose only channel isn't due yet (so a Google-only post never
    stalls the daily LinkedIn drip, and vice-versa)."""
    want = {c for c in channels if c in CHANNELS}
    rows = (db.query(SocialPost).filter(SocialPost.status == "queued")
            .order_by(SocialPost.created_at.asc()).all())
    for p in rows:
        sf = _aware(p.scheduled_for)
        if sf is not None and sf > now:
            continue
        pch = {c for c in (p.channels or ["linkedin"]) if c in CHANNELS} or {"linkedin"}
        if pch & want:
            return p
    return None


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


def _notify_reauth(db: Session, channel: str, reason: str) -> None:
    """One clear notification the moment a channel's token dies — not a stream
    of retry errors. Sent once because the breaker prevents repeat detections."""
    try:
        from ..models import Notification
        pretty = {"linkedin": "LinkedIn", "google_business": "Google Business",
                  "google_business_personal": "Google Business (Personal)"}.get(channel, channel)
        db.add(Notification(client_id=None, target_user_id=None, kind="autopost",
                            severity="warning",
                            message=f"🔑 {pretty} paused - {reason}"[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


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
        # Circuit breaker: a channel with a known-dead token is PAUSED — the
        # post stays queued, no attempts burn, and the message says which
        # button to click. Reconnecting lifts the pause and the queue drains.
        ra = get_reauth(db, ch)
        if ra:
            results[ch] = f"paused - {ra.get('reason', 'needs re-connect')}"[:300]
            continue
        fn = (posters or {}).get(ch) if posters is not None else _poster_for(db, ch)
        if fn is None:
            results[ch] = "skipped (not configured)"
            continue
        any_ready = True
        try:
            ref = fn(post.body, post.link or "", post.image_url or None)
            results[ch] = str(ref)[:160]
            any_ok = True
            _mark_channel_posted(db, ch, now)   # per-channel cadence clock
            clear_reauth(db, _REAUTH_PROVIDER.get(ch, ""))   # success proves auth is good
        except Exception as e:  # noqa: BLE001 — record + surface, never crash the tick
            msg = str(e)
            if _is_auth_error(msg):
                # First detection (breaker was clear at loop start): pause the
                # channel + tell the operator once. No any_err -> the post goes
                # back to 'queued' untouched instead of burning an attempt.
                human = _reauth_message(ch, msg)
                set_reauth(db, ch, human)
                _notify_reauth(db, ch, human)
                results[ch] = f"paused - {human}"[:300]
            else:
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


def deliver_due(db: Session, now: datetime | None = None, *, posters: dict | None = None) -> list[dict]:
    """Deliver AT MOST ONE queued post, on the per-channel cadence (LinkedIn
    daily, Google weekly), with NO campaign-enabled gate and NO auto-generate.

    v1.146: this is the delivery half, split out from publish_due so the daily
    content drip (content_autopilot) can push its own queued LinkedIn/Google
    posts out WITHOUT the operator first flipping the separate 'auto-poster'
    campaign switch. That hidden second switch is why connected LinkedIn never
    actually posted — posts were generated + queued daily but delivery sat behind
    an OFF-by-default toggle. Per-channel cadence still prevents any double-post."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    due = _due_channels(db, cfg, now)
    if not due:
        return []
    post = _next_due_for_channels(db, now, due)
    if not post:
        return []
    target = [c for c in (post.channels or ["linkedin"]) if c in CHANNELS and c in due]
    if not target:
        return []
    built = {ch: ((posters or {}).get(ch) if posters is not None else _poster_for(db, ch)) for ch in target}
    if not any(v is not None for v in built.values()):
        return []   # nothing ready for this post — wait, don't consume the gap
    return [publish_one(db, post, now, posters=built)]


def deliver_all_due(db: Session, now: datetime | None = None, *, posters: dict | None = None) -> list[dict]:
    """Flush EVERY channel that's due right now (one post each), not just one.
    Used by the daily drip so LinkedIn and (on its weekly day) Google both go out
    in the same tick. Cadence timestamps make repeat calls safe."""
    now = now or datetime.now(timezone.utc)
    out: list[dict] = []
    for _ in range(len(CHANNELS)):
        res = deliver_due(db, now, posters=posters)
        if not res:
            break
        out.extend(res)
    return out


def publish_due(db: Session, now: datetime | None = None, *, posters: dict | None = None) -> list[dict]:
    """Scheduler entrypoint for the OPT-IN auto-poster campaign: when enabled,
    keep the queue stocked (auto-generate) and deliver the next due post. Delivery
    itself (deliver_due) also runs from the always-on daily drip, so connecting a
    channel is enough to start posting even if this campaign toggle is off."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    if not cfg["enabled"]:
        return []
    # Keep the queue stocked (auto-generate) so it never runs dry.
    try:
        maybe_refill(db, now)
    except Exception:
        pass
    return deliver_due(db, now, posters=posters)
