"""v0.43 CRM — our native lead/contact pipeline (replaces SuperOps' CRM side).

Staff-only. Prospecting feeds contacts in, campaigns/dialer act on them, and a
qualified contact converts straight into a managed Client. Every touch lands on
the contact's activity timeline.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Client, CRM_STATUSES, CrmActivity, CrmContact, Role, User
from ...services import audit, crm

router = APIRouter(prefix="/api/crm", tags=["crm"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _get(db: Session, contact_id: int) -> CrmContact:
    c = db.get(CrmContact, contact_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found")
    return c


# --------------------------------------------------------------------------- #
# Pipeline summary
# --------------------------------------------------------------------------- #
@router.get("/pipeline")
def pipeline(db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    counts = {s: 0 for s in CRM_STATUSES}
    for c in db.query(CrmContact.status).all():
        counts[c.status] = counts.get(c.status, 0) + 1
    return {"statuses": list(CRM_STATUSES), "counts": counts, "total": sum(counts.values())}


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #
@router.get("/contacts")
def list_contacts(status_filter: str | None = Query(None, alias="status"),
                  source: str | None = Query(None), q: str | None = Query(None),
                  limit: int = Query(200, le=1000, ge=1),
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    query = db.query(CrmContact)
    if status_filter:
        query = query.filter(CrmContact.status == status_filter)
    if source:
        query = query.filter(CrmContact.source == source)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(CrmContact.name.ilike(like), CrmContact.email.ilike(like),
                                 CrmContact.company.ilike(like)))
    rows = query.order_by(CrmContact.last_touch_at.desc().nullslast(),
                          CrmContact.created_at.desc()).limit(limit).all()
    return {"contacts": [crm.serialize_contact(c) for c in rows]}


class ContactIn(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str | None = "manual"
    status: str | None = "new"
    score: int | None = None
    market: str | None = None
    website: str | None = None
    address: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    do_not_contact: bool | None = None
    sms_opt_in: bool | None = None


@router.post("/contacts", status_code=201)
def create_contact(body: ContactIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "name is required")
    st = (body.status or "new").lower()
    if st not in CRM_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"status must be one of {CRM_STATUSES}")
    c = CrmContact(name=body.name.strip(), email=body.email, phone=body.phone,
                   company=body.company, title=body.title, source=body.source or "manual",
                   status=st, score=body.score, market=body.market, website=body.website,
                   address=body.address, notes=body.notes, tags=body.tags or [],
                   do_not_contact=bool(body.do_not_contact), sms_opt_in=bool(body.sms_opt_in),
                   owner_user_id=user.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    crm.log_activity(db, c, "status", subject="Created", body=f"source={c.source}", user_id=user.id)
    audit.record(db, action="crm.contact.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="crm_contact", target_id=str(c.id),
                 ip=_ip(request), detail=c.company or c.name)
    return crm.serialize_contact(c)


@router.get("/contacts/{contact_id}")
def get_contact(contact_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = _get(db, contact_id)
    acts = (db.query(CrmActivity).filter(CrmActivity.contact_id == contact_id)
            .order_by(CrmActivity.created_at.desc()).limit(200).all())
    return {"contact": crm.serialize_contact(c),
            "activities": [crm.serialize_activity(a) for a in acts]}


class ContactUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    status: str | None = None
    score: int | None = None
    market: str | None = None
    website: str | None = None
    address: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    do_not_contact: bool | None = None
    sms_opt_in: bool | None = None


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: int, body: ContactUpdate, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = _get(db, contact_id)
    data = body.model_dump(exclude_unset=True)
    old_status = c.status
    if "status" in data and data["status"]:
        if data["status"].lower() not in CRM_STATUSES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"status must be one of {CRM_STATUSES}")
        data["status"] = data["status"].lower()
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    if data.get("status") and data["status"] != old_status:
        crm.log_activity(db, c, "status", subject=f"{old_status} → {c.status}", user_id=user.id)
    audit.record(db, action="crm.contact.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="crm_contact", target_id=str(c.id),
                 ip=_ip(request), detail=",".join(data.keys()))
    return crm.serialize_contact(c)


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    c = _get(db, contact_id)
    db.query(CrmActivity).filter(CrmActivity.contact_id == contact_id).delete()
    db.delete(c)
    db.commit()
    audit.record(db, action="crm.contact.delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="crm_contact", target_id=str(contact_id),
                 ip=_ip(request))


# --------------------------------------------------------------------------- #
# Activity timeline
# --------------------------------------------------------------------------- #
class ActivityIn(BaseModel):
    type: str = "note"            # note|email|call|sms|meeting
    subject: str | None = None
    body: str | None = None
    direction: str | None = None  # outbound|inbound


@router.post("/contacts/{contact_id}/activity", status_code=201)
def add_activity(contact_id: int, body: ActivityIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = _get(db, contact_id)
    if body.type not in ("note", "email", "call", "sms", "meeting", "status"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid activity type")
    a = crm.log_activity(db, c, body.type, subject=body.subject, body=body.body,
                         direction=body.direction, user_id=user.id)
    return crm.serialize_activity(a)


# --------------------------------------------------------------------------- #
# Convert a qualified contact into a managed Client (ties CRM → client list)
# --------------------------------------------------------------------------- #
@router.post("/contacts/{contact_id}/convert")
def convert_to_client(contact_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = _get(db, contact_id)
    if c.client_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Contact is already linked to a client")
    client = Client(name=c.company or c.name, primary_contact=c.name, email=c.email,
                    phone=c.phone, is_active=True)
    db.add(client)
    db.commit()
    db.refresh(client)
    c.client_id = client.id
    c.status = "customer"
    db.commit()
    crm.log_activity(db, c, "status", subject="Converted to client",
                     body=f"client_id={client.id}", user_id=user.id)
    audit.record(db, action="crm.contact.convert", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="crm_contact", target_id=str(c.id),
                 client_id=client.id, ip=_ip(request), detail=f"client={client.name}")
    return {"ok": True, "client_id": client.id, "client_name": client.name,
            "contact": crm.serialize_contact(c)}
