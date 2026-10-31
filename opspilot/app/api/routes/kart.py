"""VOLT RUSH — reverse-proxy for the multiplayer race socket.

The VOLT RUSH browser client is served statically by the portal at ``/kart``
(see ``app.main``) and plays single-player on its own. Online multiplayer runs on
an authoritative Node/ws race server shipped as the separate ``volt-rush`` compose
service (internal network only, never exposed publicly). This module bridges the
browser's same-origin ``/kart/ws`` socket to that Node server.

Routing everything through the portal's own ``api:8000`` entrypoint keeps it
proxy-agnostic: it works the same whether the box is fronted by Caddy or a
Cloudflare Tunnel, and needs no reverse-proxy config change. If the Node service
is not running yet, the bridge just closes cleanly — the client falls back to its
offline solo race, so the portal is never harmed.
"""
from __future__ import annotations

import asyncio
import os

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

router = APIRouter()

# Internal compose address of the authoritative race server. Override via env.
_UPSTREAM = os.getenv("KART_WS_UPSTREAM", "ws://volt-rush:3108/kart/ws")
_HTTP_BASE = os.getenv("KART_HTTP_UPSTREAM", "http://volt-rush:3108")


@router.get("/kart/health")
async def kart_health() -> JSONResponse:
    """Report whether the VOLT RUSH race server is reachable (and its load)."""
    try:
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(_HTTP_BASE + "/kart/health")
        return JSONResponse(status_code=r.status_code, content=r.json())
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "race_server": "down",
                     "hint": "docker compose up -d --build volt-rush"},
        )


@router.websocket("/kart/ws")
async def kart_ws(client: WebSocket) -> None:
    await client.accept()
    try:
        # Provided by uvicorn[standard]; imported lazily so a missing optional
        # dep can never break app import.
        import websockets
    except Exception:  # pragma: no cover - dependency always present in prod image
        await client.close(code=1011)
        return

    try:
        upstream = await websockets.connect(_UPSTREAM, open_timeout=5, max_size=2 ** 16)
    except Exception:
        # Node race server is not up yet (run: docker compose up -d --build volt-rush).
        # 1013 = "try again later". The client's solo mode keeps working.
        await client.close(code=1013)
        return

    async def client_to_upstream() -> None:
        try:
            while True:
                await upstream.send(await client.receive_text())
        except Exception:
            pass

    async def upstream_to_client() -> None:
        try:
            async for msg in upstream:
                await client.send_text(msg if isinstance(msg, str) else msg.decode("utf-8", "ignore"))
        except Exception:
            pass

    pump = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
    try:
        await asyncio.wait(pump, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in pump:
            task.cancel()
        try:
            await upstream.close()
        except Exception:
            pass
        try:
            await client.close()
        except (WebSocketDisconnect, Exception):
            pass
