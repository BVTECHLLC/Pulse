"""v0.33 Client Health Score — one explainable 0-100 per client.

Rolls every client's real-time posture (endpoint health, patch compliance,
online rate, open alerts, SLA performance, security findings, ticket backlog)
into a single weighted score with a letter grade and the specific factors that
moved it. Staff get an instant "who's healthy / who's at risk of churn" board;
a client sees only their own. Pure read model.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (
    Alert, AlertSeverity, AlertStatus, Client, Device, FindingSeverity,
    FindingStatus, SecurityFinding, SupportTicket, TicketStatus,
)
from . import sla

ONLINE_WINDOW = timedelta(minutes=30)

# Component weights (sum = 100). Each component yields a 0-1 quality fraction;
# the score is the weighted sum scaled to 100.
WEIGHTS = {
    "endpoint_health": 28,   # avg device health
    "patch": 20,             # patch compliance
    "uptime": 14,            # devices reporting in
    "alerts": 14,            # absence of active alerts
    "sla": 12,               # SLA adherence
    "security": 8,           # absence of open high/critical findings
    "backlog": 4,            # ticket backlog kept sane
}


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _grade(score: int) -> str:
    return ("A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70
            else "D" if score >= 60 else "F")


def _risk(score: int, factors: list[str]) -> str:
    if score < 60 or len(factors) >= 3:
        return "high"
    if score < 78 or factors:
        return "watch"
    return "healthy"


def score_client(db: Session, client: Client, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cid = client.id

    devices = db.query(Device).filter(Device.client_id == cid).all()
    healths = [d.health_score for d in devices if d.health_score is not None]
    reported = [d for d in devices if d.patches_pending is not None]
    online = sum(1 for d in devices
                 if d.last_checkin and (now - _aware(d.last_checkin)) <= ONLINE_WINDOW)

    alerts = (db.query(Alert)
              .filter(Alert.client_id == cid, Alert.status != AlertStatus.RESOLVED).all())
    crit_alerts = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)

    open_tickets = (db.query(SupportTicket)
                    .filter(SupportTicket.client_id == cid,
                            SupportTicket.status.in_([TicketStatus.OPEN,
                                                      TicketStatus.IN_PROGRESS])).all())
    sla_breached = sum(1 for t in open_tickets if sla.evaluate(t, now)["breached"])

    findings = (db.query(SecurityFinding)
                .filter(SecurityFinding.client_id == cid,
                        SecurityFinding.status.in_([FindingStatus.OPEN,
                                                    FindingStatus.REMEDIATING]),
                        SecurityFinding.severity.in_([FindingSeverity.HIGH,
                                                      FindingSeverity.CRITICAL])).all())

    # ---- Component quality fractions (1.0 = perfect) ----------------------
    comp: dict[str, float] = {}
    comp["endpoint_health"] = (sum(healths) / len(healths) / 100.0) if healths else 1.0
    comp["patch"] = (sum(1 for d in reported if (d.patches_pending or 0) == 0)
                     / len(reported)) if reported else 1.0
    comp["uptime"] = (online / len(devices)) if devices else 1.0
    # One critical alert hurts more than one warning; saturate around a few.
    alert_penalty = min(1.0, (crit_alerts * 0.34 + (len(alerts) - crit_alerts) * 0.12))
    comp["alerts"] = 1.0 - alert_penalty
    comp["sla"] = (1.0 - min(1.0, sla_breached / max(1, len(open_tickets)))) if open_tickets else 1.0
    comp["security"] = max(0.0, 1.0 - 0.34 * len(findings))
    comp["backlog"] = 1.0 if len(open_tickets) <= 5 else max(0.0, 1.0 - (len(open_tickets) - 5) / 20.0)

    raw = sum(WEIGHTS[k] * comp[k] for k in WEIGHTS)
    score = max(0, min(100, round(raw)))

    # ---- Explainable factors (what's pulling the score down) --------------
    factors: list[str] = []
    if comp["endpoint_health"] < 0.75 and healths:
        factors.append(f"avg endpoint health {round(comp['endpoint_health']*100)}")
    if comp["patch"] < 0.85 and reported:
        factors.append(f"patch compliance {round(comp['patch']*100)}%")
    if comp["uptime"] < 0.8 and devices:
        factors.append(f"{len(devices)-online}/{len(devices)} devices offline")
    if crit_alerts:
        factors.append(f"{crit_alerts} critical alert(s)")
    elif len(alerts) >= 3:
        factors.append(f"{len(alerts)} active alerts")
    if sla_breached:
        factors.append(f"{sla_breached} SLA breach(es)")
    if findings:
        factors.append(f"{len(findings)} open high/critical finding(s)")
    if len(open_tickets) > 5:
        factors.append(f"{len(open_tickets)} open tickets")

    return {
        "client_id": cid,
        "client_name": client.name,
        "score": score,
        "grade": _grade(score),
        "risk": _risk(score, factors),
        "factors": factors,
        "components": {k: round(comp[k] * 100) for k in comp},
        "stats": {
            "devices": len(devices), "online": online,
            "avg_health": round(sum(healths) / len(healths)) if healths else None,
            "active_alerts": len(alerts), "critical_alerts": crit_alerts,
            "open_tickets": len(open_tickets), "sla_breached": sla_breached,
            "security_findings": len(findings),
        },
    }


def score_all(db: Session, client_ids: list[int] | None,
              now: datetime | None = None) -> list[dict]:
    """Score a scoped set of clients, worst first (so risk floats to the top)."""
    now = now or datetime.now(timezone.utc)
    q = db.query(Client)
    if client_ids is not None:
        q = q.filter(Client.id.in_(client_ids))
    out = [score_client(db, c, now) for c in q.all()]
    out.sort(key=lambda r: r["score"])
    return out
