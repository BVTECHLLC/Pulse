"""v0.76 MSP Practice Health — the MSP's own A–F operating grade (staff-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import practice_health

router = APIRouter(prefix="/api/practice", tags=["practice"])


@router.get("/health")
def health(db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """One graded scorecard for how the MSP practice itself is performing."""
    return practice_health.practice_health(db)
