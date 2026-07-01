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
# Account + location listing live on the newer split APIs.
GBP_ACCOUNTS_API = "https://mybusinessaccountmanagement.googleapis.com/v1"
GBP_INFO_API = "https://mybusinessbusinessinformation.googleapis.com/v1"


class GBPError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GBPClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 account_name: str = "", location_name: str = ""):
        # account/location are only needed to POST; listing them needs just the
        # OAuth credentials, so they're optional at construction.
        if not (client_id and client_secret and refresh_token):
            raise GBPError("Google Business Profile is not connected (missing OAuth credentials)")
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        # e.g. "accounts/123" and "locations/456" (or "accounts/123/locations/456")
        self.account_name = (account_name or "").strip().strip("/")
        self.location_name = (location_name or "").strip().strip("/")
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

    def _get_url(self, url: str) -> dict:
        """GET an absolute Google API URL with the bearer token (tests override)."""
        req = urlrequest.Request(url, method="GET",
                                 headers={"Authorization": f"Bearer {self._token()}"})
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except error.HTTPError as e:
            raise GBPError(f"GBP list failed (HTTP {e.code}): "
                           f"{e.read().decode(errors='replace')[:200]}")
        except Exception as e:  # noqa: BLE001
            raise GBPError(f"GBP list request failed: {e}")

    def ping(self) -> bool:
        """Cheap liveness check — refreshes the OAuth token."""
        self._token()
        return True

    def list_locations(self) -> list[dict]:
        """Every location the connected account manages, ready for a picker:
        [{account, location, title, address}]. So the user never hand-types IDs."""
        accts = self._get_url(f"{GBP_ACCOUNTS_API}/accounts").get("accounts", [])
        out = []
        for a in accts:
            acct_name = a.get("name")   # "accounts/123"
            if not acct_name:
                continue
            url = (f"{GBP_INFO_API}/{acct_name}/locations"
                   "?readMask=name,title,storefrontAddress&pageSize=100")
            locs = self._get_url(url).get("locations", [])
            for loc in locs:
                addr = loc.get("storefrontAddress") or {}
                lines = addr.get("addressLines") or []
                city = addr.get("locality") or ""
                region = addr.get("administrativeArea") or ""
                pretty = ", ".join([x for x in [", ".join(lines), city, region] if x])
                out.append({"account": acct_name, "location": loc.get("name"),
                            "title": loc.get("title") or loc.get("name"),
                            "address": pretty})
        return out

    def create_post(self, summary: str, cta_url: str | None = None,
                    cta_type: str = "LEARN_MORE", image_url: str | None = None) -> dict:
        body: dict = {"languageCode": "en-US", "summary": summary[:1500],
                      "topicType": "STANDARD"}
        if cta_url:
            body["callToAction"] = {"actionType": cta_type, "url": cta_url}
        # A photo lifts engagement (and SEO) a lot. Google fetches the image from
        # the public sourceUrl — it must be a reachable https JPG/PNG.
        if image_url:
            body["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": image_url}]
        return self._api("POST", f"{self._parent()}/localPosts", body)
