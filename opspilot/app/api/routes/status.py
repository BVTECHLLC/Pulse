"""v0.84 Public status page — unauthenticated public view + owner-managed
incidents and config."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, StatusIncident, User
from ...services import audit, branding, status_page

router = APIRouter(prefix="/api/status", tags=["status"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Public (no auth) — the shareable page fetches this.
# --------------------------------------------------------------------------- #
@router.get("/public")
def public_status(db: Session = Depends(get_db)):
    view = status_page.public_view(db)
    if view is None:
        # Page not enabled — don't reveal that it exists as a managed surface.
        raise HTTPException(404, "status page not available")
    view["brand"] = branding.public_branding(db)
    return view


# --------------------------------------------------------------------------- #
# Owner: config
# --------------------------------------------------------------------------- #
@router.get("/config")
def get_config(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return status_page.get_config(db)


class ConfigIn(BaseModel):
    enabled: bool | None = None
    headline: str | None = None
    intro: str | None = None


@router.put("/config")
def save_config(body: ConfigIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    out = status_page.save_config(db, {k: v for k, v in body.model_dump().items() if v is not None})
    audit.record(db, action="status.config", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="status_page", ip=_ip(request),
                 detail=f"enabled={out['enabled']}")
    return out


# --------------------------------------------------------------------------- #
# Owner/tech: incident management
# --------------------------------------------------------------------------- #
@router.get("/incidents")
def list_incidents(db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return {"incidents": status_page.list_incidents(db)}


class IncidentIn(BaseModel):
    title: str
    impact: str = "minor"
    status: str = "investigating"
    body: str | None = None


@router.post("/incidents", status_code=201)
def create_incident(body: IncidentIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if body.impact not in status_page.IMPACTS:
        raise HTTPException(400, f"impact must be one of {status_page.IMPACTS}")
    if body.status not in status_page.STATUSES:
        raise HTTPException(400, f"status must be one of {status_page.STATUSES}")
    inc = StatusIncident(title=body.title[:200], impact=body.impact, status=body.status,
                         body=body.body, created_by_user_id=user.id)
    if body.status == "resolved":
        inc.resolved_at = datetime.now(timezone.utc)
    db.add(inc)
    db.commit()
    db.refresh(inc)
    audit.record(db, action="status.incident.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="status_incident", target_id=str(inc.id),
                 ip=_ip(request), detail=f"{inc.impact}:{inc.title}")
    return {"id": inc.id}


class IncidentUpdateIn(BaseModel):
    status: str | None = None
    impact: str | None = None
    body: str | None = None
    title: str | None = None


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id: int, body: IncidentUpdateIn, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    inc = db.get(StatusIncident, incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    if body.impact is not None:
        if body.impact not in status_page.IMPACTS:
            raise HTTPException(400, f"impact must be one of {status_page.IMPACTS}")
        inc.impact = body.impact
    if body.status is not None:
        if body.status not in status_page.STATUSES:
            raise HTTPException(400, f"status must be one of {status_page.STATUSES}")
        inc.status = body.status
        if body.status == "resolved" and inc.resolved_at is None:
            inc.resolved_at = datetime.now(timezone.utc)
        if body.status != "resolved":
            inc.resolved_at = None      # reopened
    if body.title is not None:
        inc.title = body.title[:200]
    if body.body is not None:
        inc.body = body.body
    db.commit()
    audit.record(db, action="status.incident.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="status_incident", target_id=str(inc.id),
                 ip=_ip(request), detail=f"{inc.status}:{inc.impact}")
    return {"id": inc.id, "status": inc.status, "resolved": inc.status == "resolved"}
