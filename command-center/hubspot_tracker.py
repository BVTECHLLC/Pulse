#!/usr/bin/env python3
"""
BVTech — HubSpot Tracking & Engagement Logger  v31.0
==============================================================

A thin wrapper around HubSpot's CRM v3 API for tracking manually-
sent emails, call activity, and notes. Used by v31's Super Posting
and HubSpot tabs to make sure every outreach — whether sent from
Gmail, from the tool's campaign module, or logged after the fact —
ends up on the contact's timeline in HubSpot.

DESIGN GOALS
------------
1. **Zero external dependencies beyond `requests`.** Anything
   shelling out to a binary is off the table.
2. **Idempotent-ish.** Logging the same email twice is annoying
   but not catastrophic. A local SQLite dedup cache prevents
   most accidental double-logs (see local_automation.py).
3. **Contact auto-creation.** If you scrape a prospect and then
   email them, the tool should create the HubSpot contact on
   first log instead of failing.
4. **Fail soft.** A tracking failure should never prevent the
   underlying email from being sent. Errors are captured and
   returned so the UI can show them but the caller decides what
   to do.

API ENDPOINTS USED
------------------
  POST /crm/v3/objects/contacts/search
       Find a contact by email (exact EQ match).

  POST /crm/v3/objects/contacts
       Create a contact when one doesn't exist.

  POST /crm/v3/objects/emails
       Log an email engagement on a contact.
       Required properties:
         hs_timestamp              (ms since epoch)
         hs_email_direction        "EMAIL" (outbound) or "INCOMING_EMAIL"
         hs_email_status           "SENT", "BOUNCED", "OPENED", ...
         hs_email_subject
         hs_email_text
       Optional:
         hs_email_headers          (freeform string, often the
                                    raw From/To/Cc headers)
       Associations:
         [{to: {id: contactId},
           types: [{associationCategory: "HUBSPOT_DEFINED",
                    associationTypeId: 198}]}]
       The associationTypeId 198 = EMAIL_TO_CONTACT.

  POST /crm/v3/objects/notes
       Log a sticky note for a contact.

  POST /crm/v3/objects/calls
       Log a call engagement (for Dialpad / power-dialer).

REQUIRED HUBSPOT SCOPES (Private App)
-------------------------------------
  crm.objects.contacts.read
  crm.objects.contacts.write
  crm.objects.emails.write
  crm.schemas.contacts.read

BCC TRACKING
------------
HubSpot also gives every account a unique BCC forwarding address
that auto-logs any email that BCCs it. The address looks like
`yourtoken@bcc.hubspot.com`. This module doesn't fetch it (there's
no API for that — you have to grab it from the HubSpot UI), but it
stores and returns whatever the user puts in config so the UI can
show it prominently.
"""

import json
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    raise ImportError(
        "hubspot_tracker requires the 'requests' package. "
        "Install with: pip install requests"
    )


HUBSPOT_API_BASE = "https://api.hubapi.com"
EMAIL_TO_CONTACT_ASSOCIATION_TYPE_ID = 198
NOTE_TO_CONTACT_ASSOCIATION_TYPE_ID = 202
CALL_TO_CONTACT_ASSOCIATION_TYPE_ID = 194


# ============================================================
# ERROR CLASSES
# ============================================================
class HubSpotAuthError(Exception):
    """401/403 — token invalid or missing scopes."""


class HubSpotRateLimitError(Exception):
    """429 — too many requests."""


class HubSpotAPIError(Exception):
    """Any other 4xx/5xx."""


# ============================================================
# MAIN CLIENT
# ============================================================
class HubSpotTracker:
    """Thin client for HubSpot CRM v3 engagement logging.

    Usage:
        t = HubSpotTracker(api_token="pat-na1-xxxxx")
        contact_id = t.find_or_create_contact("alice@acme.com",
                                                first_name="Alice",
                                                last_name="Smith",
                                                company="Acme Corp")
        t.log_email(contact_id,
                    subject="Quick intro",
                    body="Hi Alice, ...",
                    direction="outgoing")
    """

    def __init__(self, api_token: str,
                 logger: Optional[Callable[[str], None]] = None):
        if not api_token:
            raise ValueError("api_token is required")
        self.token = api_token.strip()
        self.log = logger or (lambda m: None)
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "BVTech-MSP-CommandCenter/31.0 (+hubspot_tracker.py)",
        })

    # ── low-level HTTP with error normalization ────────────
    def _request(self, method: str, path: str,
                  json_body: Optional[dict] = None,
                  params: Optional[dict] = None,
                  timeout: int = 30) -> dict:
        url = f"{HUBSPOT_API_BASE}{path}"
        try:
            r = self._session.request(
                method, url, json=json_body, params=params, timeout=timeout)
        except requests.RequestException as e:
            raise HubSpotAPIError(f"Network error on {method} {path}: {e}")

        if r.status_code in (200, 201):
            try:
                return r.json()
            except ValueError:
                return {}
        if r.status_code == 204:
            return {}

        body = r.text[:500] if r.text else ""
        if r.status_code == 401:
            raise HubSpotAuthError(
                f"401 Unauthorized — HubSpot token is invalid or expired. "
                f"Body: {body}"
            )
        if r.status_code == 403:
            raise HubSpotAuthError(
                f"403 Forbidden — HubSpot token is missing required scopes. "
                f"You need: crm.objects.contacts.read, "
                f"crm.objects.contacts.write, crm.objects.emails.write. "
                f"Body: {body}"
            )
        if r.status_code == 429:
            raise HubSpotRateLimitError(
                f"429 Rate limited. Retry-After: "
                f"{r.headers.get('Retry-After', 'unknown')}"
            )
        raise HubSpotAPIError(
            f"HTTP {r.status_code} on {method} {path}: {body}"
        )

    # ── contacts ───────────────────────────────────────────
    def find_contact_by_email(self, email: str
                                ) -> Optional[Dict[str, Any]]:
        """Look up a contact by exact email match.
        Returns the contact dict with `id` + `properties`, or None."""
        email = (email or "").strip().lower()
        if not email:
            return None
        body = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "email",
                    "operator": "EQ",
                    "value": email,
                }]
            }],
            "properties": ["email", "firstname", "lastname", "company",
                           "phone", "lifecyclestage"],
            "limit": 1,
        }
        try:
            data = self._request("POST",
                                  "/crm/v3/objects/contacts/search",
                                  json_body=body)
        except HubSpotAPIError as e:
            self.log(f"[hubspot] contact search failed: {e}")
            return None
        results = data.get("results", []) or []
        if not results:
            return None
        return results[0]

    def create_contact(self, email: str,
                        first_name: str = "",
                        last_name: str = "",
                        company: str = "",
                        phone: str = "",
                        lifecyclestage: str = "lead",
                        extra_props: Optional[Dict[str, str]] = None
                        ) -> Dict[str, Any]:
        """Create a new contact. Returns the new contact dict."""
        props = {"email": email.strip().lower()}
        if first_name: props["firstname"] = first_name
        if last_name:  props["lastname"] = last_name
        if company:    props["company"] = company
        if phone:      props["phone"] = phone
        if lifecyclestage: props["lifecyclestage"] = lifecyclestage
        if extra_props: props.update(extra_props)
        return self._request("POST",
                              "/crm/v3/objects/contacts",
                              json_body={"properties": props})

    def find_or_create_contact(self, email: str, **kwargs
                                 ) -> Tuple[Optional[str], str]:
        """Returns (contact_id, 'found' | 'created' | 'error:...').
        On any failure, contact_id is None and status is the error."""
        existing = self.find_contact_by_email(email)
        if existing and existing.get("id"):
            return existing["id"], "found"
        try:
            created = self.create_contact(email, **kwargs)
            return created.get("id", ""), "created"
        except HubSpotAPIError as e:
            return None, f"error:{e}"

    # ── engagement: email ──────────────────────────────────
    def log_email(self, contact_id: str,
                   subject: str,
                   body: str,
                   direction: str = "outgoing",
                   status: str = "SENT",
                   headers: str = "",
                   timestamp: Optional[datetime] = None
                   ) -> Tuple[Optional[str], Optional[str]]:
        """Log an email engagement on a contact.

        Args:
            contact_id:  HubSpot contact internal ID
            subject:     email subject line
            body:        email body (plain text or HTML)
            direction:   "outgoing" | "incoming"
            status:      "SENT" | "BOUNCED" | "OPENED" | "REPLIED" ...
            headers:     raw From/To header block, optional
            timestamp:   when the email was sent; defaults to now

        Returns (email_id, error).
        """
        if not contact_id:
            return None, "contact_id is required"
        if not subject and not body:
            return None, "at least one of subject/body is required"

        ts = timestamp or datetime.utcnow()
        ts_ms = int(ts.timestamp() * 1000)

        hs_direction = "EMAIL" if direction == "outgoing" else "INCOMING_EMAIL"

        props = {
            "hs_timestamp": str(ts_ms),
            "hs_email_direction": hs_direction,
            "hs_email_status": status,
            "hs_email_subject": subject[:998],  # HubSpot caps subject
            "hs_email_text": body[:65000],
        }
        if headers:
            props["hs_email_headers"] = headers[:10000]

        body_payload = {
            "properties": props,
            "associations": [{
                "to": {"id": str(contact_id)},
                "types": [{
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": EMAIL_TO_CONTACT_ASSOCIATION_TYPE_ID,
                }],
            }],
        }
        try:
            data = self._request("POST",
                                  "/crm/v3/objects/emails",
                                  json_body=body_payload)
            email_id = data.get("id", "")
            self.log(f"[hubspot] logged email {email_id} to contact {contact_id}")
            return email_id, None
        except HubSpotAPIError as e:
            return None, str(e)

    # ── engagement: note ───────────────────────────────────
    def log_note(self, contact_id: str, body: str,
                  timestamp: Optional[datetime] = None
                  ) -> Tuple[Optional[str], Optional[str]]:
        """Log a sticky note on a contact."""
        if not contact_id:
            return None, "contact_id is required"
        if not body:
            return None, "body is required"
        ts = timestamp or datetime.utcnow()
        ts_ms = int(ts.timestamp() * 1000)
        payload = {
            "properties": {
                "hs_timestamp": str(ts_ms),
                "hs_note_body": body[:65000],
            },
            "associations": [{
                "to": {"id": str(contact_id)},
                "types": [{
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": NOTE_TO_CONTACT_ASSOCIATION_TYPE_ID,
                }],
            }],
        }
        try:
            data = self._request("POST",
                                  "/crm/v3/objects/notes",
                                  json_body=payload)
            return data.get("id", ""), None
        except HubSpotAPIError as e:
            return None, str(e)

    # ── engagement: call ───────────────────────────────────
    def log_call(self, contact_id: str,
                  notes: str,
                  duration_seconds: int = 0,
                  disposition: str = "",
                  direction: str = "OUTBOUND",
                  from_number: str = "",
                  to_number: str = "",
                  timestamp: Optional[datetime] = None
                  ) -> Tuple[Optional[str], Optional[str]]:
        """Log a call engagement. Used by Dialpad and power-dialer flows."""
        if not contact_id:
            return None, "contact_id is required"
        ts = timestamp or datetime.utcnow()
        ts_ms = int(ts.timestamp() * 1000)
        props = {
            "hs_timestamp": str(ts_ms),
            "hs_call_title": notes[:100] if notes else "Call logged from BVTech",
            "hs_call_body": notes[:65000] if notes else "",
            "hs_call_direction": direction,
            "hs_call_status": "COMPLETED",
        }
        if duration_seconds > 0:
            props["hs_call_duration"] = str(duration_seconds * 1000)  # ms
        if disposition:
            props["hs_call_disposition"] = disposition
        if from_number:
            props["hs_call_from_number"] = from_number
        if to_number:
            props["hs_call_to_number"] = to_number
        payload = {
            "properties": props,
            "associations": [{
                "to": {"id": str(contact_id)},
                "types": [{
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": CALL_TO_CONTACT_ASSOCIATION_TYPE_ID,
                }],
            }],
        }
        try:
            data = self._request("POST",
                                  "/crm/v3/objects/calls",
                                  json_body=payload)
            return data.get("id", ""), None
        except HubSpotAPIError as e:
            return None, str(e)

    # ── high-level: one-call "track this email" ────────────
    def track_email_to_address(self, email_address: str,
                                 subject: str,
                                 body: str,
                                 direction: str = "outgoing",
                                 status: str = "SENT",
                                 create_contact_if_missing: bool = True,
                                 first_name: str = "",
                                 last_name: str = "",
                                 company: str = "",
                                 phone: str = ""
                                 ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """One-call helper: find or create the contact by email, then log
        the engagement. Returns (contact_id, email_engagement_id, error).

        This is what the UI button 'Log Manual Email' calls.
        """
        if create_contact_if_missing:
            contact_id, status_msg = self.find_or_create_contact(
                email_address, first_name=first_name, last_name=last_name,
                company=company, phone=phone)
        else:
            existing = self.find_contact_by_email(email_address)
            contact_id = existing.get("id") if existing else None
            status_msg = "found" if contact_id else "not_found"

        if not contact_id:
            return None, None, (
                f"Could not find or create contact for {email_address}: "
                f"{status_msg}"
            )

        email_id, err = self.log_email(
            contact_id=contact_id,
            subject=subject,
            body=body,
            direction=direction,
            status=status,
        )
        if err:
            return contact_id, None, err
        return contact_id, email_id, None

    # ── bulk enrichment ────────────────────────────────────
    def bulk_enrich_emails(self, email_list: List[str],
                            progress_callback: Optional[Callable[[int, int, str], None]] = None
                            ) -> Dict[str, Any]:
        """For each email in the list, find the contact ID in HubSpot
        (creating it if missing). Returns a dict mapping email → contact_id
        plus a summary count.

        Used by the 'Enrich CSV with HubSpot IDs' button. Rate-limited
        to ~8 requests/second to stay under HubSpot's 100/10s burst limit.
        """
        result: Dict[str, str] = {}
        stats = {"found": 0, "created": 0, "errored": 0, "total": len(email_list)}
        for i, email in enumerate(email_list):
            email = (email or "").strip().lower()
            if not email or "@" not in email:
                stats["errored"] += 1
                if progress_callback:
                    progress_callback(i + 1, len(email_list), f"skip (invalid): {email}")
                continue
            contact_id, status = self.find_or_create_contact(email)
            if contact_id:
                result[email] = contact_id
                if status == "found":
                    stats["found"] += 1
                elif status == "created":
                    stats["created"] += 1
            else:
                stats["errored"] += 1
                self.log(f"[hubspot] enrich failed for {email}: {status}")
            if progress_callback:
                progress_callback(i + 1, len(email_list), status)
            # Rate limit: 8 req/sec
            time.sleep(0.125)
        return {"map": result, "stats": stats}

    # ── account-level helpers ──────────────────────────────
    def verify_connection(self) -> Tuple[Optional[dict], Optional[str]]:
        """Smoke test: fetch account info. Used by the 'Test HubSpot'
        button in Settings."""
        try:
            data = self._request("GET", "/account-info/v3/details")
            return {
                "connected": True,
                "portal_id": data.get("portalId"),
                "time_zone": data.get("timeZone", ""),
                "company_currency": data.get("companyCurrency", ""),
                "utc_offset_milliseconds": data.get("utcOffsetMilliseconds", 0),
            }, None
        except HubSpotAuthError as e:
            return None, str(e)
        except HubSpotAPIError as e:
            return None, str(e)

    def count_contacts(self) -> Tuple[Optional[int], Optional[str]]:
        """How many contacts are in the HubSpot portal? Used for the
        dashboard stat card."""
        try:
            data = self._request("POST",
                                  "/crm/v3/objects/contacts/search",
                                  json_body={"filterGroups": [], "limit": 1})
            return int(data.get("total", 0)), None
        except HubSpotAPIError as e:
            return None, str(e)


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================
def track_email_from_config(cfg: dict,
                              email_address: str,
                              subject: str,
                              body: str,
                              direction: str = "outgoing",
                              **kwargs) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Build a tracker from the app config and log one email.
    Returns (contact_id, email_engagement_id, error)."""
    token = cfg.get("hubspot_token", "").strip()
    if not token:
        return None, None, "hubspot_token not configured in Settings"
    tracker = HubSpotTracker(api_token=token)
    return tracker.track_email_to_address(
        email_address=email_address,
        subject=subject,
        body=body,
        direction=direction,
        **kwargs,
    )


def get_bcc_address(cfg: dict) -> str:
    """Return the configured HubSpot BCC forwarding address, or empty."""
    return (cfg.get("hubspot_bcc_address", "") or "").strip()
