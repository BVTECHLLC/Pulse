"""Graveyard Shift co-op lobby — a tiny, stateless WebRTC *signaling* rendezvous.

Players host/join a game by a short 4-character code (or pick a listed open game),
and this endpoint only relays the WebRTC offer/answer so the two browsers can
connect peer-to-peer. No game traffic flows through the server, nothing is
persisted, and rooms are purely in-memory — safe because the app runs a single
uvicorn worker. Same-origin wss:// is allowed by our CSP (default-src 'self'),
unlike a third-party broker, so this needs no CSP changes.
"""
from __future__ import annotations

import asyncio
import secrets
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["coop"])

# code -> {"name", "host": ws, "guest": ws|None, "created": ts}
_rooms: dict[str, dict] = {}
_ROOM_TTL = 150  # a waiting room is listed/kept alive this many seconds
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O/1/I/L


def _gen_code() -> str:
    for _ in range(60):
        c = "".join(secrets.choice(_ALPHABET) for _ in range(4))
        if c not in _rooms:
            return c
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _prune() -> None:
    now = time.time()
    for code in list(_rooms):
        r = _rooms[code]
        if r.get("guest") is None and now - r["created"] > _ROOM_TTL:
            _rooms.pop(code, None)


@router.get("/api/coop/rooms")
async def list_rooms():
    """Open games waiting for a second player (newest first)."""
    _prune()
    now = time.time()
    rooms = [
        {"code": c, "name": r["name"], "age": int(now - r["created"])}
        for c, r in _rooms.items()
        if r.get("guest") is None
    ]
    rooms.sort(key=lambda x: x["age"])
    return {"rooms": rooms[:30]}


async def _send(ws: WebSocket, data: dict) -> None:
    try:
        await ws.send_json(data)
    except Exception:
        pass


@router.websocket("/ws/coop")
async def coop_ws(ws: WebSocket):
    await ws.accept()
    role: str | None = None
    code: str | None = None
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=40)
        kind = first.get("t")
        if kind == "host":
            _prune()
            name = (str(first.get("name") or "A Survivor")[:24]).strip() or "A Survivor"
            code = _gen_code()
            _rooms[code] = {"name": name, "host": ws, "guest": None, "created": time.time()}
            role = "host"
            await ws.send_json({"t": "hosted", "code": code})
        elif kind == "join":
            code = str(first.get("code") or "").strip().upper()
            room = _rooms.get(code)
            if not room or room.get("guest") is not None:
                await ws.send_json({"t": "error", "msg": "That game is no longer available."})
                await ws.close()
                return
            room["guest"] = ws
            role = "guest"
            await ws.send_json({"t": "joined", "name": room["name"]})
            await _send(room["host"], {"t": "peer"})
        else:
            await ws.close()
            return

        # Relay signaling (offer / answer / ice) to the other peer until done.
        while True:
            msg = await ws.receive_json()
            room = _rooms.get(code)
            if not room:
                break
            peer = room["guest"] if role == "host" else room["host"]
            mt = msg.get("t")
            if mt in ("offer", "answer", "ice"):
                await _send(peer, msg)
            elif mt == "bye":
                break
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        pass
    finally:
        room = _rooms.get(code) if code else None
        if room:
            peer = room.get("guest") if role == "host" else room.get("host")
            if peer is not None and peer is not ws:
                await _send(peer, {"t": "peer-left"})
            # Host leaving tears the room down; a guest leaving also clears it.
            _rooms.pop(code, None)
