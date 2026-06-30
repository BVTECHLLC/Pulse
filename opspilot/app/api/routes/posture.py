"""v0.64 Security scorecard routes.

A graded (A–F) posture report per client (endpoints, patching, identity,
threats) plus a staff portfolio view across the whole book. Clients may view
their own scorecard; only staff see the portfolio.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, require_roles
from ...models import Client, Role, User
from ...services import posture, posture_history

router = APIRouter(prefix="/api/posture", tags=["posture"])


@router.get("")
def portfolio(db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Posture overview across every client, riskiest first. Staff only."""
    rows = posture.portfolio(db)
    # Attach the latest trend (delta vs the previous snapshot) per client.
    for r in rows:
        r["trend"] = posture_history.trend(db, r["client_id"])
    return rows


@router.post("/snapshot")
def snapshot_now(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Force a posture snapshot of every client now (ignores the daily throttle)."""
    taken = posture_history.snapshot_all(db, min_interval_hours=0)
    return {"ok": True, "snapshots": taken, "dropped": [t for t in taken if t["dropped"]]}


@router.get("/{client_id}")
def client_scorecard(client_id: int, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """Full graded scorecard for one client. Staff or that client's own users."""
    if not db.get(Client, client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    sc = posture.scorecard(db, client_id)
    sc["trend"] = posture_history.trend(db, client_id)
    return sc


@router.get("/{client_id}/history")
def client_history(client_id: int, limit: int = 60, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    """Posture snapshots over time (oldest→newest). Staff or that client's users."""
    if not db.get(Client, client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    return {"client_id": client_id, "history": posture_history.history(db, client_id, limit)}
