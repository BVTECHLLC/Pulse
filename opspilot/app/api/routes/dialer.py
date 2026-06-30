"""v0.60 Power dialer + call coaching.

Staff (OWNER/TECH) build a dial session — a queue of numbers, typed in or pulled
straight from CRM contacts — then work it one click at a time. Each "Dial next"
rings their Dialpad device then the prospect; the rep logs a disposition + notes
and advances. Coaching scripts (opening, talking points, objection→response
cards) ride along to guide the call. Outcomes roll into live connect/conversion
stats and write back to the CRM timeline.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import (
    CallScript, CrmContact, DIAL_DISPOSITIONS, DialEntry, DialSession, Role, User,
)
from ...services import audit, power_dialer, secure_config

router = APIRouter(prefix="/api/dialer", tags=["dialer"])

DIALPAD_PROVIDER = "dialpad"


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _staff():
    return require_roles(Role.OWNER, Role.TECH)


# --------------------------------------------------------------------------- #
# Coaching scripts
# --------------------------------------------------------------------------- #
class ScriptIn(BaseModel):
    name: str
    opening: str | None = None
    talking_points: list[str] = []
    objections: list[dict] = []   # [{objection, response}]
    active: bool = True


def _serialize_script(s: CallScript) -> dict:
    return {"id": s.id, "name": s.name, "opening": s.opening,
            "talking_points": s.talking_points or [], "objections": s.objections or [],
            "active": s.active}


def _clean_objections(items: list) -> list[dict]:
    out = []
    for o in items or []:
        if isinstance(o, dict) and (o.get("objection") or o.get("response")):
            out.append({"objection": str(o.get("objection") or "")[:300],
                        "response": str(o.get("response") or "")[:1000]})
    return out


@router.get("/scripts")
def list_scripts(db: Session = Depends(get_db), user: User = Depends(_staff())):
    rows = db.query(CallScript).order_by(CallScript.active.desc(), CallScript.name).all()
    return [_serialize_script(s) for s in rows]


@router.post("/scripts", status_code=201)
def create_script(body: ScriptIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(_staff())):
    s = CallScript(name=body.name[:160], opening=body.opening,
                   talking_points=[str(p)[:300] for p in (body.talking_points or [])][:30],
                   objections=_clean_objections(body.objections), active=body.active,
                   created_by_user_id=user.id)
    db.add(s)
    db.commit()
    audit.record(db, action="dialer.script_create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="call_script", target_id=str(s.id),
                 ip=_ip(request), detail=body.name[:120])
    return _serialize_script(s)


class ScriptUpdate(BaseModel):
    name: str | None = None
    opening: str | None = None
    talking_points: list[str] | None = None
    objections: list[dict] | None = None
    active: bool | None = None


@router.patch("/scripts/{script_id}")
def update_script(script_id: int, body: ScriptUpdate, db: Session = Depends(get_db),
                  user: User = Depends(_staff())):
    s = db.get(CallScript, script_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    if body.name is not None:
        s.name = body.name[:160]
    if body.opening is not None:
        s.opening = body.opening
    if body.talking_points is not None:
        s.talking_points = [str(p)[:300] for p in body.talking_points][:30]
    if body.objections is not None:
        s.objections = _clean_objections(body.objections)
    if body.active is not None:
        s.active = body.active
    db.commit()
    return _serialize_script(s)


@router.delete("/scripts/{script_id}")
def delete_script(script_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    s = db.get(CallScript, script_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
class CrmPull(BaseModel):
    status: str | None = None   # filter CRM contacts by pipeline status
    market: str | None = None
    limit: int = 50


class SessionIn(BaseModel):
    name: str
    script_id: int | None = None
    items: list[dict] = []      # [{name,phone,company,client_id,crm_contact_id}]
    from_crm: CrmPull | None = None


def _serialize_entry(e: DialEntry) -> dict:
    return {"id": e.id, "position": e.position, "name": e.name, "phone": e.phone,
            "company": e.company, "client_id": e.client_id, "crm_contact_id": e.crm_contact_id,
            "status": e.status, "disposition": e.disposition, "notes": e.notes,
            "attempts": e.attempts, "dialed_at": e.dialed_at.isoformat() if e.dialed_at else None}


def _serialize_session(s: DialSession) -> dict:
    return {"id": s.id, "name": s.name, "status": s.status, "script_id": s.script_id,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None}


@router.post("/sessions", status_code=201)
def create_session(body: SessionIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(_staff())):
    items = list(body.items or [])
    # Optionally pull dial-ready CRM contacts (has a phone, not do-not-contact).
    if body.from_crm is not None:
        q = db.query(CrmContact).filter(CrmContact.phone.isnot(None),
                                        CrmContact.do_not_contact.is_(False))
        if body.from_crm.status:
            q = q.filter(CrmContact.status == body.from_crm.status)
        if body.from_crm.market:
            q = q.filter(CrmContact.market == body.from_crm.market)
        lim = max(1, min(body.from_crm.limit or 50, 500))
        for c in q.order_by(CrmContact.score.desc().nullslast(), CrmContact.id.desc()).limit(lim):
            items.append({"name": c.name, "phone": c.phone, "company": c.company,
                          "client_id": c.client_id, "crm_contact_id": c.id})
    if body.script_id is not None and not db.get(CallScript, body.script_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    if not any(str(i.get("phone") or "").strip() for i in items):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No numbers to dial.")
    sess = power_dialer.create_session(db, body.name, items, owner_user_id=user.id,
                                       script_id=body.script_id)
    audit.record(db, action="dialer.session_create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="dial_session", target_id=str(sess.id),
                 ip=_ip(request), detail=f"{sess.name}")
    return {"id": sess.id, "stats": power_dialer.session_stats(db, sess.id)}


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), user: User = Depends(_staff())):
    rows = db.query(DialSession).order_by(DialSession.created_at.desc()).limit(100).all()
    return [{**_serialize_session(s), "stats": power_dialer.session_stats(db, s.id)} for s in rows]


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(_staff())):
    s = db.get(DialSession, session_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    entries = (db.query(DialEntry).filter(DialEntry.session_id == s.id)
               .order_by(DialEntry.position.asc()).all())
    script = db.get(CallScript, s.script_id) if s.script_id else None
    nxt = power_dialer.next_entry(db, s.id)
    return {**_serialize_session(s),
            "script": _serialize_script(script) if script else None,
            "entries": [_serialize_entry(e) for e in entries],
            "next": _serialize_entry(nxt) if nxt else None,
            "stats": power_dialer.session_stats(db, s.id)}


@router.post("/sessions/{session_id}/dial-next", status_code=202)
def dial_next(session_id: int, request: Request, db: Session = Depends(get_db),
              user: User = Depends(_staff())):
    s = db.get(DialSession, session_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if s.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Session is {s.status}.")
    entry = power_dialer.next_entry(db, s.id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Queue is empty.")
    conn = secure_config.get_platform(db, DIALPAD_PROVIDER)
    cfg = (conn.config if conn else None) or {}
    try:
        call_id = power_dialer.place_call(cfg, entry.phone)
    except power_dialer.DialerError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    power_dialer.mark_calling(db, entry, call_id)
    audit.record(db, action="dialer.dial", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="phone", target_id=entry.phone,
                 client_id=entry.client_id, ip=_ip(request), detail=f"session={s.id}")
    return {"ok": True, "entry": _serialize_entry(entry), "call_id": call_id}


class StatusIn(BaseModel):
    status: str


@router.post("/sessions/{session_id}/status")
def set_session_status(session_id: int, body: StatusIn, db: Session = Depends(get_db),
                       user: User = Depends(_staff())):
    s = db.get(DialSession, session_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if body.status not in ("active", "paused", "completed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
    power_dialer.set_status(db, s, body.status)
    return _serialize_session(s)


class DispositionIn(BaseModel):
    disposition: str
    notes: str | None = None


@router.post("/entries/{entry_id}/disposition")
def set_disposition(entry_id: int, body: DispositionIn, db: Session = Depends(get_db),
                    user: User = Depends(_staff())):
    e = db.get(DialEntry, entry_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    if body.disposition not in DIAL_DISPOSITIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"disposition must be one of {list(DIAL_DISPOSITIONS)}")
    power_dialer.log_disposition(db, e, body.disposition, body.notes, user_id=user.id)
    return {"ok": True, "entry": _serialize_entry(e),
            "stats": power_dialer.session_stats(db, e.session_id)}


@router.post("/entries/{entry_id}/skip")
def skip(entry_id: int, db: Session = Depends(get_db), user: User = Depends(_staff())):
    e = db.get(DialEntry, entry_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    power_dialer.skip_entry(db, e)
    return {"ok": True, "entry": _serialize_entry(e)}
