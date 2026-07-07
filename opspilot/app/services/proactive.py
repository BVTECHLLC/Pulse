"""v1.7 Proactive Ops — turn monitoring signal into action + visibility.

Two capabilities, both opt-in / read-only-safe:

  * auto_ticket: when a monitoring alert opens at or above a chosen severity,
    open ONE support ticket for that client automatically (deduped by the
    triggering alert id), so nothing slips through overnight. The monitoring
    engine already dedupes to one active alert per (device, kind), so acting on
    the freshly-opened alert list yields exactly one ticket per real incident.

  * site_health: a per-client rollup (devices, online, avg health, open alerts,
    worst device, pending patches) — the "how is each account doing?" glance an
    MSP owner wants on the overview.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (
    Alert, AlertSeverity, AlertStatus, Client, Device, PRIORITIES,
    SupportTicket, TicketComment, TicketStatus, User,
)
from . import secure_config, sla

PROVIDER = "proactive_ops"
_TRUTHY = {"1", "true", "yes", "on"}
_SEV_RANK = {"info": 0, "warning": 1, "critical": 2}


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    sev = cfg.get("min_severity") if cfg.get("min_severity") in _SEV_RANK else "critical"
    return {
        "auto_ticket_enabled": str(cfg.get("auto_ticket_enabled", "false")).lower() in _TRUTHY,
        "min_severity": sev,
    }


def save_config(db: Session, *, auto_ticket_enabled: bool | None = None,
                min_severity: str | None = None) -> dict:
    payload: dict[str, str] = {}
    if auto_ticket_enabled is not None:
        payload["auto_ticket_enabled"] = "true" if auto_ticket_enabled else "false"
    if min_severity in _SEV_RANK:
        payload["min_severity"] = min_severity
    if payload:
        secure_config.upsert_platform(db, PROVIDER, "Proactive Ops", "Automation", payload)
    return get_config(db)


def on_new_alerts(db: Session, new_alerts: list[Alert]) -> list[dict]:
    """Open a deduped ticket for each newly-opened alert at/above the configured
    severity. Called from the check-in path and the offline sweep. Safe no-op
    when disabled. Does NOT commit — the caller's transaction owns the commit,
    EXCEPT it flushes so ticket ids exist for the summary."""
    cfg = get_config(db)
    if not cfg["auto_ticket_enabled"] or not new_alerts:
        return []
    threshold = _SEV_RANK[cfg["min_severity"]]
    opened: list[dict] = []
    for alert in new_alerts:
        if _SEV_RANK.get(alert.severity.value, 0) < threshold:
            continue
        # Dedup: never open a second ticket for the same alert.
        exists = (db.query(SupportTicket.id)
                  .filter(SupportTicket.source_alert_id == alert.id).first())
        if exists:
            continue
        dev = db.get(Device, alert.device_id) if alert.device_id else None
        host = dev.hostname if dev else "device"
        priority = "urgent" if alert.severity == AlertSeverity.CRITICAL else "high"
        if priority not in PRIORITIES:
            priority = "high"
        t = SupportTicket(
            client_id=alert.client_id,
            subject=f"[Auto] {alert.kind} on {host}"[:200],
            body=(f"Automatically opened from a {alert.severity.value} monitoring alert:\n\n"
                  f"{alert.message}\n\nDevice: {host}"),
            priority=priority, source_alert_id=alert.id,
            created_at=datetime.now(timezone.utc))
        sla.stamp_due_dates(db, t)
        db.add(t)
        db.flush()
        db.add(TicketComment(ticket_id=t.id, author_email="pulse-monitor", author_role="system",
                             body=f"🔔 Auto-opened from alert #{alert.id} ({alert.severity.value}).",
                             internal=True))
        opened.append({"ticket_id": t.id, "alert_id": alert.id, "client_id": alert.client_id,
                       "priority": priority})
    return opened


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def site_health(db: Session, user: User) -> list[dict]:
    """Per-client health rollup. Staff see every client; a client user sees only
    their own company. Sorted worst-first so problems surface at the top."""
    from ..core.deps import is_staff
    now = datetime.now(timezone.utc)
    online_cutoff = now - timedelta(seconds=180)

    clients = db.query(Client)
    if not is_staff(user):
        clients = clients.filter(Client.id == user.client_id)
    out = []
    for cli in clients.all():
        devices = db.query(Device).filter(Device.client_id == cli.id).all()
        healths = [d.health_score for d in devices if d.health_score is not None]
        online = sum(1 for d in devices if _aware(d.last_checkin) and _aware(d.last_checkin) >= online_cutoff)
        worst = min((d for d in devices if d.health_score is not None),
                    key=lambda d: d.health_score, default=None)
        alerts = (db.query(Alert)
                  .filter(Alert.client_id == cli.id, Alert.status != AlertStatus.RESOLVED).all())
        sev_counts = {"critical": 0, "warning": 0, "info": 0}
        for a in alerts:
            sev_counts[a.severity.value] = sev_counts.get(a.severity.value, 0) + 1
        patches = sum((d.patches_pending or 0) for d in devices)
        avg_health = round(sum(healths) / len(healths)) if healths else None
        out.append({
            "client_id": cli.id, "client": cli.name,
            "devices": len(devices), "online": online, "offline": len(devices) - online,
            "avg_health": avg_health,
            "worst": ({"hostname": worst.hostname, "health": worst.health_score, "id": worst.id}
                      if worst else None),
            "alerts": {"total": len(alerts), **sev_counts},
            "patches_pending": patches,
        })
    # Worst first: most critical alerts, then lowest avg health.
    out.sort(key=lambda r: (-(r["alerts"]["critical"]), -(r["alerts"]["total"]),
                            (r["avg_health"] if r["avg_health"] is not None else 101)))
    return out
