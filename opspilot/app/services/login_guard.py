"""v1.66 Account lockout — brute-force / password-spray defense for sign-in.

The per-request rate limiter in main.py caps how fast one IP can hammer the
login endpoint. It does NOT stop a patient, IP-rotating attacker spraying a few
guesses against one specific account (e.g. the owner's) over many minutes — the
classic way real accounts get taken.

This adds a second, orthogonal control: count *failed* attempts per email AND
per IP over a rolling window; once a threshold is crossed, lock that key for a
cooldown. A successful sign-in clears the counters. Locking on the submitted
email (whether or not the account exists) also avoids leaking which emails are
real via timing/behavior differences.

State is in-process (same tradeoff as the existing limiter) — fine for a single
worker; move to Redis for multi-worker. Everything is best-effort: a bug here
must never block a legitimate login, so callers wrap use defensively.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from ..core.config import get_settings

_s = get_settings()
_lock = threading.Lock()
# key -> deque[timestamp] of recent failures
_fails: dict[str, deque[float]] = defaultdict(deque)
# key -> unix time until which the key is locked
_locked_until: dict[str, float] = {}


def _cfg() -> tuple[int, float, float]:
    return (max(1, _s.LOGIN_MAX_FAILS),
            max(1, _s.LOGIN_FAIL_WINDOW_MIN) * 60.0,
            max(1, _s.LOGIN_LOCK_MIN) * 60.0)


def _keys(email: str | None, ip: str | None) -> list[str]:
    # Lock on EMAIL only. Per-IP flooding is already capped by the middleware
    # rate limiter; locking on IP too would let one bad actor behind a shared
    # NAT (a whole office, a coffee shop) lock out every colleague — a
    # self-inflicted DoS. `ip` is retained in signatures for audit context.
    return [f"e:{email.strip().lower()}"] if email else []


def locked_seconds(email: str | None, ip: str | None) -> int:
    """Seconds remaining if this email OR ip is currently locked, else 0."""
    now = time.time()
    with _lock:
        remaining = 0
        for k in _keys(email, ip):
            until = _locked_until.get(k, 0.0)
            if until > now:
                remaining = max(remaining, int(until - now) + 1)
            elif until:
                # lock expired — clean up so a stale entry never lingers
                _locked_until.pop(k, None)
                _fails.pop(k, None)
        return remaining


def record_failure(email: str | None, ip: str | None) -> int:
    """Record one failed attempt. Returns seconds locked if this trips the lock
    (0 otherwise). Locks whichever key(s) crossed the threshold."""
    max_fails, window, lock_secs = _cfg()
    now = time.time()
    tripped = 0
    with _lock:
        for k in _keys(email, ip):
            dq = _fails[k]
            dq.append(now)
            # evict old failures outside the rolling window
            cutoff = now - window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= max_fails:
                _locked_until[k] = now + lock_secs
                dq.clear()
                tripped = max(tripped, int(lock_secs) + 1)
    return tripped


def clear(email: str | None, ip: str | None = None) -> None:
    """Wipe counters/locks after a successful sign-in."""
    with _lock:
        for k in _keys(email, ip):
            _fails.pop(k, None)
            _locked_until.pop(k, None)


def reset_all() -> None:
    """Test hook — clear all state."""
    with _lock:
        _fails.clear()
        _locked_until.clear()
