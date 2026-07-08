"""v1.8 Patch management — approve pending Windows Updates; the agent installs them.

Built ON TOP of the existing governed deployment pipeline (ScriptDeployment):
a patch-install is a deployment with language "winupdate" whose content is the
approved KB list (or "all"). It inherits everything that makes remote action
safe here:
  * APPROVED by staff (OWNER/TECH) only, device-scoped, audit-logged;
  * the agent pulls only its own approved jobs via /api/agent/jobs;
  * the agent reports a result via /api/agent/jobs/{id}/result.
This is NOT arbitrary remote code execution — the agent's winupdate handler only
ever calls the Windows Update API for the approved KBs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    Device, DevicePatch, DeploymentStatus, ScriptDeployment, User,
)
from . import secure_config

LANGUAGE = "winupdate"
POLICY_PROVIDER = "patch_policy"
_TRUTHY = {"1", "true", "yes", "on"}

# Windows MsrcSeverity + the severities our agent may report, ranked.
_SEV_RANK = {"critical": 4, "important": 3, "security": 3,
             "moderate": 2, "low": 1, "unspecified": 0, "": 0}
# What the policy's min_severity choices admit.
_MIN_CHOICES = {"critical": 4, "important": 3, "all": 0}


def _sev_rank(s: str | None) -> int:
    return _SEV_RANK.get((s or "").strip().lower(), 0)


def approve_patches(db: Session, device, user: User, *, kbs: list[str] | None,
                    reason: str | None = None, autonomous: bool = False) -> ScriptDeployment:
    """Create an APPROVED winupdate job for a device. `kbs=None` means 'all
    currently-pending updates'. The content is the pinned KB list so what the
    agent installs is exactly what was approved."""
    def _norm(k: str) -> str:
        # Compare KBs regardless of a leading "KB" prefix ("5035100" == "KB5035100").
        k = (k or "").strip().upper()
        return k[2:] if k.startswith("KB") else k

    pending = (db.query(DevicePatch)
               .filter(DevicePatch.device_id == device.id).all())
    if kbs:
        want = {_norm(k) for k in kbs if k and k.strip()}
        targets = [p for p in pending if _norm(p.kb or "") in want]
        # Pin what the agent will match on — normalized "KB#####" form.
        selected = sorted({"KB" + _norm(p.kb or "") for p in targets if p.kb})
    else:
        selected = "all"
    content = json.dumps({"kbs": selected})
    dep = ScriptDeployment(
        script_id=None, script_name="Windows Update install",
        script_version=1, language=LANGUAGE, content=content,
        device_id=device.id, client_id=device.client_id,
        status=DeploymentStatus.APPROVED,
        reason=reason or "Patch install approved from Pulse",
        consent_ack=True,
        requested_by_user_id=user.id, requested_by_email=user.email,
        approved_by_user_id=user.id, approved_by_email=user.email,
        approved_at=datetime.now(timezone.utc),
    )
    db.add(dep)
    db.commit()
    # v1.17: every patch job is logged for outcome grading (job succeeded/failed),
    # so the trust ledger reflects real install results per client.
    from . import autonomy
    autonomy.record(db, action_type="patch_install",
                    playbook=f"winupdate:{'pinned' if kbs else 'all'}",
                    client_id=device.client_id, device_id=device.id,
                    ref_kind="deployment", ref_id=dep.id,
                    autonomous=autonomous, grade_after_minutes=30)
    db.commit()
    return dep


def _worst_severity(patches) -> str:
    best = ("unspecified", 0)
    for p in patches:
        r = _sev_rank(p.severity)
        if r > best[1]:
            best = ((p.severity or "unspecified").lower(), r)
    return best[0]


def fleet(db: Session) -> dict:
    """Fleet-wide patch status: every device with pending updates, worst-first,
    plus its latest patch-job status. Staff-only view."""
    from ..models import Client
    rows = (db.query(Device).filter((Device.patches_pending or 0) > 0)
            .filter(Device.patches_pending.isnot(None), Device.patches_pending > 0).all())
    names = {c.id: c.name for c in db.query(Client).all()}
    out = []
    total_pending = 0
    total_critical = 0
    for dev in rows:
        patches = db.query(DevicePatch).filter(DevicePatch.device_id == dev.id).all()
        crit = sum(1 for p in patches if _sev_rank(p.severity) >= _SEV_RANK["critical"])
        last = (db.query(ScriptDeployment)
                .filter(ScriptDeployment.device_id == dev.id,
                        ScriptDeployment.language == LANGUAGE)
                .order_by(ScriptDeployment.created_at.desc()).first())
        total_pending += dev.patches_pending or 0
        total_critical += crit
        out.append({
            "device_id": dev.id, "hostname": dev.hostname,
            "client_id": dev.client_id, "client": names.get(dev.client_id),
            "pending": dev.patches_pending or 0, "critical": crit,
            "worst_severity": _worst_severity(patches),
            "last_job": (last.status.value if last else None),
            "has_open_job": _has_open_job(db, dev.id),
        })
    out.sort(key=lambda r: (-(r["critical"]), -(r["pending"])))
    return {"devices": out, "totals": {
        "devices": len(out), "pending": total_pending, "critical": total_critical}}


def approve_fleet(db: Session, user: User, *, min_severity: str = "critical") -> list[dict]:
    """Approve install jobs across every device that has pending patches at/above
    `min_severity`. Manual bulk action (ignores the maintenance gate); deduped."""
    threshold = _MIN_CHOICES.get(min_severity, _MIN_CHOICES["critical"])
    made = []
    rows = (db.query(Device)
            .filter(Device.patches_pending.isnot(None), Device.patches_pending > 0).all())
    for dev in rows:
        if _has_open_job(db, dev.id):
            continue
        patches = db.query(DevicePatch).filter(DevicePatch.device_id == dev.id).all()
        matching = [p for p in patches if _sev_rank(p.severity) >= threshold]
        if not matching:
            continue
        kbs = sorted({p.kb for p in matching if p.kb}) or None
        dep = approve_patches(db, dev, user, kbs=kbs,
                              reason=f"Fleet approve ({min_severity}+)")
        made.append({"device_id": dev.id, "job_id": dep.id})
    return made


def list_jobs(db: Session, device_id: int, limit: int = 25) -> list[dict]:
    rows = (db.query(ScriptDeployment)
            .filter(ScriptDeployment.device_id == device_id,
                    ScriptDeployment.language == LANGUAGE)
            .order_by(ScriptDeployment.created_at.desc()).limit(limit).all())
    out = []
    for j in rows:
        try:
            kbs = json.loads(j.content or "{}").get("kbs")
        except Exception:  # noqa: BLE001
            kbs = None
        out.append({
            "id": j.id, "status": j.status.value,
            "kbs": kbs, "reason": j.reason,
            "approved_by": j.approved_by_email,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "exit_code": j.exit_code,
            "output": (j.output or "")[:2000],
        })
    return out


# --------------------------------------------------------------------------- #
# v1.9 — hands-off auto-approval policy (runs on the Autopilot heartbeat)
# --------------------------------------------------------------------------- #
def get_policy(db: Session) -> dict:
    conn = secure_config.get_platform(db, POLICY_PROVIDER)
    cfg = (conn.config if conn else None) or {}
    ms = cfg.get("min_severity") if cfg.get("min_severity") in _MIN_CHOICES else "critical"
    return {
        "auto_approve": str(cfg.get("auto_approve", "false")).lower() in _TRUTHY,
        "min_severity": ms,
        # Safe default: only auto-approve while the device/client is inside a
        # maintenance window (so installs + reboots happen when scheduled).
        "only_in_maintenance": str(cfg.get("only_in_maintenance", "true")).lower() in _TRUTHY,
    }


def save_policy(db: Session, *, auto_approve: bool | None = None,
                min_severity: str | None = None,
                only_in_maintenance: bool | None = None) -> dict:
    payload: dict[str, str] = {}
    if auto_approve is not None:
        payload["auto_approve"] = "true" if auto_approve else "false"
    if min_severity in _MIN_CHOICES:
        payload["min_severity"] = min_severity
    if only_in_maintenance is not None:
        payload["only_in_maintenance"] = "true" if only_in_maintenance else "false"
    if payload:
        secure_config.upsert_platform(db, POLICY_PROVIDER, "Patch Policy", "Automation", payload)
    return get_policy(db)


def _has_open_job(db: Session, device_id: int) -> bool:
    """A winupdate job already approved or running for this device — don't stack
    another auto-approval on top of it."""
    return db.query(ScriptDeployment.id).filter(
        ScriptDeployment.device_id == device_id,
        ScriptDeployment.language == LANGUAGE,
        ScriptDeployment.status.in_([DeploymentStatus.APPROVED, DeploymentStatus.RUNNING]),
    ).first() is not None


def auto_approve_sweep(db: Session, now=None, *, actor_email: str = "pulse-autopilot") -> list[dict]:
    """Heartbeat entrypoint. For each device with pending patches at/above the
    policy severity, auto-approve an install job (deduped; gated to maintenance
    windows unless disabled). Returns the jobs created. Safe no-op when off."""
    from . import monitoring
    pol = get_policy(db)
    if not pol["auto_approve"]:
        return []
    threshold = _MIN_CHOICES[pol["min_severity"]]
    created: list[dict] = []
    # Devices that currently have any pending patch.
    dev_ids = [r[0] for r in db.query(DevicePatch.device_id).distinct().all()]
    for did in dev_ids:
        dev = db.get(Device, did)
        if not dev:
            continue
        if _has_open_job(db, did):
            continue
        patches = db.query(DevicePatch).filter(DevicePatch.device_id == did).all()
        matching = [p for p in patches if _sev_rank(p.severity) >= threshold]
        if not matching:
            continue
        if pol["only_in_maintenance"] and not monitoring.in_maintenance(db, dev, now):
            continue
        # v1.17 earned-autonomy gate: a client whose auto-patching track record
        # collapsed is benched (operator notified) until the record recovers.
        from . import autonomy
        ok_auto, why = autonomy.allowed(db, "patch_install", dev.client_id)
        if not ok_auto:
            autonomy.notify_suspended(db, "patch_install", dev.client_id, why, now)
            continue
        kbs = sorted({p.kb for p in matching if p.kb}) or None
        # Build a synthetic user-ish actor for approval provenance.
        actor = type("A", (), {"id": None, "email": actor_email})()
        dep = approve_patches(db, dev, actor, kbs=kbs, autonomous=True,
                              reason=f"Auto-approved by patch policy ({pol['min_severity']}+)")
        created.append({"device_id": did, "job_id": dep.id, "kbs": kbs or "all"})
    return created
