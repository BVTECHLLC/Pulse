"""v0.49 HubSpot CRM connector — push Pulse CRM contacts + log activity to HubSpot.

Uses a HubSpot private-app token (Bearer; no OAuth dance). stdlib HTTP; the
``_api`` method is overridden in tests so the upsert/note mapping is verifiable
offline.
"""
from __future__ import annotations

import json
from urllib import error
from urllib import request as urlrequest

API = "https://api.hubapi.com"


class HubSpotError(Exception):
    pass


class HubSpotClient:
    def __init__(self, token: str):
        if not token:
            raise HubSpotError("HubSpot token is not configured")
        self.token = token

    def _api(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{API}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urlrequest.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except error.HTTPError as e:
            raise HubSpotError(f"HubSpot API {method} failed (HTTP {e.code}): "
                               f"{e.read().decode(errors='replace')[:200]}")
        except Exception as e:  # noqa: BLE001
            raise HubSpotError(f"HubSpot API request failed: {e}")

    def whoami(self) -> dict:
        """Cheap auth check — lists 1 contact (200 == token works)."""
        return self._api("GET", "crm/v3/objects/contacts?limit=1")

    def upsert_contact(self, *, email: str | None, name: str | None = None,
                       phone: str | None = None, company: str | None = None) -> str:
        """Create or update a contact (keyed on email). Returns the contact id."""
        first, last = "", ""
        if name:
            parts = name.split(" ", 1)
            first, last = parts[0], (parts[1] if len(parts) > 1 else "")
        props = {k: v for k, v in {
            "email": email, "firstname": first, "lastname": last,
            "phone": phone, "company": company,
        }.items() if v}
        if email:
            # Search by email; update if found, else create.
            found = self._api("POST", "crm/v3/objects/contacts/search", {
                "filterGroups": [{"filters": [
                    {"propertyName": "email", "operator": "EQ", "value": email}]}],
                "limit": 1})
            results = found.get("results") or []
            if results:
                cid = results[0]["id"]
                self._api("PATCH", f"crm/v3/objects/contacts/{cid}", {"properties": props})
                return cid
        created = self._api("POST", "crm/v3/objects/contacts", {"properties": props})
        return created["id"]

    def flag_unqualified(self, email: str, note: str = "") -> bool:
        """v1.88 write-back: when Pulse suppresses/bounces a lead, mark the same
        HubSpot contact UNQUALIFIED (+ optional note) so the source list
        self-cleans. Returns True if the contact was found and updated."""
        if not email:
            return False
        found = self._api("POST", "crm/v3/objects/contacts/search", {
            "filterGroups": [{"filters": [
                {"propertyName": "email", "operator": "EQ", "value": email}]}],
            "limit": 1})
        results = found.get("results") or []
        if not results:
            return False
        cid = results[0]["id"]
        self._api("PATCH", f"crm/v3/objects/contacts/{cid}",
                  {"properties": {"hs_lead_status": "UNQUALIFIED"}})
        if note:
            try:
                self.log_note(cid, note)
            except HubSpotError:
                pass
        return True

    def log_note(self, contact_id: str, body: str) -> str:
        note = self._api("POST", "crm/v3/objects/notes", {
            "properties": {"hs_note_body": body[:65000], "hs_timestamp": _ms_now()},
            "associations": [{"to": {"id": contact_id},
                              "types": [{"associationCategory": "HUBSPOT_DEFINED",
                                         "associationTypeId": 202}]}]})
        return note.get("id", "")


def _ms_now() -> int:
    # HubSpot wants an epoch-ms timestamp; computed without Date.now in tests via time.
    import time
    return int(time.time() * 1000)
