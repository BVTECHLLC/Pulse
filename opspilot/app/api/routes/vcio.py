"""v1.16 AI vCIO API — automated technology business reviews + roadmap.

Staff get any client's review; a client's own users can read their own (like the
QBR summary). The AI narrative is opt-in via ?narrative=true.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user
from ...models import Client, User
from ...services import vcio

router = APIRouter(prefix="/api/vcio", tags=["vcio"])


@router.get("/{client_id}/review")
def review(client_id: int, narrative: bool = False, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    return vcio.build_review(db, client, datetime.now(timezone.utc), with_narrative=narrative)
