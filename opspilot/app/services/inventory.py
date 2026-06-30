"""v0.68 Software inventory + fleet patch compliance.

Fleet-wide read aggregations over the agent-reported `DeviceSoftware` and
`DevicePatch` tables:

  * `software_fleet` — every installed title with how many devices/clients/
    versions carry it (license reconciliation + "who runs package X?").
  * `software_devices` — the exact devices running a given title (vuln response).
  * `patch_compliance` — per-client + fleet rollup: % of reporting devices fully
    patched, total pending, severity mix, worst devices, and the most-common
    pending updates across the fleet.

Pairs with auto-remediation (v0.65): a `patch_behind` rule turns a non-compliant
device into an auto-queued patch run. Pure read-only — no schema change.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Client, Device, DevicePatch, DeviceSoftware


def software_fleet(db: Session, client_id: int | None = None, q: str | None = None,
                   limit: int = 200) -> list[dict]:
    """Installed titles aggregated across the fleet (or one client)."""
    query = (db.query(
                DeviceSoftware.name,
                func.count(func.distinct(DeviceSoftware.device_id)).label("devices"),
                func.count(func.distinct(DeviceSoftware.client_id)).label("clients"),
                func.count(func.distinct(DeviceSoftware.version)).label("versions"),
                func.max(DeviceSoftware.publisher).label("publisher"))
             .group_by(DeviceSoftware.name))
    if client_id:
        query = query.filter(DeviceSoftware.client_id == client_id)
    if q and q.strip():
        query = query.filter(DeviceSoftware.name.ilike(f"%{q.strip()}%"))
    rows = (query.order_by(func.count(func.distinct(DeviceSoftware.device_id)).desc(),
                           DeviceSoftware.name)
            .limit(max(1, min(limit, 1000))).all())
    return [{"name": n, "devices": d, "clients": cl, "versions": v, "publisher": pub}
            for (n, d, cl, v, pub) in rows]


def software_devices(db: Session, name: str, client_id: int | None = None) -> list[dict]:
    """Which devices run a given title — the vuln-response drill-down."""
    rows = (db.query(DeviceSoftware, Device)
            .join(Device, Device.id == DeviceSoftware.device_id)
            .filter(DeviceSoftware.name == name))
    if client_id:
        rows = rows.filter(DeviceSoftware.client_id == client_id)
    rows = rows.order_by(Device.hostname).all()
    return [{"device_id": d.id, "hostname": d.hostname, "client_id": d.client_id,
             "version": sw.version, "publisher": sw.publisher} for (sw, d) in rows]


def _compliance_block(devices: list[Device]) -> dict:
    reporting = [d for d in devices if d.patches_pending is not None]
    fully = sum(1 for d in reporting if (d.patches_pending or 0) == 0)
    pending_total = sum((d.patches_pending or 0) for d in reporting)
    pct = round(fully / len(reporting) * 100) if reporting else 0
    return {"reporting": len(reporting), "compliant": fully,
            "compliance_pct": pct, "pending_total": pending_total}


def patch_compliance(db: Session, client_id: int | None = None) -> dict:
    """Fleet (or single-client) patch-compliance rollup + worst offenders."""
    dq = db.query(Device)
    if client_id:
        dq = dq.filter(Device.client_id == client_id)
    devices = dq.all()
    fleet = _compliance_block(devices)

    # Per-client breakdown (only meaningful in the fleet view).
    by_client = []
    if not client_id:
        names = {c.id: c.name for c in db.query(Client).all()}
        grouped: dict[int, list[Device]] = {}
        for d in devices:
            grouped.setdefault(d.client_id, []).append(d)
        for cid, devs in grouped.items():
            blk = _compliance_block(devs)
            if blk["reporting"]:
                by_client.append({"client_id": cid, "client_name": names.get(cid), **blk})
        by_client.sort(key=lambda r: (r["compliance_pct"], -r["pending_total"]))

    # Severity mix across pending updates.
    sev_q = db.query(DevicePatch.severity, func.count(DevicePatch.id))
    if client_id:
        sev_q = sev_q.filter(DevicePatch.client_id == client_id)
    by_severity = {sev or "other": cnt for sev, cnt in sev_q.group_by(DevicePatch.severity).all()}

    # Most-common pending updates across the fleet (by name+KB, device spread).
    top_q = (db.query(DevicePatch.name, DevicePatch.kb, DevicePatch.severity,
                      func.count(func.distinct(DevicePatch.device_id)).label("devices"))
             .group_by(DevicePatch.name, DevicePatch.kb, DevicePatch.severity))
    if client_id:
        top_q = top_q.filter(DevicePatch.client_id == client_id)
    top = top_q.order_by(func.count(func.distinct(DevicePatch.device_id)).desc()).limit(25).all()
    top_pending = [{"name": n, "kb": kb, "severity": sev, "devices": d}
                   for (n, kb, sev, d) in top]

    # Worst devices by pending count.
    worst = [d for d in devices if (d.patches_pending or 0) > 0]
    worst.sort(key=lambda d: d.patches_pending or 0, reverse=True)
    worst_devices = [{"device_id": d.id, "hostname": d.hostname, "client_id": d.client_id,
                      "pending": d.patches_pending or 0} for d in worst[:25]]

    return {"fleet": fleet, "by_client": by_client, "by_severity": by_severity,
            "top_pending": top_pending, "worst_devices": worst_devices}
