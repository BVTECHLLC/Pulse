"""v0.41 Content publishers — LinkedIn + website auto-publishing config.

LinkedIn posting is a direct HTTPS call Pulse can make itself (UGC share API),
so "post now" works from the portal. Website auto-publishing (bvtech.org /
jordanpolasek.com) is performed by the box-side daily cron; here we own the
*settings* — schedule, persona, enabled flag, and any repo token (encrypted) —
so the whole reputation-management surface lives in one place.

Credentials are read from the encrypted platform connection config; nothing is
hardcoded or logged.
"""
from __future__ import annotations

import json
from urllib import error, request

LINKEDIN_API = "https://api.linkedin.com/v2/ugcPosts"
_MAX_LEN = 2900  # LinkedIn hard limit 3000; leave headroom for the URL


class PublishError(Exception):
    pass


def _normalize_urn(urn: str) -> str:
    urn = urn.strip()
    return urn if urn.startswith("urn:li:") else f"urn:li:person:{urn}"


def post_linkedin(token: str, person_urn: str, text: str, url: str = "") -> str:
    """Publish a text/article share as the given person URN. Returns the post id."""
    if not (token and person_urn):
        raise PublishError("LinkedIn is not configured (need access token + person URN).")
    body = text if not url else f"{text}\n\n{url}"
    body = body[:_MAX_LEN]
    share: dict = {
        "shareCommentary": {"text": body},
        "shareMediaCategory": "ARTICLE" if url else "NONE",
    }
    if url:
        share["media"] = [{"status": "READY", "originalUrl": url}]
    payload = {
        "author": _normalize_urn(person_urn),
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": share},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    req = request.Request(LINKEDIN_API, data=json.dumps(payload).encode(), method="POST",
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json",
                                   "X-Restli-Protocol-Version": "2.0.0"})
    try:
        with request.urlopen(req, timeout=30) as r:
            return r.headers.get("x-restli-id") or "(posted)"
    except error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403):
            raise PublishError(f"LinkedIn auth failed (HTTP {e.code}) — the token is "
                               f"likely expired. Re-authorize and update it in Settings.")
        raise PublishError(f"LinkedIn HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        raise PublishError(f"LinkedIn request failed: {e}")
