"""v0.14 client reports — one aggregated, branded snapshot per client for QBRs /
monthly reviews / reselling. Pulls health, alerts, security posture, helpdesk
SLA, and recurring revenue into a single payload the report page renders.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff
from ...models import (
    Alert, AlertStatus, Client, Contract, Device, License, SupportTicket,
    TicketStatus, User,
)
from ...services import security, sla
from .contracts import monthly_value

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{client_id}/summary")
def client_summary(client_id: int, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    now = datetime.now(timezone.utc)

    # Devices / health
    devices = db.query(Device).filter(Device.client_id == client_id).all()
    healths = [d.health_score for d in devices if d.health_score is not None]
    avg_health = round(sum(healths) / len(healths)) if healths else None
    attention = sum(1 for d in devices if (d.health_score if d.health_score is not None else 100) < 70)

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

    # Revenue: licenses + active contracts (normalized monthly)
    lic = db.query(License).filter(License.client_id == client_id).all()
    license_mrr = sum((l.monthly_cost or 0.0) for l in lic)
    active_contracts = db.query(Contract).filter(
        Contract.client_id == client_id, Contract.status == "active").all()
    contract_mrr = sum(monthly_value(c) for c in active_contracts)
    mrr = round(license_mrr + contract_mrr, 2)

    return {
        "client": {"id": client.id, "name": client.name,
                   "primary_contact": client.primary_contact, "email": client.email},
        "generated_at": now.isoformat(),
        "devices": {"total": len(devices), "avg_health": avg_health, "need_attention": attention},
        "alerts": alert_counts,
        "security": security.scorecard(db, client_id),
        "tickets": {"total": len(tickets), "open": len(open_tickets), "sla_breached": breached},
        "revenue": {"mrr": mrr, "arr": round(mrr * 12, 2),
                    "license_mrr": round(license_mrr, 2), "contract_mrr": round(contract_mrr, 2),
                    "active_contracts": len(active_contracts), "licenses": len(lic)},
    }
