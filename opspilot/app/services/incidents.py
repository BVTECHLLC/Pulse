"""v1.19 Incident Intelligence — alert storms become ONE incident, not N tickets.

When a switch, site uplink, or hypervisor dies, every RMM floods the operator
with one alert per device — and Pulse's auto-ticketer would dutifully open one
ticket per alert. The correlator fixes the signal-to-noise problem at the root:

  * correlate(new_alerts): if >= STORM_MIN active alerts of the SAME kind exist
    for one client inside the correlation window, they become a single Incident
    ("Possible site outage at Acme — 6 devices offline together") with ONE
    urgent ticket (respecting the operator's auto-ticket setting) and one
    notification. Later same-kind alerts are absorbed into the open incident.
  * Alerts consumed by an incident are returned so the caller can EXCLUDE them
    from per-alert auto-ticketing — one event, one ticket.
  * sweep_resolutions(): when every member alert has resolved, the incident
    auto-resolves and the operator is told.

Deterministic — count + window thresholds, no AI in the grouping.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (Alert, AlertStatus, Client, Device, Incident, Notification,
                      SupportTicket)

STORM_MIN = 3          # same-kind active alerts to declare an incident
WINDOW_MIN = 15        # correlation window (minutes)

_TITLES = {
    "device_offline": "Possible site outage at {client} — {n} devices offline together",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _title(kind: str, client_name: str, n: int) -> str:
    tpl = _TITLES.get(kind, "Alert storm at {client} — {n} × {kind} together")
    return tpl.format(client=client_name, n=n, kind=kind)[:220]


def _open_incident_for(db: Session, client_id: int, kind: str) -> Incident | None:
    return (db.query(Incident)
            .filter(Incident.client_id == client_id, Incident.kind == kind,
                    Incident.status == "open")
            .order_by(Incident.id.desc()).first())


def correlate(db: Session, new_alerts: list[Alert],
              now: datetime | None = None) -> dict:
    """Heartbeat entrypoint (run BEFORE per-alert auto-ticketing). Groups storms
    into incidents. Commits. Returns {incidents: [...], consumed: set(alert_ids)}."""
    now = now or _utcnow()
    consumed: set[int] = set()
    touched: list[dict] = []
    if not new_alerts:
        return {"incidents": touched, "consumed": consumed}

    window_start = now - timedelta(minutes=WINDOW_MIN)
    # Consider each (client, kind) that produced fresh alerts this tick.
    combos = {(a.client_id, a.kind) for a in new_alerts if a.client_id}
    for client_id, kind in combos:
        actives = (db.query(Alert)
                   .filter(Alert.client_id == client_id, Alert.kind == kind,
                           Alert.status != AlertStatus.RESOLVED)
                   .all())
        recent = [a for a in actives
                  if _aware(a.first_seen) and _aware(a.first_seen) >= window_start]
        inc = _open_incident_for(db, client_id, kind)
        if inc is None and len(recent) < STORM_MIN:
            continue   # no storm (yet) — per-alert handling proceeds normally
        member_ids = sorted({a.id for a in recent} |
                            ({int(x) for x in (inc.alert_ids or [])} if inc else set()))
        client = db.get(Client, client_id)
        cname = client.name if client else f"client {client_id}"
        if inc is None:
            inc = Incident(client_id=client_id, kind=kind,
                           title=_title(kind, cname, len(member_ids)),
                           status="open", severity="critical",
                           alert_ids=member_ids, alert_count=len(member_ids),
                           first_seen=now, last_seen=now)
            db.add(inc)
            db.flush()
            # ONE ticket for the whole storm — honoring the auto-ticket setting.
            from . import proactive, sla
            cfg = proactive.get_config(db)
            if cfg["auto_ticket_enabled"]:
                hosts = [d.hostname for d in
                         db.query(Device).filter(Device.id.in_(
                             [a.device_id for a in recent if a.device_id])).all()]
                t = SupportTicket(
                    client_id=client_id,
                    subject=f"[Incident] {inc.title}"[:200],
                    body=(f"Pulse correlated {len(member_ids)} simultaneous '{kind}' alerts "
                          f"at {cname} into ONE incident (instead of {len(member_ids)} tickets).\n\n"
                          f"Devices: {', '.join(hosts[:20]) or 'n/a'}\n\n"
                          f"Likely a shared cause — switch, uplink, power, or host."),
                    priority="urgent", source_alert_id=member_ids[0],
                    created_at=now)
                sla.stamp_due_dates(db, t)
                db.add(t)
                db.flush()
                inc.ticket_id = t.id
                from . import autonomy
                autonomy.record(db, action_type="auto_ticket",
                                playbook=f"incident:{kind}", client_id=client_id,
                                ref_kind="ticket", ref_id=t.id, autonomous=True,
                                grade_after_minutes=60, now=now)
            db.add(Notification(client_id=client_id, target_user_id=None,
                                kind="incident", severity="critical",
                                message=(f"🌩 INCIDENT: {inc.title}. One ticket opened — "
                                         f"member alerts suppressed.")[:1000]))
            touched.append({"incident_id": inc.id, "client_id": client_id,
                            "kind": kind, "alerts": len(member_ids), "new": True,
                            "ticket_id": inc.ticket_id})
        else:
            inc.alert_ids = member_ids
            inc.alert_count = len(member_ids)
            inc.last_seen = now
            inc.title = _title(kind, cname, len(member_ids))
            touched.append({"incident_id": inc.id, "client_id": client_id,
                            "kind": kind, "alerts": len(member_ids), "new": False,
                            "ticket_id": inc.ticket_id})
        consumed |= {a.id for a in new_alerts
                     if a.client_id == client_id and a.kind == kind}
        db.commit()
    return {"incidents": touched, "consumed": consumed}


def sweep_resolutions(db: Session, now: datetime | None = None) -> list[dict]:
    """Close open incidents whose member alerts have ALL resolved. Commits."""
    now = now or _utcnow()
    closed = []
    for inc in db.query(Incident).filter(Incident.status == "open").all():
        ids = [int(x) for x in (inc.alert_ids or [])]
        if not ids:
            continue
        unresolved = (db.query(Alert)
                      .filter(Alert.id.in_(ids), Alert.status != AlertStatus.RESOLVED)
                      .count())
        if unresolved:
            continue
        inc.status = "resolved"
        inc.resolved_at = now
        client = db.get(Client, inc.client_id)
        db.add(Notification(client_id=inc.client_id, target_user_id=None,
                            kind="incident", severity="info",
                            message=(f"✅ Incident resolved: {inc.title} "
                                     f"({(client.name if client else '')}) — all "
                                     f"{inc.alert_count} member alerts cleared.")[:1000]))
        closed.append({"incident_id": inc.id, "client_id": inc.client_id})
    if closed:
        db.commit()
    return closed


def list_incidents(db: Session, user, *, status: str | None = None,
                   limit: int = 50) -> list[dict]:
    """Tenant-scoped incident list, newest first."""
    from ..core.deps import is_staff
    q = db.query(Incident)
    if not is_staff(user):
        q = q.filter(Incident.client_id == user.client_id)
    if status in ("open", "resolved"):
        q = q.filter(Incident.status == status)
    rows = q.order_by(Incident.id.desc()).limit(max(1, min(200, limit))).all()
    names = {c.id: c.name for c in db.query(Client).all()}
    return [{"id": i.id, "client_id": i.client_id, "client": names.get(i.client_id),
             "kind": i.kind, "title": i.title, "status": i.status,
             "severity": i.severity, "alert_count": i.alert_count,
             "ticket_id": i.ticket_id,
             "first_seen": _aware(i.first_seen).isoformat() if i.first_seen else None,
             "resolved_at": _aware(i.resolved_at).isoformat() if i.resolved_at else None}
            for i in rows]
