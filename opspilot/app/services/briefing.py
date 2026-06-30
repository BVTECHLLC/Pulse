"""v0.55 Morning briefing — a cross-business "what needs attention" digest.

Aggregates the whole platform into one plaintext summary: active alerts,
SLA-at-risk tickets, offline devices, failing integrations, overdue invoices,
fresh CRM leads, and contracts about to expire. Used by the `send_digest`
automation action (email it on a schedule) and previewable in the UI.

Each section is best-effort (wrapped) so a missing/empty area never breaks the
whole briefing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build(db: Session) -> dict:
    """Return a structured briefing (counts + highlights). Never raises."""
    now = datetime.now(timezone.utc)
    out: dict = {"generated_at": now.isoformat(), "sections": []}

    def section(title, fn):
        try:
            data = fn()
        except Exception as e:  # noqa: BLE001
            data = {"count": 0, "lines": [f"(unavailable: {str(e)[:60]})"]}
        out["sections"].append({"title": title, **data})

    def alerts():
        from ..models import Alert, AlertStatus
        rows = (db.query(Alert).filter(Alert.status != AlertStatus.RESOLVED)
                .order_by(Alert.severity.desc()).limit(8).all())
        total = db.query(Alert).filter(Alert.status != AlertStatus.RESOLVED).count()
        return {"count": total, "lines": [f"[{a.severity.value if hasattr(a.severity,'value') else a.severity}] "
                                          f"{(a.message or a.kind or '')[:80]}" for a in rows]}

    def sla_risk():
        from ..models import SupportTicket, TicketStatus
        from . import sla
        opens = (db.query(SupportTicket)
                 .filter(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS])).all())
        risky = []
        for t in opens:
            s = sla.evaluate(t, now)
            if s.get("breached"):
                risky.append(f"#{t.id} {t.subject[:60]} — BREACHED")
        return {"count": len(risky), "lines": risky[:8]}

    def offline():
        from ..models import Device
        cutoff = now - timedelta(minutes=30)
        devs = db.query(Device).all()
        off = [d for d in devs if d.last_checkin and _aware(d.last_checkin) < cutoff]
        return {"count": len(off), "lines": [f"{d.hostname} (last seen {_aware(d.last_checkin):%b %d %H:%M})"
                                             for d in off[:8]]}

    def integrations():
        from ..models import IntegrationConnection
        bad = (db.query(IntegrationConnection)
               .filter(IntegrationConnection.client_id.is_(None),
                       IntegrationConnection.last_health_ok.is_(False)).all())
        return {"count": len(bad), "lines": [f"{c.name}: {(c.last_health_error or 'failing')[:70]}" for c in bad]}

    def overdue_invoices():
        from ..models import Invoice, InvoiceStatus
        rows = (db.query(Invoice)
                .filter(Invoice.status == InvoiceStatus.SENT, Invoice.due_at.isnot(None)).all())
        od = [i for i in rows if _aware(i.due_at) < now]
        return {"count": len(od), "lines": [f"{i.number or ('INV-'+str(i.id))} — ${i.total:.0f} overdue" for i in od[:8]]}

    def new_leads():
        from ..models import CrmContact
        rows = db.query(CrmContact).filter(CrmContact.status == "new").all()
        return {"count": len(rows), "lines": [f"{c.name} ({c.company or '—'})" for c in rows[:8]]}

    def expiring_contracts():
        from ..models import Contract
        soon = now + timedelta(days=30)
        rows = db.query(Contract).filter(Contract.end_date.isnot(None)).all()
        exp = [c for c in rows if c.end_date and now <= _aware(c.end_date) <= soon]
        return {"count": len(exp), "lines": [f"{c.name} ends {_aware(c.end_date):%b %d}" for c in exp[:8]]}

    section("🚨 Active alerts", alerts)
    section("⏰ SLA breaches", sla_risk)
    section("🔌 Failing integrations", integrations)
    section("💻 Offline devices", offline)
    section("💸 Overdue invoices", overdue_invoices)
    section("🤝 New leads", new_leads)
    section("📄 Contracts expiring (30d)", expiring_contracts)
    out["attention_total"] = sum(s["count"] for s in out["sections"])
    return out


def render_text(brief: dict) -> str:
    """Plaintext rendering of a briefing for email."""
    lines = [f"BVTech OpsPilot — Morning Briefing",
             f"{brief['attention_total']} items need attention.", ""]
    for s in brief["sections"]:
        lines.append(f"{s['title']}: {s['count']}")
        for ln in s.get("lines", []):
            lines.append(f"   • {ln}")
        lines.append("")
    lines.append("— Pulse")
    return "\n".join(lines)
