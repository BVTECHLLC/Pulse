"""v0.70 Auto-posting queue + scheduler (staff-only).

Queue posts, toggle the auto-publisher on/off + cadence, and publish on demand.
The scheduler tick calls `autopost.publish_due`.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, SocialPost, User
from ...services import audit, autopost

router = APIRouter(prefix="/api/autopost", tags=["autopost"])

_CHANNELS = ("linkedin", "google_business")


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(p: SocialPost) -> dict:
    return {"id": p.id, "body": p.body, "link": p.link, "image_url": p.image_url,
            "channels": p.channels or [], "status": p.status, "result": p.result,
            "scheduled_for": p.scheduled_for.isoformat() if p.scheduled_for else None,
            "posted_at": p.posted_at.isoformat() if p.posted_at else None,
            "created_at": p.created_at.isoformat()}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    cfg = autopost.get_config(db)
    ready = autopost.channel_readiness(db)
    return {**cfg, "channels": list(autopost.CHANNELS), "ready": ready,
            "linkedin_ready": ready.get("linkedin", False),
            "google_business_ready": ready.get("google_business", False),
            "google_business_personal_ready": ready.get("google_business_personal", False)}


@router.get("/doctor")
def doctor(post: int = 0, db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """v1.157: 'why aren't LinkedIn/Google posting?' — every link in the chain +
    a plain-English verdict, viewable in the browser (no shell).

    v1.159: opening this page already SELF-HEALS LinkedIn — channel_readiness ->
    _linkedin_poster derives + stores the author URN from your token when it was
    missing (the #1 silent blocker). Add ?post=1 to FORCE a real LinkedIn +
    Google attempt right now and see the exact per-channel result (or the exact
    API error) inline — the one-click "make it post now and tell me what
    happened" you can run from the browser, no shell needed. Cadence still
    guards against double-posting."""
    from ...services import content_autopilot as ca, secure_config as sc
    from ...models import SocialPost, OAuthToken
    from collections import Counter
    from datetime import datetime as _dt, timezone as _tz
    forced = None
    if post:
        # Generate a fresh draft for each channel (free Groq writer / zero-token
        # floor), then deliver everything that's due and report the raw result.
        now = _dt.now(_tz.utc)
        steps = {}
        try:
            steps["linkedin_generate"] = list(ca._run_linkedin(db, now))
        except Exception as e:  # noqa: BLE001
            steps["linkedin_generate"] = [False, f"error: {e}"]
        # Google self-config: fill account/location from the API if still blank.
        try:
            steps["gbp_autoconfig"] = autopost.gbp_autoconfig(db)
        except Exception as e:  # noqa: BLE001
            steps["gbp_autoconfig"] = f"error: {e}"
        try:
            steps["gbp_generate"] = list(ca._run_gbp(db, now))
        except Exception as e:  # noqa: BLE001
            steps["gbp_generate"] = [False, f"error: {e}"]
        try:
            steps["delivered"] = autopost.deliver_all_due(db, now)
        except Exception as e:  # noqa: BLE001
            steps["delivered"] = [{"error": str(e)}]
        forced = steps
    cc = ca.get_config(db)
    ready = autopost.channel_readiness(db)
    li = sc.get_platform(db, "pub_linkedin"); licfg = (li.config if li else {}) or {}
    li_tok = bool(sc.get_secret(licfg, "access_token")) or \
        db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count() > 0
    li_urn = bool(sc.get_secret(licfg, "person_urn") or licfg.get("person_urn"))
    gb = sc.get_platform(db, "gbp"); gbcfg = (gb.config if gb else {}) or {}
    gb_fields = {k: bool(sc.get_secret(gbcfg, k) or gbcfg.get(k)) for k in
                 ("client_id", "client_secret", "refresh_token", "account_name", "location_name")}
    q = db.query(SocialPost).all()
    paused = {ch: bool(autopost.get_reauth(db, ch)) for ch in autopost.CHANNELS}
    li_ready = ready.get("linkedin")
    gb_ready = ready.get("google_business")
    if li_ready and gb_ready:
        verdict = "All connected — LinkedIn + Google are ready. Add ?post=1 to this URL to fire one now."
    elif li_ready and not gb_ready:
        miss = [k for k, v in gb_fields.items() if not v]
        verdict = (f"LinkedIn is READY and posts daily. Google Business still needs: "
                   f"{', '.join(miss) or 'connect + pick location'}. "
                   f"Add ?post=1 to post to LinkedIn right now.")
    elif not li_tok:
        verdict = ("LinkedIn has no token yet — open Settings → LinkedIn tile → click Connect "
                   "(one-click OAuth). Pasting only the Client ID/Secret is not enough; the "
                   "Connect step is what grants the posting token.")
    elif li_tok and not li_urn:
        verdict = ("LinkedIn has a token but we couldn't read your author URN from it — your "
                   "LinkedIn app is missing the 'Sign In with LinkedIn using OpenID Connect' "
                   "product (scopes openid+profile). Add that product in the LinkedIn developer "
                   "app, then click Connect again. (We auto-derive the URN the moment the token "
                   "can read it.)")
    else:
        verdict = "LinkedIn token looks expired/limited — click Connect on the LinkedIn tile to refresh."
    from ...core.config import get_settings as _gs
    return {
        "version": _gs().APP_VERSION,
        "forced": forced,
        "delivery_fix_deployed": hasattr(autopost, "deliver_all_due"),
        "self_heal_urn": True,
        "drip": {"enabled": cc["enabled"], "linkedin_channel": cc["channels"].get("linkedin"),
                 "gbp_channel": cc["channels"].get("gbp"),
                 "last_linkedin_run": cc["last"].get("linkedin"), "last_gbp_run": cc["last"].get("gbp")},
        "ready": ready, "paused": paused,
        "linkedin": {"token": li_tok, "person_urn": li_urn},
        "google_business": gb_fields,
        "queue": dict(Counter(p.status for p in q)),
        "last_delivered": {
            "linkedin": str(autopost._last_posted_channel(db, "linkedin")),
            "google_business": str(autopost._last_posted_channel(db, "google_business"))},
        "verdict": verdict,
    }


class SettingsIn(BaseModel):
    enabled: bool | None = None
    gap_hours: int | None = None          # LinkedIn / default cadence (hours); 24 = daily
    gbp_gap_hours: int | None = None      # Google Business cadence (hours); 168 = weekly (never spam)
    auto_generate: bool | None = None
    min_queue: int | None = None
    city: str | None = None          # comma-separated target metros
    voice: str | None = None         # brand-voice note for the AI writer
    keywords: list[str] | None = None
    cta_url: str | None = None
    image_url: str | None = None
    gen_channels: list[str] | None = None


@router.put("/settings")
def save_settings(body: SettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    cfg = autopost.save_config(db, **{k: v for k, v in body.model_dump().items() if v is not None})
    audit.record(db, action="autopost.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="autopost", ip=_ip(request),
                 detail=f"enabled={cfg['enabled']} gap={cfg['gap_hours']}h auto_gen={cfg['auto_generate']}")
    return cfg


class GenerateIn(BaseModel):
    count: int = 6
    city: str | None = None
    keywords: list[str] | None = None
    cta_url: str | None = None
    image_url: str | None = None
    channels: list[str] = ["linkedin"]
    use_ai: bool = False        # Claude-written posts (falls back to templates)


@router.post("/generate")
def generate(body: GenerateIn, request: Request, db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Generate SEO-tuned post drafts and add them to the queue (no AI key needed).
    Falls back to the saved brand profile for anything not passed."""
    cfg = autopost.get_config(db)
    created = autopost.generate_and_queue(
        db, max(1, min(body.count, 52)),
        city=body.city if body.city is not None else cfg["city"],
        keywords=body.keywords if body.keywords is not None else cfg["keywords"],
        cta_url=body.cta_url if body.cta_url is not None else cfg["cta_url"],
        image_url=body.image_url if body.image_url is not None else cfg["image_url"],
        channels=body.channels or cfg["gen_channels"], voice=cfg["voice"], use_ai=body.use_ai)
    audit.record(db, action="autopost.generate", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="autopost", ip=_ip(request),
                 detail=f"generated={len(created)}")
    return {"ok": True, "created": len(created)}


@router.get("")
def list_posts(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = db.query(SocialPost).order_by(SocialPost.created_at.desc()).limit(200).all()
    return [_serialize(p) for p in rows]


class PostIn(BaseModel):
    body: str
    link: str | None = None
    image_url: str | None = None
    channels: list[str] = ["linkedin"]
    scheduled_for: datetime | None = None


@router.post("", status_code=201)
def add_post(body: PostIn, request: Request, db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Post text is required.")
    channels = [c for c in (body.channels or ["linkedin"]) if c in _CHANNELS] or ["linkedin"]
    p = SocialPost(body=body.body.strip(), link=(body.link or None),
                   image_url=(body.image_url or None), channels=channels,
                   scheduled_for=body.scheduled_for, status="queued",
                   created_by_user_id=user.id)
    db.add(p)
    db.commit()
    audit.record(db, action="autopost.queue", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="social_post", target_id=str(p.id),
                 ip=_ip(request), detail=body.body[:80])
    return _serialize(p)


@router.delete("/{post_id}")
def delete_post(post_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    p = db.get(SocialPost, post_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/{post_id}/requeue")
def requeue_post(post_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Put a failed post back in the queue with fresh retries (UI 'Retry')."""
    p = autopost.requeue(db, post_id)
    if not p:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Only failed posts can be re-queued.")
    audit.record(db, action="autopost.requeue", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="social_post", target_id=str(p.id),
                 ip=_ip(request), detail="requeued")
    return {"ok": True, "post": _serialize(p)}


@router.post("/{post_id}/post-now")
def post_now(post_id: int, request: Request, db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER))):
    p = db.get(SocialPost, post_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    if p.status == "posted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already posted")
    if p.status == "failed":   # explicit human retry: fresh attempts
        p.status, p.attempts = "queued", 0
        db.commit()
    res = autopost.publish_one(db, p)
    if not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("reason") or "Publish failed")
    audit.record(db, action="autopost.post_now", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="social_post", target_id=str(p.id),
                 ip=_ip(request), detail=res.get("result", ""))
    return {"ok": True, "post": _serialize(p)}
