"""v0.45 Campaigns — outreach to CRM contacts over email (M365) and SMS (Dialpad).

Compliance is built in, not bolted on:
  * Email respects ``do_not_contact`` (CAN-SPAM) and appends an opt-out footer.
  * SMS only goes to contacts with ``sms_opt_in`` (TCPA express consent).
Every send is logged to the contact's CRM timeline. ``dry_run`` previews without
sending. The actual transport (``send_fn``) is injected, so the selection /
personalization / compliance / logging path is unit-testable with no network.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import CrmContact
from . import crm


def personalize(template: str, c: CrmContact) -> str:
    """Fill {name}/{first}/{company} placeholders from a contact."""
    first = (c.name or "").split(" ")[0] if c.name else ""
    return (template or "").replace("{name}", c.name or "there") \
                           .replace("{first}", first or "there") \
                           .replace("{company}", c.company or "your team")


def email_footer(sender: str) -> str:
    return ("\n\n—\nYou received this because we believe managed IT may help your "
            "business. Reply STOP or let us know to opt out and we won't contact "
            f"you again.\nSent by {sender}.")


def select_contacts(db: Session, *, ids: list[int] | None, status: str | None,
                    market: str | None, channel: str) -> list[CrmContact]:
    """Resolve the audience and apply per-channel compliance filters."""
    q = db.query(CrmContact)
    if ids:
        q = q.filter(CrmContact.id.in_(ids))
    if status:
        q = q.filter(CrmContact.status == status)
    if market:
        q = q.filter(CrmContact.market == market)
    rows = q.all()
    if channel == "email":
        return [c for c in rows if c.email and not c.do_not_contact]
    if channel == "sms":
        return [c for c in rows if c.phone and c.sms_opt_in and not c.do_not_contact]
    return rows


def run_email(db: Session, send_fn, contacts: list[CrmContact], subject: str,
              body: str, sender: str, *, dry_run: bool = False,
              user_id: int | None = None) -> dict:
    """send_fn(to: str, subject: str, body: str) -> None. Logs + returns counts."""
    sent, failed, errors = 0, 0, []
    footer = email_footer(sender)
    for c in contacts:
        msg = personalize(body, c) + footer
        subj = personalize(subject, c)
        if dry_run:
            continue
        try:
            send_fn(c.email, subj, msg)
        except Exception as e:  # noqa: BLE001
            failed += 1
            errors.append({"contact_id": c.id, "error": str(e)[:160]})
            continue
        sent += 1
        crm.log_activity(db, c, "email", subject=subj, body=msg[:1000],
                         direction="outbound", user_id=user_id, commit=False)
    if not dry_run:
        db.commit()
    return {"audience": len(contacts), "sent": sent, "failed": failed,
            "dry_run": dry_run, "errors": errors[:10]}


def run_sms(db: Session, send_fn, contacts: list[CrmContact], text: str, *,
            dry_run: bool = False, user_id: int | None = None) -> dict:
    """send_fn(to: str, text: str) -> None. Logs + returns counts."""
    sent, failed, errors = 0, 0, []
    for c in contacts:
        msg = personalize(text, c)
        if dry_run:
            continue
        try:
            send_fn(c.phone, msg)
        except Exception as e:  # noqa: BLE001
            failed += 1
            errors.append({"contact_id": c.id, "error": str(e)[:160]})
            continue
        sent += 1
        crm.log_activity(db, c, "sms", subject="SMS", body=msg[:500],
                         direction="outbound", user_id=user_id, commit=False)
    if not dry_run:
        db.commit()
    return {"audience": len(contacts), "sent": sent, "failed": failed,
            "dry_run": dry_run, "errors": errors[:10]}
