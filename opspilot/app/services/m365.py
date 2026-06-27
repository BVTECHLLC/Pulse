"""Microsoft 365 (Graph) integration — read-only, app-only, multi-tenant.

The MSP registers ONE Entra app (M365_CLIENT_ID / M365_CLIENT_SECRET in env);
each customer tenant grants admin consent to read-only Graph scopes. For a given
connection we fetch an app-only token for that tenant and pull:
  * subscribedSkus  -> auto-populate licenses (feeds the billing rollup)
  * secureScore     -> store on the connection
  * riskyUsers      -> raise alerts (which automation rules can act on)

`sync_connection(db, conn, graph)` takes any object implementing the three
get_* methods, so it's fully testable with a fake Graph client (no network/creds).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib import parse, request

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import (
    Alert, AlertSeverity, AlertStatus, License, M365Connection,
)
from . import crypto


class GraphError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Real Graph client (stdlib HTTP; no extra runtime deps)
# --------------------------------------------------------------------------- #
class GraphClient:
    def __init__(self, tenant_id: str):
        self.s = get_settings()
        if not self.s.m365_enabled:
            raise GraphError("Microsoft 365 is not configured (set M365_CLIENT_ID / M365_CLIENT_SECRET)")
        self.tenant_id = tenant_id
        self.last_token: str | None = None
        self.last_expiry: datetime | None = None

    def _token(self) -> str:
        if self.last_token and self.last_expiry and self.last_expiry > _utcnow() + timedelta(seconds=60):
            return self.last_token
        url = f"{self.s.M365_LOGIN_BASE}/{self.tenant_id}/oauth2/v2.0/token"
        body = parse.urlencode({
            "client_id": self.s.M365_CLIENT_ID,
            "client_secret": self.s.M365_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }).encode()
        try:
            with request.urlopen(request.Request(url, data=body), timeout=30) as r:
                tok = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            raise GraphError(f"token request failed: {e}")
        self.last_token = tok["access_token"]
        self.last_expiry = _utcnow() + timedelta(seconds=int(tok.get("expires_in", 3600)))
        return self.last_token

    def _get(self, path: str) -> dict:
        url = f"{self.s.M365_GRAPH_BASE}{path}"
        req = request.Request(url, headers={"Authorization": f"Bearer {self._token()}"})
        try:
            with request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            raise GraphError(f"graph GET {path} failed: {e}")

    def get_subscribed_skus(self) -> list[dict]:
        data = self._get("/subscribedSkus")
        out = []
        for s in data.get("value", []):
            out.append({
                "sku": s.get("skuPartNumber", "unknown"),
                "enabled": (s.get("prepaidUnits") or {}).get("enabled"),
                "consumed": s.get("consumedUnits"),
            })
        return out

    def get_secure_score(self) -> dict | None:
        data = self._get("/security/secureScores?$top=1")
        vals = data.get("value", [])
        if not vals:
            return None
        return {"current": int(vals[0].get("currentScore", 0)), "max": int(vals[0].get("maxScore", 0))}

    def get_risky_signins(self) -> list[dict]:
        data = self._get("/identityProtection/riskyUsers?$top=50")
        out = []
        for u in data.get("value", []):
            out.append({"upn": u.get("userPrincipalName", "unknown"),
                        "risk_level": (u.get("riskLevel") or "low").lower()})
        return out


# --------------------------------------------------------------------------- #
# Sync (graph is injectable — pass a fake in tests)
# --------------------------------------------------------------------------- #
def _risk_to_severity(level: str) -> AlertSeverity | None:
    if level == "high":
        return AlertSeverity.CRITICAL
    if level == "medium":
        return AlertSeverity.WARNING
    return None


def sync_connection(db: Session, conn: M365Connection, graph) -> dict:
    """Pull SKUs/score/risky users for one connection. Upserts licenses, stores
    the score, and returns (summary, new_alerts). Commits its own work."""
    new_alerts: list[Alert] = []

    # 1) Licenses from subscribedSkus -> billing.
    skus = graph.get_subscribed_skus()
    for s in skus:
        lic = (db.query(License)
               .filter(License.client_id == conn.client_id, License.product == s["sku"],
                       License.vendor == "Microsoft 365").first())
        if not lic:
            lic = License(client_id=conn.client_id, product=s["sku"], vendor="Microsoft 365")
            db.add(lic)
        lic.seats = s.get("enabled")
        lic.seats_used = s.get("consumed")
    conn.license_count = len(skus)

    # 2) Secure score.
    score = graph.get_secure_score()
    if score:
        conn.secure_score = score["current"]
        conn.secure_score_max = score["max"]

    # 3) Risky sign-ins -> alerts (deduped per user, auto-dispatch to automation).
    risky = graph.get_risky_signins()
    conn.risky_signin_count = len(risky)
    for r in risky:
        sev = _risk_to_severity(r["risk_level"])
        if sev is None:
            continue
        kind = f"m365_risky_signin:{r['upn']}"
        existing = (db.query(Alert)
                    .filter(Alert.client_id == conn.client_id, Alert.kind == kind,
                            Alert.status != AlertStatus.RESOLVED).first())
        if existing:
            existing.last_seen = _utcnow()
            continue
        a = Alert(client_id=conn.client_id, kind=kind, severity=sev, status=AlertStatus.ACTIVE,
                  message=f"M365 risky sign-in: {r['upn']} ({r['risk_level']})",
                  first_seen=_utcnow(), last_seen=_utcnow())
        db.add(a)
        new_alerts.append(a)

    # Cache the token (encrypted) if the client exposed one.
    tok = getattr(graph, "last_token", None)
    if tok:
        conn.access_token_enc = crypto.encrypt(tok)
        conn.token_expires_at = getattr(graph, "last_expiry", None)

    conn.status = "connected"
    conn.last_sync_at = _utcnow()
    conn.last_sync_status = f"ok: {len(skus)} skus, {len(risky)} risky"
    db.commit()
    return {"skus": len(skus), "secure_score": conn.secure_score,
            "risky_signins": len(risky), "new_alerts": new_alerts}
