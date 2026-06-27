"""Monitoring & alerting engine.

The engine is deliberately stateless and idempotent: given a device's current
telemetry (or last-seen time), it opens an alert when a condition is tripped and
auto-resolves it once the condition clears. There is at most one non-resolved
alert per (device, kind) at any time, so repeated evaluation never duplicates.

Two entry points:
  evaluate_device(db, device)  -> resource alerts, run on every agent check-in
  sweep_offline(db, ...)       -> offline detection, run on a schedule / on demand

Callers own the transaction (these helpers only stage changes; they don't commit)
EXCEPT sweep_offline, which commits because it's invoked standalone.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import (
    Alert, AlertPolicy, AlertSeverity, AlertStatus, Device,
    ALERT_AV_OFF, ALERT_DISK_FULL, ALERT_HIGH_CPU, ALERT_HIGH_RAM,
    ALERT_LOW_HEALTH, ALERT_OFFLINE, ALERT_PATCH_BEHIND,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _DefaultPolicy:
    """Built-in fallback when no AlertPolicy row exists."""
    disk_pct_max = 90.0
    cpu_pct_max = 95.0
    ram_pct_max = 95.0
    health_min = 60
    offline_minutes = 30
    alert_on_av_off = True
    alert_on_patch_behind = True


def get_policy(db: Session, client_id: int):
    """Resolve the effective policy: per-client row > global row > built-in."""
    p = db.query(AlertPolicy).filter(AlertPolicy.client_id == client_id).first()
    if not p:
        p = db.query(AlertPolicy).filter(AlertPolicy.client_id.is_(None)).first()
    return p or _DefaultPolicy


# --------------------------------------------------------------------------- #
# Open / resolve primitives (idempotent, dedup by device+kind)
# --------------------------------------------------------------------------- #
def _active_alert(db: Session, device_id: int, kind: str) -> Alert | None:
    return (db.query(Alert)
            .filter(Alert.device_id == device_id, Alert.kind == kind,
                    Alert.status != AlertStatus.RESOLVED)
            .first())


def _open(db: Session, device: Device, kind: str, severity: AlertSeverity,
          message: str, metric_value: float | None = None) -> None:
    existing = _active_alert(db, device.id, kind)
    now = _utcnow()
    if existing:
        # Refresh the live reading; keep its acknowledged status so techs aren't
        # re-pinged for an incident they've already seen.
        existing.last_seen = now
        existing.message = message
        existing.metric_value = metric_value
        return
    db.add(Alert(
        client_id=device.client_id, device_id=device.id, kind=kind,
        severity=severity, status=AlertStatus.ACTIVE, message=message,
        metric_value=metric_value, first_seen=now, last_seen=now,
    ))


def _resolve(db: Session, device_id: int, kind: str) -> None:
    a = _active_alert(db, device_id, kind)
    if a:
        a.status = AlertStatus.RESOLVED
        a.resolved_at = _utcnow()
        a.auto_resolved = True


# --------------------------------------------------------------------------- #
# Resource evaluation — run on each check-in
# --------------------------------------------------------------------------- #
def evaluate_device(db: Session, device: Device) -> None:
    """Open/resolve resource alerts from the device's current telemetry.
    Does NOT commit — the caller's check-in transaction owns the commit."""
    pol = get_policy(db, device.client_id)

    # A check-in means the device is online: clear any standing offline alert.
    _resolve(db, device.id, ALERT_OFFLINE)

    # Disk
    if device.disk_pct is not None and device.disk_pct >= pol.disk_pct_max:
        _open(db, device, ALERT_DISK_FULL, AlertSeverity.CRITICAL,
              f"Disk usage {device.disk_pct:.0f}% (>= {pol.disk_pct_max:.0f}%)",
              device.disk_pct)
    else:
        _resolve(db, device.id, ALERT_DISK_FULL)

    # CPU
    if device.cpu_pct is not None and device.cpu_pct >= pol.cpu_pct_max:
        _open(db, device, ALERT_HIGH_CPU, AlertSeverity.WARNING,
              f"CPU {device.cpu_pct:.0f}% (>= {pol.cpu_pct_max:.0f}%)", device.cpu_pct)
    else:
        _resolve(db, device.id, ALERT_HIGH_CPU)

    # RAM
    if device.ram_pct is not None and device.ram_pct >= pol.ram_pct_max:
        _open(db, device, ALERT_HIGH_RAM, AlertSeverity.WARNING,
              f"Memory {device.ram_pct:.0f}% (>= {pol.ram_pct_max:.0f}%)", device.ram_pct)
    else:
        _resolve(db, device.id, ALERT_HIGH_RAM)

    # Antivirus
    if pol.alert_on_av_off and device.av_status and "off" in device.av_status.lower():
        _open(db, device, ALERT_AV_OFF, AlertSeverity.CRITICAL,
              "Antivirus is reported OFF")
    else:
        _resolve(db, device.id, ALERT_AV_OFF)

    # Patch
    if pol.alert_on_patch_behind and device.patch_status and "behind" in device.patch_status.lower():
        _open(db, device, ALERT_PATCH_BEHIND, AlertSeverity.WARNING,
              "Patching is behind")
    else:
        _resolve(db, device.id, ALERT_PATCH_BEHIND)

    # Composite health score
    if device.health_score is not None and device.health_score < pol.health_min:
        _open(db, device, ALERT_LOW_HEALTH, AlertSeverity.WARNING,
              f"Health score {device.health_score} (< {pol.health_min})",
              float(device.health_score))
    else:
        _resolve(db, device.id, ALERT_LOW_HEALTH)


# --------------------------------------------------------------------------- #
# Offline detection — run on a schedule or on demand
# --------------------------------------------------------------------------- #
def sweep_offline(db: Session, client_id: int | None = None) -> dict:
    """Open offline alerts for devices that haven't checked in within their
    policy window; resolve them once a device reports again (handled in
    evaluate_device). Commits its own transaction. Returns a small summary."""
    q = db.query(Device)
    if client_id is not None:
        q = q.filter(Device.client_id == client_id)

    opened = 0
    checked = 0
    now = _utcnow()
    for dev in q.all():
        checked += 1
        pol = get_policy(db, dev.client_id)
        cutoff = now - timedelta(minutes=pol.offline_minutes)
        last = dev.last_checkin
        # SQLite returns naive datetimes; normalize so the comparison is safe.
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        # Treat a never-seen device as offline too (it enrolled but never reported).
        is_offline = last is None or last < cutoff
        if is_offline:
            if not _active_alert(db, dev.id, ALERT_OFFLINE):
                opened += 1
            mins = int((now - last).total_seconds() // 60) if last else None
            msg = (f"No check-in for {mins} min (threshold {pol.offline_minutes} min)"
                   if mins is not None else "Device has never checked in")
            _open(db, dev, ALERT_OFFLINE, AlertSeverity.CRITICAL, msg,
                  float(mins) if mins is not None else None)
    db.commit()
    return {"devices_checked": checked, "offline_opened": opened}
