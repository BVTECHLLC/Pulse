"""v1.12 Proactive Copilot briefing — Pulse tells you what needs doing each day.

Instead of waiting to be asked, the copilot assembles the morning's priorities
(critical patches pending, SLA breaches, offline devices, overdue A/R, weakest
security grade) and — once per day — drops an action-oriented briefing into
notifications (and returns it on demand). When Claude is connected it writes the
narrative; otherwise a clean template is used.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Device, Notification, SupportTicket, TicketStatus
from . import ai, secure_config, sla

PROVIDER = "copilot_briefing"
POST_HOUR_UTC = 13   # ~8am Central — land the briefing before the workday


def gather(db: Session, now: datetime | None = None) -> dict:
    """Deterministic snapshot of what needs attention (no AI needed)."""
    now = now or datetime.now(timezone.utc)
    stats: dict = {}
    try:
        from . import patching
        fl = patching.fleet(db)
        stats["patch_devices"] = fl["totals"]["devices"]
        stats["patch_critical"] = fl["totals"]["critical"]
    except Exception:  # noqa: BLE001
        pass
    try:
        from datetime import timedelta
        cutoff = now - timedelta(minutes=30)
        total = db.query(Device).count()
        offline = db.query(Device).filter((Device.last_checkin.is_(None)) |
                                          (Device.last_checkin < cutoff)).count()
        stats["devices_total"] = total
        stats["devices_offline"] = offline
    except Exception:  # noqa: BLE001
        pass
    try:
        opens = (db.query(SupportTicket)
                 .filter(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
                 .all())
        stats["tickets_open"] = len(opens)
        stats["sla_breached"] = sum(1 for t in opens if sla.evaluate(t, now)["breached"])
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import ar_aging
        ag = ar_aging.aging_report(db, now)
        stats["ar_overdue"] = ag.get("overdue_total")
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import foresight
        tr = foresight.top_risk(db, now)
        if tr:
            stats["top_prediction"] = f"{tr['hostname']}: {tr['detail']}"
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import psa_intel
        ci = psa_intel.contract_intel(db, now)
        stats["contracts_underwater"] = ci["totals"]["underwater"]
        stats["renewals_soon"] = ci["totals"]["renewals_soon"]
        lk = psa_intel.revenue_leakage(db, now)
        stats["recoverable"] = lk["total_recoverable"]
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..models import Incident
        stats["incidents_open"] = (db.query(Incident)
                                   .filter(Incident.status == "open").count())
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import autonomy
        rep = autonomy.report(db, days=1, now=now)
        stats["auto_actions_24h"] = rep["autonomous_actions"]
        if rep["success_rate"] is not None:
            stats["auto_success_pct"] = int(rep["success_rate"] * 100)
        stats["autonomy_suspended"] = len(rep["suspended_combos"])
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import posture
        port = posture.portfolio(db, now)
        graded = [p for p in port if p.get("score") is not None]
        if graded:
            worst = graded[0]
            stats["worst_client"] = worst.get("client_name")
            stats["worst_grade"] = worst.get("grade")
    except Exception:  # noqa: BLE001
        pass
    return stats


def _template(stats: dict) -> str:
    bits = []
    if stats.get("incidents_open"):
        bits.append(f"🌩 {stats['incidents_open']} ACTIVE incident(s) — correlated outages/storms. "
                    f"Handle these first (ask me 'any outages right now?').")
    if stats.get("patch_critical"):
        bits.append(f"🔴 {stats['patch_critical']} critical patch(es) pending across "
                    f"{stats.get('patch_devices', 0)} device(s) — approve them (Devices → Fleet Patch, "
                    f"or ask me 'approve critical patches for <client>').")
    if stats.get("sla_breached"):
        bits.append(f"⏰ {stats['sla_breached']} ticket(s) are breaching SLA — reassign or resolve.")
    if stats.get("devices_offline"):
        bits.append(f"📴 {stats['devices_offline']} of {stats.get('devices_total', 0)} devices are offline.")
    if stats.get("ar_overdue"):
        bits.append(f"💸 ${stats['ar_overdue']:,.0f} in invoices are overdue — send reminders.")
    if stats.get("top_prediction"):
        bits.append(f"🔮 Predicted: {stats['top_prediction']}")
    if stats.get("recoverable"):
        bits.append(f"🧾 ${stats['recoverable']:,.0f} in earned-but-unbilled revenue is recoverable "
                    f"— ask me to 'find revenue leakage'.")
    if stats.get("contracts_underwater"):
        bits.append(f"📉 {stats['contracts_underwater']} contract(s) are running underwater "
                    f"— review margins before renewal.")
    if stats.get("renewals_soon"):
        bits.append(f"🔁 {stats['renewals_soon']} contract(s) renew soon — prep pricing.")
    if stats.get("auto_actions_24h"):
        rate = f" ({stats['auto_success_pct']}% success)" if stats.get("auto_success_pct") is not None else ""
        bits.append(f"🤖 Pulse handled {stats['auto_actions_24h']} action(s) autonomously "
                    f"in the last day{rate}.")
    if stats.get("autonomy_suspended"):
        bits.append(f"🛑 {stats['autonomy_suspended']} automation(s) are suspended after "
                    f"failed runs — review the Autonomy ledger.")
    if stats.get("worst_grade") and stats["worst_grade"] not in ("A", "A+", "A-"):
        bits.append(f"🛡️ {stats.get('worst_client')} has the weakest security grade "
                    f"({stats['worst_grade']}) — review their scorecard.")
    if not bits:
        return "✅ All clear this morning — no critical patches, SLA breaches, offline devices, or overdue invoices. Nice."
    return "Here's what needs your attention today:\n\n- " + "\n- ".join(bits)


def build(db: Session, now: datetime | None = None) -> dict:
    """Assemble the briefing narrative + stats."""
    now = now or datetime.now(timezone.utc)
    stats = gather(db, now)
    narrative = _template(stats)
    if ai.enabled():
        facts = "\n".join(f"{k}: {v}" for k, v in stats.items())
        try:
            narrative = ai.complete(
                "You are Pulse Copilot writing an MSP owner's short morning briefing. "
                "Prioritize by business risk. Be specific and action-oriented; each line a "
                "concrete next step. Max 6 short bullet lines. If nothing is wrong, say so briefly.",
                f"Today's operational stats:\n{facts}\n\nWrite the briefing.",
                max_tokens=400)
        except Exception:  # noqa: BLE001
            narrative = _template(stats)
    return {"narrative": narrative, "stats": stats, "generated_at": now.isoformat()}


def maybe_post(db: Session, now: datetime | None = None) -> dict:
    """Heartbeat entrypoint: post the briefing once per day after POST_HOUR_UTC."""
    now = now or datetime.now(timezone.utc)
    if now.hour < POST_HOUR_UTC:
        return {"posted": False, "reason": "too_early"}
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    today = now.date().isoformat()
    if cfg.get("last_date") == today:
        return {"posted": False, "reason": "already_today"}
    brief = build(db, now)
    try:
        db.add(Notification(client_id=None, target_user_id=None, kind="briefing",
                            severity="info",
                            message=("☀️ Morning briefing — " + brief["narrative"])[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    secure_config.upsert_platform(db, PROVIDER, "Copilot Briefing", "Automation",
                                  {"last_date": today})
    return {"posted": True, "date": today, "stats": brief["stats"]}
