"""v0.64 Client security scorecard.

Rolls the data we already collect into ONE graded (A–F) posture report per
client, suitable for a QBR or to share with the client:

  * Endpoints  — % online, % AV-protected, average health score
  * Patching   — % of reporting devices fully patched, pending-update count
  * Identity   — Microsoft 365 Secure Score (and risky sign-ins)
  * Threats    — open security findings (weighted), via services/security

Each present domain scores 0–100; the overall is their weighted average
(renormalized over whichever domains have data), mapped to a letter grade.
Domains with no data (e.g. no M365 tenant linked) are excluded, not penalized,
so a small client isn't unfairly graded. Pure aggregation — read-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Client, Device, M365Connection
from . import security as security_svc

_ONLINE_MINUTES = 30
_AV_BAD_TOKENS = ("disabl", "off", "at risk", "not ", "none", "expired",
                  "unknown", "no av", "missing")

# Relative weight of each domain in the overall score (renormalized over those
# domains that actually have data for the client).
_WEIGHTS = {"endpoints": 0.30, "patching": 0.25, "identity": 0.25, "threats": 0.20}


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def grade_for(score: float | None) -> str:
    if score is None:
        return "N/A"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _pct(n: int, d: int) -> int:
    return round(n / d * 100) if d else 0


def _av_ok(status: str | None) -> bool:
    if not status:
        return False
    s = status.lower()
    return not any(tok in s for tok in _AV_BAD_TOKENS)


def endpoint_domain(devices: list[Device], now: datetime) -> dict | None:
    """% online + % AV-protected + avg health → a 0–100 endpoint score."""
    if not devices:
        return None
    total = len(devices)
    cutoff = now - timedelta(minutes=_ONLINE_MINUTES)
    online = sum(1 for d in devices if _aware(d.last_checkin) and _aware(d.last_checkin) >= cutoff)
    av_ok = sum(1 for d in devices if _av_ok(d.av_status))
    healths = [d.health_score for d in devices if d.health_score is not None]
    avg_health = round(sum(healths) / len(healths)) if healths else None
    online_pct, av_pct = _pct(online, total), _pct(av_ok, total)
    # Blend: online + AV protection + (avg health if reported, else the avg of the
    # other two so an un-scored fleet isn't dragged down).
    parts = [online_pct, av_pct, avg_health if avg_health is not None else round((online_pct + av_pct) / 2)]
    score = round(sum(parts) / len(parts))
    return {"score": score, "device_count": total, "online": online, "online_pct": online_pct,
            "av_protected": av_ok, "av_pct": av_pct, "avg_health": avg_health}


def patching_domain(devices: list[Device]) -> dict | None:
    reported = [d for d in devices if d.patches_pending is not None]
    if not reported:
        return None
    fully = sum(1 for d in reported if (d.patches_pending or 0) == 0)
    pending_total = sum((d.patches_pending or 0) for d in reported)
    compliance = _pct(fully, len(reported))
    return {"score": compliance, "compliance_pct": compliance,
            "pending_total": pending_total, "reporting": len(reported)}


def identity_domain(conn: M365Connection | None) -> dict | None:
    if not conn or conn.secure_score is None or not conn.secure_score_max:
        return None
    pct = _pct(conn.secure_score, conn.secure_score_max)
    return {"score": pct, "secure_score": conn.secure_score,
            "secure_score_max": conn.secure_score_max, "secure_score_pct": pct,
            "risky_signins": conn.risky_signin_count or 0}


def threats_domain(db: Session, client_id: int) -> dict:
    sc = security_svc.scorecard(db, client_id)
    return {"score": sc["score"], "open_findings": sc["open_findings"],
            "by_severity": sc["by_severity"]}


def _recommendations(domains: dict) -> list[str]:
    recs = []
    ep = domains.get("endpoints")
    if ep:
        off = ep["device_count"] - ep["online"]
        if off > 0:
            recs.append(f"{off} endpoint(s) offline — verify they're powered on and the agent is running.")
        unprot = ep["device_count"] - ep["av_protected"]
        if unprot > 0:
            recs.append(f"{unprot} endpoint(s) without confirmed AV/EDR protection.")
    pa = domains.get("patching")
    if pa and pa["pending_total"] > 0:
        recs.append(f"{pa['pending_total']} pending update(s) across the fleet — schedule patching.")
    idn = domains.get("identity")
    if idn:
        if idn["secure_score_pct"] < 70:
            recs.append(f"Microsoft 365 Secure Score is {idn['secure_score_pct']}% — enable MFA & review hardening.")
        if idn["risky_signins"]:
            recs.append(f"{idn['risky_signins']} risky sign-in(s) flagged in Microsoft 365.")
    th = domains.get("threats")
    if th:
        crit = th["by_severity"].get("critical", 0) + th["by_severity"].get("high", 0)
        if crit:
            recs.append(f"{crit} high/critical security finding(s) open — remediate first.")
    return recs


def scorecard(db: Session, client_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    devices = db.query(Device).filter(Device.client_id == client_id).all()
    conn = (db.query(M365Connection)
            .filter(M365Connection.client_id == client_id).first())

    domains = {
        "endpoints": endpoint_domain(devices, now),
        "patching": patching_domain(devices),
        "identity": identity_domain(conn),
        "threats": threats_domain(db, client_id),
    }
    present = {k: v for k, v in domains.items() if v is not None}
    wsum = sum(_WEIGHTS[k] for k in present)
    overall = (round(sum(present[k]["score"] * _WEIGHTS[k] for k in present) / wsum)
               if wsum else None)
    client = db.get(Client, client_id)
    return {
        "client_id": client_id,
        "client_name": client.name if client else None,
        "score": overall,
        "grade": grade_for(overall),
        "domains": {k: {**v, "grade": grade_for(v["score"])} for k, v in domains.items() if v},
        "missing_domains": [k for k, v in domains.items() if v is None],
        "recommendations": _recommendations(present),
        "generated_at": now.isoformat(),
    }


def portfolio(db: Session, now: datetime | None = None) -> list[dict]:
    """One graded row per client — the MSP's posture overview across the book."""
    now = now or datetime.now(timezone.utc)
    out = []
    for c in db.query(Client).order_by(Client.name).all():
        sc = scorecard(db, c.id, now)
        out.append({"client_id": c.id, "client_name": c.name, "score": sc["score"],
                    "grade": sc["grade"],
                    "domain_grades": {k: v["grade"] for k, v in sc["domains"].items()},
                    "open_recommendations": len(sc["recommendations"])})
    # Worst grades first so the riskiest clients surface at the top.
    out.sort(key=lambda r: (r["score"] if r["score"] is not None else 101))
    return out
