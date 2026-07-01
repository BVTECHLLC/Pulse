"""v0.84 Public status page.

A branded, shareable uptime/incident page every MSP can hand to its clients —
the transparency layer that SuperOps/Statuspage sell, but native and
white-labelled. The owner runs incidents through investigating→identified→
monitoring→resolved; the public endpoint exposes only display-safe values (no
client names, no counts, no internals) and derives a 90-day uptime figure from
the recorded downtime of major/critical incidents.

Config lives on the ``status_page`` platform vault row (public-safe: an enable
flag, a headline, an intro line). Disabled by default so nothing is exposed
until the owner opts in.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import StatusIncident
from . import secure_config

PROVIDER = "status_page"

STATUSES = ("investigating", "identified", "monitoring", "resolved")
IMPACTS = ("none", "minor", "major", "critical")

# Ordering used to pick the *worst* active incident for the overall banner.
_IMPACT_RANK = {"none": 0, "minor": 1, "major": 2, "critical": 3}
# Impact → the overall banner state it drives while unresolved.
_IMPACT_STATE = {
    "none": "operational",
    "minor": "degraded",
    "major": "partial_outage",
    "critical": "major_outage",
}
# Only these impacts count as real "downtime" for the uptime math.
_DOWNTIME_IMPACTS = {"major", "critical"}
_UPTIME_WINDOW_DAYS = 90


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC so math is safe."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _defaults() -> dict:
    return {"enabled": False, "headline": "Service Status",
            "intro": "Live status of the systems we manage for you."}


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    out = _defaults()
    if "enabled" in cfg:
        out["enabled"] = bool(cfg["enabled"])
    for k in ("headline", "intro"):
        v = cfg.get(k)
        if v not in (None, ""):
            out[k] = str(v)[:300]
    return out


def save_config(db: Session, fields: dict) -> dict:
    cur = get_config(db)
    payload = dict(cur)
    if "enabled" in (fields or {}):
        payload["enabled"] = bool(fields["enabled"])
    for k in ("headline", "intro"):
        if fields.get(k) is not None:
            payload[k] = str(fields[k])[:300]
    secure_config.upsert_platform(db, PROVIDER, "Status Page", "Public status", payload)
    return get_config(db)


def _serialize(inc: StatusIncident, *, public: bool) -> dict:
    started = _aware(inc.started_at)
    resolved = _aware(inc.resolved_at)
    out = {
        "id": inc.id,
        "title": inc.title,
        "status": inc.status,
        "impact": inc.impact,
        "body": inc.body or "",
        "started_at": started.isoformat() if started else None,
        "resolved_at": resolved.isoformat() if resolved else None,
        "resolved": inc.status == "resolved",
    }
    if not public:
        out["created_by_user_id"] = inc.created_by_user_id
    return out


def list_incidents(db: Session, *, limit: int = 50) -> list[dict]:
    rows = db.execute(
        select(StatusIncident).order_by(StatusIncident.started_at.desc()).limit(limit)
    ).scalars().all()
    return [_serialize(r, public=False) for r in rows]


def _overall(active: list[StatusIncident]) -> str:
    if not active:
        return "operational"
    worst = max(active, key=lambda i: _IMPACT_RANK.get(i.impact, 1))
    return _IMPACT_STATE.get(worst.impact, "degraded")


def _uptime_pct(db: Session) -> float:
    """90-day uptime derived from recorded downtime of major/critical incidents.
    Overlapping windows are merged so a busy day can't double-count minutes."""
    now = _utcnow()
    window_start = now - timedelta(days=_UPTIME_WINDOW_DAYS)
    total_minutes = _UPTIME_WINDOW_DAYS * 24 * 60

    rows = db.execute(
        select(StatusIncident).where(StatusIncident.impact.in_(tuple(_DOWNTIME_IMPACTS)))
    ).scalars().all()

    windows: list[tuple[datetime, datetime]] = []
    for inc in rows:
        start = max(_aware(inc.started_at) or window_start, window_start)
        end = _aware(inc.resolved_at) or now      # ongoing incident counts up to now
        end = min(end, now)
        if end <= start:
            continue
        windows.append((start, end))

    # Merge overlaps before summing.
    down = 0.0
    merged: list[list[datetime]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for start, end in merged:
        down += (end - start).total_seconds() / 60.0

    up = max(0.0, total_minutes - down)
    return round(up / total_minutes * 100, 3) if total_minutes else 100.0


def public_view(db: Session) -> dict | None:
    """Display-safe payload for the unauthenticated /status page. Returns None
    when the owner hasn't enabled the page (route turns that into a 404)."""
    cfg = get_config(db)
    if not cfg.get("enabled"):
        return None
    rows = db.execute(
        select(StatusIncident).order_by(StatusIncident.started_at.desc()).limit(25)
    ).scalars().all()
    active = [r for r in rows if r.status != "resolved"]
    return {
        "headline": cfg["headline"],
        "intro": cfg["intro"],
        "overall": _overall(active),
        "uptime_90d": _uptime_pct(db),
        "active_incidents": [_serialize(r, public=True) for r in active],
        "recent_incidents": [_serialize(r, public=True) for r in rows],
        "generated_at": _utcnow().isoformat(),
    }
