"""v0.2 routes: support tickets, client-admin user invites, device check-in history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...core.security import hash_password, random_token
from ...models import (
    Client, Device, DeviceCheckin, Role, SupportTicket, TicketStatus, User,
)
from ...services import audit

router = APIRouter(prefix="/api", tags=["v0.2"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Support tickets
# --------------------------------------------------------------------------- #
class TicketIn(BaseModel):
    subject: str
    body: str | None = None
    priority: str = "normal"
    client_id: int | None = None  # staff may set; clients use their own


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    # Determine which client the ticket belongs to.
    if is_staff(user):
        if not body.client_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "client_id required for staff")
        cid = body.client_id
    else:
        cid = user.client_id
        if not cid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No client associated")
    assert_client_access(user, cid)

    if body.priority not in ("low", "normal", "high", "urgent"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid priority")

    t = SupportTicket(client_id=cid, created_by_user_id=user.id, subject=body.subject,
                      body=body.body, priority=body.priority)
    db.add(t)
    db.commit()
    audit.record(db, action="ticket.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="ticket", target_id=str(t.id),
                 client_id=cid, ip=_ip(request), detail=f"subject={body.subject[:60]}")
    return {"id": t.id}


@router.get("/tickets")
def list_tickets(status_filter: str | None = None, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    q = db.query(SupportTicket)
    if not is_staff(user):
        q = q.filter(SupportTicket.client_id == user.client_id)
    if status_filter:
        q = q.filter(SupportTicket.status == status_filter)
    rows = q.order_by(SupportTicket.created_at.desc()).limit(200).all()
    return [
        {"id": t.id, "client_id": t.client_id, "subject": t.subject, "body": t.body,
         "priority": t.priority, "status": t.status.value,
         "created_at": t.created_at.isoformat()}
        for t in rows
    ]


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    assigned_to_user_id: int | None = None


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: int, body: TicketUpdate, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    if body.status is not None:
        t.status = body.status
    if body.assigned_to_user_id is not None:
        t.assigned_to_user_id = body.assigned_to_user_id
    db.commit()
    audit.record(db, action="ticket.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="ticket", target_id=str(t.id),
                 client_id=t.client_id, ip=_ip(request),
                 detail=f"status={t.status.value}")
    return {"ok": True, "status": t.status.value}


# --------------------------------------------------------------------------- #
# Client-admin user invites (scoped to own client only)
# --------------------------------------------------------------------------- #
class InviteIn(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: Role = Role.CLIENT_VIEWER


@router.post("/client-users", status_code=201)
def invite_client_user(body: InviteIn, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(current_user)):
    """A CLIENT_ADMIN may create CLIENT_VIEWER/CLIENT_ADMIN users in their OWN
    client only. Staff (OWNER/TECH) may create client users for any client."""
    # Only client_admin or staff may invite.
    if user.role not in (Role.OWNER, Role.TECH, Role.CLIENT_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to invite users")

    # Client admins can only create client-side roles, in their own org.
    if user.role == Role.CLIENT_ADMIN:
        if body.role not in (Role.CLIENT_ADMIN, Role.CLIENT_VIEWER):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Client admins create client roles only")
        target_client = user.client_id
    else:
        # staff path — derive client from query? Require it explicitly for safety.
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Staff: create client users via /api/clients flow (v0.3)")

    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")

    # Generate a temporary password; in v0.3 this becomes an email invite link.
    temp_pw = random_token(12)
    new_user = User(
        email=body.email.lower(), full_name=body.full_name,
        password_hash=hash_password(temp_pw), role=body.role,
        client_id=target_client, is_active=True,
    )
    db.add(new_user)
    db.commit()
    audit.record(db, action="client_user.invite", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="user", target_id=str(new_user.id),
                 client_id=target_client, ip=_ip(request), detail=f"role={body.role.value}")
    # temp password returned once to the inviter to relay; never stored in plaintext.
    return {"id": new_user.id, "email": new_user.email, "temp_password": temp_pw}


@router.get("/client-users")
def list_client_users(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role == Role.CLIENT_ADMIN:
        q = db.query(User).filter(User.client_id == user.client_id)
    elif is_staff(user):
        q = db.query(User).filter(User.client_id.isnot(None))
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    return [
        {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role.value,
         "client_id": u.client_id, "is_active": u.is_active}
        for u in q.order_by(User.email).all()
    ]


# --------------------------------------------------------------------------- #
# Device check-in history
# --------------------------------------------------------------------------- #
@router.get("/devices/{device_id}/history")
def device_history(device_id: int, limit: int = 50, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    assert_client_access(user, dev.client_id)
    limit = max(1, min(limit, 500))
    rows = (db.query(DeviceCheckin)
            .filter(DeviceCheckin.device_id == device_id)
            .order_by(DeviceCheckin.ts.desc()).limit(limit).all())
    return [
        {"ts": r.ts.isoformat(), "cpu_pct": r.cpu_pct, "ram_pct": r.ram_pct,
         "disk_pct": r.disk_pct, "health_score": r.health_score,
         "av_status": r.av_status, "patch_status": r.patch_status}
        for r in rows
    ]
