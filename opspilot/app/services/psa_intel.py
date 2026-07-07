"""v1.15 PSA Intelligence — the AI brain on top of the PSA book of business.

Pulse already has the full PSA spine (contracts, ticketing, SLA, time, billing,
A/R). This layer makes it *think*:

  1. sla_radar()          — PREDICTS which open tickets will breach SLA in the
                            next few hours and ranks them, so you fix it before
                            the clock runs out instead of getting a breach alert
                            after the fact.
  2. contract_intel()     — per-contract MARGIN & REALIZATION: contracted MRR vs.
                            the fully-loaded cost of service actually delivered
                            (time logged), flags money-losing contracts and
                            upcoming renewals with the numbers to price the deal.
  3. revenue_leakage()    — finds money you EARNED but haven't billed: unbilled
                            billable time, contracts overdue to be invoiced, and
                            resolved tickets with zero time captured.

Everything here is deterministic and unit-testable; AI narratives are optional
and layered on top (never the source of a number). Labor bill/cost rates live in
the encrypted vault so the margin math reflects the operator's real economics.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (Client, Contract, SupportTicket, TicketStatus, TimeEntry)
from . import secure_config, sla

RATES_PROVIDER = "psa_rates"
DEFAULT_BILL_RATE = 150.0   # $/hr billed to the client
DEFAULT_COST_RATE = 55.0    # $/hr fully-loaded technician cost

_OPEN = [TicketStatus.OPEN, TicketStatus.IN_PROGRESS]
# Nominal days in a billing period, for "overdue to invoice" detection.
_PERIOD_DAYS = {"monthly": 27, "quarterly": 88, "annual": 362}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _monthly_value(c: Contract) -> float:
    per = {"monthly": 1.0, "quarterly": 1 / 3.0, "annual": 1 / 12.0}
    return (c.amount or 0.0) * per.get(c.billing_period, 1.0)


# --------------------------------------------------------------------------- #
# Labor rates (vault-backed, operator-tunable)
# --------------------------------------------------------------------------- #
def get_rates(db: Session) -> dict:
    conn = secure_config.get_platform(db, RATES_PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"bill_rate": float(cfg.get("bill_rate", DEFAULT_BILL_RATE) or DEFAULT_BILL_RATE),
            "cost_rate": float(cfg.get("cost_rate", DEFAULT_COST_RATE) or DEFAULT_COST_RATE)}


def set_rates(db: Session, *, bill_rate: float | None = None,
              cost_rate: float | None = None) -> dict:
    r = get_rates(db)
    if bill_rate is not None:
        r["bill_rate"] = max(0.0, float(bill_rate))
    if cost_rate is not None:
        r["cost_rate"] = max(0.0, float(cost_rate))
    secure_config.upsert_platform(db, RATES_PROVIDER, "PSA Labor Rates", "Finance", r)
    return r


# --------------------------------------------------------------------------- #
# 1) Predictive SLA breach radar
# --------------------------------------------------------------------------- #
def sla_radar(db: Session, now: datetime | None = None, *, horizon_hours: int = 8,
              client_ids: list[int] | None = None) -> dict:
    """Open tickets that are breached or projected to breach within the horizon,
    ranked most-urgent first. Deterministic (uses the SLA clock)."""
    now = _now(now)
    horizon = horizon_hours * 60
    q = db.query(SupportTicket).filter(SupportTicket.status.in_(_OPEN))
    if client_ids is not None:
        q = q.filter(SupportTicket.client_id.in_(client_ids))
    rows = []
    for t in q.all():
        s = sla.evaluate(t, now)
        left = [x for x in (s["response_minutes_left"], s["resolution_minutes_left"])
                if x is not None]
        if not left:
            continue
        mins = min(left)
        if s["breached"]:
            level = "breached"
        elif mins <= 60:
            level = "critical"
        elif mins <= horizon:
            level = "warning"
        else:
            continue
        which = "response" if (not s["responded"] and s["response_minutes_left"] is not None
                               and s["response_minutes_left"] == mins) else "resolution"
        rows.append({
            "ticket_id": t.id, "client_id": t.client_id, "subject": t.subject,
            "priority": t.priority, "assigned_to_user_id": t.assigned_to_user_id,
            "minutes_to_due": mins, "which": which, "level": level,
            "breached": s["breached"],
        })
    # Breached first, then soonest-to-breach.
    rows.sort(key=lambda r: (0 if r["breached"] else 1, r["minutes_to_due"]))
    counts = {"breached": 0, "critical": 0, "warning": 0}
    for r in rows:
        counts[r["level"]] = counts.get(r["level"], 0) + 1
    return {"generated_at": now.isoformat(), "horizon_hours": horizon_hours,
            "counts": counts, "at_risk": rows}


SLA_WATCH_PROVIDER = "psa_sla_watch"


def sla_watch(db: Session, now: datetime | None = None) -> list[dict]:
    """Heartbeat entrypoint: raise a PRE-BREACH notification for each open ticket
    that just entered the critical window (<=60 min to due, not yet breached),
    deduped per ticket per day. This is the 'fix it before the clock runs out'
    signal — distinct from the existing after-the-fact breach escalation."""
    from ..models import Notification
    now = _now(now)
    radar = sla_radar(db, now)
    critical = [r for r in radar["at_risk"] if r["level"] == "critical" and not r["breached"]]
    conn = secure_config.get_platform(db, SLA_WATCH_PROVIDER)
    cfg = (conn.config if conn else None) or {}
    today = now.date().isoformat()
    seen = set(cfg.get("seen", [])) if cfg.get("date") == today else set()
    raised = []
    for r in critical:
        key = str(r["ticket_id"])
        if key in seen:
            continue
        seen.add(key)
        try:
            db.add(Notification(
                client_id=r["client_id"], target_user_id=r.get("assigned_to_user_id"),
                kind="sla_watch", severity="warning",
                message=(f"⏳ SLA risk: ticket #{r['ticket_id']} — '{r['subject']}' "
                         f"is ~{r['minutes_to_due']} min from its {r['which']} SLA. Act now.")[:1000]))
            raised.append(r)
        except Exception:  # noqa: BLE001
            pass
    if raised:
        db.commit()
    secure_config.upsert_platform(db, SLA_WATCH_PROVIDER, "SLA Watch", "Automation",
                                  {"date": today, "seen": sorted(seen)})
    return raised


# --------------------------------------------------------------------------- #
# 2) Contract margin / realization / renewal intelligence
# --------------------------------------------------------------------------- #
def _client_monthly_service_cost(db: Session, client_id: int, now: datetime,
                                 cost_rate: float, window_days: int = 90) -> tuple[float, float]:
    """(monthly_hours, monthly_cost) of service delivered to a client, from the
    trailing window of logged time normalized to a monthly figure."""
    cutoff = now - timedelta(days=window_days)
    entries = (db.query(TimeEntry)
               .filter(TimeEntry.client_id == client_id,
                       TimeEntry.created_at >= cutoff.replace(tzinfo=None))
               .all())
    total_min = sum((e.minutes or 0) for e in entries)
    monthly_hours = (total_min / 60.0) * (30.0 / window_days)
    return monthly_hours, monthly_hours * cost_rate


def contract_intel(db: Session, now: datetime | None = None, *,
                   renewal_days: int = 60, client_ids: list[int] | None = None) -> dict:
    """Per-active-contract economics: MRR vs allocated cost of service, margin %,
    effective realized rate, and renewal window. Worst margin first."""
    now = _now(now)
    rates = get_rates(db)
    q = db.query(Contract).filter(Contract.status == "active")
    if client_ids is not None:
        q = q.filter(Contract.client_id.in_(client_ids))
    contracts = q.all()
    # Group by client to allocate the client's service cost across its contracts.
    by_client: dict[int, list[Contract]] = {}
    for c in contracts:
        by_client.setdefault(c.client_id, []).append(c)
    names = {cl.id: cl.name for cl in db.query(Client).all()}

    out = []
    for cid, cs in by_client.items():
        client_mrr = sum(_monthly_value(c) for c in cs) or 0.0
        m_hours, m_cost = _client_monthly_service_cost(db, cid, now, rates["cost_rate"])
        for c in cs:
            mrr = _monthly_value(c)
            share = (mrr / client_mrr) if client_mrr > 0 else (1.0 / len(cs))
            alloc_hours = m_hours * share
            alloc_cost = m_cost * share
            margin = mrr - alloc_cost
            margin_pct = (margin / mrr) if mrr > 0 else None
            realized_rate = (mrr / alloc_hours) if alloc_hours > 0 else None
            end = _aware(c.end_date)
            days_to_renewal = int((end - now).total_seconds() // 86400) if end else None
            flags = []
            if margin < 0:
                flags.append("underwater")
            elif margin_pct is not None and margin_pct < 0.25:
                flags.append("low_margin")
            if days_to_renewal is not None and 0 <= days_to_renewal <= renewal_days:
                flags.append("renewal_soon")
            if realized_rate is not None and realized_rate < rates["cost_rate"]:
                flags.append("below_cost_rate")
            out.append({
                "contract_id": c.id, "client_id": cid, "client": names.get(cid),
                "name": c.name, "billing_period": c.billing_period,
                "mrr": round(mrr, 2), "monthly_hours": round(alloc_hours, 1),
                "monthly_cost": round(alloc_cost, 2), "margin": round(margin, 2),
                "margin_pct": round(margin_pct, 3) if margin_pct is not None else None,
                "realized_rate": round(realized_rate, 2) if realized_rate is not None else None,
                "days_to_renewal": days_to_renewal, "flags": flags,
            })
    out.sort(key=lambda r: (r["margin"] if r["margin"] is not None else 0.0))
    totals = {
        "contracts": len(out),
        "mrr": round(sum(r["mrr"] for r in out), 2),
        "monthly_cost": round(sum(r["monthly_cost"] for r in out), 2),
        "margin": round(sum(r["margin"] for r in out), 2),
        "underwater": sum(1 for r in out if "underwater" in r["flags"]),
        "renewals_soon": sum(1 for r in out if "renewal_soon" in r["flags"]),
    }
    totals["blended_margin_pct"] = (round(totals["margin"] / totals["mrr"], 3)
                                    if totals["mrr"] > 0 else None)
    return {"generated_at": now.isoformat(), "rates": rates,
            "totals": totals, "contracts": out}


# --------------------------------------------------------------------------- #
# 3) Revenue leakage — earned but not billed
# --------------------------------------------------------------------------- #
def _contract_invoice_overdue(c: Contract, now: datetime) -> bool:
    if c.status != "active" or (c.amount or 0) <= 0:
        return False
    start = _aware(c.start_date)
    end = _aware(c.end_date)
    if start and now < start:
        return False
    if end and now > end:
        return False
    gap = _PERIOD_DAYS.get(c.billing_period, 27)
    last = _aware(c.last_invoiced_at)
    if last is None:
        # Never invoiced but started long enough ago to be due once.
        return bool(start is None or (now - start).days >= gap)
    return (now - last).days >= gap


def revenue_leakage(db: Session, now: datetime | None = None, *,
                    client_ids: list[int] | None = None) -> dict:
    """Money earned but not yet captured on an invoice."""
    now = _now(now)
    rates = get_rates(db)

    # (a) Unbilled billable time.
    tq = db.query(TimeEntry).filter(TimeEntry.billable.is_(True),
                                    TimeEntry.invoiced.is_(False))
    if client_ids is not None:
        tq = tq.filter(TimeEntry.client_id.in_(client_ids))
    tentries = tq.all()
    unbilled_min = sum((e.minutes or 0) for e in tentries)
    unbilled_hours = unbilled_min / 60.0
    unbilled_value = unbilled_hours * rates["bill_rate"]

    # (b) Active contracts overdue to be invoiced.
    cq = db.query(Contract).filter(Contract.status == "active")
    if client_ids is not None:
        cq = cq.filter(Contract.client_id.in_(client_ids))
    due = [c for c in cq.all() if _contract_invoice_overdue(c, now)]
    due_value = sum(_monthly_value(c) for c in due)

    # (c) Resolved/closed tickets in the last 30d with NO time captured.
    cutoff = now - timedelta(days=30)
    rq = db.query(SupportTicket).filter(
        SupportTicket.status.in_([TicketStatus.RESOLVED, TicketStatus.CLOSED]),
        SupportTicket.updated_at >= cutoff.replace(tzinfo=None))
    if client_ids is not None:
        rq = rq.filter(SupportTicket.client_id.in_(client_ids))
    resolved = rq.all()
    timed_ids = {tid for (tid,) in db.query(TimeEntry.ticket_id)
                 .filter(TimeEntry.ticket_id.isnot(None)).distinct().all()}
    untracked = [t for t in resolved if t.id not in timed_ids]

    names = {cl.id: cl.name for cl in db.query(Client).all()}
    total_recoverable = round(unbilled_value + due_value, 2)
    return {
        "generated_at": now.isoformat(), "rates": rates,
        "unbilled_time": {
            "entries": len(tentries), "minutes": unbilled_min,
            "hours": round(unbilled_hours, 1), "value": round(unbilled_value, 2)},
        "due_contracts": {
            "count": len(due), "value": round(due_value, 2),
            "list": [{"contract_id": c.id, "client": names.get(c.client_id),
                      "name": c.name, "mrr": round(_monthly_value(c), 2)} for c in due]},
        "untracked_tickets": {
            "count": len(untracked),
            "list": [{"ticket_id": t.id, "client": names.get(t.client_id),
                      "subject": t.subject} for t in untracked[:25]]},
        "total_recoverable": total_recoverable,
    }
