"""v0.21 global search — one bar across the whole command center.

Searches clients, devices, tickets, alerts, invoices, licenses, KB articles,
software inventory and integrations, tenant-scoped (staff see all; client users
see only their own client). Returns typed results with a jump target."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff
from ...models import (
    Alert, Client, Device, DeviceSoftware, IntegrationConnection, Invoice,
    KBArticle, License, SupportTicket, User,
)

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(q: str = "", limit: int = 8, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    q = (q or "").strip()
    if len(q) < 2:
        return {"query": q, "results": []}
    like = f"%{q}%"
    cap = max(1, min(limit, 25))
    staff = is_staff(user)
    cid = user.client_id
    out: list[dict] = []

    def scope(query, model):
        return query if staff else query.filter(model.client_id == cid)

    # Clients (staff, or the user's own)
    cq = db.query(Client).filter(or_(Client.name.ilike(like), Client.email.ilike(like),
                                     Client.primary_contact.ilike(like)))
    if not staff:
        cq = cq.filter(Client.id == cid)
    for c in cq.limit(cap).all():
        out.append({"type": "client", "id": c.id, "label": c.name,
                    "sub": c.primary_contact or c.email or "", "tab": "clients"})

    for d in scope(db.query(Device).filter(
            or_(Device.hostname.ilike(like), Device.ip.ilike(like),
                Device.os.ilike(like))), Device).limit(cap).all():
        out.append({"type": "device", "id": d.id, "label": d.hostname,
                    "sub": d.os or d.ip or "", "tab": "devices"})

    for t in scope(db.query(SupportTicket).filter(
            or_(SupportTicket.subject.ilike(like), SupportTicket.body.ilike(like))),
            SupportTicket).limit(cap).all():
        out.append({"type": "ticket", "id": t.id, "label": t.subject,
                    "sub": f"{t.status.value} · {t.priority}", "tab": "tickets"})

    for a in scope(db.query(Alert).filter(Alert.message.ilike(like)), Alert).limit(cap).all():
        out.append({"type": "alert", "id": a.id, "label": a.message[:80],
                    "sub": f"{a.severity.value} · {a.status.value}", "tab": "alerts"})

    for inv in scope(db.query(Invoice).filter(Invoice.number.ilike(like)), Invoice).limit(cap).all():
        out.append({"type": "invoice", "id": inv.id, "label": inv.number,
                    "sub": f"${inv.total or 0:.2f} · {inv.status}", "tab": "billing"})

    for lic in scope(db.query(License).filter(
            or_(License.product.ilike(like), License.vendor.ilike(like))), License).limit(cap).all():
        out.append({"type": "license", "id": lic.id, "label": lic.product,
                    "sub": lic.vendor or "", "tab": "licenses"})

    # KB: staff see all; client users only client-visible docs for their own org
    kq = db.query(KBArticle).filter(or_(KBArticle.title.ilike(like), KBArticle.body.ilike(like)))
    if not staff:
        kq = kq.filter(KBArticle.visibility == "client",
                       or_(KBArticle.client_id.is_(None), KBArticle.client_id == cid))
    for k in kq.limit(cap).all():
        out.append({"type": "kb", "id": k.id, "label": k.title,
                    "sub": "knowledge base", "tab": "kb"})

    for sw in scope(db.query(DeviceSoftware).filter(DeviceSoftware.name.ilike(like)),
                    DeviceSoftware).limit(cap).all():
        out.append({"type": "software", "id": sw.device_id, "label": sw.name,
                    "sub": (sw.version or "") + " · device #%d" % sw.device_id, "tab": "devices"})

    if staff:
        for ic in db.query(IntegrationConnection).filter(
                IntegrationConnection.name.ilike(like)).limit(cap).all():
            out.append({"type": "integration", "id": ic.id, "label": ic.name,
                        "sub": ic.category or "integration", "tab": "integrations"})

    return {"query": q, "count": len(out), "results": out}
