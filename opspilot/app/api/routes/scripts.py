"""v0.7 script library + deployment governance.

Safety model (enforced here):
  * Scripts are INERT until an OWNER enables them.
  * Deploying to a device is a request that needs OWNER approval, and the
    approver must differ from the requester (separation of duties).
  * Consent + reason are recorded; the exact content+version is snapshotted onto
    the deployment so what's approved is exactly what runs.
  * The agent pulls only its own approved jobs (see agent.py) and reports back.
No arbitrary remote code execution — only approved, logged, content-pinned jobs.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import (
    Device, DeploymentStatus, Role, Script, ScriptDeployment,
    SCRIPT_LANGUAGES, SCRIPT_RISK_LEVELS, User,
)
from ...services import audit

router = APIRouter(prefix="/api", tags=["scripts"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Script library
# --------------------------------------------------------------------------- #
class ScriptIn(BaseModel):
    name: str
    language: str
    content: str
    description: str | None = None
    category: str | None = None
    risk_level: str = "medium"


def _serialize_script(s: Script, include_content: bool = False) -> dict:
    d = {
        "id": s.id, "name": s.name, "description": s.description, "language": s.language,
        "category": s.category, "risk_level": s.risk_level, "enabled": s.enabled,
        "requires_approval": s.requires_approval, "version": s.version,
        "author_email": s.author_email, "updated_at": s.updated_at.isoformat(),
    }
    if include_content:
        d["content"] = s.content
    return d


@router.get("/scripts")
def list_scripts(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return [_serialize_script(s) for s in db.query(Script).order_by(Script.name).all()]


@router.get("/scripts/{script_id}")
def get_script(script_id: int, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    s = db.get(Script, script_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    return _serialize_script(s, include_content=True)


@router.post("/scripts", status_code=201)
def create_script(body: ScriptIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if body.language not in SCRIPT_LANGUAGES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"language must be one of {list(SCRIPT_LANGUAGES)}")
    if body.risk_level not in SCRIPT_RISK_LEVELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"risk_level must be one of {list(SCRIPT_RISK_LEVELS)}")
    if not body.name.strip() or not body.content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "name and content required")
    s = Script(name=body.name[:200], description=body.description, language=body.language,
               content=body.content, category=body.category, risk_level=body.risk_level,
               created_by_user_id=user.id, author_email=user.email)  # enabled defaults False
    db.add(s)
    db.commit()
    audit.record(db, action="script.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="script", target_id=str(s.id),
                 ip=_ip(request), detail=f"lang={s.language} risk={s.risk_level}")
    return {"id": s.id}


class ScriptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None
    category: str | None = None
    risk_level: str | None = None


@router.patch("/scripts/{script_id}")
def update_script(script_id: int, body: ScriptUpdate, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    s = db.get(Script, script_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    changed_content = False
    if body.name is not None:
        s.name = body.name[:200]
    if body.description is not None:
        s.description = body.description
    if body.category is not None:
        s.category = body.category
    if body.risk_level is not None:
        if body.risk_level not in SCRIPT_RISK_LEVELS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid risk_level")
        s.risk_level = body.risk_level
    if body.content is not None and body.content != s.content:
        s.content = body.content
        s.version += 1            # editing content bumps the version
        changed_content = True
    db.commit()
    audit.record(db, action="script.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="script", target_id=str(s.id),
                 ip=_ip(request), detail=f"content_changed={changed_content} v{s.version}")
    return _serialize_script(s, include_content=True)


class EnableIn(BaseModel):
    enabled: bool


@router.post("/scripts/{script_id}/enable")
def set_enabled(script_id: int, body: EnableIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    """Enabling/disabling a script is the core safety gate, so it's OWNER-only."""
    s = db.get(Script, script_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    s.enabled = body.enabled
    db.commit()
    audit.record(db, action="script.enable" if body.enabled else "script.disable",
                 actor_user_id=user.id, actor_email=user.email, actor_role=user.role.value,
                 target_type="script", target_id=str(s.id), ip=_ip(request))
    return {"id": s.id, "enabled": s.enabled}


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
class DeployIn(BaseModel):
    device_id: int
    reason: str | None = None
    consent_ack: bool = False


def _serialize_deployment(d: ScriptDeployment, include_content: bool = False) -> dict:
    out = {
        "id": d.id, "script_id": d.script_id, "script_name": d.script_name,
        "script_version": d.script_version, "language": d.language, "device_id": d.device_id,
        "client_id": d.client_id, "status": d.status.value, "reason": d.reason,
        "consent_ack": d.consent_ack, "requested_by_email": d.requested_by_email,
        "approved_by_email": d.approved_by_email,
        "approved_at": d.approved_at.isoformat() if d.approved_at else None,
        "decision_note": d.decision_note, "exit_code": d.exit_code,
        "started_at": d.started_at.isoformat() if d.started_at else None,
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
        "created_at": d.created_at.isoformat(),
    }
    if include_content:
        out["content"] = d.content
        out["output"] = d.output
    return out


@router.post("/scripts/{script_id}/deploy", status_code=201)
def request_deploy(script_id: int, body: DeployIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    s = db.get(Script, script_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    if not s.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Script is disabled; an owner must enable it first")
    if not body.consent_ack:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "consent_ack is required to deploy")
    dev = db.get(Device, body.device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    assert_client_access(user, dev.client_id)

    # Snapshot the exact content+version so later edits can't change what runs.
    # If the script doesn't require approval it goes straight to APPROVED.
    initial = DeploymentStatus.PENDING_APPROVAL if s.requires_approval else DeploymentStatus.APPROVED
    d = ScriptDeployment(
        script_id=s.id, script_name=s.name, script_version=s.version, language=s.language,
        content=s.content, device_id=dev.id, client_id=dev.client_id, status=initial,
        reason=body.reason, consent_ack=True,
        requested_by_user_id=user.id, requested_by_email=user.email,
    )
    if initial == DeploymentStatus.APPROVED:
        d.approved_by_email = "auto (no approval required)"
        d.approved_at = datetime.now(timezone.utc)
    db.add(d)
    db.commit()
    audit.record(db, action="script.deploy_request", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="script_deployment", target_id=str(d.id),
                 client_id=dev.client_id, ip=_ip(request),
                 detail=f"script={s.name} v{s.version} device={dev.hostname} status={initial.value}")
    return {"id": d.id, "status": d.status.value}


@router.get("/deployments")
def list_deployments(status_filter: str | None = None, device_id: int | None = None,
                     db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    q = db.query(ScriptDeployment)
    if status_filter:
        q = q.filter(ScriptDeployment.status == status_filter)
    if device_id:
        q = q.filter(ScriptDeployment.device_id == device_id)
    rows = q.order_by(ScriptDeployment.created_at.desc()).limit(200).all()
    return [_serialize_deployment(d) for d in rows]


@router.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    d = db.get(ScriptDeployment, deployment_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")
    return _serialize_deployment(d, include_content=True)


class DecisionIn(BaseModel):
    note: str | None = None


@router.post("/deployments/{deployment_id}/approve")
def approve_deployment(deployment_id: int, body: DecisionIn, request: Request,
                       db: Session = Depends(get_db),
                       user: User = Depends(require_roles(Role.OWNER))):
    d = db.get(ScriptDeployment, deployment_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")
    if d.status != DeploymentStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot approve a {d.status.value} deployment")
    # Separation of duties: the approver must not be the requester.
    if d.requested_by_user_id == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Separation of duties: the requester cannot approve their own deployment")
    d.status = DeploymentStatus.APPROVED
    d.approved_by_user_id = user.id
    d.approved_by_email = user.email
    d.approved_at = datetime.now(timezone.utc)
    d.decision_note = body.note
    db.commit()
    audit.record(db, action="script.deploy_approve", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="script_deployment", target_id=str(d.id),
                 client_id=d.client_id, ip=_ip(request), detail=f"script={d.script_name} v{d.script_version}")
    return {"id": d.id, "status": d.status.value}


@router.post("/deployments/{deployment_id}/reject")
def reject_deployment(deployment_id: int, body: DecisionIn, request: Request,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER))):
    d = db.get(ScriptDeployment, deployment_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")
    if d.status != DeploymentStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot reject a {d.status.value} deployment")
    d.status = DeploymentStatus.REJECTED
    d.decision_note = body.note
    db.commit()
    audit.record(db, action="script.deploy_reject", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="script_deployment", target_id=str(d.id),
                 client_id=d.client_id, ip=_ip(request))
    return {"id": d.id, "status": d.status.value}


@router.post("/deployments/{deployment_id}/cancel")
def cancel_deployment(deployment_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Requester or any owner may cancel before the agent starts it."""
    d = db.get(ScriptDeployment, deployment_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")
    if d.status not in (DeploymentStatus.PENDING_APPROVAL, DeploymentStatus.APPROVED):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot cancel a {d.status.value} deployment")
    if user.role != Role.OWNER and d.requested_by_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the requester or an owner can cancel")
    d.status = DeploymentStatus.CANCELED
    db.commit()
    audit.record(db, action="script.deploy_cancel", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="script_deployment", target_id=str(d.id),
                 client_id=d.client_id, ip=_ip(request))
    return {"id": d.id, "status": d.status.value}
