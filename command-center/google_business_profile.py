#!/usr/bin/env python3
"""
BVTech — Google Business Profile API client  v30.0
==============================================================

Handles the full OAuth2 flow and localPost creation for Google
Business Profile (formerly Google My Business). Used by the Super
Posting system to push a short summary + call-to-action button to
your GBP listings whenever a new blog post goes live.

THE LANDSCAPE IN 2026
---------------------
Google renamed this API a few times. Current reality:

- OAuth scope:  https://www.googleapis.com/auth/business.manage
- Accounts list: GET  https://mybusinessaccountmanagement.googleapis.com/v1/accounts
- Locations:     GET  https://mybusinessbusinessinformation.googleapis.com/v1/{parent=accounts/*}/locations
- LocalPosts:    POST https://mybusiness.googleapis.com/v4/{parent=accounts/*/locations/*}/localPosts
                 (still on legacy v4 — Google has not migrated localPosts yet)

ACCESS RESTRICTION
------------------
Unlike most Google APIs, Business Profile APIs require a one-time
access request through Google's form before your OAuth client can
call them successfully. Requests without approved access get 403
errors. See:
  https://developers.google.com/my-business/content/prereqs

This module handles that failure mode gracefully — calls that get
403 return a clear "API access not granted" error with a link to
the request form, so the user knows exactly what to do.

CONFIG KEYS READ FROM bvtech_config.json
-----------------------------------------
  google_client_id           OAuth2 client ID
  google_client_secret       OAuth2 client secret
  google_redirect_uri        Usually http://localhost:5678/api/gbp/oauth/callback
  gbp_refresh_token          Set after the user completes the OAuth flow
  gbp_account_name           e.g. "accounts/123456789"
  gbp_location_name          e.g. "locations/987654321"
"""

import json
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    raise ImportError(
        "google_business_profile requires the 'requests' package. "
        "Install it with: pip install requests"
    )


OAUTH_SCOPE = "https://www.googleapis.com/auth/business.manage"
OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

ACCOUNTS_API = "https://mybusinessaccountmanagement.googleapis.com/v1"
BUSINESS_INFO_API = "https://mybusinessbusinessinformation.googleapis.com/v1"
LEGACY_V4_API = "https://mybusiness.googleapis.com/v4"

ACCESS_REQUEST_FORM = "https://support.google.com/business/contact/api_default"


# ============================================================
# OAUTH HELPERS
# ============================================================
def build_authorize_url(client_id: str, redirect_uri: str,
                        state: str = "bvtech") -> str:
    """Build the Google OAuth2 consent URL. User is redirected here
    to grant permission; on success Google sends them back to
    redirect_uri with ?code=... which we then exchange for tokens.
    """
    if not client_id:
        raise ValueError("client_id is required to build authorize URL")
    if not redirect_uri:
        raise ValueError("redirect_uri is required to build authorize URL")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "access_type": "offline",       # required to get a refresh_token
        "prompt": "consent",            # force re-consent so we actually get a new refresh_token
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code: str, client_id: str, client_secret: str,
                              redirect_uri: str) -> Tuple[Optional[dict], Optional[str]]:
    """Exchange the OAuth callback code for access_token + refresh_token.
    Returns (token_dict, error)."""
    if not code:
        return None, "No authorization code provided"
    try:
        r = requests.post(OAUTH_TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=30)
        if r.status_code != 200:
            return None, f"Token exchange failed: HTTP {r.status_code} {r.text[:300]}"
        data = r.json()
        if "refresh_token" not in data:
            return None, (
                "No refresh_token returned. This usually means the user has "
                "previously authorized this client — revoke access at "
                "https://myaccount.google.com/permissions and try again with "
                "prompt=consent."
            )
        return data, None
    except requests.RequestException as e:
        return None, f"Network error during token exchange: {e}"


def refresh_access_token(refresh_token: str, client_id: str,
                          client_secret: str) -> Tuple[Optional[str], Optional[str]]:
    """Use the refresh_token to get a fresh access_token.
    Returns (access_token, error)."""
    if not refresh_token:
        return None, "No refresh_token — user needs to complete OAuth flow first"
    try:
        r = requests.post(OAUTH_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        }, timeout=30)
        if r.status_code != 200:
            return None, f"Refresh failed: HTTP {r.status_code} {r.text[:300]}"
        data = r.json()
        token = data.get("access_token", "")
        if not token:
            return None, f"Refresh response missing access_token: {data}"
        return token, None
    except requests.RequestException as e:
        return None, f"Network error during refresh: {e}"


# ============================================================
# MAIN CLIENT
# ============================================================
class GoogleBusinessProfileClient:
    """Thin client for the Google Business Profile APIs.

    Stateless-ish: holds the refresh_token and lazily fetches an
    access_token on each call. Does NOT persist anything — the
    caller (bvtech_app.py) reads/writes the config file.
    """

    def __init__(self, client_id: str, client_secret: str,
                 refresh_token: str, logger: Optional[Callable[[str], None]] = None):
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.refresh_token = (refresh_token or "").strip()
        self.log = logger or (lambda msg: None)
        self._access_token: Optional[str] = None
        self._access_token_expires_at: float = 0.0

    # ── auth ──────────────────────────────────────────────
    def _get_access_token(self) -> Tuple[Optional[str], Optional[str]]:
        """Return a valid access_token, refreshing if necessary."""
        now = time.time()
        if self._access_token and now < self._access_token_expires_at - 60:
            return self._access_token, None
        token, err = refresh_access_token(
            self.refresh_token, self.client_id, self.client_secret)
        if err:
            return None, err
        self._access_token = token
        # Google tokens are typically valid for 3600s; be conservative
        self._access_token_expires_at = now + 3500
        return token, None

    def _headers(self) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        token, err = self._get_access_token()
        if err:
            return None, err
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "BVTech-MSP-CommandCenter/30.0 (+google_business_profile.py)",
        }, None

    @staticmethod
    def _classify_error(status: int, body: str) -> str:
        """Turn Google error responses into human-actionable messages."""
        if status == 401:
            return (
                "401 Unauthorized — refresh_token is invalid or revoked. "
                "Disconnect and re-connect Google Business in Settings."
            )
        if status == 403:
            # Most common cause: API access not granted to this OAuth client.
            body_lower = body.lower() if body else ""
            if "api has not been used" in body_lower or "disabled" in body_lower:
                return (
                    "403 — one of the Business Profile APIs is not enabled in "
                    "your Google Cloud project. Enable 'My Business Account "
                    "Management API', 'My Business Business Information API', "
                    "and 'Google My Business API' in the GCP Console."
                )
            return (
                f"403 Forbidden — this usually means your Google Cloud project "
                f"has not been granted Business Profile API access yet. Fill out "
                f"the access request form at {ACCESS_REQUEST_FORM} and wait for "
                f"approval (typically 1-2 business days). Body: {body[:200]}"
            )
        if status == 404:
            return f"404 Not Found — account or location ID may be wrong. Body: {body[:200]}"
        if status == 429:
            return "429 Rate Limited — try again in a minute."
        return f"HTTP {status}: {body[:300]}"

    # ── accounts & locations ──────────────────────────────
    def list_accounts(self) -> Tuple[Optional[List[dict]], Optional[str]]:
        """GET /v1/accounts — returns the GBP accounts the user can manage."""
        headers, err = self._headers()
        if err:
            return None, err
        try:
            r = requests.get(f"{ACCOUNTS_API}/accounts", headers=headers, timeout=30)
            if r.status_code != 200:
                return None, self._classify_error(r.status_code, r.text)
            data = r.json()
            return data.get("accounts", []), None
        except requests.RequestException as e:
            return None, f"Network error listing accounts: {e}"

    def list_locations(self, account_name: str) -> Tuple[Optional[List[dict]], Optional[str]]:
        """GET /v1/{account_name}/locations — returns locations under an account.

        account_name should be the full resource name like 'accounts/123456789'.
        The readMask parameter is required in the newer API.
        """
        if not account_name:
            return None, "account_name is required (e.g. 'accounts/123456789')"
        headers, err = self._headers()
        if err:
            return None, err
        params = {
            "readMask": "name,title,storefrontAddress,websiteUri,phoneNumbers",
            "pageSize": 100,
        }
        try:
            r = requests.get(
                f"{BUSINESS_INFO_API}/{account_name}/locations",
                headers=headers, params=params, timeout=30)
            if r.status_code != 200:
                return None, self._classify_error(r.status_code, r.text)
            data = r.json()
            return data.get("locations", []), None
        except requests.RequestException as e:
            return None, f"Network error listing locations: {e}"

    # ── local posts ───────────────────────────────────────
    def create_local_post(self, account_name: str, location_name: str,
                           summary: str, cta_url: str,
                           cta_action_type: str = "LEARN_MORE",
                           language_code: str = "en-US",
                           ) -> Tuple[Optional[dict], Optional[str]]:
        """Create a LocalPost (a 'Google Post' on the business profile).

        Args:
            account_name:  'accounts/123456789'
            location_name: 'locations/987654321' (just the locations/... part,
                           NOT the full accounts/X/locations/Y path)
            summary:       post text (max 1500 chars but 300 is the sweet spot)
            cta_url:       URL the call-to-action button links to
            cta_action_type: one of BOOK, ORDER, SHOP, LEARN_MORE, SIGN_UP, CALL
            language_code: BCP-47 language tag

        Returns (post_dict, error).
        """
        if not account_name or not location_name:
            return None, "account_name and location_name are both required"
        if not summary:
            return None, "summary is required (the post body)"
        if len(summary) > 1500:
            return None, f"summary is {len(summary)} chars, max is 1500"

        # Normalize location_name: it might be passed as just 'locations/X' or
        # as a full path. For the localPosts endpoint we need
        # 'accounts/A/locations/L'.
        if location_name.startswith("locations/"):
            parent_path = f"{account_name}/{location_name}"
        elif location_name.startswith("accounts/"):
            parent_path = location_name
        else:
            return None, f"location_name must start with 'locations/' or 'accounts/' — got {location_name!r}"

        headers, err = self._headers()
        if err:
            return None, err

        body = {
            "languageCode": language_code,
            "summary": summary,
            "callToAction": {
                "actionType": cta_action_type,
                "url": cta_url,
            },
            "topicType": "STANDARD",
        }

        url = f"{LEGACY_V4_API}/{parent_path}/localPosts"
        try:
            r = requests.post(url, headers=headers, json=body, timeout=60)
            if r.status_code not in (200, 201):
                return None, self._classify_error(r.status_code, r.text)
            return r.json(), None
        except requests.RequestException as e:
            return None, f"Network error creating local post: {e}"

    # ── verification helper ───────────────────────────────
    def verify_connection(self) -> Tuple[Optional[dict], Optional[str]]:
        """Call list_accounts as a smoke test. Used by the 'Test Connection'
        button in Settings."""
        accounts, err = self.list_accounts()
        if err:
            return None, err
        return {
            "connected": True,
            "account_count": len(accounts),
            "accounts": [
                {
                    "name": a.get("name", ""),
                    "account_name": a.get("accountName", ""),
                    "type": a.get("type", ""),
                    "role": a.get("role", ""),
                    "state": a.get("verificationState", ""),
                }
                for a in accounts[:10]
            ],
        }, None


# ============================================================
# HIGH-LEVEL HELPER — one-call "post to GBP" for Super Posting
# ============================================================
def post_to_gbp(cfg: dict, summary: str, cta_url: str,
                 logger: Optional[Callable[[str], None]] = None
                 ) -> Tuple[Optional[dict], Optional[str]]:
    """Read config, create a client, post one localPost. Returns
    (result, error). Used by _generate_one_post() in bvtech_app.py.
    """
    log = logger or (lambda m: None)

    client_id = cfg.get("google_client_id", "").strip()
    client_secret = cfg.get("google_client_secret", "").strip()
    refresh_token = cfg.get("gbp_refresh_token", "").strip()
    account_name = cfg.get("gbp_account_name", "").strip()
    location_name = cfg.get("gbp_location_name", "").strip()

    missing = []
    if not client_id: missing.append("google_client_id")
    if not client_secret: missing.append("google_client_secret")
    if not refresh_token: missing.append("gbp_refresh_token (not connected)")
    if not account_name: missing.append("gbp_account_name")
    if not location_name: missing.append("gbp_location_name")
    if missing:
        return None, (
            "GBP not configured. Missing: " + ", ".join(missing) +
            ". Open Settings → Google Business Profile to complete setup."
        )

    client = GoogleBusinessProfileClient(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        logger=log,
    )

    log(f"GBP: creating local post ({len(summary)} chars, CTA → {cta_url})")
    result, err = client.create_local_post(
        account_name=account_name,
        location_name=location_name,
        summary=summary,
        cta_url=cta_url,
    )
    if err:
        return None, err
    log(f"GBP: post created, name={result.get('name', '?')}")
    return result, None
