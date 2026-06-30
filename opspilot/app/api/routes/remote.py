"""v0.47 Remote desktop — native WebRTC signaling relay.

Pulse brokers a peer-to-peer WebRTC connection between an operator (browser) and
a device (agent). No third party: we are the signaling server. The operator and
the agent each open a WebSocket to ``/api/remote/ws/{token}`` and we forward the
SDP offer/answer + ICE candidates between them. Media flows P2P (or via the
configured STUN/TURN); only signaling crosses Pulse.

Security:
  * Creating a session is OWNER-only and audited.
  * The operator WS authenticates with the session cookie (staff only).
  * The agent WS authenticates with the device's enroll_id + agent_key.
  * The token scopes the relay: only the two peers holding it are bridged.

NOTE: the relay registry is in-process. A single uvicorn worker (the portal's
default) is fine; multi-worker needs a Redis pub/sub fan-out (documented follow-up).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import (APIRouter, Depends, HTTPException, Request, WebSocket,
                     WebSocketDisconnect, status)
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.db import SessionLocal, get_db
from ...core.deps import require_roles
from ...core.security import decode_token, random_token, verify_password
from ...models import AuthSession, Device, RemoteSession, Role, User
from ...services import audit

router = APIRouter(prefix="/api/remote", tags=["remote"])
_s = get_settings()


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# In-process relay registry: token -> {"operator": ws, "agent": ws}
# --------------------------------------------------------------------------- #
_PEERS: dict[str, dict] = {}


def _serialize(rs: RemoteSession) -> dict:
    return {"id": rs.id, "device_id": rs.device_id, "token": rs.token, "status": rs.status,
            "operator_email": rs.operator_email,
            "created_at": rs.created_at.isoformat() if rs.created_at else None,
            "ended_at": rs.ended_at.isoformat() if rs.ended_at else None}


# --------------------------------------------------------------------------- #
# REST: start / list / close a session
# --------------------------------------------------------------------------- #
@router.post("/sessions/{device_id}", status_code=201)
def start_session(device_id: int, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    # Reuse a still-pending session for this device if one exists.
    rs = RemoteSession(device_id=dev.id, client_id=dev.client_id, token=random_token(24),
                       status="pending", operator_user_id=user.id, operator_email=user.email)
    db.add(rs)
    db.commit()
    db.refresh(rs)
    audit.record(db, action="remote.start", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="device", target_id=str(dev.id),
                 client_id=dev.client_id, ip=_ip(request))
    return {"ok": True, "session": _serialize(rs), "viewer_url": f"/remote/{rs.token}"}


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = (db.query(RemoteSession).filter(RemoteSession.status != "closed")
            .order_by(RemoteSession.created_at.desc()).limit(50).all())
    return {"sessions": [_serialize(r) for r in rows]}


@router.post("/sessions/{token}/close")
def close_session(token: str, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rs = db.query(RemoteSession).filter(RemoteSession.token == token).first()
    if not rs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    rs.status = "closed"
    rs.ended_at = _now()
    db.commit()
    peers = _PEERS.pop(token, None)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Agent: poll for pending remote sessions targeting this device
# --------------------------------------------------------------------------- #
def _auth_device_ws(db: Session, enroll_id: str | None, agent_key: str | None) -> Device | None:
    if not (enroll_id and agent_key):
        return None
    dev = db.query(Device).filter(Device.enroll_id == enroll_id).first()
    if not dev or not dev.agent_key_hash or not verify_password(agent_key, dev.agent_key_hash):
        return None
    return dev


def _resolve_cookie_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception:
        return None
    if payload.get("typ") != "access":
        return None
    sess = db.get(AuthSession, payload.get("sid")) if payload.get("sid") else None
    if not sess or sess.revoked:
        return None
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        return None
    return user


# --------------------------------------------------------------------------- #
# WebSocket signaling relay
# --------------------------------------------------------------------------- #
@router.websocket("/ws/{token}")
async def relay(websocket: WebSocket, token: str, role: str = "operator"):
    """Bridge the operator and agent peers holding `token`. role=operator|agent."""
    db = SessionLocal()
    try:
        rs = db.query(RemoteSession).filter(RemoteSession.token == token).first()
        if not rs or rs.status == "closed":
            await websocket.close(code=4404)
            return
        # --- authenticate per role ---
        if role == "agent":
            dev = _auth_device_ws(db, websocket.query_params.get("enroll_id"),
                                  websocket.query_params.get("agent_key"))
            if not dev or dev.id != rs.device_id:
                await websocket.close(code=4401)
                return
        else:  # operator
            role = "operator"
            user = _resolve_cookie_user(db, websocket.cookies.get("access_token")
                                        or websocket.query_params.get("access_token"))
            if not user or user.role not in (Role.OWNER, Role.TECH):
                await websocket.close(code=4401)
                return

        await websocket.accept()
        slot = _PEERS.setdefault(token, {})
        slot[role] = websocket
        # mark connection state
        if role == "agent":
            rs.agent_connected_at = _now()
        else:
            rs.operator_connected_at = _now()
        if "operator" in slot and "agent" in slot:
            rs.status = "connected"
        db.commit()

        # Tell this peer whether its counterpart is already present.
        other = "agent" if role == "operator" else "operator"
        await websocket.send_json({"type": "relay.ready", "role": role,
                                   "peer_present": other in slot})
        if other in slot:
            try:
                await slot[other].send_json({"type": "relay.peer-joined", "role": role})
            except Exception:
                pass

        # Forward every signaling message to the other peer verbatim.
        while True:
            msg = await websocket.receive_text()
            peer = _PEERS.get(token, {}).get(other)
            if peer is not None:
                try:
                    await peer.send_text(msg)
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        slot = _PEERS.get(token)
        if slot:
            if slot.get(role) is websocket:
                slot.pop(role, None)
            other = "agent" if role == "operator" else "operator"
            peer = slot.get(other)
            if peer is not None:
                try:
                    await peer.send_json({"type": "relay.peer-left", "role": role})
                except Exception:
                    pass
            if not slot:
                _PEERS.pop(token, None)
        try:
            rs2 = db.query(RemoteSession).filter(RemoteSession.token == token).first()
            if rs2 and rs2.status != "closed" and token not in _PEERS:
                rs2.status = "closed"
                rs2.ended_at = _now()
                db.commit()
        except Exception:
            pass
        db.close()
