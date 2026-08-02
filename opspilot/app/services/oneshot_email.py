"""v1.88.1 One-shot operator emails — queue one-time sends via code deploy.

The box self-deploys CI-green main every ~2 minutes, which makes the repo a
remote control: drop a task in ``TASKS``, merge to main, and the next
heartbeat on the box sends it — exactly once. Each task id is stamped in the
DB (provider ``oneshot_email``) the moment its send succeeds, so redeploys,
restarts, and repeat ticks can never double-send. Transport failures retry on
later ticks, capped at ``MAX_ATTEMPTS``. Delivery uses the same resolved
transport as the outbound engine (M365 Graph with the operator signature).

Intended for operator/personal sends that are not part of a campaign:
corrections, resends to fixed addresses, one-off notices. Ship the list,
watch the Notification confirm, then clear TASKS in a follow-up commit.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "oneshot_email"
MAX_ATTEMPTS = 5

# Each task: {"id": unique-stable-string, "to": email, "subject": ..., "body": ...}
# The id is the idempotency key — NEVER reuse an id for different content.
TASKS: list[dict] = []


def _resolver(db: Session):
    from . import outbound
    return outbound.resolve_send_fn(db)


_SEND_RESOLVER = _resolver          # test seam


def tick(db: Session, now: datetime | None = None) -> dict:
    """Heartbeat entrypoint. Sends every not-yet-done task; harmless when
    TASKS is empty or everything is stamped done."""
    now = now or datetime.now(timezone.utc)
    if not TASKS:
        return {"ran": False, "reason": "no_tasks"}
    conn = secure_config.get_platform(db, PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    done = dict(raw.get("done") or {})
    attempts = {k: int(v) for k, v in dict(raw.get("attempts") or {}).items()}
    pending = [t for t in TASKS
               if t["id"] not in done and attempts.get(t["id"], 0) < MAX_ATTEMPTS]
    if not pending:
        return {"ran": False, "reason": "all_done"}
    send_fn, transport = _SEND_RESOLVER(db)
    if send_fn is None:
        return {"ran": False, "reason": "no_transport", "detail": transport}
    sent = failed = 0
    for task in pending:
        attempts[task["id"]] = attempts.get(task["id"], 0) + 1
        try:
            send_fn(task["to"], task["subject"], task["body"])
            done[task["id"]] = now.date().isoformat()
            sent += 1
        except Exception:  # noqa: BLE001 — transport hiccup: retry next tick
            failed += 1
    secure_config.upsert_platform(db, PROVIDER, "One-shot Emails", "System",
                                  {**raw, "done": done, "attempts": attempts})
    if sent or failed:
        _notify(db, "info" if not failed else "warning",
                f"📮 One-shot emails: {sent} sent, {failed} failed "
                f"(will retry, cap {MAX_ATTEMPTS}) via {transport}.")
    return {"ran": True, "sent": sent, "failed": failed, "transport": transport}


def _notify(db: Session, severity: str, message: str) -> None:
    try:
        from ..models import Notification
        db.add(Notification(client_id=None, target_user_id=None, kind="system",
                            severity=severity, message=message[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
