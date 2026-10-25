"""BVTech Answers API (v1.103).

Public to READ (browse questions, see answers), signed-in to WRITE. Every write
goes through services/answers.py, which moderates, rate-limits and awards
reputation. No endpoint ever posts on a user's behalf automatically.

The HTML pages (/answers, /answers/{id}) are served by pages_answers.py; this
file is the JSON API they call (same-origin on the portal, so the Academy
session cookie authenticates writes).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, optional_user
from ...models import User
from ...services import answers

router = APIRouter(prefix="/api/answers", tags=["answers"])


class AskIn(BaseModel):
    title: str
    body: str = ""
    category: str = "general"


class AnswerIn(BaseModel):
    body: str


class VoteIn(BaseModel):
    kind: str
    target_id: int
    value: int


class BestIn(BaseModel):
    reply_id: int


@router.get("/me")
def me(db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    if not user:
        return {"authed": False}
    return {"authed": True, **answers.profile_card(db, user)}


@router.get("/questions")
def list_q(sort: str = "new", category: str | None = None, q: str | None = None,
           page: int = 0, db: Session = Depends(get_db)):
    return answers.list_questions(db, sort=sort, category=category, q=q, page=page)


@router.get("/questions/{qid}")
def get_q(qid: int, db: Session = Depends(get_db),
          user: User | None = Depends(optional_user)):
    out = answers.get_question(db, qid, viewer=user, bump_view=True)
    if not out:
        raise HTTPException(404, "Question not found")
    return out


def _reject(res: dict):
    if not res.get("ok"):
        raise HTTPException(422, "; ".join(res.get("reasons") or ["Not allowed"]))
    return res


@router.post("/questions", status_code=201)
def post_q(body: AskIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _reject(answers.ask(db, user, title=body.title, body=body.body, category=body.category))


@router.post("/questions/{qid}/answers", status_code=201)
def post_a(qid: int, body: AnswerIn, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    return _reject(answers.answer(db, user, question_id=qid, body=body.body))


@router.post("/vote")
def post_vote(body: VoteIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _reject(answers.vote(db, user, kind=body.kind, target_id=body.target_id, value=body.value))


@router.post("/questions/{qid}/best")
def post_best(qid: int, body: BestIn, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    return _reject(answers.best(db, user, question_id=qid, reply_id=body.reply_id))
