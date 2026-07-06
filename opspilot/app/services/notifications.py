"""Notification fan-out: an in-app Notification can also be delivered to
configured channels (email / Slack / Teams / generic webhook).

Channels are configured by staff (trusted). Webhook delivery is best-effort with
a tight timeout and never raises into the caller. We still block the cloud
metadata address and require http(s) to avoid the most dangerous SSRF target.
"""
from __future__ import annotations

import json
import socket
from urllib import request as urlreq
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models import NotificationChannel, SEVERITY_RANK
from . import email as email_svc


def _safe_webhook(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        # Block the cloud metadata endpoint specifically.
        for info in socket.getaddrinfo(p.hostname, None):
            if info[4][0] in ("169.254.169.254", "fd00:ec2::254"):
                return False
        return True
    except Exception:
        return False


def _post_webhook(url: str, payload: dict) -> bool:
    if not _safe_webhook(url):
        return False
    try:
        data = json.dumps(payload).encode()
        req = urlreq.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urlreq.urlopen(req, timeout=8) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def deliver(channel: NotificationChannel, message: str, severity: str) -> bool:
    """Send one message via one channel. Returns True if accepted/sent."""
    if channel.type == "email":
        return email_svc.send(channel.target, f"[OpsPilot:{severity}] alert", message)
    if channel.type in ("slack", "webhook"):
        return _post_webhook(channel.target, {"text": message})
    if channel.type == "teams":
        # Teams incoming webhooks accept a simple text card.
        return _post_webhook(channel.target, {"text": message})
    return False


def fanout(db: Session, *, message: str, severity: str = "info", client_id: int | None = None) -> int:
    """Deliver to all enabled channels whose scope + min severity match. Returns
    the number of successful deliveries. Best-effort; never raises."""
    rank = SEVERITY_RANK.get(severity, 0)
    q = db.query(NotificationChannel).filter(NotificationChannel.enabled.is_(True))
    delivered = 0
    for ch in q.all():
        if ch.client_id is not None and ch.client_id != client_id:
            continue
        if rank < SEVERITY_RANK.get(ch.min_severity, 0):
            continue
        try:
            if deliver(ch, message, severity):
                delivered += 1
            else:
                print(f"[notify] delivery to channel '{ch.name}' ({ch.type}) failed")
        except Exception as e:  # noqa: BLE001
            print(f"[notify] delivery to channel '{ch.name}' ({ch.type}) raised: {e}")
    return delivered
