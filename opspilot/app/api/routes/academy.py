"""v1.2 Pulse Cyber Academy API — every authenticated portal user can train.

Staff (OWNER/TECH) and client users (CLIENT_ADMIN/CLIENT_VIEWER) all get the
same trainer; the leaderboard is tenant-isolated so client companies compete
internally and staff see the whole board. Quiz answers never leave the server —
grading is server-side only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff
from ...models import User
from ...services import academy

router = APIRouter(prefix="/api/academy", tags=["academy"])


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return academy.profile_view(db, user)


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), user: User = Depends(current_user)):
    out = academy.catalog_view(db, user)
    out["profile"] = academy.profile_view(db, user)
    return out


@router.get("/lessons/{lesson_id}")
def lesson(lesson_id: str, user: User = Depends(current_user)):
    l = academy.lesson_view(lesson_id)
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


@router.get("/leaderboard")
def board(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"leaderboard": academy.leaderboard(db, user, staff=is_staff(user))}
