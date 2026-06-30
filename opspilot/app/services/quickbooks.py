"""v0.48 QuickBooks Online integration — push Pulse invoices to QBO.

The MSP connects QuickBooks once (client id/secret + realm id + a long-lived
refresh token, all stored encrypted in the vault). We exchange the refresh token
for a short-lived access token on demand and call the QBO v3 API to find/create
the customer and create the invoice.

stdlib HTTP (no new deps). The token + API calls go through ``_token`` / ``_api``
which tests override, so the customer/invoice mapping is verifiable offline.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from urllib import error, parse
from urllib import request as urlrequest

TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_PROD = "https://quickbooks.api.intuit.com/v3/company"
API_SANDBOX = "https://sandbox-quickbooks.api.intuit.com/v3/company"


class QBOError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QBOClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 realm_id: str, sandbox: bool = False):
        if not (client_id and client_secret and refresh_token and realm_id):
            raise QBOError("QuickBooks is not fully configured")
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.realm_id = realm_id
        self.base = (API_SANDBOX if sandbox else API_PROD) + f"/{realm_id}"
        self._access = None
        self._exp = None

    # -- auth --------------------------------------------------------------- #
    def _token(self) -> str:
        if self._access and self._exp and self._exp > _utcnow() + timedelta(seconds=60):
            return self._access
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        data = parse.urlencode({"grant_type": "refresh_token",
                                "refresh_token": self.refresh_token}).encode()
        req = urlrequest.Request(TOKEN_URL, data=data, method="POST", headers={
            "Authorization": f"Basic {basic}", "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                tok = json.loads(r.read().decode())
        except error.HTTPError as e:
            raise QBOError(f"QuickBooks token refresh failed (HTTP {e.code}): "
                           f"{e.read().decode(errors='replace')[:200]}")
        except Exception as e:  # noqa: BLE001
            raise QBOError(f"QuickBooks token refresh failed: {e}")
        self._access = tok["access_token"]
        # QBO also rotates the refresh token; keep the newest for this client life.
        self.refresh_token = tok.get("refresh_token", self.refresh_token)
        self._exp = _utcnow() + timedelta(seconds=int(tok.get("expires_in", 3600)))
        return self._access

    # -- low-level API ------------------------------------------------------ #
    def _api(self, method: str, path: str, body: dict | None = None,
             params: dict | None = None) -> dict:
        url = f"{self.base}/{path.lstrip('/')}"
        if params:
            url += "?" + parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urlrequest.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token()}", "Accept": "application/json",
            "Content-Type": "application/json"})
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except error.HTTPError as e:
            raise QBOError(f"QuickBooks API {method} {path} failed (HTTP {e.code}): "
                           f"{e.read().decode(errors='replace')[:200]}")
        except Exception as e:  # noqa: BLE001
            raise QBOError(f"QuickBooks API request failed: {e}")

    # -- high-level --------------------------------------------------------- #
    def company_name(self) -> str:
        info = self._api("GET", "companyinfo/" + self.realm_id)
        return (info.get("CompanyInfo") or {}).get("CompanyName", "")

    def find_or_create_customer(self, name: str) -> str:
        safe = name.replace("'", "\\'")
        q = self._api("GET", "query", params={
            "query": f"select * from Customer where DisplayName = '{safe}'"})
        rows = (q.get("QueryResponse") or {}).get("Customer") or []
        if rows:
            return rows[0]["Id"]
        created = self._api("POST", "customer", {"DisplayName": name[:100]})
        return created["Customer"]["Id"]

    def create_invoice(self, customer_id: str, lines: list[dict], *,
                       doc_number: str | None = None) -> dict:
        qbo_lines = []
        for ln in lines:
            qbo_lines.append({
                "DetailType": "SalesItemLineDetail",
                "Amount": round(float(ln.get("amount", 0)), 2),
                "Description": (ln.get("description") or "")[:1000],
                "SalesItemLineDetail": {
                    "Qty": float(ln.get("quantity", 1)),
                    "UnitPrice": round(float(ln.get("unit_price", 0)), 2),
                },
            })
        payload: dict = {"CustomerRef": {"value": customer_id}, "Line": qbo_lines}
        if doc_number:
            payload["DocNumber"] = str(doc_number)[:21]
        return self._api("POST", "invoice", payload)


def build_lines(line_items) -> list[dict]:
    """Map Pulse InvoiceLineItem rows to the dicts create_invoice expects."""
    out = []
    for li in line_items:
        out.append({"description": li.description, "quantity": li.quantity or 1,
                    "unit_price": li.unit_price or 0,
                    "amount": li.amount if li.amount is not None else (li.quantity or 1) * (li.unit_price or 0)})
    return out
