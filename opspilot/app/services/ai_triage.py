"""v1.1 AI ticket triage — Claude reads every new ticket so a human doesn't have to.

Within ~2 minutes of a ticket arriving (the Autopilot heartbeat), Claude:
  * suggests a priority (low|normal|high|urgent),
  * writes a one-line summary + a concrete first troubleshooting step,
  * leaves it all as an internal note the whole team can see.

Suggestions never silently change the ticket — unless the owner turns on
auto-apply, in which case a HIGHER suggested priority is applied (never lowered:
AI can raise the alarm, only a human can lower it) and the SLA due dates are
re-stamped to match.

Degrades to a clean no-op when Claude isn't connected. Fully offline-testable
via ai._CALLER.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import PRIORITIES, SupportTicket, TicketComment, TicketStatus
from . import ai, secure_config, sla

_PROVIDER = "ai_triage"
_TRUTHY = {"1", "true", "yes", "on"}

_SYSTEM = (
    "You are the triage engine of an MSP helpdesk (managed IT services). "
    "Read the ticket and reply with ONLY a JSON object — no prose, no markdown "
    "fences — with exactly these keys:\n"
    '  "priority": one of "low", "normal", "high", "urgent" — how fast a tech '
    "must respond. Business-down or security incidents are urgent; single-user "
    "blockers are high; questions and nice-to-haves are low/normal.\n"
    '  "summary": ONE sentence, max 140 chars, stating the actual problem.\n'
    '  "next_step": the single most useful first action for the technician, '
    "max 200 chars, specific to this ticket."
)


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, _PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {
        "enabled": str(cfg.get("enabled", "true")).lower() in _TRUTHY,
        "auto_apply": str(cfg.get("auto_apply", "false")).lower() in _TRUTHY,
        "ai_connected": ai.enabled(),
    }


def save_config(db: Session, *, enabled: bool | None = None,
                auto_apply: bool | None = None) -> dict:
    payload: dict[str, str] = {}
    if enabled is not None:
        payload["enabled"] = "true" if enabled else "false"
    if auto_apply is not None:
        payload["auto_apply"] = "true" if auto_apply else "false"
    if payload:
        secure_config.upsert_platform(db, _PROVIDER, "AI Ticket Triage", "AI", payload)
    return get_config(db)


def _parse(raw: str) -> dict | None:
    """Extract the JSON object from a model reply, tolerating stray text/fences."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        out = json.loads(raw[start:end + 1])
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(out, dict):
        return None
    pr = str(out.get("priority", "")).lower().strip()
    if pr not in PRIORITIES:
        return None
    return {"priority": pr,
            "summary": str(out.get("summary", "")).strip()[:300],
            "next_step": str(out.get("next_step", "")).strip()[:400]}


def triage_ticket(db: Session, t: SupportTicket,
                  now: datetime | None = None) -> dict | None:
    """Run Claude triage on one ticket and persist the result. Returns the
    suggestion dict, or None when parsing failed (ticket left untriaged so a
    later sweep retries)."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    user_msg = (f"Subject: {t.subject}\n"
                f"Reported priority: {t.priority}\n"
                f"Body:\n{(t.body or '(no body)')[:4000]}")
    raw = ai.complete(_SYSTEM, user_msg, max_tokens=300)
    parsed = _parse(raw)
    if not parsed:
        return None

    t.ai_priority = parsed["priority"]
    t.ai_summary = parsed["summary"]
    t.ai_next_step = parsed["next_step"]
    t.ai_triaged_at = now

    applied = False
    cur = t.priority if t.priority in PRIORITIES else "normal"
    if (cfg["auto_apply"]
            and PRIORITIES.index(parsed["priority"]) > PRIORITIES.index(cur)):
        t.priority = parsed["priority"]
        sla.stamp_due_dates(db, t)   # tighter priority ⇒ tighter SLA clock
        applied = True

    note = (f"🤖 AI triage: {parsed['summary']}\n"
            f"Suggested priority: {parsed['priority']}"
            + (" (applied — was " + cur + ")" if applied else "")
            + f"\nFirst step: {parsed['next_step']}")
    db.add(TicketComment(ticket_id=t.id, author_email="pulse-ai",
                         author_role="ai", body=note, internal=True))
    db.commit()
    return {**parsed, "applied": applied, "ticket_id": t.id}


def sweep(db: Session, now: datetime | None = None, limit: int = 5) -> list[dict]:
    """Triage up to `limit` untriaged open tickets. Called by the Autopilot
    heartbeat; cheap no-op when disabled, AI-less, or nothing is pending.
    Per-ticket best-effort: one API failure doesn't poison the batch, and the
    failed ticket stays untriaged so the next tick retries it."""
    cfg = get_config(db)
    if not (cfg["enabled"] and cfg["ai_connected"]):
        return []
    pending = (db.query(SupportTicket)
               .filter(SupportTicket.ai_triaged_at.is_(None),
                       SupportTicket.status.in_([TicketStatus.OPEN,
                                                 TicketStatus.IN_PROGRESS]))
               .order_by(SupportTicket.id.asc())
               .limit(limit).all())
    out: list[dict] = []
    for t in pending:
        try:
            res = triage_ticket(db, t, now)
            if res:
                out.append(res)
        except Exception:  # noqa: BLE001
            db.rollback()
    return out
