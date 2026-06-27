"""Audit logging. Every sensitive action funnels through record()."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    client_id: int | None = None,
    ip: str | None = None,
    detail: str | None = None,
    success: bool = True,
) -> None:
    entry = AuditLog(
        action=action,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        actor_role=actor_role,
        target_type=target_type,
        target_id=target_id,
        client_id=client_id,
        ip=ip,
        detail=detail,
        success=success,
    )
    db.add(entry)
    db.commit()
