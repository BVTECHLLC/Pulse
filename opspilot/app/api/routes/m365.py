"""v0.9 Microsoft 365 routes: per-client tenant connections + read-only sync.

Staff-only. The actual Graph credentials live in env (M365_CLIENT_ID /
M365_CLIENT_SECRET); until those are set, connections can be recorded but the
live sync returns 503. Sync auto-populates licenses, stores the Secure Score,
and raises alerts for risky sign-ins (which automation rules can act on).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.db import get_db
from ...core.deps import current_user, is_staff, require_roles
from ...models import Client, Device, M365Connection, Role, User
from ...services import audit, automation, m365

router = APIRouter(prefix="/api/m365", tags=["microsoft-365"])
_s = get_settings()


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(c: M365Connection) -> dict:
    return {
        "id": c.id, "client_id": c.client_id, "tenant_id": c.tenant_id,
        "display_name": c.display_name, "status": c.status,
        "secure_score": c.secure_score, "secure_score_max": c.secure_score_max,
        "license_count": c.license_count, "risky_signin_count": c.risky_signin_count,
        "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
        "last_sync_status": c.last_sync_status,
    }


@router.get("/status")
def m365_status(user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Whether the platform has Graph credentials configured."""
    return {"configured": _s.m365_enabled}


@router.get("/connections")
def list_connections(db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return [_serialize(c) for c in db.query(M365Connection).order_by(M365Connection.client_id).all()]


class ConnectionIn(BaseModel):
    client_id: int
    tenant_id: str
    display_name: str | None = None


@router.post("/connections", status_code=201)
def create_connection(body: ConnectionIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    if db.query(M365Connection).filter(M365Connection.client_id == body.client_id).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "This client already has an M365 connection")
    if not body.tenant_id.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tenant_id is required")
    c = M365Connection(client_id=body.client_id, tenant_id=body.tenant_id.strip(),
                       display_name=body.display_name, created_by_user_id=user.id)
    db.add(c)
    db.commit()
    audit.record(db, action="m365.connect", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="m365_connection", target_id=str(c.id),
                 client_id=body.client_id, ip=_ip(request), detail=f"tenant={c.tenant_id}")
    return {"id": c.id, "status": c.status}


@router.delete("/connections/{conn_id}")
def delete_connection(conn_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER))):
    c = db.get(M365Connection, conn_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    cid = c.client_id
    db.delete(c)
    db.commit()
    audit.record(db, action="m365.disconnect", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="m365_connection", target_id=str(conn_id),
                 client_id=cid, ip=_ip(request))
    return {"ok": True}


@router.post("/connections/{conn_id}/sync")
def sync_connection(conn_id: int, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = db.get(M365Connection, conn_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    if not _s.m365_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Microsoft 365 is not configured on this server (set M365_CLIENT_ID / M365_CLIENT_SECRET)")
    try:
        graph = m365.GraphClient(c.tenant_id)
        result = m365.sync_connection(db, c, graph)
    except m365.GraphError as e:
        c.status = "error"
        c.last_sync_status = str(e)[:200]
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Graph sync failed: {e}")
    # Risky-sign-in alerts feed the automation engine.
    for alert in result.get("new_alerts", []):
        automation.dispatch(db, "alert.opened", automation.build_alert_context(alert, None))
    audit.record(db, action="m365.sync", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="m365_connection", target_id=str(c.id),
                 client_id=c.client_id, ip=_ip(request), detail=c.last_sync_status)
    return {"ok": True, "skus": result["skus"], "secure_score": result["secure_score"],
            "risky_signins": result["risky_signins"]}
