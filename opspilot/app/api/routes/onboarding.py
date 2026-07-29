"""v1.70 Client onboarding wizard API.

Staff get any client's onboarding state; a client's own users get their own
(same tenant rule as the QBR/vCIO views). Every step is computed from live data,
so this also answers "is this existing client fully set up?" at a glance.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff
from ...models import Client, User
from ...services import onboarding

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.get("/{client_id}")
def client_onboarding(client_id: int, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    return onboarding.wizard(db, client)


@router.get("")
def onboarding_overview(db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    """Staff: onboarding progress across every client — spot who's stalled.
    Client users get just their own client's card."""
    q = db.query(Client).filter(Client.is_active.is_(True))
    if not is_staff(user):
        if not user.client_id:
            return {"clients": []}
        q = q.filter(Client.id == user.client_id)
    out = []
    for c in q.order_by(Client.name).all():
        w = onboarding.wizard(db, c)
        out.append({"client_id": c.id, "client": c.name, "percent": w["percent"],
                    "complete": w["complete"], "required_done": w["required_done"],
                    "required_total": w["required_total"],
                    "next_step": w["next_step"]})
    out.sort(key=lambda r: (r["complete"], r["percent"]))   # least-done first
    return {"clients": out}
