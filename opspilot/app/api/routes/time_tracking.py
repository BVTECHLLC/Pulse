"""v0.26 time tracking — live timers, task time, and unbilled visibility.

Closes the PSA money loop: start a stopwatch on a ticket or project task, stop it
to log billable minutes, see exactly how much billable-but-uninvoiced time each
client has accrued, then roll it into an invoice (existing /invoices/generate).
Staff only — time is staff-logged work."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import (
    ActiveTimer, Client, ProjectTask, Role, SupportTicket, TimeEntry, User,
)
from ...services import audit

router = APIRouter(prefix="/api", tags=["time-tracking"])

_STAFF = require_roles(Role.OWNER, Role.TECH)


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _aware(dt):
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


def _resolve_context(db: Session, ticket_id: int | None, task_id: int | None) -> tuple[int, int | None, int | None]:
    """Return (client_id, ticket_id, task_id) for a timer/entry. Exactly one of
    ticket/task must be given; client is derived from it."""
    if bool(ticket_id) == bool(task_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide exactly one of ticket_id or task_id")
    if ticket_id:
        tk = db.get(SupportTicket, ticket_id)
        if not tk:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
        return tk.client_id, ticket_id, None
    ts = db.get(ProjectTask, task_id)
    if not ts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return ts.client_id, None, task_id


def _entry_out(e: TimeEntry) -> dict:
    return {"id": e.id, "client_id": e.client_id, "ticket_id": e.ticket_id, "task_id": e.task_id,
            "minutes": e.minutes, "billable": e.billable, "invoiced": e.invoiced,
            "note": e.note, "user_email": e.user_email,
            "created_at": e.created_at.isoformat() if e.created_at else None}


def _timer_out(t: ActiveTimer, now: datetime) -> dict:
    elapsed = int((now - _aware(t.started_at)).total_seconds())
    return {"id": t.id, "client_id": t.client_id, "ticket_id": t.ticket_id, "task_id": t.task_id,
            "note": t.note, "billable": t.billable,
            "started_at": _aware(t.started_at).isoformat(), "elapsed_seconds": max(0, elapsed)}


def _stop_timer(db: Session, t: ActiveTimer, now: datetime) -> TimeEntry:
    minutes = max(1, math.ceil((now - _aware(t.started_at)).total_seconds() / 60))
    e = TimeEntry(ticket_id=t.ticket_id, task_id=t.task_id, client_id=t.client_id,
                  user_id=t.user_id, user_email=t.user_email, minutes=minutes,
                  note=t.note, billable=t.billable)
    db.add(e)
    db.delete(t)
    return e


# --------------------------------------------------------------------------- #
# Live timers
# --------------------------------------------------------------------------- #
class TimerStart(BaseModel):
    ticket_id: int | None = None
    task_id: int | None = None
    note: str | None = None
    billable: bool = True


@router.get("/timers/current")
def current_timer(db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    t = db.query(ActiveTimer).filter(ActiveTimer.user_id == user.id).first()
    return _timer_out(t, datetime.now(timezone.utc)) if t else None


@router.post("/timers/start", status_code=201)
def start_timer(body: TimerStart, request: Request, db: Session = Depends(get_db),
                user: User = Depends(_STAFF)):
    client_id, ticket_id, task_id = _resolve_context(db, body.ticket_id, body.task_id)
    now = datetime.now(timezone.utc)
    # At most one running timer per user — stop & bank the previous one first.
    existing = db.query(ActiveTimer).filter(ActiveTimer.user_id == user.id).first()
    banked = None
    if existing:
        banked = _stop_timer(db, existing, now)
        db.flush()
    t = ActiveTimer(user_id=user.id, user_email=user.email, client_id=client_id,
                    ticket_id=ticket_id, task_id=task_id, note=body.note,
                    billable=body.billable, started_at=now)
    db.add(t)
    db.commit()
    out = _timer_out(t, datetime.now(timezone.utc))
    if banked:
        out["banked_entry"] = _entry_out(banked)
    return out


@router.post("/timers/stop")
def stop_timer(request: Request, db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    t = db.query(ActiveTimer).filter(ActiveTimer.user_id == user.id).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No running timer")
    e = _stop_timer(db, t, datetime.now(timezone.utc))
    db.commit()
    audit.record(db, action="time.logged", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="time_entry", target_id=str(e.id),
                 client_id=e.client_id, ip=_ip(request), detail=f"{e.minutes}min billable={e.billable}")
    return _entry_out(e)


# --------------------------------------------------------------------------- #
# Manual task time (parity with /tickets/{id}/time)
# --------------------------------------------------------------------------- #
class TaskTimeIn(BaseModel):
    minutes: int
    note: str | None = None
    billable: bool = True


@router.post("/tasks/{task_id}/time", status_code=201)
def log_task_time(task_id: int, body: TaskTimeIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(_STAFF)):
    ts = db.get(ProjectTask, task_id)
    if not ts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    if body.minutes <= 0 or body.minutes > 24 * 60:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "minutes must be 1..1440")
    e = TimeEntry(task_id=task_id, client_id=ts.client_id, user_id=user.id, user_email=user.email,
                  minutes=body.minutes, note=body.note, billable=body.billable)
    db.add(e)
    db.commit()
    return _entry_out(e)


# --------------------------------------------------------------------------- #
# Reporting — entries + unbilled rollup
# --------------------------------------------------------------------------- #
@router.get("/time/entries")
def list_entries(client_id: int | None = None, limit: int = 100, db: Session = Depends(get_db),
                 user: User = Depends(_STAFF)):
    q = db.query(TimeEntry)
    if client_id:
        q = q.filter(TimeEntry.client_id == client_id)
    rows = q.order_by(TimeEntry.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return [_entry_out(e) for e in rows]


@router.get("/time/unbilled")
def unbilled(db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    """Billable, not-yet-invoiced time grouped by client — what's ready to bill."""
    rows = (db.query(TimeEntry.client_id,
                     func.sum(TimeEntry.minutes).label("minutes"),
                     func.count(TimeEntry.id).label("entries"))
            .filter(TimeEntry.billable.is_(True), TimeEntry.invoiced.is_(False))
            .group_by(TimeEntry.client_id).all())
    names = {c.id: c.name for c in db.query(Client).all()}
    out = [{"client_id": cid, "client_name": names.get(cid, f"#{cid}"),
            "minutes": int(mins or 0), "hours": round((mins or 0) / 60.0, 2), "entries": int(cnt)}
           for (cid, mins, cnt) in rows]
    out.sort(key=lambda r: r["minutes"], reverse=True)
    total_min = sum(r["minutes"] for r in out)
    return {"by_client": out, "total_minutes": total_min, "total_hours": round(total_min / 60.0, 2)}
