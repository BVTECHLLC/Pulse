"""v0.52 Integration health watchdog.

Runs a cheap liveness check against each *connected* integration, records the
result on the connection, and raises an in-app notification the moment one goes
unhealthy (e.g. an expired token or exhausted API credit). This is what turns a
silent failure — "the posts just stopped" — into something Pulse tells you about.

Each checker returns (status, detail):
  "ok"   — the live call succeeded
  "fail" — configured but the live call errored (raises a notification)
  "skip" — connected but no cheap liveness check exists for it (e.g. LinkedIn)
Checkers are best-effort and never raise; one bad provider can't stop the sweep.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import IntegrationConnection
from . import secure_config


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- per-provider liveness checks (pure: take a config snapshot, do network,
#     return a result — they NEVER touch the DB session) ---------------------- #
def _check_m365(cfg) -> tuple[str, str]:
    from . import m365
    if not secure_config.configured(cfg, ("tenant_id", "client_id", "client_secret")):
        return "skip", "not configured"
    m365.GraphClient(
        str(secure_config.get_secret(cfg, "tenant_id") or cfg.get("tenant_id")),
        str(secure_config.get_secret(cfg, "client_id") or cfg.get("client_id")),
        str(secure_config.get_secret(cfg, "client_secret"))).ping()
    return "ok", "token OK"


def _check_hubspot(cfg) -> tuple[str, str]:
    from . import hubspot
    token = secure_config.get_secret(cfg, "token")
    if not token:
        return "skip", "not configured"
    hubspot.HubSpotClient(str(token)).whoami()
    return "ok", "auth OK"


def _check_quickbooks(cfg) -> tuple[str, str]:
    from . import quickbooks
    if not secure_config.configured(cfg, ("client_id", "client_secret", "refresh_token", "realm_id")):
        return "skip", "not configured"
    quickbooks.QBOClient(
        str(secure_config.get_secret(cfg, "client_id") or cfg.get("client_id")),
        str(secure_config.get_secret(cfg, "client_secret")),
        str(secure_config.get_secret(cfg, "refresh_token")),
        str(cfg.get("realm_id")), sandbox=bool(cfg.get("sandbox"))).company_name()
    return "ok", "company OK"


def _check_gbp(cfg) -> tuple[str, str]:
    from . import gbp
    req = ("client_id", "client_secret", "refresh_token", "account_name", "location_name")
    if not secure_config.configured(cfg, req):
        return "skip", "not configured"
    gbp.GBPClient(
        str(secure_config.get_secret(cfg, "client_id") or cfg.get("client_id")),
        str(secure_config.get_secret(cfg, "client_secret")),
        str(secure_config.get_secret(cfg, "refresh_token")),
        str(cfg.get("account_name")), str(cfg.get("location_name"))).ping()
    return "ok", "token OK"


def _check_rmm(cfg) -> tuple[str, str]:
    from . import tacticalrmm
    if not secure_config.configured(cfg, ("base_url", "api_key")):
        return "skip", "not configured"
    tacticalrmm.TacticalRMMClient(
        str(cfg.get("base_url") or secure_config.get_secret(cfg, "base_url")),
        str(secure_config.get_secret(cfg, "api_key"))).get_dashboard()
    return "ok", "dashboard OK"


# Providers with a cheap, side-effect-free liveness check.
CHECKERS = {
    "m365_mailbox": _check_m365,
    "hubspot": _check_hubspot,
    "quickbooks": _check_quickbooks,
    "gbp": _check_gbp,
    "tacticalrmm": _check_rmm,
}


def check_all(db: Session, *, notify: bool = True) -> dict:
    """Run every available checker, then persist. Network I/O happens FIRST (with
    no DB transaction held open), then a single short write records results and
    raises a notification on each NEW failure (healthy/unknown -> failing)."""
    # 1) Snapshot what we need — id, provider, config, prior health — so the slow
    #    network checks below don't hold the DB session/transaction open.
    targets = [(conn.id, conn.provider, conn.name, dict(conn.config or {}), conn.last_health_ok)
               for conn in db.query(IntegrationConnection)
               .filter(IntegrationConnection.client_id.is_(None)).all()
               if conn.provider in CHECKERS]

    # 2) Run the live checks (pure network, no DB).
    checked = []
    results = []
    for cid, provider, name, cfg, was_ok in targets:
        try:
            status, detail = CHECKERS[provider](cfg)
        except Exception as e:  # noqa: BLE001
            status, detail = "fail", str(e)[:280]
        results.append({"provider": provider, "status": status, "detail": detail})
        if status != "skip":
            checked.append((cid, name, status == "ok", detail, was_ok))

    # 3) Persist results in one short transaction.
    newly_failed = []
    for cid, name, ok, detail, was_ok in checked:
        conn = db.get(IntegrationConnection, cid)
        if not conn:
            continue
        conn.last_health_at = _now()
        conn.last_health_ok = ok
        conn.last_health_error = None if ok else detail
        if not ok and was_ok is not False:
            newly_failed.append((name, detail))
    db.commit()

    # 4) Raise a notification per NEW failure (best-effort).
    if notify and newly_failed:
        from ..models import Notification
        from . import notifications as notif_svc
        for name, detail in newly_failed:
            msg = f"Integration '{name}' is failing: {detail[:200]}"
            db.add(Notification(client_id=None, kind="integration_health",
                                severity="critical", message=msg[:1000]))
            try:
                notif_svc.fanout(db, message=msg, severity="critical", client_id=None)
            except Exception:
                pass
        db.commit()

    return {"checked": len(checked),
            "failing": len([r for r in results if r["status"] == "fail"]),
            "newly_failed": len(newly_failed), "results": results}
