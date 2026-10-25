"""Reverse-proxy the self-hosted Signal 199X game (a Node service in the compose
stack) under the portal at /signal/ (v1.104).

Why a subpath proxy instead of a subdomain: the portal already has working DNS,
TLS and the Cloudflare tunnel, so routing /signal/* through it means the game is
live with ZERO DNS/tunnel/Caddy changes. The game speaks plain HTTP + a raw
WebSocket at /ws; we forward both to the internal `game` container, carrying the
browser's cookie (the game's own `lv_session`) so accounts work, and presenting a
fixed Origin so the game's CSRF/origin guard is satisfied.

The game client was patched to use RELATIVE asset/API paths and a path-aware
WebSocket URL, so everything it requests lands under /signal/ and maps cleanly
onto the game's own root routes.
"""
from __future__ import annotations

import asyncio
import os

import httpx
import websockets
from fastapi import APIRouter, Request, Response, WebSocket
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["game"])

GAME_HTTP = os.environ.get("GAME_INTERNAL_URL", "http://game:3000").rstrip("/")
GAME_WS = GAME_HTTP.replace("http://", "ws://").replace("https://", "wss://")
PUBLIC_ORIGIN = os.environ.get("GAME_PUBLIC_ORIGIN", "https://portal.bvtech.org")

# Headers we forward upstream (request) and back (response). We never forward
# Host (httpx sets it to the game container) and we pin Origin so the game's
# same-origin guard accepts proxied calls.
_REQ_HDRS = {"cookie", "content-type", "accept", "accept-language", "user-agent",
             "range", "if-none-match", "if-modified-since"}
_RESP_HDRS = {"content-type", "cache-control", "etag", "last-modified", "expires",
              "content-disposition", "content-range", "accept-ranges", "vary"}

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, read=30.0),
                                    follow_redirects=False)
    return _client


@router.get("/signal")
def signal_root():
    # the client uses relative paths, so it MUST load from a trailing-slash URL
    return RedirectResponse(url="/signal/", status_code=307)


@router.api_route("/signal/{path:path}", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def signal_proxy(path: str, request: Request):
    # /signal/ws is the WebSocket (handled by the ws route); never proxy it here.
    if path == "ws":
        return Response(status_code=426, content="Upgrade Required")
    url = f"{GAME_HTTP}/{path}"
    hdrs = {k: v for k, v in request.headers.items() if k.lower() in _REQ_HDRS}
    hdrs["origin"] = PUBLIC_ORIGIN
    body = await request.body()
    try:
        up = await _get_client().request(request.method, url, content=body or None,
                                         headers=hdrs, params=request.query_params)
    except httpx.HTTPError:
        return Response(status_code=502, content="The game service is unavailable.",
                        media_type="text/plain")
    out = Response(content=up.content, status_code=up.status_code)
    for k in _RESP_HDRS:
        if k in up.headers:
            out.headers[k] = up.headers[k]
    for cookie in up.headers.get_list("set-cookie"):
        out.raw_headers.append((b"set-cookie", cookie.encode("latin-1")))
    return out


@router.websocket("/signal/ws")
async def signal_ws(ws: WebSocket):
    await ws.accept()
    # carry the browser's cookie (the game's lv_session) + a fixed Origin so the
    # game authenticates the socket to the right account.
    headers = {"Origin": PUBLIC_ORIGIN}
    cookie = ws.headers.get("cookie")
    if cookie:
        headers["Cookie"] = cookie
    try:
        upstream = await websockets.connect(f"{GAME_WS}/ws", additional_headers=headers,
                                            open_timeout=10, max_size=2 ** 20,
                                            ping_interval=20, ping_timeout=20)
    except Exception:  # noqa: BLE001  (bad auth / game down / full server)
        try:
            await ws.close(code=1011)
        except Exception:  # noqa: BLE001
            pass
        return

    async def browser_to_game():
        try:
            while True:
                msg = await ws.receive_text()
                await upstream.send(msg)
        except Exception:  # noqa: BLE001
            pass

    async def game_to_browser():
        try:
            async for msg in upstream:
                if isinstance(msg, bytes):
                    await ws.send_bytes(msg)
                else:
                    await ws.send_text(msg)
        except Exception:  # noqa: BLE001
            pass

    t1 = asyncio.create_task(browser_to_game())
    t2 = asyncio.create_task(game_to_browser())
    try:
        await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in (t1, t2):
            t.cancel()
        await upstream.close()
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
