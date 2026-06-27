"""Public access-request ('sign up') flow + staff review.

A submission creates a lead and emails both the requester (confirmation) and
SUPPORT_EMAIL (notice). It does NOT create an account — staff provision access
deliberately. Open self-provisioning into an MSP console would be unsafe.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, SignupRequest, User
from ...services import audit, email

router = APIRouter(prefix="/api", tags=["signup"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


class SignupIn(BaseModel):
    name: str
    email: EmailStr
    company: str | None = None
    message: str | None = None


@router.post("/signup", status_code=201)
def submit_signup(body: SignupIn, request: Request, db: Session = Depends(get_db)):
    """PUBLIC — no auth. Rate-limited in middleware (see main.py)."""
    if not body.name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name is required")
    req = SignupRequest(name=body.name.strip()[:200], email=str(body.email).lower(),
                        company=(body.company or None), message=(body.message or None),
                        ip=_ip(request))
    db.add(req)
    db.commit()
    audit.record(db, action="signup.request", actor_email=req.email, ip=_ip(request),
                 target_type="signup_request", target_id=str(req.id),
                 detail=f"company={req.company or '-'}")
    # Fire-and-forget notifications (no-op if SMTP unconfigured).
    email.send_signup_confirmation(req.email, req.name)
    email.send_signup_notice(req.name, req.email, req.company, req.message)
    return {"ok": True, "message": "Thanks! We'll be in touch shortly."}


@router.get("/signup-requests")
def list_signups(status_filter: str | None = None, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    q = db.query(SignupRequest)
    if status_filter:
        q = q.filter(SignupRequest.status == status_filter)
    rows = q.order_by(SignupRequest.created_at.desc()).limit(200).all()
    return [
        {"id": r.id, "name": r.name, "email": r.email, "company": r.company,
         "message": r.message, "status": r.status, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


class SignupUpdate(BaseModel):
    status: str


@router.patch("/signup-requests/{req_id}")
def update_signup(req_id: int, body: SignupUpdate, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if body.status not in ("new", "contacted", "approved", "rejected"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
    r = db.get(SignupRequest, req_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    r.status = body.status
    db.commit()
    audit.record(db, action="signup.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="signup_request", target_id=str(r.id),
                 ip=_ip(request), detail=f"status={r.status}")
    return {"id": r.id, "status": r.status}
