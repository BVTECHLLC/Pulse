"""v1.19 Incident Intelligence API — correlated alert storms, tenant-scoped."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user
from ...models import User
from ...services import incidents

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("")
def list_incidents(status: str | None = None, limit: int = 50,
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"incidents": incidents.list_incidents(db, user, status=status, limit=limit)}
