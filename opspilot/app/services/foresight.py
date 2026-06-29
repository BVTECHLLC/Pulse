"""v0.33 Predictive Foresight — turn telemetry history into the future.

RMM tools tell you a disk is 80% full. An *elite* tool tells you it will be full
on Thursday. This engine reads each device's check-in history and projects where
the metrics are heading: days-until-disk-full (linear trend), resource pressure
trajectory (improving / stable / degrading), and a health trend. It's pure math
on data we already collect — no agent changes, no new tables, no external calls.

The same projections feed the Action Center so "disk full in ~5 days" shows up
as a ranked action *before* it becomes a 2 a.m. outage.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Device, DeviceCheckin

# Only project when we have enough signal to be honest about it.
MIN_POINTS = 4
MIN_SPAN_HOURS = 2.0
# Horizons we consider actionable (ignore "full in 400 days" noise).
DISK_HORIZON_DAYS = 45
DISK_WARN_DAYS = 14          # within this → high severity
DISK_CRIT_DAYS = 3           # within this → critical
LOOKBACK_DAYS = 21           # window of history we trend over


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _linfit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Ordinary least squares. Returns (slope, intercept) for y = slope*x + b,
    or None if x has no variance."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-9:
        return None
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    slope = sxy / sxx
    return slope, my - slope * mx


def _trend_label(slope_per_day: float, scale: float = 1.0) -> str:
    """Classify a per-day slope into a human trajectory. `scale` is the unit
    'meaningful change per day' (e.g. ~2 points/day for utilization)."""
    if slope_per_day <= -scale:
        return "improving"
    if slope_per_day >= scale:
        return "degrading"
    return "stable"


def forecast_device(db: Session, device: Device, now: datetime | None = None) -> dict:
    """Project a single device's near future from its check-in history."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS)
    rows = (db.query(DeviceCheckin)
            .filter(DeviceCheckin.device_id == device.id, DeviceCheckin.ts >= since)
            .order_by(DeviceCheckin.ts.asc()).all())

    out = {
        "device_id": device.id, "hostname": device.hostname, "client_id": device.client_id,
        "points": len(rows), "enough_data": False,
        "disk": None, "ram": None, "cpu": None, "health": None,
        "risks": [],
    }
    pts = [(_aware(r.ts), r) for r in rows if r.ts is not None]
    if len(pts) < MIN_POINTS:
        return out
    t0 = pts[0][0]
    span_h = (pts[-1][0] - t0).total_seconds() / 3600.0
    if span_h < MIN_SPAN_HOURS:
        return out
    out["enough_data"] = True

    def series(attr):
        xs, ys = [], []
        for ts, r in pts:
            v = getattr(r, attr)
            if v is not None:
                xs.append((ts - t0).total_seconds() / 86400.0)  # days since t0
                ys.append(float(v))
        return xs, ys

    # ---- Disk: the headline projection (days until full) ------------------
    dxs, dys = series("disk_pct")
    if len(dys) >= MIN_POINTS:
        fit = _linfit(dxs, dys)
        cur = dys[-1]
        block = {"current": round(cur, 1), "slope_per_day": None,
                 "days_to_full": None, "projected_full_date": None,
                 "trend": "stable"}
        if fit:
            slope, _b = fit
            block["slope_per_day"] = round(slope, 2)
            block["trend"] = _trend_label(slope, scale=1.0)
            if slope > 0.05 and cur < 100:
                days = (100.0 - cur) / slope
                if 0 < days <= DISK_HORIZON_DAYS:
                    block["days_to_full"] = round(days, 1)
                    block["projected_full_date"] = (now + timedelta(days=days)).isoformat()
                    sev = ("critical" if days <= DISK_CRIT_DAYS
                           else "high" if days <= DISK_WARN_DAYS else "medium")
                    out["risks"].append({
                        "kind": "disk_fill", "severity": sev, "metric": "disk_pct",
                        "days": round(days, 1),
                        "detail": f"Disk trending +{slope:.1f}%/day — full in ~{days:.0f} day(s) "
                                  f"(now {cur:.0f}%).",
                    })
        out["disk"] = block

    # ---- RAM / CPU pressure trajectory ------------------------------------
    for attr, key in (("ram_pct", "ram"), ("cpu_pct", "cpu")):
        xs, ys = series(attr)
        if len(ys) >= MIN_POINTS:
            fit = _linfit(xs, ys)
            cur = ys[-1]
            blk = {"current": round(cur, 1), "slope_per_day": None, "trend": "stable"}
            if fit:
                slope, _b = fit
                blk["slope_per_day"] = round(slope, 2)
                blk["trend"] = _trend_label(slope, scale=2.0)
                # Sustained, rising pressure that's already high is worth flagging.
                if slope >= 2.0 and cur >= 85:
                    out["risks"].append({
                        "kind": f"{key}_pressure", "severity": "medium", "metric": attr,
                        "days": None,
                        "detail": f"{key.upper()} climbing (+{slope:.1f}%/day) and already "
                                  f"{cur:.0f}% — investigate before it saturates.",
                    })
            out[key] = blk

    # ---- Health trajectory ------------------------------------------------
    hxs, hys = series("health_score")
    if len(hys) >= MIN_POINTS:
        fit = _linfit(hxs, hys)
        cur = hys[-1]
        blk = {"current": round(cur), "slope_per_day": None, "trend": "stable"}
        if fit:
            slope, _b = fit
            blk["slope_per_day"] = round(slope, 2)
            blk["trend"] = _trend_label(slope, scale=1.5)
            if slope <= -1.5 and cur < 80:
                out["risks"].append({
                    "kind": "health_decline", "severity": "medium", "metric": "health_score",
                    "days": None,
                    "detail": f"Health declining ({slope:.1f}/day), now {cur:.0f} — "
                              f"degrading endpoint.",
                })
        out["health"] = blk

    return out


def fleet_risks(db: Session, client_ids: list[int] | None, now: datetime | None = None,
                limit_devices: int = 500) -> list[dict]:
    """Run forecasts across a (scoped) set of devices and return only the
    actionable risks, each tagged with its device. Used by the Action Center.
    `client_ids=None` means all clients (staff, unfiltered)."""
    now = now or datetime.now(timezone.utc)
    q = db.query(Device)
    if client_ids is not None:
        q = q.filter(Device.client_id.in_(client_ids))
    devices = q.limit(limit_devices).all()
    risks: list[dict] = []
    for d in devices:
        fc = forecast_device(db, d, now)
        for r in fc["risks"]:
            risks.append({**r, "device_id": d.id, "hostname": d.hostname,
                          "client_id": d.client_id})
    return risks
