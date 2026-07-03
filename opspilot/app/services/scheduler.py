"""v1.1 Autopilot — the in-process scheduler. Pulse now runs itself.

Before this, every recurring behavior (offline sweeps, SLA breach detection,
weekly digest, scheduled reports, recurring invoices, auto-posts, connector
health) only happened when an EXTERNAL cron hit /api/automation/run-checks —
one more thing to install, one more thing to silently not be running.

Now a daemon thread inside the API process runs the same master tick every
couple of minutes. Nothing to install, nothing to forget. The thread:
  * starts on app startup (disable with SCHEDULER_ENABLED=0 for tests/dev),
  * waits FIRST_DELAY_SEC before the first tick so boot (and fast test runs)
    finish undisturbed,
  * skips a tick when another worker ran one recently (DB-recency guard, so
    multi-worker deployments don't double-send),
  * records every tick as a SchedulerRun row driving the Settings panel.

Every job inside the tick is idempotent/deduped, so an occasional double-run
is harmless by design — the guard just avoids pointless work.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import SchedulerRun

INTERVAL_SEC = 120        # matches the cadence the old external cron used
FIRST_DELAY_SEC = 90      # let boot/migrations settle; outlives fast test runs

_thread: threading.Thread | None = None
_stop = threading.Event()


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def enabled_by_env() -> bool:
    return str(os.environ.get("SCHEDULER_ENABLED", "1")).lower() not in (
        "0", "false", "no", "off")


def _recent_auto_run(db: Session, now: datetime) -> bool:
    last = (db.query(SchedulerRun).filter(SchedulerRun.source == "auto")
            .order_by(SchedulerRun.id.desc()).first())
    if not last or not last.ran_at:
        return False
    return (now - _aware(last.ran_at)) < timedelta(seconds=INTERVAL_SEC * 0.75)


def tick(db: Session, *, source: str = "auto") -> dict:
    """Run the master heartbeat once and record it. Used by the background
    thread (source='auto') and the Settings panel's Run-now (source='manual')."""
    from . import heartbeat
    now = datetime.now(timezone.utc)
    t0 = time.monotonic()
    ok = True
    try:
        result = heartbeat.run_all(db, now)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        ok = False
        result = {"error": str(e)[:400]}
    run = SchedulerRun(ran_at=now, source=source, ok=ok,
                       duration_ms=int((time.monotonic() - t0) * 1000),
                       summary=json.dumps(result, default=str)[:4000])
    db.add(run)
    # Keep history bounded (~last 500 ticks ≈ 17 hours at 2-min cadence).
    try:
        stale = (db.query(SchedulerRun.id)
                 .order_by(SchedulerRun.id.desc()).offset(500).all())
        if stale:
            (db.query(SchedulerRun)
             .filter(SchedulerRun.id.in_([s[0] for s in stale]))
             .delete(synchronize_session=False))
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return result


def _loop() -> None:
    from ..core.db import SessionLocal
    if _stop.wait(FIRST_DELAY_SEC):
        return
    while not _stop.is_set():
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            if not _recent_auto_run(db, now):
                tick(db, source="auto")
        except Exception as e:  # noqa: BLE001
            print(f"[autopilot] tick error: {e}")
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            db.close()
        if _stop.wait(INTERVAL_SEC):
            return


def start() -> bool:
    """Start the Autopilot thread (idempotent). Returns whether it's running."""
    global _thread
    if not enabled_by_env():
        return False
    if _thread is not None and _thread.is_alive():
        return True
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="pulse-autopilot", daemon=True)
    _thread.start()
    return True


def stop() -> None:
    _stop.set()


def status(db: Session) -> dict:
    runs = (db.query(SchedulerRun)
            .order_by(SchedulerRun.id.desc()).limit(10).all())
    now = datetime.now(timezone.utc)
    last_auto = next((r for r in runs if r.source == "auto"), None)
    next_eta = None
    running = _thread is not None and _thread.is_alive()
    if running:
        base = _aware(last_auto.ran_at) if last_auto else now
        next_eta = max(0, int((base + timedelta(seconds=INTERVAL_SEC) - now)
                              .total_seconds())) if last_auto else FIRST_DELAY_SEC
    return {
        "running": running,
        "enabled": enabled_by_env(),
        "interval_seconds": INTERVAL_SEC,
        "next_tick_eta_seconds": next_eta,
        "recent_runs": [{
            "ran_at": r.ran_at.isoformat() if r.ran_at else None,
            "source": r.source, "ok": r.ok, "duration_ms": r.duration_ms,
            "summary": (json.loads(r.summary) if r.summary else None),
        } for r in runs],
    }
