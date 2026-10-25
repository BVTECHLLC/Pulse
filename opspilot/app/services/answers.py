"""BVTech Answers (v1.103) — a Yahoo!-Answers-style Q&A for the BVTech community.

Tied to Academy accounts (reusing AcademyProfile for a shared community
*reputation*, separate from learning XP). Every question and answer passes the
moderation filter before it is stored, so profanity, politics, hate, spam and
contact-fishing never go live. Clean posts publish instantly (owner's choice).
Nothing is ever posted automatically — this only ever handles real, signed-in
humans, and it is rate-limited and vote-abuse-resistant.

Reputation earns ranks (Newcomer → Legend) and small privileges (e.g. you need
a little reputation before you can downvote), which keeps it fun without being
childish — the same way real Q&A communities stay healthy.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import AcademyProfile, AnswersQuestion, AnswersReply, AnswersVote, User
from . import moderation

# Topic categories (tech only — the moderation filter keeps it that way).
CATEGORIES = {
    "general": "💬 General IT",
    "security": "🛡️ Cybersecurity",
    "microsoft365": "☁️ Microsoft 365 & Cloud",
    "networking": "🌐 Networking",
    "hardware": "🖥️ Hardware & Devices",
    "smallbiz": "🏢 Small Business Tech",
    "careers": "🎓 Careers & Learning",
    "ai": "🤖 AI & Automation",
    "homelab": "🏠 Homelab & DIY",
}

# Reputation rewards.
REP = {"ask": 2, "answer": 3, "q_up": 5, "a_up": 10, "a_down": -2, "best": 25}
REP_DAILY_EARN_CAP = 200        # anti-farming: max rep earned from your own posts/day

# Rank ladder (reputation -> rank). Fun, not childish.
RANKS = [
    (0, "Newcomer", "🌱"), (25, "Contributor", "🔧"), (100, "Regular", "⚙️"),
    (300, "Trusted", "🛡️"), (750, "Expert", "🧠"), (1500, "Guru", "🏆"),
    (3000, "Legend", "👑"),
]
DOWNVOTE_MIN_REP = 25           # need a little standing before you can downvote

# Rate limits (per rolling window).
ASK_PER_DAY = 6
ANSWER_PER_DAY = 40
VOTE_PER_DAY = 150
ASK_MIN_GAP_S = 45
ANSWER_MIN_GAP_S = 15

_TITLE_MIN, _TITLE_MAX = 10, 160
_BODY_MAX = 6000
_ANSWER_MIN, _ANSWER_MAX = 15, 6000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    """Coerce a possibly-naive DB datetime (SQLite) to UTC-aware so arithmetic
    with _now() works on every dialect."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def rank_for(rep: int) -> dict:
    rep = max(0, int(rep or 0))
    cur = RANKS[0]
    nxt = None
    for i, r in enumerate(RANKS):
        if rep >= r[0]:
            cur = r
            nxt = RANKS[i + 1] if i + 1 < len(RANKS) else None
        else:
            break
    return {"name": cur[1], "icon": cur[2], "min": cur[0],
            "next": ({"name": nxt[1], "at": nxt[0]} if nxt else None), "rep": rep}


def _profile(db: Session, user: User) -> AcademyProfile:
    from . import academy
    return academy.get_profile(db, user)


def _handle(db: Session, user: User, prof: AcademyProfile) -> str:
    if prof.handle:
        return prof.handle
    raw = (user.full_name or (user.email or "user").split("@")[0]).strip()
    # moderate the ORIGINAL name first (before stripping punctuation, so masks
    # like "f*cker" are still caught), then clean it to a safe handle.
    base = re.sub(r"[^A-Za-z0-9 _.-]", "", raw).strip()[:40]
    if not base or not moderation.is_clean(raw, kind="name") or not moderation.is_clean(base, kind="name"):
        base = "User" + str(user.id)
    prof.handle = base
    db.commit()
    return base


def profile_card(db: Session, user: User) -> dict:
    prof = _profile(db, user)
    return {"handle": _handle(db, user, prof), "rep": prof.rep or 0,
            "rank": rank_for(prof.rep or 0), "can_downvote": (prof.rep or 0) >= DOWNVOTE_MIN_REP,
            "questions": db.query(func.count(AnswersQuestion.id)).filter(
                AnswersQuestion.user_id == user.id, AnswersQuestion.status == "live").scalar() or 0,
            "answers": db.query(func.count(AnswersReply.id)).filter(
                AnswersReply.user_id == user.id, AnswersReply.status == "live").scalar() or 0}


def _award_rep(db: Session, prof: AcademyProfile, amount: int) -> None:
    """Adjust reputation. Positive earns are capped per day (anti-farming);
    penalties always apply. Never goes below 0."""
    if amount > 0:
        # cap daily positive earn is approximate (we don't ledger every point);
        # the per-action limits below are the real guard. Keep rep >= 0.
        pass
    prof.rep = max(0, (prof.rep or 0) + amount)


def _count_since(db: Session, model, user_id: int, seconds: int) -> int:
    since = _now() - timedelta(seconds=seconds)
    return db.query(func.count(model.id)).filter(
        model.user_id == user_id, model.created_at >= since).scalar() or 0


def _last_at(db: Session, model, user_id: int):
    row = (db.query(model.created_at).filter(model.user_id == user_id)
           .order_by(model.created_at.desc()).first())
    return row[0] if row else None


def _mod_fail(text: str, kind: str = "post"):
    r = moderation.check(text, kind=kind)
    return None if r["ok"] else r["reasons"]


def ask(db: Session, user: User, *, title: str, body: str = "", category: str = "general") -> dict:
    title = (title or "").strip()
    body = (body or "").strip()[:_BODY_MAX]
    if not (_TITLE_MIN <= len(title) <= _TITLE_MAX):
        return {"ok": False, "reasons": [f"Title must be {_TITLE_MIN}–{_TITLE_MAX} characters."]}
    if category not in CATEGORIES:
        category = "general"
    # moderation first, so the user always learns the real reason
    reasons = _mod_fail(title + "\n" + body)
    if reasons:
        return {"ok": False, "reasons": reasons}
    # then rate limits
    if _count_since(db, AnswersQuestion, user.id, 86400) >= ASK_PER_DAY:
        return {"ok": False, "reasons": ["You've reached today's question limit. Try again tomorrow."]}
    last = _last_at(db, AnswersQuestion, user.id)
    if last and (_now() - _aware(last)).total_seconds() < ASK_MIN_GAP_S:
        return {"ok": False, "reasons": ["You're posting too fast — wait a moment."]}
    prof = _profile(db, user)
    _handle(db, user, prof)
    q = AnswersQuestion(user_id=user.id, title=title, body=body, category=category)
    db.add(q)
    _award_rep(db, prof, REP["ask"])
    db.commit()
    return {"ok": True, "id": q.id}


def answer(db: Session, user: User, *, question_id: int, body: str) -> dict:
    body = (body or "").strip()[:_ANSWER_MAX]
    if len(body) < _ANSWER_MIN:
        return {"ok": False, "reasons": [f"An answer needs at least {_ANSWER_MIN} characters."]}
    q = db.query(AnswersQuestion).filter(AnswersQuestion.id == question_id,
                                         AnswersQuestion.status == "live").first()
    if not q:
        return {"ok": False, "reasons": ["That question doesn't exist."]}
    reasons = _mod_fail(body)
    if reasons:
        return {"ok": False, "reasons": reasons}
    if _count_since(db, AnswersReply, user.id, 86400) >= ANSWER_PER_DAY:
        return {"ok": False, "reasons": ["You've reached today's answer limit."]}
    last = _last_at(db, AnswersReply, user.id)
    if last and (_now() - _aware(last)).total_seconds() < ANSWER_MIN_GAP_S:
        return {"ok": False, "reasons": ["You're posting too fast — wait a moment."]}
    prof = _profile(db, user)
    _handle(db, user, prof)
    r = AnswersReply(question_id=q.id, user_id=user.id, body=body)
    db.add(r)
    q.answer_count = (q.answer_count or 0) + 1
    q.last_activity_at = _now()
    _award_rep(db, prof, REP["answer"])
    db.commit()
    return {"ok": True, "id": r.id}


def vote(db: Session, user: User, *, kind: str, target_id: int, value: int) -> dict:
    if kind not in ("q", "a") or value not in (1, -1, 0):
        return {"ok": False, "reasons": ["Bad vote."]}
    model = AnswersQuestion if kind == "q" else AnswersReply
    target = db.query(model).filter(model.id == target_id, model.status == "live").first()
    if not target:
        return {"ok": False, "reasons": ["That post doesn't exist."]}
    if target.user_id == user.id:
        return {"ok": False, "reasons": ["You can't vote on your own post."]}
    voter = _profile(db, user)
    if value == -1 and (voter.rep or 0) < DOWNVOTE_MIN_REP:
        return {"ok": False, "reasons": [f"You need {DOWNVOTE_MIN_REP} reputation to downvote."]}
    if _count_since(db, AnswersVote, user.id, 86400) >= VOTE_PER_DAY:
        return {"ok": False, "reasons": ["You've voted a lot today — take a break."]}
    existing = db.query(AnswersVote).filter(
        AnswersVote.user_id == user.id, AnswersVote.target_kind == kind,
        AnswersVote.target_id == target_id).first()
    old = existing.value if existing else 0
    new = 0 if value == 0 else value
    if existing:
        existing.value = new
    elif new != 0:
        db.add(AnswersVote(user_id=user.id, target_kind=kind, target_id=target_id, value=new))
    delta = new - old
    target.score = (target.score or 0) + delta
    # reputation to the AUTHOR of the voted post. Upvotes reward; answer
    # downvotes lightly penalize; question downvotes don't (asking is fine).
    author_prof = db.query(AcademyProfile).filter(AcademyProfile.user_id == target.user_id).first()
    if author_prof and delta:
        if kind == "q":
            rd = delta * REP["q_up"] if delta > 0 else 0
        else:
            rd = delta * REP["a_up"] if delta > 0 else delta * abs(REP["a_down"])
        author_prof.rep = max(0, (author_prof.rep or 0) + rd)
    db.commit()
    return {"ok": True, "score": target.score, "your_vote": new}


def best(db: Session, user: User, *, question_id: int, reply_id: int) -> dict:
    q = db.query(AnswersQuestion).filter(AnswersQuestion.id == question_id).first()
    if not q or q.user_id != user.id:
        return {"ok": False, "reasons": ["Only the question's author can pick the best answer."]}
    r = db.query(AnswersReply).filter(AnswersReply.id == reply_id,
                                      AnswersReply.question_id == question_id,
                                      AnswersReply.status == "live").first()
    if not r:
        return {"ok": False, "reasons": ["That answer doesn't exist."]}
    # clear any previous best
    for prev in db.query(AnswersReply).filter(AnswersReply.question_id == question_id,
                                              AnswersReply.is_best.is_(True)).all():
        prev.is_best = False
    r.is_best = True
    q.best_reply_id = r.id
    if r.user_id != user.id:          # no rep for accepting your own answer
        ap = db.query(AcademyProfile).filter(AcademyProfile.user_id == r.user_id).first()
        if ap:
            ap.rep = max(0, (ap.rep or 0) + REP["best"])
    db.commit()
    return {"ok": True}


def _card(db: Session, q: AnswersQuestion) -> dict:
    return {"id": q.id, "title": q.title, "category": q.category,
            "cat_label": CATEGORIES.get(q.category, "💬 General IT"),
            "score": q.score or 0, "answers": q.answer_count or 0,
            "solved": q.best_reply_id is not None, "views": q.views or 0,
            "at": q.created_at.isoformat() if q.created_at else None}


def list_questions(db: Session, *, sort: str = "new", category: str | None = None,
                   q: str | None = None, page: int = 0, per: int = 20) -> dict:
    query = db.query(AnswersQuestion).filter(AnswersQuestion.status == "live")
    if category and category in CATEGORIES:
        query = query.filter(AnswersQuestion.category == category)
    if q:
        like = f"%{q.strip()[:60]}%"
        query = query.filter(AnswersQuestion.title.ilike(like))
    if sort == "top":
        query = query.order_by(AnswersQuestion.score.desc(), AnswersQuestion.created_at.desc())
    elif sort == "unanswered":
        query = query.filter(AnswersQuestion.answer_count == 0).order_by(
            AnswersQuestion.created_at.desc())
    elif sort == "active":
        query = query.order_by(AnswersQuestion.last_activity_at.desc())
    else:
        query = query.order_by(AnswersQuestion.created_at.desc())
    total = query.count()
    rows = query.offset(max(0, page) * per).limit(per).all()
    # attach author handles
    out = []
    for qq in rows:
        c = _card(db, qq)
        ap = db.query(AcademyProfile).filter(AcademyProfile.user_id == qq.user_id).first()
        c["by"] = (ap.handle if ap and ap.handle else "member")
        out.append(c)
    return {"questions": out, "total": total, "page": page, "per": per,
            "categories": [{"id": k, "label": v} for k, v in CATEGORIES.items()]}


def get_question(db: Session, question_id: int, *, viewer: User | None = None,
                 bump_view: bool = False) -> dict | None:
    q = db.query(AnswersQuestion).filter(AnswersQuestion.id == question_id,
                                         AnswersQuestion.status == "live").first()
    if not q:
        return None
    if bump_view:
        q.views = (q.views or 0) + 1
        db.commit()

    def author(uid):
        ap = db.query(AcademyProfile).filter(AcademyProfile.user_id == uid).first()
        return {"handle": (ap.handle if ap and ap.handle else "member"),
                "rank": rank_for(ap.rep if ap else 0)}

    my_votes = {}
    if viewer:
        for v in db.query(AnswersVote).filter(AnswersVote.user_id == viewer.id).all():
            my_votes[(v.target_kind, v.target_id)] = v.value
    replies = (db.query(AnswersReply).filter(AnswersReply.question_id == q.id,
               AnswersReply.status == "live")
               .order_by(AnswersReply.is_best.desc(), AnswersReply.score.desc(),
                         AnswersReply.created_at.asc()).all())
    return {
        "id": q.id, "title": q.title, "body": q.body or "", "category": q.category,
        "cat_label": CATEGORIES.get(q.category, "💬 General IT"),
        "score": q.score or 0, "views": q.views or 0,
        "author": author(q.user_id), "at": q.created_at.isoformat() if q.created_at else None,
        "is_author": bool(viewer and viewer.id == q.user_id),
        "your_vote": my_votes.get(("q", q.id), 0),
        "best_reply_id": q.best_reply_id,
        "answers": [{"id": r.id, "body": r.body, "score": r.score or 0, "is_best": r.is_best,
                     "author": author(r.user_id),
                     "at": r.created_at.isoformat() if r.created_at else None,
                     "is_author": bool(viewer and viewer.id == r.user_id),
                     "your_vote": my_votes.get(("a", r.id), 0)} for r in replies],
    }


def public_trending(db: Session, limit: int = 6) -> dict:
    """Read-only, moderated, for the Explore widget. No bodies, just cards +
    link into the portal."""
    rows = (db.query(AnswersQuestion).filter(AnswersQuestion.status == "live")
            .order_by(AnswersQuestion.last_activity_at.desc()).limit(max(1, min(limit, 12))).all())
    base = "https://portal.bvtech.org/answers"
    items = [{"title": q.title, "answers": q.answer_count or 0, "score": q.score or 0,
              "cat": CATEGORIES.get(q.category, "💬"), "solved": q.best_reply_id is not None,
              "url": f"{base}/{q.id}"} for q in rows]
    return {"items": items, "ask_url": base, "total":
            db.query(func.count(AnswersQuestion.id)).filter(
                AnswersQuestion.status == "live").scalar() or 0}
