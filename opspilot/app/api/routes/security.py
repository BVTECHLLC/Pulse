"""v0.6 security posture routes: authorized assessments, findings (vulnerability
tracking + remediation), and a per-client security scorecard.

Ethos: this module is DEFENSIVE. It documents and helps remediate weaknesses.
It does not scan, exploit, or run anything. Assessments must name an authorizing
party at the client (so there's always a record of consent for the engagement).

RBAC: staff manage assessments & findings. Clients can read their own scorecard
and only the findings explicitly marked client_visible.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import (
    AssessmentStatus, Client, Device, FindingSeverity, FindingStatus, Role,
    SecurityAssessment, SecurityFinding, User,
)
from ...services import audit, automation, security

router = APIRouter(prefix="/api/security", tags=["security"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Assessments
# --------------------------------------------------------------------------- #
class AssessmentIn(BaseModel):
    client_id: int
    title: str
    scope: str | None = None
    authorized_by: str  # REQUIRED — who at the client authorized this engagement


def _serialize_assessment(a: SecurityAssessment) -> dict:
    return {
        "id": a.id, "client_id": a.client_id, "title": a.title, "scope": a.scope,
        "authorized_by": a.authorized_by, "status": a.status.value, "summary": a.summary,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "created_at": a.created_at.isoformat(),
    }


@router.post("/assessments", status_code=201)
def create_assessment(body: AssessmentIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    if not body.authorized_by.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "authorized_by is required — record who authorized this engagement")
    a = SecurityAssessment(client_id=body.client_id, title=body.title[:200], scope=body.scope,
                           authorized_by=body.authorized_by.strip(),
                           created_by_user_id=user.id, author_email=user.email)
    db.add(a)
    db.commit()
    audit.record(db, action="security.assessment_create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="security_assessment", target_id=str(a.id),
                 client_id=body.client_id, ip=_ip(request), detail=f"authorized_by={a.authorized_by[:60]}")
    return {"id": a.id}


@router.get("/assessments")
def list_assessments(client_id: int | None = None, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    q = db.query(SecurityAssessment)
    if client_id:
        q = q.filter(SecurityAssessment.client_id == client_id)
    return [_serialize_assessment(a) for a in q.order_by(SecurityAssessment.created_at.desc()).all()]


class AssessmentUpdate(BaseModel):
    status: AssessmentStatus | None = None
    summary: str | None = None


@router.patch("/assessments/{assessment_id}")
def update_assessment(assessment_id: int, body: AssessmentUpdate, request: Request,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    a = db.get(SecurityAssessment, assessment_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    now = datetime.now(timezone.utc)
    if body.status is not None:
        a.status = body.status
        if body.status == AssessmentStatus.IN_PROGRESS and not a.started_at:
            a.started_at = now
        if body.status == AssessmentStatus.COMPLETED and not a.completed_at:
            a.completed_at = now
    if body.summary is not None:
        a.summary = body.summary
    db.commit()
    audit.record(db, action="security.assessment_update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="security_assessment", target_id=str(a.id),
                 client_id=a.client_id, ip=_ip(request), detail=f"status={a.status.value}")
    return _serialize_assessment(a)


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #
class FindingIn(BaseModel):
    client_id: int
    title: str
    severity: FindingSeverity = FindingSeverity.MEDIUM
    device_id: int | None = None
    assessment_id: int | None = None
    category: str | None = None
    cve: str | None = None
    description: str | None = None
    recommendation: str | None = None
    client_visible: bool = False


def _serialize_finding(f: SecurityFinding) -> dict:
    return {
        "id": f.id, "client_id": f.client_id, "device_id": f.device_id,
        "assessment_id": f.assessment_id, "title": f.title, "category": f.category,
        "severity": f.severity.value, "cve": f.cve, "description": f.description,
        "recommendation": f.recommendation, "status": f.status.value,
        "source": f.source, "client_visible": f.client_visible,
        "discovered_at": f.discovered_at.isoformat() if f.discovered_at else None,
        "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
    }


@router.post("/findings", status_code=201)
def create_finding(body: FindingIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    if body.device_id is not None:
        dev = db.get(Device, body.device_id)
        if not dev or dev.client_id != body.client_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Device not in this client")

    f = SecurityFinding(
        client_id=body.client_id, device_id=body.device_id, assessment_id=body.assessment_id,
        title=body.title[:200], category=body.category, severity=body.severity, cve=body.cve,
        description=body.description, recommendation=body.recommendation,
        client_visible=body.client_visible,
        source="assessment" if body.assessment_id else "manual",
        created_by_user_id=user.id, author_email=user.email,
    )
    db.add(f)
    db.flush()  # need f.id before raising a linked alert

    # High/critical findings raise an alert so the dashboard + automation see them.
    alert = security.raise_finding_alert(db, f)
    db.commit()
    audit.record(db, action="security.finding_create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="security_finding", target_id=str(f.id),
                 client_id=body.client_id, ip=_ip(request),
                 detail=f"severity={f.severity.value} cve={f.cve or '-'}")
    if alert is not None:
        automation.dispatch(db, "alert.opened",
                            automation.build_alert_context(alert, db.get(Device, f.device_id) if f.device_id else None))
    return {"id": f.id, "alert_raised": alert is not None}


@router.get("/findings")
def list_findings(client_id: int | None = None, status_filter: str | None = None,
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(SecurityFinding)
    if is_staff(user):
        if client_id:
            q = q.filter(SecurityFinding.client_id == client_id)
    else:
        # Clients see only their own client's findings that are explicitly shared.
        q = q.filter(SecurityFinding.client_id == user.client_id,
                     SecurityFinding.client_visible.is_(True))
    if status_filter:
        q = q.filter(SecurityFinding.status == status_filter)
    rows = q.order_by(SecurityFinding.discovered_at.desc()).limit(500).all()
    return [_serialize_finding(f) for f in rows]


class FindingUpdate(BaseModel):
    status: FindingStatus | None = None
    severity: FindingSeverity | None = None
    recommendation: str | None = None
    client_visible: bool | None = None


@router.patch("/findings/{finding_id}")
def update_finding(finding_id: int, body: FindingUpdate, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    f = db.get(SecurityFinding, finding_id)
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found")
    if body.severity is not None:
        f.severity = body.severity
    if body.recommendation is not None:
        f.recommendation = body.recommendation
    if body.client_visible is not None:
        f.client_visible = body.client_visible
    if body.status is not None:
        f.status = body.status
        if body.status in (FindingStatus.RESOLVED, FindingStatus.RISK_ACCEPTED):
            f.resolved_at = datetime.now(timezone.utc)
            f.resolved_by_user_id = user.id
            security.resolve_finding_alert(db, f)  # close the linked alert too
        elif body.status in (FindingStatus.OPEN, FindingStatus.REMEDIATING):
            f.resolved_at = None
    db.commit()
    audit.record(db, action="security.finding_update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="security_finding", target_id=str(f.id),
                 client_id=f.client_id, ip=_ip(request), detail=f"status={f.status.value}")
    return _serialize_finding(f)


# --------------------------------------------------------------------------- #
# Scorecard
# --------------------------------------------------------------------------- #
@router.get("/scorecard")
def scorecard(client_id: int | None = None, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    """Staff: scorecards for all clients (or one via client_id). Client users:
    only their own client's posture score."""
    if is_staff(user):
        if client_id:
            return security.scorecard(db, client_id)
        clients = db.query(Client).all()
        return [security.scorecard(db, c.id) for c in clients]
    if not user.client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No client associated")
    return security.scorecard(db, user.client_id)
