"""v1.2 Pulse Cyber Academy API — every authenticated portal user can train.

Staff (OWNER/TECH) and client users (CLIENT_ADMIN/CLIENT_VIEWER) all get the
same trainer; the leaderboard is tenant-isolated so client companies compete
internally and staff see the whole board. Quiz answers never leave the server —
grading is server-side only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff, require_roles
from ...models import Role, User
from ...services import academy

router = APIRouter(prefix="/api/academy", tags=["academy"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response,
             db: Session = Depends(get_db)):
    """PUBLIC, open self-registration for the Academy (students, CTF players,
    anyone). Creates an isolated Academy-tenant learner and signs them straight
    in — hack-this-site style. Never creates staff or real-client access.
    Rate-limited in middleware."""
    from ...services import school
    from .auth import issue_session
    user, err = school.register_student(
        db, email=str(body.email), password=body.password, full_name=body.full_name)
    if err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, err)
    issue_session(db, user, request, response, method="academy_register")
    return {"ok": True, "home": "/academy"}


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return academy.profile_view(db, user)


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), user: User = Depends(current_user)):
    out = academy.catalog_view(db, user)
    out["profile"] = academy.profile_view(db, user)
    return out


@router.get("/lessons/{lesson_id}")
def lesson(lesson_id: str, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    l = academy.lesson_view(db, lesson_id)
    if not l:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")
    return l


class AnswersIn(BaseModel):
    answers: list[int]


@router.post("/lessons/{lesson_id}/submit")
def submit_lesson(lesson_id: str, body: AnswersIn, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    out = academy.grade_lesson(db, user, lesson_id, body.answers)
    if not out:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")
    return out


@router.get("/games/{game_id}")
def game(game_id: str, user: User = Depends(current_user)):
    g = academy.game_view(game_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found")
    return g


class GameAnswersIn(BaseModel):
    answers: list = []


@router.post("/games/{game_id}/submit")
def submit_game(game_id: str, body: GameAnswersIn, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    out = academy.grade_game(db, user, game_id, body.answers)
    if not out:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found")
    return out


@router.get("/range")
def range_catalog(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The Cyber Range: hands-on CTF-style labs, with per-user solved state."""
    out = academy.range_view(db, user)
    out["profile"] = academy.profile_view(db, user)
    return out


@router.get("/labs/{lab_id}")
def lab(lab_id: str, db: Session = Depends(get_db),
        user: User = Depends(current_user)):
    b = academy.lab_view(db, user, lab_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab not found")
    return b


@router.get("/labs/{lab_id}/probe")
def lab_probe(lab_id: str, request: Request,
              user: User = Depends(current_user)):
    """The lab's SAFE emulated endpoint — hardcoded simulators only. Query params
    are the learner's 'attack' input (id=, file=, user=, pass=, path=)."""
    if lab_id not in academy._LABS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab not found")
    return academy.lab_probe(lab_id, dict(request.query_params))


class FlagIn(BaseModel):
    flag: str = ""


@router.post("/labs/{lab_id}/submit")
def submit_lab(lab_id: str, body: FlagIn, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    out = academy.grade_lab(db, user, lab_id, body.flag)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab not found")
    return out


@router.get("/team")
def team(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """A client user's own team training adoption — powers the portal's
    Guardz-style 'Security Awareness Training' card. Scoped to the caller's own
    client; staff (no single client) get an empty shell."""
    if not user.client_id:
        return {"users": 0, "trained_users": 0, "trained_pct": None,
                "total_lessons": academy.TOTAL_LESSONS}
    out = academy.client_compliance(db, user.client_id)
    out["total_lessons"] = academy.TOTAL_LESSONS
    return out


@router.get("/dojo")
def dojo_catalog(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Code Dojo: write-real-code challenges, graded server-side on hidden tests."""
    from ...services import dojo
    out = dojo.dojo_view(db, user)
    out["profile"] = academy.profile_view(db, user)
    return out


@router.get("/dojo/{challenge_id}")
def dojo_challenge(challenge_id: str, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    from ...services import dojo
    c = dojo.challenge_view(db, user, challenge_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challenge not found")
    return c


class OutputsIn(BaseModel):
    outputs: list = []


@router.post("/dojo/{challenge_id}/submit")
def dojo_submit(challenge_id: str, body: OutputsIn, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    """Grade the outputs the browser produced by running the learner's code on
    the hidden inputs. Expected answers never leave the server."""
    from ...services import dojo
    out = dojo.grade(db, user, challenge_id, body.outputs)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challenge not found")
    return out


@router.post("/shell/start")
def shell_start(user: User = Depends(current_user)):
    """Boot (or reboot) The Grid terminal box for this user. Pure emulator — no
    real shell, filesystem, or code execution ever runs."""
    from ...services import shell_range
    return shell_range.start(user.id)


class ShellIn(BaseModel):
    line: str = ""


@router.post("/shell/exec")
def shell_exec(body: ShellIn, user: User = Depends(current_user)):
    """Run one command line against the emulated box. State is per-user, server-side."""
    from ...services import shell_range
    return shell_range.run(user.id, (body.line or "")[:400])


@router.get("/leaderboard")
def board(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"leaderboard": academy.leaderboard(db, user, staff=is_staff(user))}


@router.get("/compliance")
def compliance(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Per-client training adoption (staff) — the QBR/renewal number."""
    return {"clients": academy.compliance_all(db),
            "total_lessons": academy.TOTAL_LESSONS}
