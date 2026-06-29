"""v0.33 Client Health Score API — explainable 0-100 posture per client.

Staff get the whole portfolio (worst first); a client user sees only their own
org. Read-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff
from ...models import Client, User
from ...services import client_health as ch

router = APIRouter(prefix="/api", tags=["client-health"])


@router.get("/clients/health")
def clients_health(db: Session = Depends(get_db), user: User = Depends(current_user)):
    staff = is_staff(user)
    scope = None if staff else ([user.client_id] if user.client_id else [])
    rows = ch.score_all(db, scope)
    portfolio = round(sum(r["score"] for r in rows) / len(rows)) if rows else None
    return {
        "portfolio_score": portfolio,
        "count": len(rows),
        "at_risk": sum(1 for r in rows if r["risk"] == "high"),
        "clients": rows,
    }


@router.get("/clients/{client_id}/health")
def one_client_health(client_id: int, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    assert_client_access(user, client_id)
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return ch.score_client(db, client)
