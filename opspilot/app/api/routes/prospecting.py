"""v0.44 Prospecting — find & score leads, drop them into the CRM.

Google Places lead discovery. The API key is stored in the secure vault. Runs
are OWNER/TECH and audited. Each run creates scored CRM contacts (deduped).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, prospecting, secure_config

router = APIRouter(prefix="/api/prospecting", tags=["prospecting"])

PROVIDER = "google_places"


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _api_key(db: Session) -> str:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    key = secure_config.get_secret(cfg, "api_key")
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Prospecting not configured — add a Google API key in Settings → Prospecting.")
    return str(key)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"configured": secure_config.configured(cfg, ("api_key",)),
            "fields": secure_config.public_view(cfg)}


class SettingsIn(BaseModel):
    api_key: str | None = None


@router.put("/settings")
def save_settings(body: SettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, PROVIDER, "Google Places (Prospecting)", "Sales", payload)
    audit.record(db, action="prospecting.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="google places key")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, ("api_key",)),
            "fields": secure_config.public_view(cfg)}


@router.get("/options")
def options(user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return {
        "markets": [{"key": k, "name": v["name"]} for k, v in prospecting.MARKETS.items()],
        "industries": [{"query": i["query"], "industry": i["industry"]} for i in prospecting.INDUSTRIES],
    }


class RunIn(BaseModel):
    market: str
    industry: str          # an industry query string from /options
    max_results: int = 20


@router.post("/run")
def run(body: RunIn, request: Request, db: Session = Depends(get_db),
        user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    key = _api_key(db)
    try:
        client = prospecting.PlacesClient(key)
        result = prospecting.run(db, client, body.market, body.industry,
                                 max_results=body.max_results, user_id=user.id)
    except prospecting.ProspectingError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    audit.record(db, action="prospecting.run", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="prospecting", target_id=body.market,
                 ip=_ip(request), detail=f"{body.industry}: +{result['created']} leads")
    return result
