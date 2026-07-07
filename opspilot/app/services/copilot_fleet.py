"""v1.14 Multi-agent fleet workflows — Copilot that fans out across every client.

A single Copilot loop answers "how is Acme doing?". A *fleet sweep* answers the
harder MSP question — "go through ALL my clients and <do X>" — by spawning one
governed sub-agent PER CLIENT, in parallel, each pinned to that client's data
(client_scope), then synthesising a portfolio-level answer.

Each sub-agent is a full agentic Copilot: it can read the client's health,
posture, tickets and predictions and — when the operator has confirmed
(allow_actions) — take the same governed write actions (approve patches, open a
ticket, schedule maintenance) scoped to that one client. Nothing leaks across
tenants: a sub-agent for client A literally cannot see client B.

Parallelism is real: each worker runs on its own DB session in a thread pool, so
N clients are analysed concurrently rather than one-after-another.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from ..core.db import SessionLocal
from ..core.deps import is_staff
from ..models import Client, User
from . import ai, copilot

MAX_CLIENTS = 40          # hard cap so one sweep can't fan out unbounded
MAX_WORKERS = 6           # concurrent sub-agents (each an AI tool-use loop)


def _sub_task(objective: str, client_name: str, client_id: int) -> str:
    return (
        f"You are analysing exactly ONE managed client: {client_name} "
        f"(client_id={client_id}). Every tool you call is already restricted to "
        f"this client. Objective: {objective}\n\n"
        "Do the work with the tools, then reply with a short verdict (1-3 "
        "sentences) covering: the client's current state relevant to the "
        "objective, and any action you took or recommend. Be specific with "
        "numbers from the tools; never guess."
    )


def _analyse_one(caller_user_id: int, objective: str, client_id: int,
                 client_name: str, allow_actions: bool) -> dict:
    """Run one per-client sub-agent on its OWN session (thread-safe)."""
    s: Session = SessionLocal()
    try:
        u = s.get(User, caller_user_id)
        if u is None:
            return {"client_id": client_id, "client": client_name,
                    "answer": "(caller not found)", "actions": [],
                    "proposed_actions": [], "tools_used": []}
        out = copilot.run(s, u, _sub_task(objective, client_name, client_id),
                          allow_actions=allow_actions, client_scope=client_id)
        return {"client_id": client_id, "client": client_name, **out}
    except Exception as e:  # noqa: BLE001 — one client failing must not sink the sweep
        return {"client_id": client_id, "client": client_name,
                "answer": f"(analysis failed: {e})", "actions": [],
                "proposed_actions": [], "tools_used": [], "error": str(e)}
    finally:
        s.close()


def _synthesize(objective: str, results: list[dict]) -> str:
    """Roll the per-client verdicts into one portfolio answer."""
    lines = []
    for r in results:
        acted = len(r.get("actions") or [])
        prop = len(r.get("proposed_actions") or [])
        tag = ""
        if acted:
            tag = f" [{acted} action(s) taken]"
        elif prop:
            tag = f" [{prop} action(s) proposed]"
        lines.append(f"- {r['client']}: {r.get('answer', '').strip()}{tag}")
    body = "\n".join(lines)
    if ai.enabled() and results:
        try:
            return ai.complete(
                "You are Pulse Copilot summarising a fleet-wide sweep for an MSP "
                "owner. Give a crisp portfolio verdict: lead with the headline, "
                "then call out the clients that need attention first. Be concrete; "
                "don't repeat every client if nothing's wrong with them.",
                f"Objective: {objective}\n\nPer-client findings:\n{body}\n\n"
                "Write the summary (max ~8 lines).", max_tokens=500)
        except Exception:  # noqa: BLE001
            pass
    header = f"Swept {len(results)} client(s) for: {objective}\n\n"
    return header + (body or "No clients in scope.")


def _clients_in_scope(db: Session, user: User, max_clients: int) -> list[Client]:
    if is_staff(user):
        return db.query(Client).order_by(Client.name).limit(max_clients).all()
    # A client user can only ever sweep their own company (one sub-agent).
    c = db.get(Client, user.client_id) if user.client_id else None
    return [c] if c else []


def sweep(db: Session, user: User, objective: str, *, allow_actions: bool = False,
          max_clients: int = MAX_CLIENTS) -> dict:
    """Fan a governed sub-agent out across every in-scope client, in parallel,
    then synthesise. Returns {objective, results[], summary, totals}."""
    objective = (objective or "").strip()
    clients = [c for c in _clients_in_scope(db, user, max_clients) if c]
    if not clients:
        return {"objective": objective, "results": [],
                "summary": "No clients in scope to sweep.",
                "totals": {"clients": 0, "actions": 0, "proposed": 0}}

    results: list[dict] = []
    workers = min(MAX_WORKERS, len(clients))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_analyse_one, user.id, objective, c.id, c.name, allow_actions)
                for c in clients]
        for f in as_completed(futs):
            results.append(f.result())

    results.sort(key=lambda r: (r.get("client") or "").lower())
    totals = {
        "clients": len(results),
        "actions": sum(len(r.get("actions") or []) for r in results),
        "proposed": sum(len(r.get("proposed_actions") or []) for r in results),
    }
    return {"objective": objective, "results": results,
            "summary": _synthesize(objective, results), "totals": totals}
