"""v0.68 Fleet software inventory + patch compliance (staff dashboards).

Read-only aggregations across the agent-reported software/patch tables. Staff
see the whole fleet (or filter to a client); a client user is pinned to their own
data so the same views work in the client portal later.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff, require_roles
from ...models import Role, User
from ...services import inventory

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _scope(user: User, client_id: int | None) -> int | None:
    """Staff may pass a client_id (or none for the whole fleet); a client user is
    always constrained to their own client_id."""
    if is_staff(user):
        return client_id
    return user.client_id


@router.get("/software")
def software(q: str = "", client_id: int | None = None, db: Session = Depends(get_db),
             user: User = Depends(current_user)):
    """Installed titles aggregated across the fleet (or one client)."""
    return inventory.software_fleet(db, client_id=_scope(user, client_id), q=q)


@router.get("/software/devices")
def software_devices(name: str = Query(..., min_length=1), client_id: int | None = None,
                     db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Which devices run a given title — vulnerability-response drill-down."""
    if not name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "name is required")
    return {"name": name,
            "devices": inventory.software_devices(db, name, client_id=_scope(user, client_id))}


@router.get("/patches")
def patches(client_id: int | None = None, db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Fleet (or single-client) patch-compliance rollup + worst offenders."""
    return inventory.patch_compliance(db, client_id=client_id)
