"""v1.154 Canned responses (reply templates) for the service desk.

Staff save common ticket replies once — "Password reset steps", "Resolved,
please confirm", "We're on it", onboarding checklists — and insert them into any
ticket comment with one click, with {placeholders} filled from the ticket. A
real time-saver for a busy MSP desk.

Stored as a JSON list in the vault (not secret), so there's no migration; each
template is {id, title, body}. Placeholders: {client_name} {ticket_id}
{ticket_subject} {tech_name} {company}."""
from __future__ import annotations

import re
import secrets

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "canned_responses"
MAX_TEMPLATES = 100
_VALID = re.compile(r"\{(client_name|ticket_id|ticket_subject|tech_name|company)\}")

# Shipped defaults so the feature is useful on day one (only seeded when empty).
_SEED = [
    {"title": "Acknowledged — we're on it",
     "body": "Hi {client_name},\n\nThanks for reaching out — we've received ticket #{ticket_id} "
             "(\"{ticket_subject}\") and the BVTech team is looking into it now. We'll follow up "
             "shortly with an update.\n\n— {tech_name}, {company}"},
    {"title": "Resolved — please confirm",
     "body": "Hi {client_name},\n\nWe believe ticket #{ticket_id} is resolved. Please take a moment "
             "to confirm everything's working on your end, and we'll close it out. If anything's "
             "still off, just reply here.\n\nThanks,\n{tech_name} — {company}"},
    {"title": "Password reset steps",
     "body": "Hi {client_name},\n\nTo reset your password:\n1. Go to the sign-in page and choose "
             "\"Forgot password\".\n2. Enter your work email and submit.\n3. Check your inbox for the "
             "reset link (check spam too).\n4. Set a new, unique password and store it in your "
             "password manager.\n\nIf the email doesn't arrive in 5 minutes, reply here and we'll "
             "reset it for you.\n\n— {tech_name}, {company}"},
    {"title": "Need a bit more info",
     "body": "Hi {client_name},\n\nTo get ticket #{ticket_id} moving we need a little more detail:\n"
             "• What were you doing when the issue happened?\n• Any error message (a screenshot is "
             "perfect)?\n• Which device / app?\n\nThanks — this helps us fix it fast.\n\n{tech_name}, {company}"},
]


def _load(db: Session) -> list[dict]:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return list(cfg.get("items") or [])


def _save(db: Session, items: list[dict]) -> None:
    secure_config.upsert_platform(db, PROVIDER, "Canned Responses", "Service Desk",
                                  {"items": items[:MAX_TEMPLATES]})


def list_templates(db: Session, *, seed: bool = True) -> list[dict]:
    items = _load(db)
    if not items and seed:
        items = [{"id": secrets.token_hex(6), **t} for t in _SEED]
        _save(db, items)
    return items


def add(db: Session, title: str, body: str) -> dict:
    title = (title or "").strip()[:120]
    body = (body or "").strip()[:4000]
    if not title or not body:
        raise ValueError("title and body are required")
    items = list_templates(db, seed=False)
    tpl = {"id": secrets.token_hex(6), "title": title, "body": body}
    items.append(tpl)
    _save(db, items)
    return tpl


def delete(db: Session, tid: str) -> bool:
    items = list_templates(db, seed=False)
    new = [t for t in items if t.get("id") != tid]
    if len(new) == len(items):
        return False
    _save(db, new)
    return True


def render(body: str, ctx: dict) -> str:
    """Fill {placeholders} from a context dict; unknown placeholders are left as-is."""
    def sub(m):
        key = m.group(1)
        v = ctx.get(key)
        return str(v) if v not in (None, "") else m.group(0)
    return _VALID.sub(sub, body or "")
