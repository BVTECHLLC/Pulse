"""v0.49 Google Business Profile — connect + publish localPosts. Staff-only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, gbp, secure_config

router = APIRouter(prefix="/api/gbp", tags=["google-business"])

PROVIDER = "gbp"
_REQUIRED = ("client_id", "client_secret", "refresh_token", "account_name", "location_name")

# v1.146: one route set now serves BOTH Google listings — the BVTech business
# listing ("gbp") and Jordan's personal listing ("gbp_personal") — selected by a
# ?listing= query param, so each has its own connect + location-picker + post.
_LISTINGS = {"business": ("gbp", "Google Business Profile"),
             "personal": ("gbp_personal", "Google Business Profile (Personal)")}


def _listing(listing: str) -> tuple[str, str]:
    return _LISTINGS.get((listing or "business").lower(), _LISTINGS["business"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


_CONNECTED = ("client_id", "client_secret", "refresh_token")   # enough to LIST


def _client(db: Session, listing: str = "business", *, require_location: bool = True) -> gbp.GBPClient:
    provider, label = _listing(listing)
    conn = secure_config.get_platform(db, provider)
    cfg = (conn.config if conn else None) or {}
    need = _REQUIRED if require_location else _CONNECTED
    if not secure_config.configured(cfg, need):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"{label} not connected — add credentials + Connect in Settings.")
    return gbp.GBPClient(
        str(secure_config.get_secret(cfg, "client_id") or cfg.get("client_id")),
        str(secure_config.get_secret(cfg, "client_secret")),
        str(secure_config.get_secret(cfg, "refresh_token")),
        str(cfg.get("account_name") or ""), str(cfg.get("location_name") or ""))


@router.get("/locations")
def locations(listing: str = "business", db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """List the connected account's locations so the user picks one (no ID typing).
    ?listing=business|personal selects which Google listing to read."""
    client = _client(db, listing, require_location=False)
    try:
        return {"locations": client.list_locations(), "listing": listing}
    except gbp.GBPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


class GBPSettingsIn(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    account_name: str | None = None
    location_name: str | None = None


@router.get("/settings")
def get_settings(listing: str = "business", db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    provider, _ = _listing(listing)
    conn = secure_config.get_platform(db, provider)
    cfg = (conn.config if conn else None) or {}
    return {"configured": secure_config.configured(cfg, _REQUIRED),
            "listing": listing, "fields": secure_config.public_view(cfg)}


@router.put("/settings")
def save_settings(body: GBPSettingsIn, request: Request, listing: str = "business",
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    provider, label = _listing(listing)
    channel = "google_business" if provider == "gbp" else "google_business_personal"
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, provider, label, "Marketing", payload)
    from ...services import autopost
    autopost.clear_reauth(db, provider)   # fresh creds lift the delivery pause
    autopost.clear_reauth(db, channel)
    audit.record(db, action="gbp.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail=f"{provider} credentials")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, _REQUIRED),
            "listing": listing, "fields": secure_config.public_view(cfg)}


class PostIn(BaseModel):
    summary: str
    cta_url: str | None = None
    image_url: str | None = None


@router.post("/post")
def post(body: PostIn, request: Request, listing: str = "business",
         db: Session = Depends(get_db),
         user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.summary.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "summary is required")
    client = _client(db, listing)
    try:
        res = client.create_post(body.summary, body.cta_url, image_url=body.image_url)
    except gbp.GBPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    audit.record(db, action="gbp.post", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="gbp", target_id=res.get("name", "post"),
                 ip=_ip(request), detail=body.summary[:120])
    return {"ok": True, "post": res.get("name")}
