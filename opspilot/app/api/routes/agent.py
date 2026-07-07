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
    Client, Device, DeviceCheckin, DevicePatch, DeviceSoftware, DeploymentStatus,
    DiagnosticRequest, Role, ScriptDeployment, User,
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
    # baseline_device_id lets the onboarding UI detect the NEW device that
    # enrolls with this token (any device id greater than the baseline).
    last = (db.query(Device).filter(Device.client_id == client_id)
            .order_by(Device.id.desc()).first())
    return {"enroll_token": token, "expires_hours": 72,
            "baseline_device_id": last.id if last else 0}


# --- Staff: poll for a freshly-onboarded device (live onboarding feedback) ---
@router.get("/onboarding/{client_id}")
def onboarding_status(client_id: int, after: int = 0, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Return the newest device for this client with id > `after` (the baseline
    captured when the installer was generated), so the UI can light up the
    moment the endpoint enrolls and checks in — SuperOps-style live onboarding."""
    from datetime import timedelta
    q = db.query(Device).filter(Device.client_id == client_id, Device.id > after)
    onboarded = q.count()   # bulk: a token onboards many devices in its 72h window
    dev = q.order_by(Device.id.desc()).first()
    if not dev:
        return {"enrolled": False, "onboarded": 0}
    lc = dev.last_checkin
    if lc is not None and lc.tzinfo is None:
        lc = lc.replace(tzinfo=timezone.utc)
    online = bool(lc and lc >= datetime.now(timezone.utc) - timedelta(seconds=180))
    # "checked_in" means real telemetry arrived (health_score is only set by a
    # check-in) — enroll alone stamps last_checkin, so don't use that as proof.
    reported = dev.health_score is not None
    return {"enrolled": True, "onboarded": onboarded, "device": {
        "id": dev.id, "hostname": dev.hostname, "os": dev.os,
        "checked_in": reported, "online": bool(reported and online),
        "cpu_pct": dev.cpu_pct, "ram_pct": dev.ram_pct, "disk_pct": dev.disk_pct,
        "av_status": dev.av_status, "patch_status": dev.patch_status,
        "health_score": dev.health_score,
        "last_checkin": dev.last_checkin.isoformat() if dev.last_checkin else None,
    }}


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
    agent_version: str | None = None
    platform: str | None = None


# Live-feel default check-in cadence (seconds). The agent honors interval_sec.
CHECKIN_INTERVAL_SEC = 60


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
    if body.agent_version:
        dev.agent_version = body.agent_version[:40]
    if body.platform:
        dev.platform = body.platform[:40]
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
    # Proactive Ops (v1.7): auto-open a ticket for critical alerts (opt-in, deduped).
    if new_alerts:
        from ...services import proactive
        try:
            if proactive.on_new_alerts(db, new_alerts):
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    # Auto-remediation (v0.65): queue approved fix-scripts for matching alerts.
    if new_alerts:
        from ...services import auto_remediation
        try:
            auto_remediation.on_new_alerts(db, new_alerts, dev)
        except Exception:  # never let remediation break a check-in
            pass
    return {"ok": True, "interval_sec": CHECKIN_INTERVAL_SEC}


# --- Agent: end-user submits a support ticket from this device --------------
class AgentTicketIn(BaseModel):
    subject: str
    body: str | None = None
    priority: str | None = "normal"


@router.post("/ticket", status_code=201)
def agent_ticket(body: AgentTicketIn, request: Request,
                 x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
                 db: Session = Depends(get_db)):
    """The person at the endpoint can raise a ticket straight from the agent. The
    ticket is filed against the device's client and shows the originating host."""
    from ...models import SupportTicket, TicketStatus  # local import avoids cycle
    from ...services import events, sla
    dev = _auth_device(db, x_enroll_id, x_agent_key)
    subject = (body.subject or "").strip()[:200]
    if not subject:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "subject is required")
    pri = (body.priority or "normal").lower()
    if pri not in ("low", "normal", "high", "urgent"):
        pri = "normal"
    text = (body.body or "").strip()
    text = f"[from device: {dev.hostname}] {text}".strip()
    t = SupportTicket(client_id=dev.client_id, subject=subject, body=text,
                      priority=pri, status=TicketStatus.OPEN)
    db.add(t)
    db.flush()
    try:
        sla.stamp_due_dates(db, t)   # apply SLA targets like any other ticket
    except Exception:
        pass
    db.commit()
    events.emit(db, "ticket.created", {"id": t.id, "client_id": dev.client_id,
                "subject": subject, "priority": pri, "source": "agent"},
                client_id=dev.client_id)
    audit.record(db, action="agent.ticket", target_type="ticket", target_id=str(t.id),
                 client_id=dev.client_id, ip=_ip(request), detail=f"host={dev.hostname}")
    return {"ok": True, "ticket_id": t.id}


# --------------------------------------------------------------------------- #
# Staff: push a command to a device (v0.46). Creates an APPROVED deployment the
# agent picks up on its next poll, runs, and reports output back. OWNER-only and
# audited — this is real remote command execution, so it is deliberately gated.
# --------------------------------------------------------------------------- #
class RunCommandIn(BaseModel):
    command: str
    language: str = "powershell"   # powershell|bash|cmd|python


@router.post("/devices/{device_id}/run-command", status_code=201)
def run_command(device_id: int, body: RunCommandIn, request: Request,
                db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    cmd = (body.command or "").strip()
    if not cmd:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "command is required")
    if body.language not in ("powershell", "bash", "cmd", "python"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported language")
    dep = ScriptDeployment(
        script_id=None, script_name="ad-hoc command", script_version=0,
        language=body.language, content=cmd, device_id=dev.id, client_id=dev.client_id,
        status=DeploymentStatus.APPROVED, reason="ad-hoc console command",
        consent_ack=True, requested_by_user_id=user.id, requested_by_email=user.email,
        approved_by_user_id=user.id, approved_by_email=user.email,
        approved_at=datetime.now(timezone.utc),
    )
    db.add(dep)
    db.commit()
    audit.record(db, action="agent.run_command", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="device", target_id=str(dev.id),
                 client_id=dev.client_id, ip=_ip(request), detail=f"{body.language}: {cmd[:120]}")
    return {"ok": True, "deployment_id": dep.id, "status": dep.status.value}


@router.get("/devices/{device_id}/commands")
def device_commands(device_id: int, limit: int = 20, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Recent command deployments for a device (so the console can show output)."""
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    rows = (db.query(ScriptDeployment)
            .filter(ScriptDeployment.device_id == device_id)
            .order_by(ScriptDeployment.created_at.desc()).limit(min(limit, 100)).all())
    return {"commands": [{
        "id": d.id, "language": d.language, "content": d.content, "status": d.status.value,
        "exit_code": d.exit_code, "output": d.output,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
    } for d in rows]}


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


@router.get("/remote-sessions")
def pull_remote_sessions(x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
                         db: Session = Depends(get_db)):
    """Pending remote-desktop sessions targeting this device. The agent connects
    to the signaling relay (/api/remote/ws/{token}?role=agent) for each one."""
    from ...models import RemoteSession  # local import avoids cycle
    dev = _auth_device(db, x_enroll_id, x_agent_key)
    rows = (db.query(RemoteSession)
            .filter(RemoteSession.device_id == dev.id, RemoteSession.status == "pending")
            .order_by(RemoteSession.created_at).all())
    return {"sessions": [{"token": r.token, "id": r.id} for r in rows]}


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


# --------------------------------------------------------------------------- #
# Software inventory (v0.19). The agent reports installed apps; we replace the
# device's full set each time so the inventory always reflects current state.
# --------------------------------------------------------------------------- #
class SoftwareItem(BaseModel):
    name: str
    version: str | None = None
    publisher: str | None = None


class InventoryIn(BaseModel):
    software: list[SoftwareItem]


@router.post("/inventory")
def report_inventory(body: InventoryIn, request: Request,
                     x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
                     db: Session = Depends(get_db)):
    dev = _auth_device(db, x_enroll_id, x_agent_key)
    # Replace the whole set (dedup by name+version; cap to a sane fleet size).
    db.query(DeviceSoftware).filter(DeviceSoftware.device_id == dev.id).delete()
    seen: set[tuple[str, str | None]] = set()
    now = datetime.now(timezone.utc)
    count = 0
    for item in body.software:
        name = (item.name or "").strip()[:300]
        if not name:
            continue
        version = (item.version or None)
        key = (name.lower(), (version or "").lower())
        if key in seen:
            continue
        seen.add(key)
        db.add(DeviceSoftware(
            device_id=dev.id, client_id=dev.client_id, name=name,
            version=(version[:120] if version else None),
            publisher=((item.publisher or None) and item.publisher.strip()[:200]),
            reported_at=now,
        ))
        count += 1
        if count >= 5000:   # guardrail against a runaway report
            break
    db.commit()
    return {"ok": True, "stored": count}


# --------------------------------------------------------------------------- #
# Patch reporting (v0.20). The agent reports pending OS/software updates; we
# replace the device's pending set and keep a count on the device for fast views.
# --------------------------------------------------------------------------- #
class PatchItem(BaseModel):
    name: str
    kb: str | None = None
    severity: str | None = None


class PatchesIn(BaseModel):
    patches: list[PatchItem]


@router.post("/patches")
def report_patches(body: PatchesIn, request: Request,
                   x_enroll_id: str = Header(...), x_agent_key: str = Header(...),
                   db: Session = Depends(get_db)):
    dev = _auth_device(db, x_enroll_id, x_agent_key)
    db.query(DevicePatch).filter(DevicePatch.device_id == dev.id).delete()
    now = datetime.now(timezone.utc)
    count = 0
    for item in body.patches:
        name = (item.name or "").strip()[:400]
        if not name:
            continue
        db.add(DevicePatch(
            device_id=dev.id, client_id=dev.client_id, name=name,
            kb=(item.kb or None) and item.kb.strip()[:60],
            severity=(item.severity or None) and item.severity.strip()[:40],
            reported_at=now,
        ))
        count += 1
        if count >= 2000:
            break
    dev.patches_pending = count
    dev.patch_status = "current" if count == 0 else f"{count} pending"
    db.commit()
    return {"ok": True, "pending": count}


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
