"""v1.11 Pulse Copilot — agentic AI over the whole platform.

POST /api/copilot/ask runs Claude's tool-use loop server-side against a governed,
tenant-scoped toolset. Read tools run freely; write tools only execute when
`allow_actions` is true (so the UI can propose, then confirm).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user
from ...models import User
from ...services import ai, audit, copilot

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


class AskIn(BaseModel):
    message: str
    allow_actions: bool = False


@router.post("/ask")
def ask(body: AskIn, request: Request, db: Session = Depends(get_db),
        user: User = Depends(current_user)):
    if not ai.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Claude isn't connected yet — add your Anthropic API key on the server.")
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ask something.")
    try:
        out = copilot.run(db, user, msg, allow_actions=body.allow_actions)
    except ai.AIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    if out.get("actions"):
        audit.record(db, action="copilot.action", actor_user_id=user.id,
                     actor_email=user.email, actor_role=user.role.value,
                     target_type="copilot", ip=_ip(request),
                     detail=f"tools={out.get('tools_used')} actions={len(out['actions'])}")
    return out
