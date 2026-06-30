"""v0.42 RMM — Tactical RMM integration surfaced inside Pulse.

Connect a self-hosted Tactical RMM instance (base URL + API key, stored encrypted
in the secure vault) and manage fleet from Pulse: dashboard rollup, agents,
alerts, services, Windows updates. Reads are staff (OWNER/TECH); mutating actions
(reboot, resolve alert, service control, update install) are OWNER-only and
audited. The RMM URL is user-supplied, so the client SSRF-guards every call.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, secure_config, tacticalrmm

router = APIRouter(prefix="/api/rmm", tags=["rmm"])

PROVIDER = "tacticalrmm"
_REQUIRED = ("base_url", "api_key")


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _client(db: Session) -> tacticalrmm.TacticalRMMClient:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    if not secure_config.configured(cfg, _REQUIRED):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Tactical RMM not configured — add a URL & API key in Settings → RMM.")
    base = cfg.get("base_url") or secure_config.get_secret(cfg, "base_url")
    key = secure_config.get_secret(cfg, "api_key")
    try:
        return tacticalrmm.TacticalRMMClient(str(base), str(key))
    except tacticalrmm.TRMMError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except tacticalrmm.TRMMError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class RmmSettingsIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"configured": secure_config.configured(cfg, _REQUIRED),
            "fields": secure_config.public_view(cfg)}


@router.put("/settings")
def save_settings(body: RmmSettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    # base_url isn't a secret, but validate it eagerly so a bad URL is caught now.
    if payload.get("base_url"):
        try:
            tacticalrmm._guard_url(payload["base_url"])
        except tacticalrmm.TRMMError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    conn = secure_config.upsert_platform(db, PROVIDER, "Tactical RMM", "RMM", payload)
    audit.record(db, action="rmm.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="tactical rmm credentials")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, _REQUIRED),
            "fields": secure_config.public_view(cfg)}


@router.post("/test")
def test(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = _client(db)
    dash = _call(c.get_dashboard)
    return {"ok": True, "dashboard": dash}


# --------------------------------------------------------------------------- #
# Read endpoints
# --------------------------------------------------------------------------- #
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _call(_client(db).get_dashboard)


@router.get("/agents")
def agents(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    raw = _call(_client(db).get_agents, detail=False)
    return {"agents": [tacticalrmm.summarize_agent(a) for a in raw]}


@router.get("/agents/{agent_id}")
def agent(agent_id: str, db: Session = Depends(get_db),
          user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _call(_client(db).get_agent, agent_id)


@router.get("/agents/{agent_id}/software")
def agent_software(agent_id: str, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return {"software": _call(_client(db).get_software, agent_id)}


@router.get("/agents/{agent_id}/updates")
def agent_updates(agent_id: str, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return {"updates": _call(_client(db).get_updates, agent_id)}


@router.get("/agents/{agent_id}/services")
def agent_services(agent_id: str, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return {"services": _call(_client(db).get_services, agent_id)}


@router.get("/alerts")
def alerts(resolved: bool | None = Query(None), db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    raw = _call(_client(db).get_alerts, resolved=resolved)
    return {"alerts": [tacticalrmm.summarize_alert(a) for a in raw]}


@router.get("/clients")
def clients(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return {"clients": _call(_client(db).get_clients)}


# --------------------------------------------------------------------------- #
# Mutating actions (OWNER-only, audited)
# --------------------------------------------------------------------------- #
@router.post("/agents/{agent_id}/reboot")
def reboot(agent_id: str, request: Request, db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OWNER))):
    res = _call(_client(db).reboot_agent, agent_id)
    audit.record(db, action="rmm.reboot", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="rmm_agent", target_id=agent_id, ip=_ip(request))
    return {"ok": True, "result": res}


@router.post("/agents/{agent_id}/scan-updates")
def scan_updates(agent_id: str, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER))):
    res = _call(_client(db).scan_updates, agent_id)
    audit.record(db, action="rmm.scan_updates", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="rmm_agent", target_id=agent_id, ip=_ip(request))
    return {"ok": True, "result": res}


@router.post("/agents/{agent_id}/install-updates")
def install_updates(agent_id: str, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER))):
    res = _call(_client(db).install_updates, agent_id)
    audit.record(db, action="rmm.install_updates", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="rmm_agent", target_id=agent_id, ip=_ip(request))
    return {"ok": True, "result": res}


class ServiceActionIn(BaseModel):
    service: str
    action: str  # start|stop|restart


@router.post("/agents/{agent_id}/service")
def service_action(agent_id: str, body: ServiceActionIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    res = _call(_client(db).control_service, agent_id, body.service, body.action)
    audit.record(db, action="rmm.service", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="rmm_agent", target_id=agent_id,
                 ip=_ip(request), detail=f"{body.action} {body.service}")
    return {"ok": True, "result": res}


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    res = _call(_client(db).resolve_alert, alert_id)
    audit.record(db, action="rmm.resolve_alert", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="rmm_alert", target_id=alert_id, ip=_ip(request))
    return {"ok": True, "result": res}
