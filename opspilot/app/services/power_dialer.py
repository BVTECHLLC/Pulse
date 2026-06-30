"""v0.60 Power dialer — work a queue of numbers one click at a time.

A `DialSession` is a named queue of `DialEntry` rows. The rep hits "Dial next",
which rings their Dialpad device then the target (reusing the click-to-call
flow), logs a disposition + notes, and advances. Outcomes roll up into live
connect-rate / conversion stats, and a call against a CRM contact is written
back to that contact's timeline.

The Dialpad HTTP call is isolated behind `place_call()` (module-level `CALLER`)
so the queue/stat logic is pure and unit-testable offline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib import error
from urllib import request as urlrequest

from sqlalchemy.orm import Session

from ..models import (
    CONNECTED_DISPOSITIONS, CrmActivity, CrmContact, DialEntry, DialSession,
)

DIALPAD_CALL_API = "https://dialpad.com/api/v2/call"


class DialerError(Exception):
    """Raised when the upstream Dialpad call can't be placed."""


# --------------------------------------------------------------------------- #
# Dialpad call (isolated + injectable)
# --------------------------------------------------------------------------- #
def _http_call(cfg: dict, number: str) -> str | None:
    """Place a click-to-call via Dialpad. Returns the call id (or None)."""
    from . import secure_config
    api_key = secure_config.get_secret(cfg, "api_key")
    user_id = secure_config.get_secret(cfg, "user_id") or cfg.get("user_id")
    if not (api_key and user_id):
        raise DialerError("Dialpad not configured — add an API key & user in Settings.")
    payload = {"phone_number": number, "user_id": str(user_id)}
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
        detail = e.read().decode(errors="replace")[:200]
        if e.code in (401, 403):
            raise DialerError(f"Dialpad auth failed (HTTP {e.code}) — check the API key.")
        raise DialerError(f"Dialpad HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        raise DialerError(f"Dialpad request failed: {e}")
    return data.get("id") if isinstance(data, dict) else None


# Tests / offline runs override CALLER to avoid real network I/O.
CALLER = _http_call


def place_call(cfg: dict, number: str) -> str | None:
    return CALLER(cfg, number)


# --------------------------------------------------------------------------- #
# Queue management
# --------------------------------------------------------------------------- #
def create_session(db: Session, name: str, items: list[dict], *,
                   owner_user_id: int | None = None,
                   script_id: int | None = None) -> DialSession:
    """Create a session and its queued entries. Items missing a phone are skipped."""
    sess = DialSession(name=(name or "Dial session")[:200], status="active",
                       owner_user_id=owner_user_id, script_id=script_id)
    db.add(sess)
    db.flush()
    pos = 0
    for it in items or []:
        phone = str(it.get("phone") or "").strip()
        if not phone:
            continue
        db.add(DialEntry(
            session_id=sess.id, position=pos, phone=phone,
            name=(it.get("name") or None), company=(it.get("company") or None),
            client_id=it.get("client_id"), crm_contact_id=it.get("crm_contact_id"),
            status="queued"))
        pos += 1
    db.commit()
    db.refresh(sess)
    return sess


def next_entry(db: Session, session_id: int) -> DialEntry | None:
    """The next number to dial: lowest-position entry still queued."""
    return (db.query(DialEntry)
            .filter(DialEntry.session_id == session_id, DialEntry.status == "queued")
            .order_by(DialEntry.position.asc()).first())


def mark_calling(db: Session, entry: DialEntry, call_id: str | None) -> None:
    entry.status = "calling"
    entry.attempts = (entry.attempts or 0) + 1
    entry.call_id = call_id
    entry.dialed_at = datetime.now(timezone.utc)
    db.commit()


def log_disposition(db: Session, entry: DialEntry, disposition: str,
                    notes: str | None, *, user_id: int | None = None) -> None:
    """Record a call outcome, advance the entry, and write back to the CRM."""
    entry.status = "done"
    entry.disposition = disposition
    if notes is not None:
        entry.notes = notes
    # Write the call to the CRM contact's timeline + honor a do-not-call result.
    if entry.crm_contact_id:
        contact = db.get(CrmContact, entry.crm_contact_id)
        if contact:
            db.add(CrmActivity(
                contact_id=contact.id, type="call", direction="outbound",
                subject=f"Power-dial: {disposition}", body=notes or None,
                created_by_user_id=user_id, meta={"disposition": disposition}))
            contact.last_touch_at = datetime.now(timezone.utc)
            if disposition == "do_not_call":
                contact.do_not_contact = True
    db.commit()


def skip_entry(db: Session, entry: DialEntry) -> None:
    entry.status = "skipped"
    db.commit()


def set_status(db: Session, sess: DialSession, status: str) -> None:
    sess.status = status
    if status == "completed":
        sess.completed_at = datetime.now(timezone.utc)
    db.commit()


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
def session_stats(db: Session, session_id: int) -> dict:
    entries = db.query(DialEntry).filter(DialEntry.session_id == session_id).all()
    total = len(entries)
    by_status: dict[str, int] = {}
    by_disp: dict[str, int] = {}
    for e in entries:
        by_status[e.status] = by_status.get(e.status, 0) + 1
        if e.disposition:
            by_disp[e.disposition] = by_disp.get(e.disposition, 0) + 1
    dialed = sum(1 for e in entries if e.status in ("done", "calling")) or 0
    connected = sum(by_disp.get(d, 0) for d in CONNECTED_DISPOSITIONS)
    won = by_disp.get("won", 0)
    remaining = by_status.get("queued", 0)
    completed = sum(1 for e in entries if e.status in ("done", "skipped"))
    return {
        "total": total, "remaining": remaining, "completed": completed,
        "dialed": dialed, "connected": connected, "won": won,
        "connect_rate": round(connected / dialed, 3) if dialed else 0.0,
        "by_status": by_status, "by_disposition": by_disp,
    }
