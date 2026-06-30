"""v0.43 CRM service — small helpers shared by the CRM routes and (later) the
prospecting + campaign engines.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import CrmActivity, CrmContact


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def log_activity(db: Session, contact: CrmContact, type_: str, *, subject: str | None = None,
                 body: str | None = None, direction: str | None = None,
                 meta: dict | None = None, user_id: int | None = None,
                 commit: bool = True) -> CrmActivity:
    """Append a timeline entry and bump the contact's last-touch timestamp."""
    act = CrmActivity(contact_id=contact.id, type=type_, subject=subject, body=body,
                      direction=direction, meta=meta or {}, created_by_user_id=user_id)
    db.add(act)
    contact.last_touch_at = _utcnow()
    if commit:
        db.commit()
        db.refresh(act)
    return act


def serialize_contact(c: CrmContact) -> dict:
    return {
        "id": c.id, "name": c.name, "email": c.email, "phone": c.phone,
        "company": c.company, "title": c.title, "source": c.source, "status": c.status,
        "score": c.score, "market": c.market, "website": c.website, "address": c.address,
        "notes": c.notes, "tags": c.tags or [], "do_not_contact": c.do_not_contact,
        "sms_opt_in": c.sms_opt_in, "client_id": c.client_id, "owner_user_id": c.owner_user_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "last_touch_at": c.last_touch_at.isoformat() if c.last_touch_at else None,
    }


def serialize_activity(a: CrmActivity) -> dict:
    return {
        "id": a.id, "type": a.type, "direction": a.direction, "subject": a.subject,
        "body": a.body, "meta": a.meta or {}, "created_by_user_id": a.created_by_user_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
