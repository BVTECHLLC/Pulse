"""v0.40 Analytics API — SLA performance metrics. Tenant-scoped, read-only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff
from ...models import User
from ...services import analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/sla-performance")
def sla_performance(client_id: int | None = Query(default=None),
                    days: int = Query(default=90, ge=1, le=365),
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    staff = is_staff(user)
    if client_id is not None and not staff:
        assert_client_access(user, client_id)
    if not staff:
        scope = [user.client_id] if user.client_id else []
    elif client_id is not None:
        scope = [client_id]
    else:
        scope = None
    return analytics.sla_performance(db, scope, days=days)
