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
    DevicePatch, DeploymentStatus, ScriptDeployment, User,
)

LANGUAGE = "winupdate"


def approve_patches(db: Session, device, user: User, *, kbs: list[str] | None,
                    reason: str | None = None) -> ScriptDeployment:
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
    return dep


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
