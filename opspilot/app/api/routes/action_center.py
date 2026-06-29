"""v0.32 Action Center API.

One tenant-scoped call returns a ranked, explainable list of everything that
needs a human's attention right now — across RMM, PSA, security, and billing —
plus an overall Ops Score. The heavy lifting lives in services/action_center.py;
this route just resolves scope/RBAC and serializes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff
from ...models import User
from ...services import action_center as ac

router = APIRouter(prefix="/api", tags=["action-center"])


@router.get("/action-center")
def get_action_center(
    client_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    staff = is_staff(user)
    # A client user is pinned to their own org; a filter to a foreign client is denied.
    if client_id is not None and not staff:
        assert_client_access(user, client_id)
    return ac.build(db, user, client_id=client_id, limit=limit, is_staff=staff)
