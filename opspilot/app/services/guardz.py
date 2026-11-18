"""Guardz (MDR / managed security) connector.

Pulls the Guardz account's open detections/threats and normalizes them so the
portal can raise alerts and security findings alongside everything else.

Auth: a Guardz API token (stored encrypted via Settings → Integrations → Guardz),
sent as a Bearer token. The base URL and the detections resource path are both
part of the stored config (with sensible defaults) so the exact endpoint can be
tuned to the Guardz API version without a code change.

Design note: Guardz's resource shapes can differ by API version, so this client
is deliberately defensive — it tolerates list-or-wrapped JSON and missing fields,
and every call raises a clear GuardzError instead of crashing. The field mapping
in `normalize_detection` should be confirmed once against a live account.
"""
from __future__ import annotations

import json
from urllib import parse, request as urlrequest

DEFAULT_BASE = "https://api.guardz.com"
DEFAULT_DETECTIONS_PATH = "/v1/detections"

# Map common Guardz/MDR severity words to the portal's FindingSeverity values.
_SEV = {
    "critical": "critical", "high": "high", "severe": "high",
    "medium": "medium", "moderate": "medium", "warning": "medium",
    "low": "low", "info": "low", "informational": "low",
}


class GuardzError(Exception):
    pass


class GuardzClient:
    def __init__(self, api_key: str, base_url: str | None = None,
                 detections_path: str | None = None):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise GuardzError("Guardz API key is not set (add it in Settings → Integrations → Guardz).")
        self.base = (base_url or DEFAULT_BASE).rstrip("/")
        self.detections_path = detections_path or DEFAULT_DETECTIONS_PATH

    def _get(self, path: str, params: dict | None = None):
        url = self.base + path
        if params:
            url += "?" + parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = urlrequest.Request(url, method="GET", headers={
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except Exception as e:  # noqa: BLE001
            raise GuardzError(f"Guardz GET {path} failed: {e}")

    @staticmethod
    def _items(data) -> list[dict]:
        """Pull the list of records out of whatever envelope Guardz returns."""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("data", "items", "results", "detections", "value"):
                v = data.get(key)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
            # a single record
            return [data] if data else []
        return []

    def test_connection(self) -> dict:
        """Prove the token works by fetching one detection. Returns a small summary."""
        data = self._get(self.detections_path, params={"limit": 1})
        items = self._items(data)
        return {"ok": True, "endpoint": self.detections_path, "sample_count": len(items)}

    def get_detections(self, limit: int = 100) -> list[dict]:
        data = self._get(self.detections_path, params={"limit": max(1, min(limit, 500))})
        return self._items(data)


def normalize_detection(d: dict) -> dict:
    """Best-effort map of a Guardz detection to the portal's finding shape. Tolerant
    of field-name differences across API versions."""
    def first(*keys, default=None):
        for k in keys:
            v = d.get(k)
            if v not in (None, "", []):
                return v
        return default
    sev_raw = str(first("severity", "riskLevel", "risk", "priority", default="medium")).lower()
    severity = _SEV.get(sev_raw, "medium")
    title = first("title", "name", "detectionName", "type", "ruleName", default="Guardz detection")
    desc = first("description", "summary", "details", "message", default="")
    return {
        "ext_id": str(first("id", "detectionId", "uuid", "_id", default="")),
        "title": str(title)[:200],
        "severity": severity,
        "description": str(desc),
        "category": "guardz",
        "entity": first("deviceName", "userName", "asset", "entity", "hostname", default=None),
        "status": str(first("status", "state", default="open")),
        "created": first("createdAt", "created", "timestamp", "detectedAt", default=None),
    }
