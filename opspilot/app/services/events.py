"""v0.21 outbound event bus. Internal events (ticket.created, alert.opened, …)
are delivered to matching WebhookSubscription URLs as a signed JSON POST, so any
external tool can react to Pulse in real time.

Best-effort and never raises into the caller. Reuses the SSRF guard from
notifications (blocks the cloud-metadata address; http(s) only)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..core.security import sign_hmac
from ..models import WebhookSubscription
from .notifications import _safe_webhook
from urllib import request as urlreq


def _deliver(sub: WebhookSubscription, event: str, data: dict) -> int | None:
    if not _safe_webhook(sub.url):
        return None
    body = json.dumps({"event": event, "data": data,
                       "ts": datetime.now(timezone.utc).isoformat()}).encode()
    headers = {"Content-Type": "application/json", "X-OpsPilot-Event": event}
    if sub.secret:
        headers["X-OpsPilot-Signature"] = "sha256=" + sign_hmac(sub.secret, body)
    try:
        req = urlreq.Request(sub.url, data=body, headers=headers, method="POST")
        with urlreq.urlopen(req, timeout=8) as r:
            return int(r.status)
    except Exception as exc:  # capture HTTP error codes where available
        return getattr(exc, "code", None)


def emit(db: Session, event: str, data: dict, *, client_id: int | None = None) -> int:
    """Fan an event out to every enabled subscription that wants it. Returns the
    count of deliveries attempted. Never raises."""
    try:
        subs = db.query(WebhookSubscription).filter(WebhookSubscription.enabled.is_(True)).all()
    except Exception:
        return 0
    fired = 0
    now = datetime.now(timezone.utc)
    for sub in subs:
        # client-scoped subscriptions only get their client's events
        if sub.client_id is not None and client_id is not None and sub.client_id != client_id:
            continue
        wanted = sub.events or []
        if wanted and event not in wanted:
            continue
        status = _deliver(sub, event, data)
        sub.last_status = status
        sub.last_fired_at = now
        fired += 1
    if fired:
        try:
            db.commit()
        except Exception:
            db.rollback()
    return fired
