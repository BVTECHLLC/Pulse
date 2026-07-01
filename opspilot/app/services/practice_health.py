"""v0.76 MSP Practice Health — a single A–F grade for how well the MSP itself
is running (not any one client).

Four domains, each scored 0–100, weighted into an overall grade:
  * Service   — SLA attainment (response + resolution) over the last 90 days
  * Security  — average client security-posture score
  * Endpoints — fleet online % blended with patch-compliance %
  * Billing   — share of A/R that's current (not overdue)

This is the number a franchise HQ benchmarks across locations, an established MSP
tracks month over month, and a solo operator uses to see where to focus.
Domains with no data yet are excluded from the weighting (not scored zero).
Pure read-only aggregation over data we already collect.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Device
from . import posture

_WEIGHTS = {"service": 0.30, "security": 0.25, "endpoints": 0.25, "billing": 0.20}
_ONLINE_MINUTES = 30


def _service_domain(db: Session, now: datetime) -> dict | None:
    try:
        from . import analytics
        perf = analytics.sla_performance(db, None, days=90)
    except Exception:
        return None
    o = perf.get("overall", {})
    if not o.get("tickets"):
        return None
    resp = o.get("response_attainment_pct") or 0
    res = o.get("resolution_attainment_pct") or 0
    score = round((resp + res) / 2)
    return {"score": score, "response_attainment": resp, "resolution_attainment": res,
            "tickets_90d": o.get("tickets", 0),
            "avg_resolution_hrs": round((o.get("avg_resolution_minutes") or 0) / 60.0, 1)}


def _security_domain(db: Session) -> dict | None:
    try:
        port = posture.portfolio(db)
    except Exception:
        return None
    scored = [p["score"] for p in port if p.get("score") is not None]
    if not scored:
        return None
    avg = round(sum(scored) / len(scored))
    at_risk = sum(1 for s in scored if s < 70)
    return {"score": avg, "clients_graded": len(scored), "at_risk": at_risk}


def _endpoints_domain(db: Session, now: datetime) -> dict | None:
    devices = db.query(Device).all()
    if not devices:
        return None
    cutoff = now - timedelta(minutes=_ONLINE_MINUTES)
    online = sum(1 for d in devices
                 if d.last_checkin and (d.last_checkin if d.last_checkin.tzinfo
                                        else d.last_checkin.replace(tzinfo=timezone.utc)) >= cutoff)
    online_pct = round(online / len(devices) * 100)
    try:
        from . import inventory
        patch_pct = inventory.patch_compliance(db)["fleet"]["compliance_pct"]
    except Exception:
        patch_pct = online_pct
    score = round((online_pct + patch_pct) / 2)
    return {"score": score, "devices": len(devices), "online_pct": online_pct,
            "patch_compliance_pct": patch_pct}


def _billing_domain(db: Session, now: datetime) -> dict | None:
    try:
        from . import ar_aging
        aging = ar_aging.aging_report(db, now)
    except Exception:
        return None
    total = aging["total"]
    if total <= 0:
        # Nothing outstanding = healthy collections (but only meaningful if there
        # are invoices at all — otherwise there's no billing signal yet).
        from ..models import Invoice
        if db.query(Invoice).count() == 0:
            return None
        return {"score": 100, "outstanding": 0.0, "overdue": 0.0, "current_pct": 100}
    current_pct = round((total - aging["overdue_total"]) / total * 100)
    return {"score": current_pct, "outstanding": round(total, 2),
            "overdue": round(aging["overdue_total"], 2), "current_pct": current_pct}


def _recommendations(domains: dict) -> list[str]:
    recs = []
    s = domains.get("service")
    if s and s["score"] < 90:
        recs.append(f"SLA attainment is {s['score']}% — tighten response/resolution on open tickets.")
    sec = domains.get("security")
    if sec and sec["at_risk"]:
        recs.append(f"{sec['at_risk']} client(s) below a C security grade — schedule hardening.")
    ep = domains.get("endpoints")
    if ep and ep["patch_compliance_pct"] < 90:
        recs.append(f"Fleet patch compliance is {ep['patch_compliance_pct']}% — run a patch cycle "
                    "(or add a patch_behind auto-remediation rule).")
    if ep and ep["online_pct"] < 90:
        recs.append(f"Only {ep['online_pct']}% of endpoints are online — chase the stragglers.")
    b = domains.get("billing")
    if b and b.get("overdue", 0) > 0:
        recs.append(f"${b['overdue']:,.0f} of A/R is overdue — send reminders / follow up.")
    return recs


def practice_health(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    domains = {
        "service": _service_domain(db, now),
        "security": _security_domain(db),
        "endpoints": _endpoints_domain(db, now),
        "billing": _billing_domain(db, now),
    }
    present = {k: v for k, v in domains.items() if v is not None}
    wsum = sum(_WEIGHTS[k] for k in present)
    overall = (round(sum(present[k]["score"] * _WEIGHTS[k] for k in present) / wsum)
               if wsum else None)
    return {
        "score": overall,
        "grade": posture.grade_for(overall),
        "domains": {k: {**v, "grade": posture.grade_for(v["score"])} for k, v in present.items()},
        "missing_domains": [k for k, v in domains.items() if v is None],
        "recommendations": _recommendations(present),
        "generated_at": now.isoformat(),
    }
