"""v0.41 Publishers — LinkedIn auto-publisher + website (reputation) settings.

One Settings surface for everything that posts on the MSP's behalf:
  * LinkedIn        — store token/person URN (encrypted); "post now" works from here.
  * Website (BVTech) — auto-publishing schedule/persona/repo settings.
  * Website (Jordan) — jordanpolasek.com auto-post settings (reputation mgmt).

Secrets are encrypted at rest and never returned to the browser. Staff-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, publishers, secure_config

router = APIRouter(prefix="/api/publishers", tags=["publishers"])

# Provider keys for the three publisher channels.
LINKEDIN = "pub_linkedin"
WEB_BVTECH = "pub_web_bvtech"
WEB_JP = "pub_web_jp"

_WEBSITE_DEFAULTS = {
    WEB_BVTECH: {"name": "BVTech.org Auto-Publisher", "site_url": "https://bvtech.org"},
    WEB_JP: {"name": "JordanPolasek.com Auto-Publisher", "site_url": "https://jordanpolasek.com"},
}


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _channel_state(db: Session, provider: str) -> dict:
    conn = secure_config.get_platform(db, provider)
    cfg = (conn.config if conn else None) or {}
    return {"provider": provider, "enabled": bool(conn.enabled) if conn else False,
            "fields": secure_config.public_view(cfg)}


# --------------------------------------------------------------------------- #
# Read all publisher settings at once (for the Settings tab)
# --------------------------------------------------------------------------- #
@router.get("/settings")
def all_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    li = secure_config.get_platform(db, LINKEDIN)
    li_cfg = (li.config if li else None) or {}
    return {
        "linkedin": {
            "configured": secure_config.configured(li_cfg, ("access_token", "person_urn")),
            "fields": secure_config.public_view(li_cfg),
        },
        "website_bvtech": _channel_state(db, WEB_BVTECH),
        "website_jp": _channel_state(db, WEB_JP),
    }


# --------------------------------------------------------------------------- #
# LinkedIn
# --------------------------------------------------------------------------- #
class LinkedInIn(BaseModel):
    access_token: str | None = None
    person_urn: str | None = None


@router.put("/linkedin")
def save_linkedin(body: LinkedInIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, LINKEDIN, "LinkedIn Publisher", "Marketing", payload)
    audit.record(db, action="publisher.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="linkedin credentials")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, ("access_token", "person_urn")),
            "fields": secure_config.public_view(cfg)}


class LinkedInPostIn(BaseModel):
    text: str
    url: str | None = None


@router.post("/linkedin/post")
def post_linkedin(body: LinkedInPostIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Post text is required.")
    conn = secure_config.get_platform(db, LINKEDIN)
    cfg = (conn.config if conn else None) or {}
    token = secure_config.get_secret(cfg, "access_token")
    urn = secure_config.get_secret(cfg, "person_urn") or cfg.get("person_urn")
    if not (token and urn):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "LinkedIn not configured — add a token & person URN in Settings.")
    try:
        post_id = publishers.post_linkedin(str(token), str(urn), body.text, body.url or "")
    except publishers.PublishError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    audit.record(db, action="publisher.linkedin.post", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="linkedin", target_id=post_id,
                 ip=_ip(request), detail=body.text[:120])
    return {"ok": True, "post_id": post_id}


# --------------------------------------------------------------------------- #
# Website auto-publishers (settings consumed by the box-side daily cron)
# --------------------------------------------------------------------------- #
class WebsiteIn(BaseModel):
    site_url: str | None = None
    schedule: str | None = None         # e.g. "07:30 America/Chicago"
    persona: str | None = None          # short tone/voice guidance
    topics: str | None = None           # comma-separated focus areas
    cross_post_linkedin: bool | None = None
    enabled: bool | None = None


def _save_website(db: Session, provider: str, body: WebsiteIn, user: User, request: Request) -> dict:
    defaults = _WEBSITE_DEFAULTS[provider]
    payload = {k: v for k, v in body.model_dump().items() if v is not None and k != "enabled"}
    conn = secure_config.upsert_platform(db, provider, defaults["name"], "Marketing", payload)
    if body.enabled is not None:
        conn.enabled = body.enabled
        db.commit()
    audit.record(db, action="publisher.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail=f"{provider} settings")
    return _channel_state(db, provider)


@router.put("/website/bvtech")
def save_web_bvtech(body: WebsiteIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER))):
    return _save_website(db, WEB_BVTECH, body, user, request)


@router.put("/website/jp")
def save_web_jp(body: WebsiteIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    return _save_website(db, WEB_JP, body, user, request)
