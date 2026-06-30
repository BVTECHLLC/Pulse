"""v0.67 Posture trend + drop alerting.

On the scheduler tick (throttled to ~once a day) we snapshot every client's
security scorecard. Comparing the new snapshot to the prior one lets us:
  * draw a trend line (is this client getting more or less secure?), and
  * raise a staff notification the moment a client's **grade slips** (e.g. B→C),
    so a degrading client surfaces immediately instead of at the next QBR.

The grade ladder is A(best) → F(worst); "N/A" (no data) never triggers an alert.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Client, Notification, PostureSnapshot
from . import posture

# Lower rank = better. Used to decide whether a grade got worse.
_GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _latest(db: Session, client_id: int) -> PostureSnapshot | None:
    return (db.query(PostureSnapshot)
            .filter(PostureSnapshot.client_id == client_id)
            .order_by(PostureSnapshot.created_at.desc()).first())


def grade_dropped(old_grade: str, new_grade: str) -> bool:
    """True only when both grades are real and the new one is strictly worse."""
    if old_grade not in _GRADE_RANK or new_grade not in _GRADE_RANK:
        return False
    return _GRADE_RANK[new_grade] > _GRADE_RANK[old_grade]


def snapshot_client(db: Session, client_id: int, now: datetime,
                    *, alert: bool = True) -> dict:
    """Take a snapshot for one client; alert staff if the grade dropped vs the
    previous snapshot. Returns a summary dict. Does NOT commit (caller commits)."""
    sc = posture.scorecard(db, client_id, now)
    prev = _latest(db, client_id)
    snap = PostureSnapshot(
        client_id=client_id, score=sc["score"], grade=sc["grade"],
        domains={k: v["score"] for k, v in sc["domains"].items()}, created_at=now)
    db.add(snap)
    dropped = False
    if alert and prev and grade_dropped(prev.grade, sc["grade"]):
        dropped = True
        client = db.get(Client, client_id)
        name = client.name if client else f"client {client_id}"
        db.add(Notification(
            client_id=client_id, target_user_id=None, kind="posture_drop",
            severity="warning",
            message=(f"Security grade for {name} dropped {prev.grade}→{sc['grade']} "
                     f"(score {prev.score}→{sc['score']}). Review the scorecard.")))
    return {"client_id": client_id, "grade": sc["grade"], "score": sc["score"],
            "prev_grade": prev.grade if prev else None,
            "prev_score": prev.score if prev else None, "dropped": dropped}


def snapshot_all(db: Session, now: datetime | None = None, *,
                 min_interval_hours: int = 20) -> list[dict]:
    """Snapshot every client whose last snapshot is older than the interval (or
    who has none). Throttled so calling it every tick still snapshots ~daily.
    Commits. Returns the per-client summaries that were taken."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=min_interval_hours)
    taken = []
    for c in db.query(Client).all():
        last = _latest(db, c.id)
        if last and _aware(last.created_at) and _aware(last.created_at) > cutoff:
            continue   # snapshotted recently
        taken.append(snapshot_client(db, c.id, now))
    if taken:
        db.commit()
    return taken


def history(db: Session, client_id: int, limit: int = 60) -> list[dict]:
    rows = (db.query(PostureSnapshot)
            .filter(PostureSnapshot.client_id == client_id)
            .order_by(PostureSnapshot.created_at.desc())
            .limit(max(1, min(limit, 365))).all())
    rows.reverse()   # oldest → newest for charting
    return [{"score": r.score, "grade": r.grade, "domains": r.domains or {},
             "at": r.created_at.isoformat()} for r in rows]


def trend(db: Session, client_id: int) -> dict:
    """Latest grade/score and the delta vs the previous snapshot."""
    rows = (db.query(PostureSnapshot)
            .filter(PostureSnapshot.client_id == client_id)
            .order_by(PostureSnapshot.created_at.desc()).limit(2).all())
    if not rows:
        return {"grade": None, "score": None, "delta": None, "direction": "flat"}
    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    delta = None
    direction = "flat"
    if prev and latest.score is not None and prev.score is not None:
        delta = latest.score - prev.score
        direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
    return {"grade": latest.grade, "score": latest.score, "delta": delta,
            "direction": direction, "prev_grade": prev.grade if prev else None}
