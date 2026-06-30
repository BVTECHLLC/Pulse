"""Tactical RMM integration (v0.42) — ported from the BVTech Command Center.

A read-first REST client for a self-hosted Tactical RMM instance (the open RMM
that "replaces SuperOps"). Credentials (base URL + API key) are stored in the
Pulse secure vault, encrypted at rest. The base URL is **user-supplied**, so
every request is SSRF-guarded: the host is resolved and any private / loopback /
link-local (incl. cloud metadata 169.254.169.254) / reserved address is refused.

Auth: ``X-API-KEY`` header (Tactical RMM API-key auth). Uses stdlib urllib to
avoid adding a ``requests`` dependency (matches services/m365.py).
"""
from __future__ import annotations

import json
from urllib import error, parse
from urllib import request as urlrequest

from . import netdiag


class TRMMError(Exception):
    pass


def _guard_url(raw: str) -> str:
    """Validate scheme/host and SSRF-guard the resolved IPs. Returns clean base."""
    base = (raw or "").strip().rstrip("/")
    if not base:
        raise TRMMError("Tactical RMM URL is not configured")
    parsed = parse.urlparse(base)
    if parsed.scheme not in ("http", "https"):
        raise TRMMError("Tactical RMM URL must be http(s)")
    host = parsed.hostname
    if not host:
        raise TRMMError("Tactical RMM URL has no host")
    # Resolve + guard against internal/metadata ranges (raises DiagError otherwise).
    try:
        netdiag.resolve(host)
    except netdiag.DiagError as e:
        raise TRMMError(f"Refusing to connect to {host}: {e}")
    return base


class TacticalRMMClient:
    """REST client for self-hosted Tactical RMM (read-first, SSRF-guarded)."""

    def __init__(self, base_url: str, api_key: str):
        self.base = _guard_url(base_url)
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise TRMMError("Tactical RMM API key is not configured")

    # -- low-level ---------------------------------------------------------- #
    def _request(self, method: str, path: str, params: dict | None = None,
                 body: dict | None = None) -> object:
        url = f"{self.base}/{path.lstrip('/')}"
        if params:
            url += "?" + parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urlrequest.Request(url, data=data, method=method, headers={
            "Content-Type": "application/json", "X-API-KEY": self.api_key,
        })
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (401, 403):
                raise TRMMError(f"Tactical RMM auth failed (HTTP {e.code}) — check the API key.")
            raise TRMMError(f"Tactical RMM HTTP {e.code}: {detail}")
        except Exception as e:  # noqa: BLE001
            raise TRMMError(f"Tactical RMM request failed: {e}")

    def _get(self, path, params=None):
        return self._request("GET", path, params=params)

    def _post(self, path, body=None):
        return self._request("POST", path, body=body or {})

    def _put(self, path, body=None):
        return self._request("PUT", path, body=body or {})

    # -- agents ------------------------------------------------------------- #
    def get_agents(self, detail: bool = False) -> list:
        out = self._get("agents/", {} if detail else {"detail": "false"})
        return out if isinstance(out, list) else []

    def get_agent(self, agent_id: str) -> dict:
        out = self._get(f"agents/{agent_id}/")
        return out if isinstance(out, dict) else {}

    def reboot_agent(self, agent_id: str) -> dict:
        return self._post(f"agents/{agent_id}/reboot/")  # type: ignore[return-value]

    # -- clients / sites ---------------------------------------------------- #
    def get_clients(self) -> list:
        out = self._get("clients/")
        return out if isinstance(out, list) else []

    def get_sites(self) -> list:
        out = self._get("sites/")
        return out if isinstance(out, list) else []

    # -- alerts ------------------------------------------------------------- #
    def get_alerts(self, severity: str | None = None, resolved: bool | None = None) -> list:
        params: dict = {}
        if severity:
            params["severity"] = severity
        if resolved is not None:
            params["resolved"] = str(resolved).lower()
        out = self._get("alerts/", params)
        return out if isinstance(out, list) else []

    def resolve_alert(self, alert_id: str) -> dict:
        return self._put(f"alerts/{alert_id}/resolve/")  # type: ignore[return-value]

    # -- services ----------------------------------------------------------- #
    def get_services(self, agent_id: str) -> object:
        return self._get(f"services/{agent_id}/")

    def control_service(self, agent_id: str, svc_name: str, action: str) -> dict:
        if action not in ("start", "stop", "restart"):
            raise TRMMError("service action must be start|stop|restart")
        return self._post(f"services/{agent_id}/{action}/", {"svc_name": svc_name})  # type: ignore[return-value]

    # -- windows updates ---------------------------------------------------- #
    def scan_updates(self, agent_id: str) -> dict:
        return self._post(f"winupdate/{agent_id}/scan/")  # type: ignore[return-value]

    def get_updates(self, agent_id: str) -> object:
        return self._get(f"winupdate/{agent_id}/")

    def install_updates(self, agent_id: str) -> dict:
        return self._post(f"winupdate/{agent_id}/install/")  # type: ignore[return-value]

    # -- software ----------------------------------------------------------- #
    def get_software(self, agent_id: str) -> object:
        return self._get(f"software/{agent_id}/")

    # -- dashboard rollup --------------------------------------------------- #
    def get_dashboard(self) -> dict:
        agents = self.get_agents(detail=False)
        total = len(agents)
        online = sum(1 for a in agents if (a or {}).get("status") == "online")
        alerts = self.get_alerts(resolved=False)
        clients = self.get_clients()
        return {
            "total_agents": total, "online": online, "offline": total - online,
            "active_alerts": len(alerts), "clients": len(clients),
        }


def summarize_agent(a: dict) -> dict:
    """Project a Tactical RMM agent record down to the fields the UI shows."""
    return {
        "id": a.get("agent_id") or a.get("id"),
        "hostname": a.get("hostname"),
        "client": a.get("client_name") or a.get("client"),
        "site": a.get("site_name") or a.get("site"),
        "status": a.get("status"),
        "os": a.get("operating_system") or a.get("plat"),
        "last_seen": a.get("last_seen"),
        "needs_reboot": a.get("needs_reboot"),
        "pending_actions": a.get("pending_actions_count"),
        "cpu": a.get("cpu_load") or a.get("cpu_model"),
        "checks": a.get("checks"),
    }


def summarize_alert(a: dict) -> dict:
    return {
        "id": a.get("id"),
        "severity": a.get("severity"),
        "message": a.get("message") or a.get("alert_type"),
        "agent": a.get("hostname") or a.get("agent"),
        "client": a.get("client"),
        "snoozed": a.get("snoozed"),
        "resolved": a.get("resolved"),
        "created": a.get("alert_time") or a.get("created_time"),
    }
