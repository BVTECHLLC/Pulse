"""v0.49 Google Business Profile — publish localPosts (reputation/visibility).

OAuth refresh-token flow (Google). Posts a short update + optional call-to-action
button to a GBP location. Creds in the vault. stdlib HTTP; the token + API calls
go through ``_token`` / ``_api`` which tests override (verifiable offline).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib import error, parse
from urllib import request as urlrequest

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GBP_API = "https://mybusiness.googleapis.com/v4"


class GBPError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GBPClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 account_name: str, location_name: str):
        if not (client_id and client_secret and refresh_token and account_name and location_name):
            raise GBPError("Google Business Profile is not fully configured")
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        # e.g. "accounts/123" and "locations/456" (or "accounts/123/locations/456")
        self.account_name = account_name.strip().strip("/")
        self.location_name = location_name.strip().strip("/")
        self._access = None
        self._exp = None

    def _parent(self) -> str:
        loc = self.location_name
        if loc.startswith("accounts/"):
            return loc
        if "/" not in loc:
            loc = f"locations/{loc}" if not loc.startswith("locations/") else loc
        return f"{self.account_name}/{loc}"

    def _token(self) -> str:
        if self._access and self._exp and self._exp > _utcnow() + timedelta(seconds=60):
            return self._access
        data = parse.urlencode({"client_id": self.client_id, "client_secret": self.client_secret,
                                "refresh_token": self.refresh_token,
                                "grant_type": "refresh_token"}).encode()
        req = urlrequest.Request(GOOGLE_TOKEN_URL, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                tok = json.loads(r.read().decode())
        except error.HTTPError as e:
            raise GBPError(f"Google token refresh failed (HTTP {e.code}): "
                           f"{e.read().decode(errors='replace')[:200]}")
        except Exception as e:  # noqa: BLE001
            raise GBPError(f"Google token refresh failed: {e}")
        self._access = tok["access_token"]
        self._exp = _utcnow() + timedelta(seconds=int(tok.get("expires_in", 3600)))
        return self._access

    def _api(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{GBP_API}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urlrequest.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"})
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except error.HTTPError as e:
            raise GBPError(f"GBP API {method} failed (HTTP {e.code}): "
                           f"{e.read().decode(errors='replace')[:200]}")
        except Exception as e:  # noqa: BLE001
            raise GBPError(f"GBP API request failed: {e}")

    def create_post(self, summary: str, cta_url: str | None = None,
                    cta_type: str = "LEARN_MORE") -> dict:
        body: dict = {"languageCode": "en-US", "summary": summary[:1500],
                      "topicType": "STANDARD"}
        if cta_url:
            body["callToAction"] = {"actionType": cta_type, "url": cta_url}
        return self._api("POST", f"{self._parent()}/localPosts", body)
