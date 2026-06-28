"""v0.20 scheduled client reports — staff CRUD. The recurring run-checks tick
delivers due reports (see services.scheduled_reports)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, require_roles
from ...models import Client, ReportSchedule, Role, User
from ...services import audit, scheduled_reports

router = APIRouter(prefix="/api/report-schedules", tags=["report-schedules"])

_CADENCES = {"weekly", "monthly", "quarterly"}


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _out(s: ReportSchedule) -> dict:
    return {"id": s.id, "client_id": s.client_id, "recipient_email": s.recipient_email,
            "cadence": s.cadence, "enabled": s.enabled,
            "last_sent_at": s.last_sent_at.isoformat() if s.last_sent_at else None}


class ScheduleIn(BaseModel):
    client_id: int
    recipient_email: str
    cadence: str = "monthly"


@router.get("")
def list_schedules(db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return [_out(s) for s in db.query(ReportSchedule).order_by(ReportSchedule.id).all()]


@router.post("", status_code=201)
def create_schedule(body: ScheduleIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if body.cadence not in _CADENCES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"cadence must be one of {sorted(_CADENCES)}")
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    s = ReportSchedule(client_id=body.client_id, recipient_email=body.recipient_email.strip(),
                       cadence=body.cadence, enabled=True)
    db.add(s)
    db.commit()
    audit.record(db, action="report_schedule.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="report_schedule", target_id=str(s.id),
                 client_id=s.client_id, ip=_ip(request), detail=f"cadence={s.cadence}")
    return _out(s)


@router.post("/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    s = db.get(ReportSchedule, schedule_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    s.enabled = not s.enabled
    db.commit()
    return _out(s)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    s = db.get(ReportSchedule, schedule_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    db.delete(s)
    db.commit()


@router.post("/run-now")
def run_now(db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Send any due reports immediately (also runs automatically via run-checks)."""
    return scheduled_reports.send_due(db)
