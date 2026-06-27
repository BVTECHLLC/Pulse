"""Support tickets (with SLA tracking, assignment & time entries), client-admin
user invites, and device check-in history."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...core.security import hash_password, random_token
from ...models import (
    Client, Device, DeviceCheckin, PRIORITIES, Role, STAFF_ROLES, SupportTicket,
    TicketComment, TicketStatus, TimeEntry, User,
)
from ...services import audit, sla

router = APIRouter(prefix="/api", tags=["tickets"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize_ticket(t: SupportTicket, now: datetime) -> dict:
    return {
        "id": t.id, "client_id": t.client_id, "subject": t.subject, "body": t.body,
        "priority": t.priority, "status": t.status.value,
        "assigned_to_user_id": t.assigned_to_user_id,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
        "sla": sla.evaluate(t, now),
    }


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

    if body.priority not in PRIORITIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid priority")

    t = SupportTicket(client_id=cid, created_by_user_id=user.id, subject=body.subject,
                      body=body.body, priority=body.priority, created_at=datetime.now(timezone.utc))
    sla.stamp_due_dates(db, t)  # set response/resolution due targets from policy
    db.add(t)
    db.commit()
    audit.record(db, action="ticket.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="ticket", target_id=str(t.id),
                 client_id=cid, ip=_ip(request), detail=f"subject={body.subject[:60]}")
    return {"id": t.id}


@router.get("/tickets")
def list_tickets(status_filter: str | None = None, mine: bool = False,
                 breached: bool = False, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    q = db.query(SupportTicket)
    if not is_staff(user):
        q = q.filter(SupportTicket.client_id == user.client_id)
    if status_filter:
        q = q.filter(SupportTicket.status == status_filter)
    if mine and is_staff(user):
        q = q.filter(SupportTicket.assigned_to_user_id == user.id)
    rows = q.order_by(SupportTicket.created_at.desc()).limit(200).all()
    now = datetime.now(timezone.utc)
    out = [_serialize_ticket(t, now) for t in rows]
    if breached:
        out = [t for t in out if t["sla"]["breached"]]
    return out


@router.get("/tickets/sla-summary")
def sla_summary(db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Open-ticket SLA health for the staff dashboard: how many are breaching or
    at risk (due within 60 min)."""
    now = datetime.now(timezone.utc)
    rows = (db.query(SupportTicket)
            .filter(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
            .all())
    out = {"open": len(rows), "response_breached": 0, "resolution_breached": 0, "at_risk": 0}
    for t in rows:
        s = sla.evaluate(t, now)
        if s["response_breached"]:
            out["response_breached"] += 1
        if s["resolution_breached"]:
            out["resolution_breached"] += 1
        left = s["resolution_minutes_left"]
        if not s["breached"] and left is not None and 0 <= left <= 60:
            out["at_risk"] += 1
    return out


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    assert_client_access(user, t.client_id)
    data = _serialize_ticket(t, datetime.now(timezone.utc))
    # Time rollup is staff-facing only.
    if is_staff(user):
        entries = db.query(TimeEntry).filter(TimeEntry.ticket_id == t.id).all()
        data["time_logged_minutes"] = sum(e.minutes for e in entries)
        data["time_billable_minutes"] = sum(e.minutes for e in entries if e.billable)
    return data


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    assigned_to_user_id: int | None = None
    priority: str | None = None


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: int, body: TicketUpdate, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    if body.priority is not None:
        if body.priority not in PRIORITIES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid priority")
        t.priority = body.priority
        sla.stamp_due_dates(db, t)  # re-base SLA targets on the new priority
    if body.assigned_to_user_id is not None:
        # Only staff users may carry tickets.
        assignee = db.get(User, body.assigned_to_user_id)
        if not assignee or assignee.role not in STAFF_ROLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assignee must be a staff user")
        t.assigned_to_user_id = body.assigned_to_user_id
    if body.status is not None:
        t.status = body.status
        # Stamp resolution time once when the ticket first closes out.
        if body.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED) and not t.resolved_at:
            t.resolved_at = datetime.now(timezone.utc)
        if body.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS):
            t.resolved_at = None  # reopened
    db.commit()
    audit.record(db, action="ticket.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="ticket", target_id=str(t.id),
                 client_id=t.client_id, ip=_ip(request),
                 detail=f"status={t.status.value}")
    return {"ok": True, "status": t.status.value}


# --------------------------------------------------------------------------- #
# Ticket comments (threaded conversation)
# --------------------------------------------------------------------------- #
class CommentIn(BaseModel):
    body: str
    internal: bool = False  # staff-only note; never shown to client users


@router.post("/tickets/{ticket_id}/comments", status_code=201)
def add_comment(ticket_id: int, body: CommentIn, request: Request,
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    assert_client_access(user, t.client_id)

    if not body.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Comment body required")
    # Only staff may post internal notes; clients can never create or read them.
    internal = bool(body.internal) and is_staff(user)

    c = TicketComment(ticket_id=t.id, author_user_id=user.id, author_email=user.email,
                      author_role=user.role.value, body=body.body.strip(), internal=internal)
    db.add(c)
    now = datetime.now(timezone.utc)
    # First public staff reply satisfies the response SLA.
    if is_staff(user) and not internal and t.first_responded_at is None:
        t.first_responded_at = now
    # Touch the ticket so list ordering reflects recent activity.
    t.updated_at = now
    db.commit()
    audit.record(db, action="ticket.comment", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="ticket", target_id=str(t.id),
                 client_id=t.client_id, ip=_ip(request),
                 detail=f"internal={internal}")
    return {"id": c.id, "internal": internal}


@router.get("/tickets/{ticket_id}/comments")
def list_comments(ticket_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    assert_client_access(user, t.client_id)

    q = db.query(TicketComment).filter(TicketComment.ticket_id == ticket_id)
    if not is_staff(user):
        # Client users never see internal staff notes.
        q = q.filter(TicketComment.internal.is_(False))
    rows = q.order_by(TicketComment.created_at.asc()).all()
    return [
        {"id": c.id, "author_email": c.author_email, "author_role": c.author_role,
         "body": c.body, "internal": c.internal, "created_at": c.created_at.isoformat()}
        for c in rows
    ]


# --------------------------------------------------------------------------- #
# Ticket time tracking (staff only — powers PSA time rollups & invoicing)
# --------------------------------------------------------------------------- #
class TimeEntryIn(BaseModel):
    minutes: int
    note: str | None = None
    billable: bool = True


@router.post("/tickets/{ticket_id}/time", status_code=201)
def log_time(ticket_id: int, body: TimeEntryIn, request: Request,
             db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    if body.minutes <= 0 or body.minutes > 24 * 60:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "minutes must be 1..1440")

    e = TimeEntry(ticket_id=t.id, client_id=t.client_id, user_id=user.id,
                  user_email=user.email, minutes=body.minutes, note=body.note,
                  billable=body.billable)
    db.add(e)
    db.commit()
    audit.record(db, action="ticket.time_log", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="ticket", target_id=str(t.id),
                 client_id=t.client_id, ip=_ip(request),
                 detail=f"minutes={body.minutes} billable={body.billable}")
    return {"id": e.id}


@router.get("/tickets/{ticket_id}/time")
def list_time(ticket_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    rows = (db.query(TimeEntry).filter(TimeEntry.ticket_id == ticket_id)
            .order_by(TimeEntry.created_at.desc()).all())
    return [
        {"id": e.id, "user_email": e.user_email, "minutes": e.minutes,
         "note": e.note, "billable": e.billable, "created_at": e.created_at.isoformat()}
        for e in rows
    ]


# --------------------------------------------------------------------------- #
# Staff directory (for assignment dropdowns) + workload
# --------------------------------------------------------------------------- #
@router.get("/staff")
def list_staff(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Active staff users with their current open-ticket load."""
    staff = (db.query(User).filter(User.role.in_(list(STAFF_ROLES)), User.is_active.is_(True))
             .order_by(User.email).all())
    open_states = [TicketStatus.OPEN, TicketStatus.IN_PROGRESS]
    out = []
    for s in staff:
        load = (db.query(SupportTicket)
                .filter(SupportTicket.assigned_to_user_id == s.id,
                        SupportTicket.status.in_(open_states)).count())
        out.append({"id": s.id, "email": s.email, "full_name": s.full_name,
                    "role": s.role.value, "open_tickets": load})
    return out


# --------------------------------------------------------------------------- #
# SLA policies (per-priority response/resolution targets) — staff only
# --------------------------------------------------------------------------- #
class SLAPolicyIn(BaseModel):
    client_id: int | None = None  # None == global default
    priority: str
    response_minutes: int
    resolution_minutes: int


@router.get("/sla-policies")
def list_sla_policies(db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Configured rows plus the built-in defaults, so the UI can show the full
    effective matrix."""
    from ...models import SLAPolicy  # local import keeps the module header tidy
    rows = db.query(SLAPolicy).order_by(SLAPolicy.client_id, SLAPolicy.priority).all()
    return {
        "defaults": {p: {"response_minutes": r, "resolution_minutes": res}
                     for p, (r, res) in sla.DEFAULT_TARGETS.items()},
        "policies": [
            {"id": p.id, "client_id": p.client_id, "priority": p.priority,
             "response_minutes": p.response_minutes, "resolution_minutes": p.resolution_minutes}
            for p in rows
        ],
    }


@router.put("/sla-policies")
def upsert_sla_policy(body: SLAPolicyIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...models import SLAPolicy
    if body.priority not in PRIORITIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid priority")
    if body.response_minutes < 1 or body.resolution_minutes < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Minutes must be >= 1")
    if body.response_minutes > body.resolution_minutes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Response target cannot exceed resolution target")

    q = db.query(SLAPolicy).filter(SLAPolicy.priority == body.priority)
    q = q.filter(SLAPolicy.client_id == body.client_id) if body.client_id is not None \
        else q.filter(SLAPolicy.client_id.is_(None))
    p = q.first()
    if not p:
        p = SLAPolicy(client_id=body.client_id, priority=body.priority,
                      response_minutes=body.response_minutes,
                      resolution_minutes=body.resolution_minutes)
        db.add(p)
    else:
        p.response_minutes = body.response_minutes
        p.resolution_minutes = body.resolution_minutes
    db.commit()
    audit.record(db, action="sla_policy.upsert", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="sla_policy", target_id=str(p.id),
                 client_id=body.client_id, ip=_ip(request),
                 detail=f"priority={body.priority}")
    return {"id": p.id, "priority": p.priority, "response_minutes": p.response_minutes,
            "resolution_minutes": p.resolution_minutes}


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
