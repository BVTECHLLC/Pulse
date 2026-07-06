"""v0.14 client reports — one aggregated, branded snapshot per client for QBRs /
monthly reviews / reselling. Pulls health, alerts, security posture, helpdesk
SLA, and recurring revenue into a single payload the report page renders.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff
from ...models import (
    Alert, AlertStatus, Asset, Client, Contract, Device, License, Project,
    ProjectStatus, ProjectTask, SupportTicket, TicketStatus, TimeEntry, User,
)
from ...services import posture, security, sla
from .contracts import monthly_value

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _aware(dt):
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


def _build_summary(db: Session, client: Client, now: datetime) -> dict:
    client_id = client.id
    # Devices / health
    devices = db.query(Device).filter(Device.client_id == client_id).all()
    healths = [d.health_score for d in devices if d.health_score is not None]
    avg_health = round(sum(healths) / len(healths)) if healths else None
    attention = sum(1 for d in devices if (d.health_score if d.health_score is not None else 100) < 70)
    # Patch compliance
    reported = [d for d in devices if d.patches_pending is not None]
    patch_compliance = (round(sum(1 for d in reported if (d.patches_pending or 0) == 0) / len(reported) * 100)
                        if reported else None)
    pending_patches = sum((d.patches_pending or 0) for d in devices)

    # Alerts (non-resolved) by severity
    alerts = (db.query(Alert)
              .filter(Alert.client_id == client_id, Alert.status != AlertStatus.RESOLVED).all())
    alert_counts = {"total": len(alerts), "critical": 0, "warning": 0, "info": 0}
    for a in alerts:
        alert_counts[a.severity.value] = alert_counts.get(a.severity.value, 0) + 1

    # Tickets / SLA
    tickets = db.query(SupportTicket).filter(SupportTicket.client_id == client_id).all()
    open_tickets = [t for t in tickets if t.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)]
    breached = sum(1 for t in open_tickets if sla.evaluate(t, now)["breached"])
    resolved = sum(1 for t in tickets if t.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED))

    # Projects
    projects = db.query(Project).filter(Project.client_id == client_id).all()
    active_projects = sum(1 for p in projects if p.status == ProjectStatus.ACTIVE)
    ptasks = db.query(ProjectTask).filter(ProjectTask.client_id == client_id).all()
    tasks_done = sum(1 for t in ptasks if t.status == "done")

    # Assets + warranty
    assets = db.query(Asset).filter(Asset.client_id == client_id).all()
    warranty_soon = sum(1 for a in assets if a.warranty_expires
                        and _aware(a.warranty_expires) <= now + timedelta(days=60))

    # Hours delivered (last 90d) — value the client received
    since = now - timedelta(days=90)
    entries = (db.query(TimeEntry)
               .filter(TimeEntry.client_id == client_id, TimeEntry.created_at >= since).all())
    minutes_90d = sum(e.minutes for e in entries)
    billable_90d = sum(e.minutes for e in entries if e.billable)

    # Revenue: licenses + active contracts (normalized monthly)
    lic = db.query(License).filter(License.client_id == client_id).all()
    license_mrr = sum((l.monthly_cost or 0.0) for l in lic)
    active_contracts = db.query(Contract).filter(
        Contract.client_id == client_id, Contract.status == "active").all()
    contract_mrr = sum(monthly_value(c) for c in active_contracts)
    mrr = round(license_mrr + contract_mrr, 2)

    # Security-awareness training adoption (v1.3) — the QBR/renewal number.
    from ...services import academy
    training = academy.client_compliance(db, client_id)

    return {
        "client": {"id": client.id, "name": client.name,
                   "primary_contact": client.primary_contact, "email": client.email},
        "generated_at": now.isoformat(),
        "devices": {"total": len(devices), "avg_health": avg_health, "need_attention": attention},
        "patch": {"compliance_pct": patch_compliance, "pending_total": pending_patches},
        "alerts": alert_counts,
        "security": security.scorecard(db, client_id),
        "posture": posture.scorecard(db, client_id, now),
        "tickets": {"total": len(tickets), "open": len(open_tickets),
                    "resolved": resolved, "sla_breached": breached},
        "projects": {"total": len(projects), "active": active_projects,
                     "tasks_total": len(ptasks), "tasks_done": tasks_done},
        "assets": {"total": len(assets), "warranty_expiring": warranty_soon},
        "service": {"hours_90d": round(minutes_90d / 60.0, 1),
                    "billable_hours_90d": round(billable_90d / 60.0, 1)},
        "revenue": {"mrr": mrr, "arr": round(mrr * 12, 2),
                    "license_mrr": round(license_mrr, 2), "contract_mrr": round(contract_mrr, 2),
                    "active_contracts": len(active_contracts), "licenses": len(lic)},
        "training": training,
    }


@router.get("/{client_id}/summary")
def client_summary(client_id: int, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    return _build_summary(db, client, datetime.now(timezone.utc))


@router.post("/{client_id}/narrative")
def qbr_narrative(client_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Claude turns the client's QBR data into a polished, client-ready executive
    summary you can drop into a review deck or email. Staff, or the client's own
    users (they can read their own review)."""
    from ...services import ai
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    if not ai.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Claude isn't connected yet — add your Anthropic API key on the server.")
    s = _build_summary(db, client, datetime.now(timezone.utc))
    p = s.get("posture", {})
    facts = (
        f"Client: {client.name}\n"
        f"Security grade: {p.get('grade')} (score {p.get('score')})\n"
        f"Devices: {s['devices']['total']} ({s['devices']['need_attention']} need attention), "
        f"avg health {s['devices']['avg_health']}\n"
        f"Patch compliance: {s['patch']['compliance_pct']}% ({s['patch']['pending_total']} pending)\n"
        f"Tickets (period): {s['tickets']['total']} total, {s['tickets']['resolved']} resolved, "
        f"{s['tickets']['sla_breached']} SLA-breached\n"
        f"Projects: {s['projects']['active']} active\n"
        f"Assets: {s['assets']['total']} ({s['assets']['warranty_expiring']} warranties expiring)\n"
        f"Service hours (90d): {s['service']['hours_90d']}\n"
        f"Open security findings: {s['security'].get('open_findings')}\n"
    )
    system = ("You write concise, positive-but-honest quarterly business review "
              "(QBR) narratives for an MSP's client. Audience: a non-technical "
              "business owner. 3-4 short paragraphs: what we did, current health, "
              "risks/recommendations, and what's next. No fluff, no fabricated numbers.")
    try:
        text = ai.complete(system, f"Write the QBR narrative from these facts:\n\n{facts}",
                           smart=True, max_tokens=900)
    except ai.AIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"client_id": client_id, "client": client.name, "narrative": text}


def summary_csv(s: dict) -> str:
    """Render a summary dict (from _build_summary) as a flat Metric,Value CSV.
    Shared by the export endpoint and the scheduled-report attachment."""
    rows = [
        ("Client", s["client"]["name"]),
        ("Generated", s["generated_at"]),
        ("Devices", s["devices"]["total"]),
        ("Avg device health", s["devices"]["avg_health"]),
        ("Devices needing attention", s["devices"]["need_attention"]),
        ("Patch compliance %", s["patch"]["compliance_pct"]),
        ("Pending patches", s["patch"]["pending_total"]),
        ("Active alerts", s["alerts"]["total"]),
        ("Critical alerts", s["alerts"]["critical"]),
        ("Security score", s["security"].get("score")),
        ("Posture grade", s.get("posture", {}).get("grade")),
        ("Posture score", s.get("posture", {}).get("score")),
        ("Tickets total", s["tickets"]["total"]),
        ("Tickets open", s["tickets"]["open"]),
        ("Tickets resolved", s["tickets"]["resolved"]),
        ("SLA breached", s["tickets"]["sla_breached"]),
        ("Projects active", s["projects"]["active"]),
        ("Project tasks done", f'{s["projects"]["tasks_done"]}/{s["projects"]["tasks_total"]}'),
        ("Assets tracked", s["assets"]["total"]),
        ("Warranties expiring (60d)", s["assets"]["warranty_expiring"]),
        ("Hours delivered (90d)", s["service"]["hours_90d"]),
        ("Billable hours (90d)", s["service"]["billable_hours_90d"]),
        ("Staff trained (security awareness) %", s.get("training", {}).get("trained_pct")),
        ("Training curriculum completed %", s.get("training", {}).get("curriculum_pct")),
        ("MRR", s["revenue"]["mrr"]),
        ("ARR", s["revenue"]["arr"]),
        ("Active contracts", s["revenue"]["active_contracts"]),
        ("Licensed products", s["revenue"]["licenses"]),
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Metric", "Value"])
    w.writerows(rows)
    return buf.getvalue()


@router.get("/{client_id}/export.csv", response_class=PlainTextResponse)
def export_csv(client_id: int, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    """The QBR snapshot as a flat CSV — drop into Excel/Sheets or a deck."""
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    s = _build_summary(db, client, datetime.now(timezone.utc))
    fname = f"report-{client.name.replace(' ', '_')}.csv"
    return PlainTextResponse(summary_csv(s), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
