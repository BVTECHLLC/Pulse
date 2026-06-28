"""v0.12 network diagnostics.

Two layers:
  * Looking glass (server-side): DNS / TCP port / reachability / HTTP checks run
    FROM the portal toward PUBLIC targets — for a client's internet-facing
    issues. SSRF-guarded (see services/netdiag.py), staff-only.
  * Agent diagnostics: read-only probes (ping/traceroute/dns/port_check/
    subnet_discovery) queued for an ON-SITE agent to run against the client's
    INTERNAL LAN and report back (the agent pull/report lives in routes/agent.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import DIAG_KINDS, Device, DiagnosticRequest, Role, User
from ...services import audit, netdiag

router = APIRouter(prefix="/api/netdiag", tags=["network-diagnostics"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Looking glass (server-side, public targets only)
# --------------------------------------------------------------------------- #
class HostIn(BaseModel):
    host: str


class PortIn(BaseModel):
    host: str
    port: int


class UrlIn(BaseModel):
    url: str


def _run(fn, *args):
    try:
        return fn(*args)
    except netdiag.DiagError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/dns")
def lg_dns(body: HostIn, user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _run(netdiag.dns_lookup, body.host)


@router.post("/reachability")
def lg_reach(body: HostIn, user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _run(netdiag.reachability, body.host)


@router.post("/port")
def lg_port(body: PortIn, user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _run(netdiag.tcp_check, body.host, body.port)


@router.post("/http")
def lg_http(body: UrlIn, user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _run(netdiag.http_check, body.url)


# --------------------------------------------------------------------------- #
# Agent diagnostics (queued for an on-site agent)
# --------------------------------------------------------------------------- #
class DiagIn(BaseModel):
    device_id: int
    kind: str
    target: str | None = None
    params: dict = {}


def _serialize(d: DiagnosticRequest) -> dict:
    return {
        "id": d.id, "client_id": d.client_id, "device_id": d.device_id, "kind": d.kind,
        "target": d.target, "params": d.params, "status": d.status, "result": d.result,
        "requested_by_email": d.requested_by_email,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
    }


@router.post("/diagnostics", status_code=201)
def create_diag(body: DiagIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if body.kind not in DIAG_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"kind must be one of {list(DIAG_KINDS)}")
    dev = db.get(Device, body.device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    if body.kind in ("ping", "traceroute", "dns", "port_check") and not body.target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{body.kind} requires a target")
    d = DiagnosticRequest(client_id=dev.client_id, device_id=dev.id, kind=body.kind,
                          target=body.target, params=body.params or {},
                          requested_by_user_id=user.id, requested_by_email=user.email)
    db.add(d)
    db.commit()
    audit.record(db, action="diag.request", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="diagnostic", target_id=str(d.id),
                 client_id=dev.client_id, ip=_ip(request), detail=f"{body.kind} {body.target or ''}".strip())
    return {"id": d.id, "status": d.status}


@router.get("/diagnostics")
def list_diag(device_id: int | None = None, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    q = db.query(DiagnosticRequest)
    if not is_staff(user):
        q = q.filter(DiagnosticRequest.client_id == user.client_id)
    if device_id:
        q = q.filter(DiagnosticRequest.device_id == device_id)
    rows = q.order_by(DiagnosticRequest.created_at.desc()).limit(100).all()
    return [_serialize(d) for d in rows]


@router.get("/diagnostics/{diag_id}")
def get_diag(diag_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = db.get(DiagnosticRequest, diag_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diagnostic not found")
    assert_client_access(user, d.client_id)
    return _serialize(d)
