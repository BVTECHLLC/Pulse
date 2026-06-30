"""v0.3 monitoring routes: alerts (list / acknowledge / resolve), alert
policies (thresholds), and the offline-detection sweep.

Scope rules mirror the rest of the app: staff see everything; client users see
only their own client's alerts and may NOT mutate them or edit policies."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import case
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import Alert, AlertPolicy, AlertSeverity, AlertStatus, Device, Role, User
from ...services import audit, automation, monitoring

router = APIRouter(prefix="/api", tags=["monitoring"])

# Most-severe-first ranking (the stored enum string would sort alphabetically).
_SEVERITY_RANK = case(
    (Alert.severity == AlertSeverity.CRITICAL, 0),
    (Alert.severity == AlertSeverity.WARNING, 1),
    (Alert.severity == AlertSeverity.INFO, 2),
    else_=3,
)


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(a: Alert, hostname: str | None) -> dict:
    return {
        "id": a.id, "client_id": a.client_id, "device_id": a.device_id,
        "hostname": hostname, "kind": a.kind, "severity": a.severity.value,
        "status": a.status.value, "message": a.message, "metric_value": a.metric_value,
        "first_seen": a.first_seen.isoformat() if a.first_seen else None,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "auto_resolved": a.auto_resolved,
    }


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
@router.get("/alerts")
def list_alerts(status_filter: str | None = None, client_id: int | None = None,
                limit: int = 200, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    """Default view is non-resolved alerts (active + acknowledged); pass
    status_filter=resolved (or any specific status) to see history."""
    limit = max(1, min(limit, 500))
    q = db.query(Alert)
    if is_staff(user):
        if client_id:
            q = q.filter(Alert.client_id == client_id)
    else:
        q = q.filter(Alert.client_id == user.client_id)

    if status_filter:
        q = q.filter(Alert.status == status_filter)
    else:
        q = q.filter(Alert.status != AlertStatus.RESOLVED)

    rows = q.order_by(_SEVERITY_RANK.asc(), Alert.last_seen.desc()).limit(limit).all()
    # Resolve hostnames in one pass.
    dev_ids = {r.device_id for r in rows if r.device_id}
    hosts = {d.id: d.hostname for d in db.query(Device).filter(Device.id.in_(dev_ids)).all()} if dev_ids else {}
    return [_serialize(r, hosts.get(r.device_id)) for r in rows]


@router.get("/alerts/summary")
def alerts_summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Counts of non-resolved alerts by severity — feeds dashboard badges."""
    q = db.query(Alert).filter(Alert.status != AlertStatus.RESOLVED)
    if not is_staff(user):
        q = q.filter(Alert.client_id == user.client_id)
    rows = q.all()
    out = {"total": len(rows), "critical": 0, "warning": 0, "info": 0, "acknowledged": 0}
    for r in rows:
        out[r.severity.value] = out.get(r.severity.value, 0) + 1
        if r.status == AlertStatus.ACKNOWLEDGED:
            out["acknowledged"] += 1
    return out


@router.post("/alerts/{alert_id}/ack")
def acknowledge_alert(alert_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    if a.status == AlertStatus.RESOLVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Alert already resolved")
    a.status = AlertStatus.ACKNOWLEDGED
    a.acknowledged_at = datetime.now(timezone.utc)
    a.acknowledged_by_user_id = user.id
    db.commit()
    audit.record(db, action="alert.ack", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="alert", target_id=str(a.id),
                 client_id=a.client_id, ip=_ip(request), detail=f"kind={a.kind}")
    return {"ok": True, "status": a.status.value}


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Manual resolve. The engine may reopen it on the next check-in if the
    underlying condition still holds — that's intentional."""
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    if a.status == AlertStatus.RESOLVED:
        return {"ok": True, "status": a.status.value}
    a.status = AlertStatus.RESOLVED
    a.resolved_at = datetime.now(timezone.utc)
    a.auto_resolved = False
    db.commit()
    audit.record(db, action="alert.resolve", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="alert", target_id=str(a.id),
                 client_id=a.client_id, ip=_ip(request), detail=f"kind={a.kind}")
    return {"ok": True, "status": a.status.value}


class BulkAlertAction(BaseModel):
    ids: list[int]
    action: str   # "ack" | "resolve"


@router.post("/alerts/bulk")
def bulk_alert_action(body: BulkAlertAction, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Acknowledge or resolve many alerts in one call — triage a storm in one
    click. Skips already-resolved (ack) and missing ids; returns per-id results."""
    if body.action not in ("ack", "resolve"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action must be 'ack' or 'resolve'")
    if not body.ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no ids given")
    now = datetime.now(timezone.utc)
    changed, skipped = [], []
    for aid in body.ids[:500]:
        a = db.get(Alert, aid)
        if not a:
            skipped.append(aid); continue
        if body.action == "ack":
            if a.status == AlertStatus.RESOLVED:
                skipped.append(aid); continue
            a.status = AlertStatus.ACKNOWLEDGED
            a.acknowledged_at = now
            a.acknowledged_by_user_id = user.id
        else:  # resolve
            if a.status == AlertStatus.RESOLVED:
                skipped.append(aid); continue
            a.status = AlertStatus.RESOLVED
            a.resolved_at = now
            a.auto_resolved = False
        changed.append(aid)
    if changed:
        db.commit()
        audit.record(db, action=f"alert.bulk_{body.action}", actor_user_id=user.id,
                     actor_email=user.email, actor_role=user.role.value, target_type="alert",
                     target_id=",".join(map(str, changed))[:80], ip=_ip(request),
                     detail=f"{len(changed)} alerts {body.action}'d")
    return {"action": body.action, "changed": changed, "skipped": skipped,
            "changed_count": len(changed)}


# --------------------------------------------------------------------------- #
# Offline sweep (staff / scheduler)
# --------------------------------------------------------------------------- #
@router.post("/monitoring/sweep")
def run_sweep(client_id: int | None = None, request: Request = None,
              db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Scan for devices that have gone silent and raise offline alerts. In
    production this is wired to a scheduler (cron / APScheduler); exposing it as
    an endpoint also lets staff force a refresh on demand."""
    result, new_alerts = monitoring.sweep_offline(db, client_id=client_id)
    audit.record(db, action="monitoring.sweep", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="monitoring",
                 ip=_ip(request) if request else None,
                 detail=f"checked={result['devices_checked']} opened={result['offline_opened']}")
    # Newly offline devices are alerts too — let automation react.
    for alert in new_alerts:
        dev = db.get(Device, alert.device_id)
        automation.dispatch(db, "alert.opened", automation.build_alert_context(alert, dev))
    return result


# --------------------------------------------------------------------------- #
# Alert policies (thresholds) — staff only
# --------------------------------------------------------------------------- #
class PolicyIn(BaseModel):
    client_id: int | None = None  # None == global default
    disk_pct_max: float = 90.0
    cpu_pct_max: float = 95.0
    ram_pct_max: float = 95.0
    health_min: int = 60
    offline_minutes: int = 30
    alert_on_av_off: bool = True
    alert_on_patch_behind: bool = True


def _serialize_policy(p: AlertPolicy) -> dict:
    return {
        "id": p.id, "client_id": p.client_id, "disk_pct_max": p.disk_pct_max,
        "cpu_pct_max": p.cpu_pct_max, "ram_pct_max": p.ram_pct_max,
        "health_min": p.health_min, "offline_minutes": p.offline_minutes,
        "alert_on_av_off": p.alert_on_av_off, "alert_on_patch_behind": p.alert_on_patch_behind,
    }


@router.get("/alert-policies")
def list_policies(db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return [_serialize_policy(p) for p in db.query(AlertPolicy).order_by(AlertPolicy.client_id).all()]


@router.put("/alert-policies")
def upsert_policy(body: PolicyIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Create or update the policy for a client (or the global default when
    client_id is null). One policy per scope — upsert keeps it simple."""
    if body.offline_minutes < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "offline_minutes must be >= 1")

    if body.client_id is not None:
        p = db.query(AlertPolicy).filter(AlertPolicy.client_id == body.client_id).first()
    else:
        p = db.query(AlertPolicy).filter(AlertPolicy.client_id.is_(None)).first()

    if not p:
        p = AlertPolicy(client_id=body.client_id)
        db.add(p)
    for field, val in body.model_dump().items():
        setattr(p, field, val)
    db.commit()
    audit.record(db, action="alert_policy.upsert", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="alert_policy", target_id=str(p.id),
                 client_id=body.client_id, ip=_ip(request))
    return _serialize_policy(p)
