"""v1.4 Website publishing — WordPress connection + AI auto-blogger controls.

Staff-only. The WordPress Application Password is stored encrypted in the vault
and never echoed back (masked view)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import BlogPost, Role, User
from ...services import audit, blog_autopilot, secure_config, wordpress

router = APIRouter(prefix="/api/website", tags=["website"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


class SettingsIn(BaseModel):
    # WordPress connection
    base_url: str | None = None
    username: str | None = None
    app_password: str | None = None
    # Auto-blogger
    enabled: bool | None = None
    every_days: int | None = None
    wp_status: str | None = None          # publish | draft
    cross_post_linkedin: bool | None = None
    topics: str | None = None             # comma-separated overrides


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, wordpress.PROVIDER)
    wp = secure_config.public_view((conn.config if conn else None) or {})
    return {"wordpress": wp, **blog_autopilot.get_config(db)}


@router.put("/settings")
def save_settings(body: SettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    wp_payload = {k: v for k, v in
                  {"base_url": body.base_url, "username": body.username,
                   "app_password": body.app_password}.items()
                  if v is not None and str(v).strip() != ""}
    if wp_payload:
        secure_config.upsert_platform(db, wordpress.PROVIDER, "WordPress (bvtech.org)",
                                      "Website", wp_payload)
    out = blog_autopilot.save_config(
        db, enabled=body.enabled, every_days=body.every_days,
        wp_status=body.wp_status, cross_post_linkedin=body.cross_post_linkedin,
        topics=body.topics)
    audit.record(db, action="website.configure", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="website", ip=_ip(request),
                 detail=f"enabled={out['enabled']} status={out['wp_status']}")
    return get_settings(db=db, user=user)


@router.post("/test")
def test_connection(db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Live WordPress check — proves URL + username + app password actually work
    BEFORE anything auto-publishes."""
    try:
        return wordpress.test_connection(db)
    except wordpress.WPError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/posts")
def list_posts(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = db.query(BlogPost).order_by(BlogPost.id.desc()).limit(50).all()
    return [{"id": r.id, "title": r.title, "status": r.status, "url": r.url,
             "wp_post_id": r.wp_post_id, "error": r.error, "source": r.source,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


@router.post("/publish-now")
def publish_now(request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    """Write one article with Claude and publish it immediately (cadence bypass)."""
    from ...services import ai
    if not wordpress.configured(db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Connect WordPress first (site URL, username, app password).")
    if not ai.enabled():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Claude is not connected — add ANTHROPIC_API_KEY.")
    try:
        article = blog_autopilot.generate_article(db)
    except ai.AIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    if not article:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Claude returned an unparseable article — try again.")
    row = blog_autopilot.publish_article(db, article, source="manual")
    audit.record(db, action="website.publish_now", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="blog_post", target_id=str(row.id), ip=_ip(request),
                 detail=row.title[:80])
    if row.status != "posted":
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, row.error or "Publish failed")
    return {"ok": True, "id": row.id, "title": row.title, "url": row.url}


class ManualPostIn(BaseModel):
    title: str
    html: str
    excerpt: str | None = None
    wp_status: str | None = None   # override: publish | draft


@router.post("/publish")
def publish_manual(body: ManualPostIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Publish YOUR content (e.g. written/edited in Content Studio) to the site."""
    if not body.title.strip() or not body.html.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Title and body are required.")
    article = {"title": body.title, "excerpt": body.excerpt or "", "html": body.html}
    if body.wp_status in ("publish", "draft"):
        # temporary per-call status override, without persisting config
        cfg = blog_autopilot.get_config(db)
        if cfg["wp_status"] != body.wp_status:
            blog_autopilot.save_config(db, wp_status=body.wp_status)
            row = blog_autopilot.publish_article(db, article, source="manual")
            blog_autopilot.save_config(db, wp_status=cfg["wp_status"])
        else:
            row = blog_autopilot.publish_article(db, article, source="manual")
    else:
        row = blog_autopilot.publish_article(db, article, source="manual")
    audit.record(db, action="website.publish_manual", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="blog_post", target_id=str(row.id), ip=_ip(request),
                 detail=row.title[:80])
    if row.status != "posted":
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, row.error or "Publish failed")
    return {"ok": True, "id": row.id, "url": row.url}
