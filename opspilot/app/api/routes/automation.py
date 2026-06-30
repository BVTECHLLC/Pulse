"""v0.5 automation routes: rule CRUD, the execution log, a scheduler 'tick'
(`run-checks`), and in-app notifications.

Rules/runs are staff-only (they act across clients). Notifications are scoped:
staff see staff-targeted + global notifications; client users see only their own
client's notifications addressed to them.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff, require_roles
from ...models import (
    AUTOMATION_ACTIONS, AUTOMATION_TRIGGERS, AutomationRule, AutomationRun,
    Client, Notification, Role, SupportTicket, TicketStatus, User,
)
from ...services import audit, automation, monitoring, scheduled_reports, sla

router = APIRouter(prefix="/api/automation", tags=["automation"])
notif_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
class RuleIn(BaseModel):
    name: str
    trigger: str
    conditions: dict = {}
    actions: list = []
    client_id: int | None = None
    enabled: bool = True


def _serialize_rule(r: AutomationRule) -> dict:
    return {
        "id": r.id, "name": r.name, "trigger": r.trigger, "enabled": r.enabled,
        "client_id": r.client_id, "conditions": r.conditions, "actions": r.actions,
        "trigger_count": r.trigger_count,
        "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None,
    }


def _validate_rule(body: RuleIn, db: Session) -> None:
    if body.trigger not in AUTOMATION_TRIGGERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"trigger must be one of {list(AUTOMATION_TRIGGERS)}")
    if not isinstance(body.actions, list) or not body.actions:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one action is required")
    for a in body.actions:
        if not isinstance(a, dict) or a.get("type") not in AUTOMATION_ACTIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"each action.type must be one of {list(AUTOMATION_ACTIONS)}")
    if not isinstance(body.conditions, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "conditions must be an object")
    if body.client_id is not None and not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")


@router.get("/rules")
def list_rules(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = db.query(AutomationRule).order_by(AutomationRule.id.desc()).all()
    return [_serialize_rule(r) for r in rows]


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    _validate_rule(body, db)
    r = AutomationRule(name=body.name[:200], trigger=body.trigger, conditions=body.conditions,
                       actions=body.actions, client_id=body.client_id, enabled=body.enabled,
                       created_by_user_id=user.id, author_email=user.email)
    db.add(r)
    db.commit()
    audit.record(db, action="automation.rule_create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="automation_rule", target_id=str(r.id),
                 client_id=body.client_id, ip=_ip(request), detail=f"trigger={body.trigger}")
    return {"id": r.id}


class RuleUpdate(BaseModel):
    name: str | None = None
    conditions: dict | None = None
    actions: list | None = None
    enabled: bool | None = None


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    r = db.get(AutomationRule, rule_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    if body.name is not None:
        r.name = body.name[:200]
    if body.conditions is not None:
        r.conditions = body.conditions
    if body.actions is not None:
        for a in body.actions:
            if not isinstance(a, dict) or a.get("type") not in AUTOMATION_ACTIONS:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid action")
        r.actions = body.actions
    if body.enabled is not None:
        r.enabled = body.enabled
    db.commit()
    audit.record(db, action="automation.rule_update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="automation_rule", target_id=str(r.id),
                 client_id=r.client_id, ip=_ip(request), detail=f"enabled={r.enabled}")
    return _serialize_rule(r)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    r = db.get(AutomationRule, rule_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    db.delete(r)
    db.commit()
    audit.record(db, action="automation.rule_delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="automation_rule", target_id=str(rule_id),
                 ip=_ip(request))
    return {"ok": True}


@router.get("/runs")
def list_runs(limit: int = 100, db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    limit = max(1, min(limit, 500))
    rows = db.query(AutomationRun).order_by(AutomationRun.created_at.desc()).limit(limit).all()
    return [
        {"id": r.id, "rule_id": r.rule_id, "rule_name": r.rule_name, "trigger": r.trigger,
         "client_id": r.client_id, "success": r.success, "summary": r.summary,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Scheduler tick: sweep offline devices + fire SLA-breach automation
# --------------------------------------------------------------------------- #
@router.post("/run-checks")
def run_checks(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """The cron entrypoint. In production a scheduler hits this on an interval;
    staff can also run it on demand. It (1) sweeps for offline devices and fires
    alert.opened automation for new ones, and (2) fires ticket.sla_breached for
    open tickets that have newly breached (de-duplicated via sla_breach_alerted)."""
    sweep, new_offline = monitoring.sweep_offline(db)
    from ...services import auto_remediation
    for alert in new_offline:
        from ...models import Device
        dev = db.get(Device, alert.device_id)
        automation.dispatch(db, "alert.opened", automation.build_alert_context(alert, dev))
        try:
            auto_remediation.on_alert(db, alert, dev)   # detect → fix
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    open_tickets = (db.query(SupportTicket)
                    .filter(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
                    .all())
    from ...services import sla_escalation
    sla_fired = 0
    escalated = 0
    for t in open_tickets:
        s = sla.evaluate(t, now)
        if s["breached"] and not t.sla_breach_alerted:
            t.sla_breach_alerted = True
            # Built-in escalation: bump priority + internal note + notification.
            esc = sla_escalation.escalate(db, t, now)
            if esc["priority_bumped"]:
                escalated += 1
            db.commit()  # persist the flag + escalation before custom rules dispatch
            ctx = automation.build_ticket_context(t)
            ctx["breach"] = True
            automation.dispatch(db, "ticket.sla_breached", ctx)
            sla_fired += 1

    # Run any due scheduled automation rules (v0.53) — time-based automations.
    scheduled = automation.run_scheduled(db, now)

    # Recurring billing (v0.58): auto-generate invoices for due contracts.
    from ...services import recurring_billing
    recurring = []
    try:
        recurring = recurring_billing.generate_due(db, now)
    except Exception:
        pass

    # A/R payment reminders (v0.62): nudge overdue unpaid invoices (7-day cadence).
    from ...services import ar_aging
    reminders = []
    try:
        reminders = ar_aging.send_due_reminders(db, now)
    except Exception:
        pass

    # Posture snapshots (v0.67): capture each client's security grade ~daily and
    # alert staff if a grade slipped since the last snapshot.
    from ...services import posture_history
    snapshots = []
    try:
        snapshots = posture_history.snapshot_all(db, now)
    except Exception:
        pass

    # Deliver any due scheduled client reports (v0.20).
    reports = scheduled_reports.send_due(db, now)

    # Connector health watchdog (v0.52.2) — auto-sweep at most hourly so a dead
    # token / exhausted credit raises an alert without anyone clicking "Test".
    from ...services import integration_health
    health = None
    try:
        health = integration_health.maybe_sweep(db, min_interval_minutes=60)
    except Exception:
        pass

    audit.record(db, action="automation.run_checks", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="automation", ip=None,
                 detail=f"offline_opened={sweep['offline_opened']} sla_breaches_fired={sla_fired} "
                        f"escalated={escalated} reports_sent={reports['reports_sent']}")
    return {"offline": sweep, "sla_breaches_fired": sla_fired, "escalated": escalated,
            "reports": reports, "health_checked": (health or {}).get("checked", 0),
            "scheduled_fired": len(scheduled), "recurring_invoices": len(recurring),
            "reminders_sent": len(reminders), "posture_snapshots": len(snapshots)}


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
@notif_router.get("")
def list_notifications(unread_only: bool = False, limit: int = 50,
                       db: Session = Depends(get_db), user: User = Depends(current_user)):
    limit = max(1, min(limit, 200))
    q = db.query(Notification)
    if is_staff(user):
        # Staff see broadcast (no target) + notifications addressed to them.
        q = q.filter(or_(Notification.target_user_id.is_(None),
                         Notification.target_user_id == user.id))
    else:
        # Client users: only their client's notifications addressed to them.
        q = q.filter(Notification.client_id == user.client_id,
                     Notification.target_user_id == user.id)
    if unread_only:
        q = q.filter(Notification.read.is_(False))
    rows = q.order_by(Notification.created_at.desc()).limit(limit).all()
    return [
        {"id": n.id, "kind": n.kind, "severity": n.severity, "message": n.message,
         "read": n.read, "client_id": n.client_id, "created_at": n.created_at.isoformat()}
        for n in rows
    ]


def _scope_notification(db: Session, user: User, notif_id: int) -> Notification:
    n = db.get(Notification, notif_id)
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    if is_staff(user):
        ok = n.target_user_id in (None, user.id)
    else:
        ok = n.client_id == user.client_id and n.target_user_id == user.id
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return n


@notif_router.post("/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = _scope_notification(db, user, notif_id)
    n.read = True
    db.commit()
    return {"ok": True}


@notif_router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Notification).filter(Notification.read.is_(False))
    if is_staff(user):
        q = q.filter(or_(Notification.target_user_id.is_(None),
                         Notification.target_user_id == user.id))
    else:
        q = q.filter(Notification.client_id == user.client_id,
                     Notification.target_user_id == user.id)
    n = q.update({"read": True}, synchronize_session=False)
    db.commit()
    return {"ok": True, "marked": n}
