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
from ...services import posture

router = APIRouter(prefix="/api/posture", tags=["posture"])


@router.get("")
def portfolio(db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Posture overview across every client, riskiest first. Staff only."""
    return posture.portfolio(db)


@router.get("/{client_id}")
def client_scorecard(client_id: int, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """Full graded scorecard for one client. Staff or that client's own users."""
    if not db.get(Client, client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    return posture.scorecard(db, client_id)
