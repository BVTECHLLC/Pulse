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
            "google_business_ready": ready.get("google_business", False)}


class SettingsIn(BaseModel):
    enabled: bool | None = None
    gap_hours: int | None = None
    auto_generate: bool | None = None
    min_queue: int | None = None
    city: str | None = None
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
        channels=body.channels or cfg["gen_channels"], use_ai=body.use_ai)
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


@router.post("/{post_id}/post-now")
def post_now(post_id: int, request: Request, db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER))):
    p = db.get(SocialPost, post_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    if p.status == "posted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already posted")
    res = autopost.publish_one(db, p)
    if not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("reason") or "Publish failed")
    audit.record(db, action="autopost.post_now", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="social_post", target_id=str(p.id),
                 ip=_ip(request), detail=res.get("result", ""))
    return {"ok": True, "post": _serialize(p)}
