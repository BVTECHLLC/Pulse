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

# --- v1.88.2 mailbox verification -----------------------------------------
# MX-only proves the DOMAIN can receive mail, not that the specific mailbox
# exists — so a stale info@ on a live domain still bounces ("address not
# found"). An SMTP RCPT probe asks the mail server directly. It fails OPEN
# (unknown -> allow) and SELF-DISABLES after a few connect failures, so a box
# whose outbound port 25 is blocked pays at most a couple of timeouts, then
# stops probing entirely and behaves exactly like the MX-only guard.
_MB_CACHE: dict[str, bool | None] = {}
_PROBE_CONNECT_FAILS = 0
_PROBE_MAX_FAILS = 3
_PROBE_DISABLED = False


def _mx_host(domain: str) -> str | None:
    try:
        answers = _doh_mx(domain)
    except Exception:  # noqa: BLE001
        return None
    hosts = sorted((int(a.get("data", "999 x").split()[0]),
                    a.get("data", "").split()[-1].strip("."))
                   for a in answers if a.get("data"))
    return hosts[0][1] if hosts else None


def _smtp_probe(email: str, domain: str) -> bool | None:
    """True = mailbox accepts, False = server rejects (user unknown), None =
    undeterminable (port blocked, timeout, greylist, catch-all). Never raises."""
    global _PROBE_CONNECT_FAILS, _PROBE_DISABLED
    host = _mx_host(domain)
    if not host:
        return None
    import smtplib
    try:
        srv = smtplib.SMTP(timeout=8)
        srv.connect(host, 25)
    except Exception:  # noqa: BLE001 — port 25 blocked/unreachable
        _PROBE_CONNECT_FAILS += 1
        if _PROBE_CONNECT_FAILS >= _PROBE_MAX_FAILS:
            _PROBE_DISABLED = True
        return None
    try:
        srv.helo("bvtech.org")
        srv.mail("postmaster@bvtech.org")
        code, _ = srv.rcpt(email)
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            srv.quit()
        except Exception:  # noqa: BLE001
            pass
    if code in (250, 251, 252):
        return True
    if code in (550, 551, 553, 554):   # user unknown / mailbox unavailable
        return False
    return None


_PROBE_FN = _smtp_probe     # test seam


def mailbox_exists(email: str, domain: str) -> bool | None:
    """Cached mailbox probe. None when undeterminable (treated as sendable)."""
    if _PROBE_DISABLED:
        return None
    key = email.strip().lower()
    if key in _MB_CACHE:
        return _MB_CACHE[key]
    result = _PROBE_FN(key, domain)
    _MB_CACHE[key] = result
    return result


def is_sendable(email: str) -> tuple[bool, str]:
    """(ok, reason). Pre-send verification: valid syntax + a real MX on the
    domain + (best-effort) the mailbox actually accepting mail. reason is
    'ok' | 'bad_syntax' | 'junk_domain' | 'no_mx' | 'no_mailbox'."""
    e = (email or "").strip().lower()
    m = _EMAIL_RX.match(e)
    if not m:
        return False, "bad_syntax"
    dom = m.group(1)
    if dom in _JUNK_DOMAINS:
        return False, "junk_domain"
    if not _MX_FN(dom):
        return False, "no_mx"
    if mailbox_exists(e, dom) is False:   # only a hard rejection blocks
        return False, "no_mailbox"
    return True, "ok"
