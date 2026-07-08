"""v1.20 Content Autopilot API — one-click daily posting to all four channels."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, content_autopilot, jp_site

router = APIRouter(prefix="/api/content-autopilot", tags=["content-autopilot"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


@router.get("/status")
def get_status(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return content_autopilot.status(db)


class SettingsIn(BaseModel):
    enabled: bool | None = None
    hour_utc: int | None = None
    channels: dict[str, bool] | None = None


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER))):
    return content_autopilot.save_config(db, enabled=body.enabled,
                                         hour_utc=body.hour_utc, channels=body.channels)


class JpIn(BaseModel):
    project: str | None = None
    token: str | None = None
    branch: str | None = None


@router.put("/jp-site")
def put_jp(body: JpIn, db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OWNER))):
    if body.project is None and body.token is None and body.branch is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to save.")
    return jp_site.save_config(db, project=body.project, token=body.token,
                               branch=body.branch)


@router.post("/run-now")
def run_now(request: Request, db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER))):
    """Post to every enabled channel right now (ignores hour + daily dedupe)."""
    out = content_autopilot.run_daily(db, force=True)
    audit.record(db, action="content_autopilot.run_now", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="content", ip=_ip(request),
                 detail=str({k: v["ok"] for k, v in out.get("results", {}).items()})[:200])
    return out
