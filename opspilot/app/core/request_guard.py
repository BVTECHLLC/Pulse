"""Outermost request guard (v1.94) — cheap rejection before any app work.

Written in response to PHP2Shell (CVE-2026-109618 / CVE-2026-109619, Oct 2026).
The portal runs no PHP, so those bugs can't execute here — but the attack
technique (large multipart bodies to put a worker under memory pressure) and
the internet-wide scanning wave that followed apply to ANY web stack. This
layer makes the portal a dead end for both:

  * Body size cap. Requests larger than MAX_REQUEST_BODY_MB get a 413. A
    declared Content-Length is refused up front; a chunked body (no declared
    length) is counted as it streams and cut off the moment it crosses the cap,
    so a client can't lie its way past the check.
  * No multipart. The portal has no upload endpoints — every inbound body is
    JSON — so multipart/form-data is refused with 415 and the multipart parser
    is never reached. Paths that ever need uploads go in MULTIPART_ALLOW.
  * PHP / WordPress probe paths (*.php, /wp-admin, /xmlrpc.php, phpunit, …)
    get a tiny 404 here, before the audit logger, rate limiter or database ever
    see them. Mass scanners burn nothing on us.

Pure ASGI (not BaseHTTPMiddleware) so it can wrap `receive` and abort a body
mid-stream. Registered last in main.py, which makes it the outermost layer.
"""
from __future__ import annotations

import json
import re

MAX_REQUEST_BODY_MB = 10            # far above any legit JSON body (agent check-ins, studio)
MULTIPART_ALLOW: tuple[str, ...] = ()  # path prefixes allowed to receive multipart

_PROBE_RE = re.compile(
    r"(\.php\d?$|\.phtml$|/wp-(admin|login|includes|content|json)\b|/xmlrpc\b"
    r"|/phpunit\b|/vendor/|/cgi-bin/|/phpmyadmin\b|/\.env$|/\.git/)",
    re.I)


class _BodyTooLarge(Exception):
    pass


async def _send_plain(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class RequestGuard:
    def __init__(self, app, max_body_mb: int = MAX_REQUEST_BODY_MB):
        self.app = app
        self.max_body = max_body_mb * 1024 * 1024

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if _PROBE_RE.search(path):
            return await _send_plain(send, 404, "Not Found")
        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        ctype = headers.get(b"content-type", b"").decode("latin-1").lower()
        if "multipart/" in ctype and not path.startswith(MULTIPART_ALLOW or ("\0",)):
            return await _send_plain(send, 415, "multipart uploads are not accepted here")
        clen = headers.get(b"content-length")
        if clen is not None:
            try:
                declared = int(clen)
            except ValueError:
                return await _send_plain(send, 400, "bad Content-Length")
            if declared > self.max_body:
                return await _send_plain(send, 413, "request body too large")

        seen = 0
        started = False
        exceeded = False

        async def guarded_receive():
            nonlocal seen, exceeded
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.max_body:
                    exceeded = True
                    raise _BodyTooLarge()
            return msg

        async def tracking_send(msg):
            nonlocal started
            if exceeded:
                # The framework turns the aborted read into its own error page
                # (FastAPI: a generic 400). Answer with an honest 413 instead
                # and drop whatever the app tries to send after it.
                if msg["type"] == "http.response.start" and not started:
                    started = True
                    await _send_plain(send, 413, "request body too large")
                return
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, guarded_receive, tracking_send)
        except _BodyTooLarge:
            if not started:
                await _send_plain(send, 413, "request body too large")
