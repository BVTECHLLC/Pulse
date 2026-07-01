"""v0.75 White-label branding — public read (login/portal need it) + staff write."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, branding

router = APIRouter(prefix="/api/branding", tags=["branding"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


@router.get("")
def get_branding(db: Session = Depends(get_db)):
    """Public: display-only brand values (no auth — the login page uses this)."""
    return branding.public_branding(db)


class BrandingIn(BaseModel):
    company: str | None = None
    product: str | None = None
    logo_url: str | None = None
    accent: str | None = None
    support_email: str | None = None
    tagline: str | None = None
    footer_note: str | None = None


@router.put("")
def save_branding(body: BrandingIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    out = branding.save_branding(db, {k: v for k, v in body.model_dump().items() if v is not None})
    audit.record(db, action="branding.save", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="branding", ip=_ip(request),
                 detail=out.get("app_name", ""))
    return out
