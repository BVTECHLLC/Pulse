"""v0.41 Comms — Dialpad auto-dialer (click-to-call).

Dialpad credentials (API key + the user/device to ring + caller-ID number) are
stored encrypted on a platform connection. "Call" rings the configured Dialpad
user's device first, then dials the target number — the standard click-to-call
flow. Credentials are never returned to the browser or logged.

Staff-only (OWNER/TECH).
"""
from __future__ import annotations

import json
from urllib import error
from urllib import request as urlrequest

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, secure_config

router = APIRouter(prefix="/api/comms", tags=["comms"])

PROVIDER = "dialpad"
DIALPAD_CALL_API = "https://dialpad.com/api/v2/call"


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class DialpadSettingsIn(BaseModel):
    api_key: str | None = None
    user_id: str | None = None        # the Dialpad user/device to ring
    caller_number: str | None = None  # outbound caller ID (E.164)


@router.get("/dialpad/settings")
def get_dialpad_settings(db: Session = Depends(get_db),
                         user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"configured": secure_config.configured(cfg, ("api_key", "user_id")),
            "fields": secure_config.public_view(cfg)}


@router.put("/dialpad/settings")
def save_dialpad_settings(body: DialpadSettingsIn, request: Request, db: Session = Depends(get_db),
                          user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, PROVIDER, "Dialpad", "Telephony", payload)
    audit.record(db, action="dialpad.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="dialpad credentials")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, ("api_key", "user_id")),
            "fields": secure_config.public_view(cfg)}


# --------------------------------------------------------------------------- #
# Click-to-call
# --------------------------------------------------------------------------- #
class CallIn(BaseModel):
    to: str                       # number to dial (E.164 preferred)
    client_id: int | None = None  # optional, for audit context


@router.post("/dialpad/call", status_code=202)
def click_to_call(body: CallIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    target = (body.to or "").strip()
    if not target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A number to dial is required.")
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    api_key = secure_config.get_secret(cfg, "api_key")
    user_id = secure_config.get_secret(cfg, "user_id") or cfg.get("user_id")
    if not (api_key and user_id):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Dialpad not configured — add an API key & user in Settings.")
    payload = {"phone_number": target, "user_id": str(user_id)}
    caller = cfg.get("caller_number")
    if caller:
        payload["outbound_caller_id"] = str(caller)
    req = urlrequest.Request(
        DIALPAD_CALL_API, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urlrequest.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            data = json.loads(raw) if raw.strip() else {}
    except error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                                f"Dialpad auth failed (HTTP {e.code}) — check the API key.")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Dialpad HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Dialpad request failed: {e}")
    audit.record(db, action="dialpad.call", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="phone", target_id=target,
                 client_id=body.client_id, ip=_ip(request), detail=f"dialed {target}")
    return {"ok": True, "dialed": target, "call": data.get("id") if isinstance(data, dict) else None}
