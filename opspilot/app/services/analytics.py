"""v0.40 SLA performance analytics — the numbers an MSP reports on.

Pure read model over the tickets table: SLA attainment (did we hit the response
and resolution targets?), average response/resolution times, and a per-priority
breakdown, over a rolling window. Tenant-scoped. Feeds QBRs and the dashboard.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import PRIORITIES, SupportTicket, TicketStatus


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _mins(a, b) -> float | None:
    a, b = _aware(a), _aware(b)
    if a is None or b is None:
        return None
    return max(0.0, (a - b).total_seconds() / 60.0)


def _pct(num: int, den: int) -> float | None:
    return round(num / den * 100, 1) if den else None


def _avg(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 1) if vals else None


def sla_performance(db: Session, client_ids: list[int] | None,
                    now: datetime | None = None, days: int = 90) -> dict:
    """Compute SLA attainment + timing over the last `days`. `client_ids=None`
    means all clients (staff). Considers tickets created in the window."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    q = db.query(SupportTicket).filter(SupportTicket.created_at >= since)
    if client_ids is not None:
        q = q.filter(SupportTicket.client_id.in_(client_ids))
    tickets = q.all()

    def blank():
        return {"tickets": 0, "responded": 0, "resolved": 0,
                "response_met": 0, "resolution_met": 0,
                "_resp_times": [], "_res_times": []}

    overall = blank()
    by_priority = {p: blank() for p in PRIORITIES}

    for t in tickets:
        buckets = (overall, by_priority.get(t.priority, overall))
        for b in buckets:
            b["tickets"] += 1
        # Response: did first response happen, and by the due time?
        if t.first_responded_at is not None:
            for b in buckets:
                b["responded"] += 1
                rt = _mins(t.first_responded_at, t.created_at)
                if rt is not None:
                    b["_resp_times"].append(rt)
            if t.first_response_due_at is None or \
               _aware(t.first_responded_at) <= _aware(t.first_response_due_at):
                for b in buckets:
                    b["response_met"] += 1
        # Resolution: only count tickets that actually reached resolved/closed.
        if t.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED) and t.resolved_at is not None:
            for b in buckets:
                b["resolved"] += 1
                rs = _mins(t.resolved_at, t.created_at)
                if rs is not None:
                    b["_res_times"].append(rs)
            if t.resolution_due_at is None or \
               _aware(t.resolved_at) <= _aware(t.resolution_due_at):
                for b in buckets:
                    b["resolution_met"] += 1

    def finalize(b: dict) -> dict:
        return {
            "tickets": b["tickets"],
            "responded": b["responded"],
            "resolved": b["resolved"],
            "response_attainment_pct": _pct(b["response_met"], b["responded"]),
            "resolution_attainment_pct": _pct(b["resolution_met"], b["resolved"]),
            "avg_response_minutes": _avg(b["_resp_times"]),
            "avg_resolution_minutes": _avg(b["_res_times"]),
        }

    return {
        "generated_at": now.isoformat(),
        "window_days": days,
        "overall": finalize(overall),
        "by_priority": {p: finalize(by_priority[p]) for p in PRIORITIES},
    }
