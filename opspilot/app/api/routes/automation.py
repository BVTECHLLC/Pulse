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
    """Run the master maintenance tick on demand. The same tick runs
    automatically every couple of minutes via the in-process Autopilot
    scheduler (see /autopilot below) — this endpoint remains for staff
    "run now" and for any external cron that still points here."""
    from ...services import heartbeat
    result = heartbeat.run_all(db)
    audit.record(db, action="automation.run_checks", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="automation", ip=None,
                 detail=f"offline_opened={result['offline']['offline_opened']} "
                        f"sla_breaches_fired={result['sla_breaches_fired']} "
                        f"escalated={result['escalated']} "
                        f"reports_sent={result['reports']['reports_sent']}")
    return result


# --------------------------------------------------------------------------- #
# Autopilot (v1.1) — the built-in scheduler. Status panel + manual tick.
# --------------------------------------------------------------------------- #
@router.get("/autopilot")
def autopilot_status(db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...services import scheduler
    return scheduler.status(db)


@router.post("/autopilot/tick")
def autopilot_tick(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...services import scheduler
    result = scheduler.tick(db, source="manual")
    audit.record(db, action="automation.autopilot_tick", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="automation", ip=_ip(request), detail="manual tick")
    return {"ok": True, "result": result}


# --------------------------------------------------------------------------- #
# AI ticket triage settings (v1.1)
# --------------------------------------------------------------------------- #
class AITriageIn(BaseModel):
    enabled: bool | None = None
    auto_apply: bool | None = None


class ProactiveIn(BaseModel):
    auto_ticket_enabled: bool | None = None
    min_severity: str | None = None


@router.get("/proactive")
def get_proactive(db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...services import proactive
    return proactive.get_config(db)


@router.put("/proactive")
def save_proactive(body: ProactiveIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    from ...services import proactive
    out = proactive.save_config(db, auto_ticket_enabled=body.auto_ticket_enabled,
                                min_severity=body.min_severity)
    audit.record(db, action="automation.proactive_config", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="automation", ip=_ip(request),
                 detail=f"auto_ticket={out['auto_ticket_enabled']} sev={out['min_severity']}")
    return out


@router.get("/ai-triage")
def get_ai_triage(db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...services import ai_triage
    return ai_triage.get_config(db)


@router.put("/ai-triage")
def save_ai_triage(body: AITriageIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    from ...services import ai_triage
    out = ai_triage.save_config(db, enabled=body.enabled, auto_apply=body.auto_apply)
    audit.record(db, action="automation.ai_triage_config", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="automation", ip=_ip(request),
                 detail=f"enabled={out['enabled']} auto_apply={out['auto_apply']}")
    return out


# --------------------------------------------------------------------------- #
# Weekly "State of the Practice" digest (v0.85)
# --------------------------------------------------------------------------- #
@router.get("/weekly-digest")
def get_weekly_digest(db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...services import weekly_digest
    cfg = weekly_digest.get_config(db)
    if not cfg.get("recipients"):
        cfg["effective_recipients"] = weekly_digest._owner_emails(db)
    else:
        cfg["effective_recipients"] = cfg["recipients"]
    return cfg


class WeeklyDigestIn(BaseModel):
    enabled: bool | None = None
    weekday: int | None = None
    hour: int | None = None
    recipients: list[str] | str | None = None


@router.put("/weekly-digest")
def save_weekly_digest(body: WeeklyDigestIn, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_roles(Role.OWNER))):
    from ...services import weekly_digest
    out = weekly_digest.save_config(db, {k: v for k, v in body.model_dump().items() if v is not None})
    audit.record(db, action="automation.weekly_digest.save", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value, target_type="weekly_digest",
                 ip=_ip(request), detail=f"enabled={out['enabled']} weekday={out['weekday']}")
    return out


@router.get("/weekly-digest/preview")
def preview_weekly_digest(db: Session = Depends(get_db),
                          user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...services import weekly_digest
    subject, body = weekly_digest.render(db)
    return {"subject": subject, "body": body}


@router.post("/weekly-digest/send-now")
def send_weekly_digest_now(request: Request, db: Session = Depends(get_db),
                           user: User = Depends(require_roles(Role.OWNER))):
    """Send this week's digest immediately to the configured recipients,
    regardless of weekday/hour. Does not consume the once-per-week guard."""
    from ...services import email as email_svc, weekly_digest
    cfg = weekly_digest.get_config(db)
    recipients = cfg.get("recipients") or weekly_digest._owner_emails(db)
    subject, body = weekly_digest.render(db)
    delivered = sum(1 for to in recipients if _safe_send(email_svc.send, to, subject, body))
    audit.record(db, action="automation.weekly_digest.send_now", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value, target_type="weekly_digest",
                 ip=_ip(request), detail=f"recipients={len(recipients)} delivered={delivered}")
    return {"recipients": len(recipients), "delivered": delivered}


def _safe_send(send, to, subject, body) -> bool:
    try:
        return bool(send(to, subject, body))
    except Exception:
        return False


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
