"""v0.25 live command-center overview.

One tenant-scoped call fuses RMM + PSA + billing + security into a single pulse,
so the dashboard's home screen is a real-time command center instead of a dozen
round-trips. Staff see the whole fleet; client users see only their own org."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff, require_roles
from ...models import (
    Alert, AlertStatus, AuditLog, Client, Contract, Device, Invoice, InvoiceStatus,
    License, Project, ProjectStatus, ProjectTask, Role, SupportTicket, TicketStatus, User,
)
from ...services import sla
from .contracts import monthly_value

router = APIRouter(prefix="/api", tags=["overview"])

ONLINE_WINDOW = timedelta(minutes=30)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/briefing")
def briefing_view(db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """The cross-business morning briefing (preview of what `send_digest` emails)."""
    from ...services import briefing as _b
    brief = _b.build(db)
    return {**brief, "text": _b.render_text(brief)}


@router.get("/site-health")
def site_health(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Per-client health rollup (worst-first). Staff see all clients; a client
    user sees only their own company."""
    from ...services import proactive
    return {"sites": proactive.site_health(db, user)}


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    now = datetime.now(timezone.utc)
    staff = is_staff(user)
    cid = user.client_id

    def scope(q, model):
        return q if staff else q.filter(model.client_id == cid)

    # --- Clients ---
    cq = db.query(Client) if staff else db.query(Client).filter(Client.id == cid)
    clients = cq.all()
    clients_active = sum(1 for c in clients if c.is_active)

    # --- Devices / health / patch compliance ---
    devices = scope(db.query(Device), Device).all()
    online = sum(1 for d in devices if d.last_checkin and (now - _aware(d.last_checkin)) <= ONLINE_WINDOW)
    healths = [d.health_score for d in devices if d.health_score is not None]
    avg_health = round(sum(healths) / len(healths)) if healths else None
    attention = sum(1 for d in devices if (d.health_score if d.health_score is not None else 100) < 70)
    pending_patches = sum((d.patches_pending or 0) for d in devices)
    devices_behind = sum(1 for d in devices if (d.patches_pending or 0) > 0)
    reported = [d for d in devices if d.patches_pending is not None]
    patch_compliance = (round(sum(1 for d in reported if (d.patches_pending or 0) == 0) / len(reported) * 100)
                        if reported else None)

    # --- Alerts ---
    aq = scope(db.query(Alert).filter(Alert.status != AlertStatus.RESOLVED), Alert).all()
    alerts_active = len(aq)
    alerts_critical = sum(1 for a in aq if a.severity.value == "critical")

    # --- Tickets + SLA ---
    open_tickets = scope(db.query(SupportTicket).filter(
        SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS])), SupportTicket).all()
    sla_breached = 0
    sla_at_risk = 0
    for t in open_tickets:
        s = sla.evaluate(t, now)
        if s["breached"]:
            sla_breached += 1
        else:
            mins = [m for m in (s["response_minutes_left"], s["resolution_minutes_left"]) if m is not None]
            if mins and min(mins) <= 60:
                sla_at_risk += 1

    # --- Projects ---
    projects = scope(db.query(Project), Project).all()
    active_projects = sum(1 for p in projects if p.status == ProjectStatus.ACTIVE)
    ptasks = scope(db.query(ProjectTask), ProjectTask).all()
    tasks_done = sum(1 for t in ptasks if t.status == "done")

    # --- Billing: MRR (active contracts normalized + license monthly) + outstanding ---
    contracts = scope(db.query(Contract).filter(Contract.status == "active"), Contract).all()
    contract_mrr = sum(monthly_value(c) for c in contracts)
    license_mrr = sum((l.monthly_cost or 0) for l in scope(db.query(License), License).all())
    mrr = round(contract_mrr + license_mrr, 2)
    # Outstanding = issued (sent) but not yet paid.
    outstanding = scope(db.query(Invoice).filter(Invoice.status == InvoiceStatus.SENT), Invoice).all()
    outstanding_total = round(sum((i.total or 0) for i in outstanding), 2)

    # --- Recent activity (audit trail), scoped ---
    actq = db.query(AuditLog).order_by(AuditLog.ts.desc())
    if not staff:
        actq = actq.filter(AuditLog.client_id == cid)
    activity = [{"ts": a.ts.isoformat() if a.ts else None, "action": a.action,
                 "actor": a.actor_email, "target": f"{a.target_type or ''} {a.target_id or ''}".strip(),
                 "success": a.success} for a in actq.limit(12).all()]

    return {
        "generated_at": now.isoformat(),
        "clients": {"total": len(clients), "active": clients_active},
        "devices": {"total": len(devices), "online": online, "offline": len(devices) - online,
                    "avg_health": avg_health, "attention": attention},
        "patch": {"compliance_pct": patch_compliance, "devices_behind": devices_behind,
                  "pending_total": pending_patches},
        "alerts": {"active": alerts_active, "critical": alerts_critical},
        "tickets": {"open": len(open_tickets), "sla_breached": sla_breached, "sla_at_risk": sla_at_risk},
        "projects": {"active": active_projects, "total": len(projects),
                     "tasks_total": len(ptasks), "tasks_done": tasks_done},
        "billing": {"mrr": mrr, "outstanding_total": outstanding_total,
                    "outstanding_count": len(outstanding)},
        "activity": activity,
    }
