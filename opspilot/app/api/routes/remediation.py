"""v0.65 Auto-remediation rules — map an alert kind to a fix script.

Staff define rules ("when device_offline on this client, run Restart-Agent");
the engine (services/auto_remediation) queues an approved deployment whenever a
matching alert opens. All mutations are staff-gated and audited — this drives
real remote execution.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import (
    Client, REMEDIABLE_ALERT_KINDS, RemediationRule, Role, Script,
    ScriptDeployment, User,
)
from ...services import audit, auto_remediation

router = APIRouter(prefix="/api/remediation", tags=["remediation"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(r: RemediationRule, script_name: str | None = None) -> dict:
    return {"id": r.id, "name": r.name, "alert_kind": r.alert_kind, "script_id": r.script_id,
            "script_name": script_name, "client_id": r.client_id, "enabled": r.enabled,
            "cooldown_minutes": r.cooldown_minutes, "max_per_day": r.max_per_day,
            "fire_count": r.fire_count,
            "last_fired_at": r.last_fired_at.isoformat() if r.last_fired_at else None}


@router.get("/alert-kinds")
def alert_kinds(user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return {"alert_kinds": list(REMEDIABLE_ALERT_KINDS)}


@router.get("/rules")
def list_rules(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = db.query(RemediationRule).order_by(RemediationRule.id.desc()).all()
    names = {s.id: s.name for s in db.query(Script).all()}
    return [_serialize(r, names.get(r.script_id)) for r in rows]


class RuleIn(BaseModel):
    name: str
    alert_kind: str
    script_id: int
    client_id: int | None = None
    enabled: bool = True
    cooldown_minutes: int = 60
    max_per_day: int = 3


def _validate(db: Session, alert_kind: str, script_id: int, client_id: int | None) -> Script:
    if alert_kind not in REMEDIABLE_ALERT_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"alert_kind must be one of {list(REMEDIABLE_ALERT_KINDS)}")
    script = db.get(Script, script_id)
    if not script:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    if client_id is not None and not db.get(Client, client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return script


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    script = _validate(db, body.alert_kind, body.script_id, body.client_id)
    r = RemediationRule(name=body.name[:200], alert_kind=body.alert_kind, script_id=body.script_id,
                        client_id=body.client_id, enabled=body.enabled,
                        cooldown_minutes=max(0, body.cooldown_minutes),
                        max_per_day=max(1, body.max_per_day), created_by_user_id=user.id)
    db.add(r)
    db.commit()
    audit.record(db, action="remediation.rule_create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="remediation_rule", target_id=str(r.id),
                 client_id=body.client_id, ip=_ip(request),
                 detail=f"{body.alert_kind}→{script.name}")
    return _serialize(r, script.name)


class RuleUpdate(BaseModel):
    name: str | None = None
    script_id: int | None = None
    enabled: bool | None = None
    cooldown_minutes: int | None = None
    max_per_day: int | None = None


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    r = db.get(RemediationRule, rule_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    if body.script_id is not None:
        if not db.get(Script, body.script_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
        r.script_id = body.script_id
    if body.name is not None:
        r.name = body.name[:200]
    if body.enabled is not None:
        r.enabled = body.enabled
    if body.cooldown_minutes is not None:
        r.cooldown_minutes = max(0, body.cooldown_minutes)
    if body.max_per_day is not None:
        r.max_per_day = max(1, body.max_per_day)
    db.commit()
    name = (db.get(Script, r.script_id) or Script()).name if r.script_id else None
    return _serialize(r, name)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    r = db.get(RemediationRule, rule_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    db.delete(r)
    db.commit()
    audit.record(db, action="remediation.rule_delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="remediation_rule", target_id=str(rule_id),
                 ip=_ip(request))
    return {"ok": True}


@router.get("/recent")
def recent_runs(limit: int = 25, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Recent auto-remediation deployments (what the engine actually fired)."""
    limit = max(1, min(limit, 200))
    rows = (db.query(ScriptDeployment)
            .filter(ScriptDeployment.requested_by_email == auto_remediation.AUTO_EMAIL)
            .order_by(ScriptDeployment.created_at.desc()).limit(limit).all())
    return [{"deployment_id": d.id, "script": d.script_name, "device_id": d.device_id,
             "client_id": d.client_id, "status": d.status.value, "reason": d.reason,
             "exit_code": d.exit_code, "created_at": d.created_at.isoformat()} for d in rows]
