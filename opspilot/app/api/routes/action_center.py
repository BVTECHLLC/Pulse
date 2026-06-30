"""v0.32 Action Center API.

One tenant-scoped call returns a ranked, explainable list of everything that
needs a human's attention right now — across RMM, PSA, security, and billing —
plus an overall Ops Score. The heavy lifting lives in services/action_center.py;
this route just resolves scope/RBAC and serializes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import Role, SupportTicket, User
from ...services import action_center as ac, audit, automation, sla

router = APIRouter(prefix="/api", tags=["action-center"])

# Action-item severity -> ticket priority.
_SEV_TO_PRIORITY = {"critical": "urgent", "high": "high", "medium": "normal", "low": "low"}


@router.get("/action-center")
def get_action_center(
    client_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    staff = is_staff(user)
    # A client user is pinned to their own org; a filter to a foreign client is denied.
    if client_id is not None and not staff:
        assert_client_access(user, client_id)
    return ac.build(db, user, client_id=client_id, limit=limit, is_staff=staff)


class CreateTicketFromItem(BaseModel):
    client_id: int
    title: str
    detail: str | None = None
    severity: str = "medium"
    link: str | None = None
    kind: str | None = None          # the action item's kind, for the audit trail
    entity_type: str | None = None
    entity_id: str | None = None


@router.post("/action-center/create-ticket", status_code=201)
def create_ticket_from_item(body: CreateTicketFromItem, request: Request,
                            db: Session = Depends(get_db),
                            user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Turn an Action Center item into a tracked ticket in one click. Maps the
    item's severity to a ticket priority, stamps SLA targets, and lets automation
    react — exactly like a normally-created ticket."""
    assert_client_access(user, body.client_id)
    priority = _SEV_TO_PRIORITY.get(body.severity, "normal")
    src = f" [from Action Center: {body.kind}]" if body.kind else ""
    body_text = "\n".join(p for p in [body.detail, (f"Ref: {body.link}" if body.link else None)] if p)
    t = SupportTicket(client_id=body.client_id, created_by_user_id=user.id,
                      subject=body.title[:200], body=(body_text or None),
                      priority=priority, created_at=datetime.now(timezone.utc))
    sla.stamp_due_dates(db, t)
    db.add(t)
    db.commit()
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    audit.record(db, action="action_center.create_ticket", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value, target_type="ticket",
                 target_id=str(t.id), client_id=body.client_id, ip=ip,
                 detail=f"{body.kind or 'item'}{src} -> ticket #{t.id} ({priority})")
    automation.dispatch(db, "ticket.created", automation.build_ticket_context(t))
    return {"id": t.id, "priority": priority, "subject": t.subject}
