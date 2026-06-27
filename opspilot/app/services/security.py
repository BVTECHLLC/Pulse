"""Security posture service: scorecard math and bridging findings into the
alert engine. Defensive only — this tracks and helps remediate weaknesses; it
never scans, exploits, or executes anything.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    Alert, AlertSeverity, AlertStatus, FindingSeverity, FindingStatus,
    SecurityFinding,
)

# How many points each open finding subtracts from a 100-point posture score.
SEVERITY_WEIGHTS = {
    FindingSeverity.CRITICAL: 25,
    FindingSeverity.HIGH: 15,
    FindingSeverity.MEDIUM: 7,
    FindingSeverity.LOW: 2,
}

# Findings at/above this severity raise an alert (so automation can react).
def _alert_severity_for(sev: FindingSeverity) -> AlertSeverity | None:
    if sev == FindingSeverity.CRITICAL:
        return AlertSeverity.CRITICAL
    if sev == FindingSeverity.HIGH:
        return AlertSeverity.WARNING
    return None  # medium/low don't page anyone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_score(findings: list[SecurityFinding]) -> int:
    """100 minus the weighted sum of still-open findings, floored at 0."""
    score = 100
    for f in findings:
        if f.status in (FindingStatus.OPEN, FindingStatus.REMEDIATING):
            score -= SEVERITY_WEIGHTS.get(f.severity, 0)
    return max(0, score)


def scorecard(db: Session, client_id: int) -> dict:
    """Posture summary for one client: score + open-finding counts by severity."""
    findings = db.query(SecurityFinding).filter(SecurityFinding.client_id == client_id).all()
    open_f = [f for f in findings if f.status in (FindingStatus.OPEN, FindingStatus.REMEDIATING)]
    by_sev = {s.value: 0 for s in FindingSeverity}
    for f in open_f:
        by_sev[f.severity.value] += 1
    return {
        "client_id": client_id,
        "score": compute_score(findings),
        "open_findings": len(open_f),
        "by_severity": by_sev,
        "total_findings": len(findings),
    }


def raise_finding_alert(db: Session, finding: SecurityFinding) -> Alert | None:
    """Open an alert for a high/critical finding and link it. Returns the Alert
    (not committed) so the caller can commit then dispatch automation."""
    sev = _alert_severity_for(finding.severity)
    if sev is None:
        return None
    now = _utcnow()
    msg = f"Security finding ({finding.severity.value}): {finding.title}"
    if finding.cve:
        msg += f" [{finding.cve}]"
    a = Alert(
        client_id=finding.client_id, device_id=finding.device_id,
        kind=f"security_finding:{finding.id}", severity=sev,
        status=AlertStatus.ACTIVE, message=msg, first_seen=now, last_seen=now,
    )
    db.add(a)
    db.flush()  # get the alert id to link back
    finding.alert_id = a.id
    return a


def resolve_finding_alert(db: Session, finding: SecurityFinding) -> None:
    """Resolve the alert linked to a finding once the finding is closed out."""
    if not finding.alert_id:
        return
    a = db.get(Alert, finding.alert_id)
    if a and a.status != AlertStatus.RESOLVED:
        a.status = AlertStatus.RESOLVED
        a.resolved_at = _utcnow()
        a.auto_resolved = True
