"""v1.23 Browser & SaaS Guardian API — SaaS/extension inventory + governance."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, require_roles
from ...models import Client, Role, User
from ...services import audit, browser_guard

router = APIRouter(prefix="/api/browser", tags=["browser"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


@router.get("/inventory/{client_id}")
def inventory(client_id: int, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    """SaaS + extension rollup for one client. Staff, or the client's own users
    (they can see their own app landscape — read-only)."""
    if not db.get(Client, client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    assert_client_access(user, client_id)
    return browser_guard.inventory(db, client_id)


class DecideIn(BaseModel):
    client_id: int
    identifier: str
    action: str   # approve | block | clear


@router.post("/decide")
def decide(body: DecideIn, request: Request, db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    try:
        out = browser_guard.decide(db, body.client_id, body.identifier, body.action)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    audit.record(db, action=f"browser.{body.action}", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="browser_item", target_id=out["identifier"], ip=_ip(request),
                 detail=f"client={body.client_id}")
    return out


class ProtectIn(BaseModel):
    client_id: int
    protect: bool


@router.put("/protect")
def protect(body: ProtectIn, request: Request, db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    out = browser_guard.set_protect(db, body.client_id, body.protect)
    audit.record(db, action="browser.protect", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="browser_policy", target_id=str(body.client_id),
                 ip=_ip(request), detail=f"protect={body.protect}")
    return out
