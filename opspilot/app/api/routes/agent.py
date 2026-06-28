"""Endpoint agent API — Phase 1: enrollment + telemetry check-in ONLY.

SECURITY POSTURE (Phase 1):
  - No remote command execution endpoint exists. At all. By design.
  - Enrollment requires a signed, time-limited, client-scoped token minted by staff.
  - On first enroll the agent receives a long-lived per-device agent_key; we store
    only its hash. Subsequent check-ins authenticate with that key.
  - Telemetry is health data only (see CheckinIn). No file contents, no keystrokes,
    no screen capture. Consent language ships in the installer.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, require_roles
from ...core.security import (
    hash_password, mint_enrollment_token, random_token, verify_enrollment_token,
    verify_password,
)
from ...models import (
    Client, Device, DeviceCheckin, DeploymentStatus, DiagnosticRequest, Role,
    ScriptDeployment, User,
)
from ...services import audit, automation, monitoring

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --- Staff: mint an enrollment token for a client ---------------------------
@router.post("/enroll-token/{client_id}")
def make_enroll_token(client_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    token = mint_enrollment_token(client_id=client_id)
    audit.record(db, action="agent.enroll_token_minted", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="client", target_id=str(client_id),
                 client_id=client_id, ip=_ip(request))
    return {"enroll_token": token, "expires_hours": 72}


# --- Agent: enroll using the token ------------------------------------------
class EnrollIn(BaseModel):
    enroll_token: str
    hostname: str
    os: str | None = None
    serial: str | None = None


@router.post("/enroll")
def enroll(body: EnrollIn, request: Request, db: Session = Depends(get_db)):
    try:
        payload = verify_enrollment_token(body.enroll_token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid enrollment token")
    client_id = int(payload["client_id"])

    enroll_id = random_token(16)
    agent_key = random_token(32)
    dev = Device(
        client_id=client_id, hostname=body.hostname, os=body.os, serial=body.serial,
        enroll_id=enroll_id, agent_key_hash=hash_password(agent_key),
        last_checkin=datetime.now(timezone.utc),
    )
    db.add(dev)
    db.commit()
    audit.record(db, action="agent.enrolled", target_type="device", target_id=str(dev.id),
                 client_id=client_id, ip=_ip(request), detail=f"host={body.hostname}")
    # agent_key is returned exactly once; agent stores it locally.
    return {"enroll_id": enroll_id, "agent_key": agent_key, "device_id": dev.id}


# --- Agent: telemetry check-in ----------------------------------------------
class CheckinIn(BaseModel):
    cpu_pct: float | None = None
    ram_pct: float | None = None
    disk_pct: float | None = None
    logged_in_user: str | None = None
    av_status: str | None = None
    patch_status: str | None = None
    ip: str | None = None


def _health_score(c: CheckinIn) -> int:
    score = 100
    if c.disk_pct and c.disk_pct > 90:
        score -= 25
    if c.cpu_pct and c.cpu_pct > 90:
        score -= 15
    if c.ram_pct and c.ram_pct > 90:
        score -= 15
    if c.av_status and "off" in c.av_status.lower():
        score -= 30
    if c.patch_status and "behind" in c.patch_status.lower():
        score -= 20
    return max(0, score)


@router.post("/checkin")
def checkin(body: CheckinIn, request: Request,
            x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
            db: Session = Depends(get_db)):
    dev = db.query(Device).filter(Device.enroll_id == x_enroll_id).first()
    if not dev or not dev.agent_key_hash or not verify_password(x_agent_key, dev.agent_key_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Agent not authorized")

    dev.cpu_pct = body.cpu_pct
    dev.ram_pct = body.ram_pct
    dev.disk_pct = body.disk_pct
    dev.logged_in_user = body.logged_in_user
    dev.av_status = body.av_status
    dev.patch_status = body.patch_status
    dev.ip = body.ip or _ip(request)
    dev.health_score = _health_score(body)
    dev.last_checkin = datetime.now(timezone.utc)

    # Append to history (keeps a trend record; latest summary stays on Device).
    db.add(DeviceCheckin(
        device_id=dev.id, cpu_pct=body.cpu_pct, ram_pct=body.ram_pct,
        disk_pct=body.disk_pct, health_score=dev.health_score,
        av_status=body.av_status, patch_status=body.patch_status,
    ))
    # Run the monitoring engine against this fresh telemetry (opens/auto-resolves
    # alerts). Staged in this same transaction; committed below.
    new_alerts = monitoring.evaluate_device(db, dev)
    db.commit()
    # Fire automation for each newly-opened alert (after commit so ids exist).
    for alert in new_alerts:
        automation.dispatch(db, "alert.opened", automation.build_alert_context(alert, dev))
    return {"ok": True, "interval_sec": 300}


# --------------------------------------------------------------------------- #
# Approved-job queue (v0.7). The agent PULLS only its own approved jobs and
# reports results. The server never pushes ad-hoc commands; every job here was
# individually approved (see routes/scripts.py) and its content is pinned.
# --------------------------------------------------------------------------- #
def _auth_device(db: Session, enroll_id: str, agent_key: str) -> Device:
    dev = db.query(Device).filter(Device.enroll_id == enroll_id).first()
    if not dev or not dev.agent_key_hash or not verify_password(agent_key, dev.agent_key_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Agent not authorized")
    return dev


@router.get("/jobs")
def pull_jobs(x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
              db: Session = Depends(get_db)):
    """Return this device's APPROVED deployments and move them to RUNNING. The
    agent only ever sees jobs explicitly approved for its own enrolled device."""
    dev = _auth_device(db, x_enroll_id, x_agent_key)
    jobs = (db.query(ScriptDeployment)
            .filter(ScriptDeployment.device_id == dev.id,
                    ScriptDeployment.status == DeploymentStatus.APPROVED)
            .order_by(ScriptDeployment.created_at).all())
    out = []
    for j in jobs:
        j.status = DeploymentStatus.RUNNING
        j.started_at = datetime.now(timezone.utc)
        out.append({"id": j.id, "language": j.language, "content": j.content})
    if jobs:
        db.commit()
    return {"jobs": out}


class JobResultIn(BaseModel):
    exit_code: int
    output: str | None = None


@router.post("/jobs/{job_id}/result")
def report_job_result(job_id: int, body: JobResultIn, request: Request,
                      x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
                      db: Session = Depends(get_db)):
    dev = _auth_device(db, x_enroll_id, x_agent_key)
    j = db.get(ScriptDeployment, job_id)
    if not j or j.device_id != dev.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if j.status != DeploymentStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Job is {j.status.value}, not running")
    j.exit_code = body.exit_code
    j.output = (body.output or "")[:20000]  # cap stored output
    j.status = DeploymentStatus.SUCCEEDED if body.exit_code == 0 else DeploymentStatus.FAILED
    j.completed_at = datetime.now(timezone.utc)
    db.commit()
    audit.record(db, action="script.deploy_result", target_type="script_deployment",
                 target_id=str(j.id), client_id=j.client_id, ip=_ip(request),
                 detail=f"exit={body.exit_code} status={j.status.value}", success=(body.exit_code == 0))
    return {"ok": True, "status": j.status.value}


# --------------------------------------------------------------------------- #
# Diagnostics queue (v0.12). Read-only network probes the on-site agent runs and
# reports — pull only this device's pending diagnostics, post results back.
# --------------------------------------------------------------------------- #
@router.get("/diagnostics")
def pull_diagnostics(x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
                     db: Session = Depends(get_db)):
    dev = _auth_device(db, x_enroll_id, x_agent_key)
    rows = (db.query(DiagnosticRequest)
            .filter(DiagnosticRequest.device_id == dev.id, DiagnosticRequest.status == "pending")
            .order_by(DiagnosticRequest.created_at).all())
    out = []
    for d in rows:
        d.status = "running"
        d.started_at = datetime.now(timezone.utc)
        out.append({"id": d.id, "kind": d.kind, "target": d.target, "params": d.params or {}})
    if rows:
        db.commit()
    return {"diagnostics": out}


class DiagResultIn(BaseModel):
    ok: bool = True
    result: str | None = None


@router.post("/diagnostics/{diag_id}/result")
def report_diagnostic(diag_id: int, body: DiagResultIn, request: Request,
                      x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
                      db: Session = Depends(get_db)):
    dev = _auth_device(db, x_enroll_id, x_agent_key)
    d = db.get(DiagnosticRequest, diag_id)
    if not d or d.device_id != dev.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diagnostic not found")
    d.result = (body.result or "")[:50000]
    d.status = "done" if body.ok else "failed"
    d.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "status": d.status}
