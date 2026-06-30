"""v0.65 Auto-remediation — detect → fix, automatically.

When a monitoring alert opens on a device, matching `RemediationRule`s queue an
**already-approved** `ScriptDeployment` of a chosen script on that exact device.
The native agent pulls approved deployments on its next check-in and runs them,
reporting the exit code + output back — so the loop closes with no human in the
middle.

Safety rails (this is real remote execution):
  * The target script must be **enabled** — a disabled script never auto-runs.
  * **Cooldown** per device+script, so a flapping alert can't re-fire instantly.
  * **Daily cap** per device+script, so a stuck condition can't hammer the box.
  * Each auto deployment is tagged (reason prefix + `requested_by_email`) so it's
    auditable and counted against the caps.
  * Scoped: a rule can target one client or all; it only ever runs the script on
    the device the alert is about.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (
    Device, DeploymentStatus, RemediationRule, Script, ScriptDeployment,
)

AUTO_EMAIL = "auto-remediation"
_REASON_PREFIX = "auto-remediation"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def eligible_rules(db: Session, alert_kind: str, client_id: int) -> list[RemediationRule]:
    """Enabled rules for this alert kind that apply to the device's client
    (client-specific rules first, then global)."""
    rows = (db.query(RemediationRule)
            .filter(RemediationRule.enabled.is_(True),
                    RemediationRule.alert_kind == alert_kind)
            .all())
    return [r for r in rows if r.client_id in (None, client_id)]


# Cooldown/cap math keys off `approved_at` (which the engine stamps with the
# incident time) rather than the DB-set `created_at`, so the window reflects when
# the remediation actually fired.
def _auto_count_since(db: Session, device_id: int, script_id: int,
                      since: datetime) -> int:
    return (db.query(ScriptDeployment)
            .filter(ScriptDeployment.device_id == device_id,
                    ScriptDeployment.script_id == script_id,
                    ScriptDeployment.requested_by_email == AUTO_EMAIL,
                    ScriptDeployment.approved_at >= since)
            .count())


def _last_auto(db: Session, device_id: int, script_id: int) -> datetime | None:
    row = (db.query(ScriptDeployment)
           .filter(ScriptDeployment.device_id == device_id,
                   ScriptDeployment.script_id == script_id,
                   ScriptDeployment.requested_by_email == AUTO_EMAIL)
           .order_by(ScriptDeployment.approved_at.desc()).first())
    if not row or not row.approved_at:
        return None
    dt = row.approved_at
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def on_alert(db: Session, alert, device: Device, now: datetime | None = None) -> list[dict]:
    """Evaluate auto-remediation for a freshly-opened alert. Creates APPROVED
    deployments for any rule that passes its safety checks. Commits. Returns a
    summary list of what was queued (empty if nothing fired)."""
    if alert is None or device is None:
        return []
    now = now or _utcnow()
    created = []
    for rule in eligible_rules(db, alert.kind, device.client_id):
        script = db.get(Script, rule.script_id)
        # Safety: only ENABLED scripts auto-run.
        if not script or not script.enabled:
            continue
        # Cooldown since the last auto-run of this script on this device.
        last = _last_auto(db, device.id, script.id)
        if last and (now - last) < timedelta(minutes=max(0, rule.cooldown_minutes or 0)):
            continue
        # Daily cap (rolling 24h) per device+script.
        if rule.max_per_day and _auto_count_since(db, device.id, script.id,
                                                  now - timedelta(days=1)) >= rule.max_per_day:
            continue
        dep = ScriptDeployment(
            script_id=script.id, script_name=script.name, script_version=script.version,
            language=script.language, content=script.content,
            device_id=device.id, client_id=device.client_id,
            status=DeploymentStatus.APPROVED,
            reason=f"{_REASON_PREFIX}: {rule.name} (alert {alert.kind})",
            consent_ack=True, requested_by_email=AUTO_EMAIL,
            approved_by_email=AUTO_EMAIL, approved_at=now)
        db.add(dep)
        rule.last_fired_at = now
        rule.fire_count = (rule.fire_count or 0) + 1
        db.flush()
        created.append({"deployment_id": dep.id, "rule_id": rule.id, "rule": rule.name,
                        "script": script.name, "device_id": device.id,
                        "alert_kind": alert.kind})
    if created:
        db.commit()
    return created


def on_new_alerts(db: Session, alerts: list, device: Device,
                  now: datetime | None = None) -> list[dict]:
    """Convenience: run on_alert for several freshly-opened alerts on one device."""
    out = []
    for a in alerts or []:
        out.extend(on_alert(db, a, device, now))
    return out
