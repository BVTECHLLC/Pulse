"""v1.87 Deliverability guard — protect the sending domain's reputation.

Cold outreach to guessed/generic addresses (info@, contact@) bounces, and every
bounce hurts the mailbox's standing with Microsoft/Google. Two cheap defenses:

  * is_sendable(email)  — pre-send check: syntax + a REAL MX record on the domain.
    Catches dead domains before we ever email them. It does NOT prove the mailbox
    exists (that needs an SMTP probe, which is unreliable and itself reputation-
    risky), so the bounce watcher is the second line: anything that slips through
    and bounces is retired permanently on the first NDR.

MX lookups go over DNS-over-HTTPS (Cloudflare resolver, fixed host — no SSRF),
cached per-domain for the process so a batch of 20 sends does at most a handful
of lookups. Fails OPEN on a network hiccup (don't block real leads on a blip).
"""
from __future__ import annotations

import json
import re
import urllib.request

_EMAIL_RX = re.compile(r"^[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})$")
# Obvious non-deliverable placeholders sometimes scraped/imported.
_JUNK_DOMAINS = {"example.com", "example.org", "test.com", "email.com",
                 "domain.com", "yourdomain.com", "sentry.io", "wixpress.com"}
_MX_CACHE: dict[str, bool] = {}


def _doh_mx(domain: str) -> list[dict]:
    req = urllib.request.Request(
        f"https://cloudflare-dns.com/dns-query?name={domain}&type=MX",
        headers={"accept": "application/dns-json"})
    with urllib.request.urlopen(req, timeout=6) as r:
        data = json.loads(r.read().decode())
    return [a for a in (data.get("Answer") or []) if a.get("type") == 15]


def domain_has_mx(domain: str) -> bool:
    """True if the domain publishes an MX record (can receive mail). Cached;
    fails OPEN (returns True) on any lookup error so a DNS blip never blocks a
    real lead — a genuinely dead domain will still bounce and get retired."""
    dom = (domain or "").strip().lower().strip(".")
    if not dom or "." not in dom:
        return False
    if dom in _MX_CACHE:
        return _MX_CACHE[dom]
    try:
        ok = bool(_doh_mx(dom))
    except Exception:  # noqa: BLE001 — network hiccup -> don't block
        ok = True
    _MX_CACHE[dom] = ok
    return ok


_MX_FN = domain_has_mx     # test seam


def is_sendable(email: str) -> tuple[bool, str]:
    """(ok, reason). Cheap pre-send verification: valid syntax + a real MX on the
    domain. reason is 'ok' | 'bad_syntax' | 'junk_domain' | 'no_mx'."""
    e = (email or "").strip().lower()
    m = _EMAIL_RX.match(e)
    if not m:
        return False, "bad_syntax"
    dom = m.group(1)
    if dom in _JUNK_DOMAINS:
        return False, "junk_domain"
    if not _MX_FN(dom):
        return False, "no_mx"
    return True, "ok"
