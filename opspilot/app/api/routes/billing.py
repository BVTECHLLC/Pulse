"""v0.3 billing visibility: MRR rollup, per-client breakdown, seat utilization,
and an upcoming-renewals calendar — all derived from the License table.

This is reporting only (no invoicing/charging). Staff see the whole book of
business; a client user sees just their own numbers. Stripe/QuickBooks export is
a later phase (see ROADMAP)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff
from ...models import Client, License, User

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _scoped_licenses(db: Session, user: User, client_id: int | None):
    q = db.query(License)
    if is_staff(user):
        if client_id:
            q = q.filter(License.client_id == client_id)
    else:
        q = q.filter(License.client_id == user.client_id)
    return q.all()


@router.get("/summary")
def billing_summary(client_id: int | None = None, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    """Top-line MRR/ARR, seat utilization, and a per-client breakdown (staff)."""
    licenses = _scoped_licenses(db, user, client_id)

    total_mrr = 0.0
    seats_total = 0
    seats_used = 0
    per_client: dict[int, dict] = {}

    for lic in licenses:
        cost = lic.monthly_cost or 0.0
        total_mrr += cost
        if lic.seats:
            seats_total += lic.seats
        if lic.seats_used:
            seats_used += lic.seats_used
        pc = per_client.setdefault(
            lic.client_id, {"client_id": lic.client_id, "mrr": 0.0,
                            "seats": 0, "seats_used": 0, "license_count": 0})
        pc["mrr"] += cost
        pc["seats"] += lic.seats or 0
        pc["seats_used"] += lic.seats_used or 0
        pc["license_count"] += 1

    # Fold in active recurring contracts (normalized to monthly).
    from ...models import Contract
    from .contracts import monthly_value
    cq = db.query(Contract).filter(Contract.status == "active")
    if is_staff(user):
        if client_id:
            cq = cq.filter(Contract.client_id == client_id)
    else:
        cq = cq.filter(Contract.client_id == user.client_id)
    contract_mrr = 0.0
    for ct in cq.all():
        mv = monthly_value(ct)
        contract_mrr += mv
        total_mrr += mv
        pc = per_client.setdefault(
            ct.client_id, {"client_id": ct.client_id, "mrr": 0.0,
                           "seats": 0, "seats_used": 0, "license_count": 0})
        pc["mrr"] += mv
        pc["contract_mrr"] = pc.get("contract_mrr", 0.0) + mv

    # Attach client names for staff-facing breakdown.
    if per_client:
        names = {c.id: c.name for c in
                 db.query(Client).filter(Client.id.in_(per_client.keys())).all()}
        for cid_, row in per_client.items():
            row["client_name"] = names.get(cid_)
            row["mrr"] = round(row["mrr"], 2)

    utilization = round(100.0 * seats_used / seats_total, 1) if seats_total else None
    breakdown = sorted(per_client.values(), key=lambda r: r["mrr"], reverse=True)

    return {
        "total_mrr": round(total_mrr, 2),
        "total_arr": round(total_mrr * 12, 2),
        "license_mrr": round(total_mrr - contract_mrr, 2),
        "contract_mrr": round(contract_mrr, 2),
        "license_count": len(licenses),
        "seats_total": seats_total,
        "seats_used": seats_used,
        "seat_utilization_pct": utilization,
        "by_client": breakdown,
    }


@router.get("/renewals")
def upcoming_renewals(days: int = 60, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    """Licenses renewing within the next `days` days, soonest first. Overdue
    renewals (renewal_date in the past) are included and flagged."""
    days = max(1, min(days, 365))
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)

    q = db.query(License).filter(License.renewal_date.isnot(None))
    if not is_staff(user):
        q = q.filter(License.client_id == user.client_id)
    q = q.filter(License.renewal_date <= horizon)

    rows = q.order_by(License.renewal_date.asc()).all()
    names = {c.id: c.name for c in db.query(Client).all()} if is_staff(user) else {}
    out = []
    for lic in rows:
        rd = lic.renewal_date
        # Normalize naive timestamps (SQLite drops tz) so the math never crashes.
        if rd.tzinfo is None:
            rd = rd.replace(tzinfo=timezone.utc)
        days_until = (rd - now).days
        out.append({
            "license_id": lic.id, "client_id": lic.client_id,
            "client_name": names.get(lic.client_id),
            "product": lic.product, "vendor": lic.vendor,
            "monthly_cost": lic.monthly_cost,
            "renewal_date": lic.renewal_date.isoformat(),
            "days_until": days_until, "overdue": days_until < 0,
        })
    return out
