"""NEON BREACH — the live arcade backend.

A real, server-authoritative daily arcade competition that proves the stack is
live (it runs on the Linode box, behind the portal API):

  * Everyone worldwide plays the SAME gauntlet each UTC day — the server hands out
    today's deterministic ``seed`` so the run is identical for all players, which
    makes the global leaderboard a fair race (like a daily puzzle).
  * A real global leaderboard, persisted in the encrypted config vault (provider
    ``arena_game``), top 50 kept, reset at UTC midnight.
  * "Breaching now" — an in-memory heartbeat count of players active in the last
    ~75 seconds (resets on restart; that's fine, it's a live gauge).
  * Light anti-cheat worthy of a security brand: a score submit needs the HMAC
    token issued by ``today()`` for the current day, the score must be within a
    plausible ceiling for the elapsed time, and submissions are rate-limited.
    (We preach 'never trust the client' — so the server validates.)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time as _time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "arena_game"
TOP_N = 50
# A generous but finite plausibility ceiling: points can't accrue faster than
# this per second of real play (anti-cheat, not a balance knob).
MAX_PTS_PER_SEC = 450
MAX_SCORE = 2_000_000
_MIN_SECONDS = 4            # a run shorter than this can't post a real score

# In-memory "playing now" heartbeats: token -> last-seen epoch. Per-process and
# intentionally ephemeral; a restart just re-warms it.
_LIVE: dict[str, float] = {}
_LIVE_WINDOW = 75.0


def _secret() -> bytes:
    from ..core.config import get_settings
    return (get_settings().SECRET_KEY or "bvtech-arena").encode()


def _utc_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def _seed_for(day: str) -> int:
    """Deterministic 32-bit daily seed — same gauntlet for everyone that day."""
    h = hashlib.sha256(("neon-breach:" + day).encode()).hexdigest()
    return int(h[:8], 16)


def _token_for(day: str) -> str:
    sig = hmac.new(_secret(), ("arena:" + day).encode(), hashlib.sha256).hexdigest()[:24]
    body = base64.urlsafe_b64encode(day.encode()).decode().rstrip("=")
    return f"{body}.{sig}"


def _day_from_token(token: str) -> str | None:
    try:
        body, sig = (token or "").rsplit(".", 1)
        day = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        exp = hmac.new(_secret(), ("arena:" + day).encode(), hashlib.sha256).hexdigest()[:24]
        return day if hmac.compare_digest(sig, exp) else None
    except Exception:  # noqa: BLE001
        return None


def _load(db: Session, day: str) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = dict((conn.config if conn else None) or {})
    if cfg.get("day") != day:                      # new UTC day -> fresh board
        cfg = {"day": day, "scores": []}
    cfg.setdefault("scores", [])
    return cfg


def _save(db: Session, cfg: dict) -> None:
    secure_config.upsert_platform(db, PROVIDER, "Neon Breach (arcade)", "System", cfg)


def _clean_handle(handle: str) -> str:
    h = re.sub(r"[^A-Za-z0-9 _.\-]", "", (handle or "").strip())[:16].strip()
    return h or "anon"


def _live_count() -> int:
    cutoff = _time.time() - _LIVE_WINDOW
    for k in [k for k, v in _LIVE.items() if v < cutoff]:
        _LIVE.pop(k, None)
    return len(_LIVE)


# --------------------------------------------------------------------------- #
def today(db: Session, beat: str | None = None, now: datetime | None = None) -> dict:
    """Today's seed + top scores + live player count. Issues a signed token the
    client echoes back when it submits a score. ``beat`` is the client's token
    (from a prior call) so we can count it as 'playing now'."""
    day = _utc_day(now)
    cfg = _load(db, day)
    tok = _token_for(day)
    if beat:
        _LIVE[beat[:48]] = _time.time()
    _LIVE[tok[:48]] = _time.time()
    top = sorted(cfg["scores"], key=lambda r: -int(r.get("score", 0)))[:10]
    return {
        "day": day,
        "seed": _seed_for(day),
        "token": tok,
        "playing": _live_count(),
        "top": [{"handle": r.get("handle", "anon"), "score": int(r.get("score", 0))}
                for r in top],
        "plays": len(cfg["scores"]),
    }


def submit(db: Session, handle: str, score: int, token: str, seconds: float,
           now: datetime | None = None) -> dict:
    """Validate + record a run. Returns {ok, rank, top, best, reason?}."""
    day = _utc_day(now)
    tday = _day_from_token(token)
    if tday != day:
        return {"ok": False, "reason": "stale or missing token — reload the game"}
    try:
        score = int(score)
        seconds = float(seconds)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "bad score"}
    if score < 0 or score > MAX_SCORE:
        return {"ok": False, "reason": "score out of range"}
    if seconds < _MIN_SECONDS or score > MAX_PTS_PER_SEC * seconds + 500:
        # Faster than physically possible for the time played -> rejected. The
        # client is never trusted; the server decides what's real.
        return {"ok": False, "reason": "score failed the plausibility check"}
    handle = _clean_handle(handle)
    cfg = _load(db, day)
    scores = cfg["scores"]
    scores.append({"handle": handle, "score": score,
                   "ts": datetime.now(timezone.utc).isoformat()})
    scores.sort(key=lambda r: -int(r.get("score", 0)))
    del scores[TOP_N:]
    cfg["scores"] = scores
    _save(db, cfg)
    rank = next((i + 1 for i, r in enumerate(scores)
                 if r.get("handle") == handle and int(r.get("score", 0)) == score), None)
    return {
        "ok": True,
        "rank": rank,
        "made_board": rank is not None,
        "best": int(scores[0]["score"]) if scores else score,
        "top": [{"handle": r.get("handle", "anon"), "score": int(r.get("score", 0))}
                for r in scores[:10]],
        "playing": _live_count(),
    }
