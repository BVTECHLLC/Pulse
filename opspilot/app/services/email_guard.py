"""Email sanity gate for public forms (v1.122).

Stops the two things that waste BVTech's inbox: disposable/throwaway email
addresses (mailinator, temp-mail, …) and obviously malformed ones. Used by every
public intake (the free-tool lead relay, the memorial, any contact form) on top
of the proof-of-work human check in ``captcha.py``.

Deterministic, no network: a curated denylist of the domains abuse actually comes
from. Legitimate free webmail (gmail, outlook, yahoo, icloud, proton, …) is
explicitly allowed — we only block throwaway/relay services. A ``reason`` is
returned so callers can log why something was refused.
"""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@([a-z0-9.\-]+\.[a-z]{2,})$", re.I)

# Free webmail we DO accept (so the denylist's broad patterns never catch them).
ALLOW = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "yahoo.com", "ymail.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "pm.me", "gmx.com", "zoho.com",
    "fastmail.com", "hey.com", "comcast.net", "att.net", "sbcglobal.net",
    "verizon.net", "cox.net", "charter.net", "bellsouth.net", "txrr.com",
}

# Known disposable / throwaway / temp-mail domains (the ones abuse comes from).
DISPOSABLE = {
    "mailinator.com", "mailinator.net", "mailinator.org", "mailinater.com",
    "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "guerrillamail.biz",
    "guerrillamailblock.com", "sharklasers.com", "grr.la", "spam4.me",
    "10minutemail.com", "10minutemail.net", "10minutemail.org", "20minutemail.com",
    "temp-mail.org", "temp-mail.io", "tempmail.com", "tempmail.net", "tempmailo.com",
    "tempr.email", "tempmailaddress.com", "tmpmail.org", "tmpmail.net",
    "throwawaymail.com", "throwaway.email", "trashmail.com", "trashmail.net",
    "trash-mail.com", "mytrashmail.com", "getnada.com", "nada.email", "inboxkitten.com",
    "maildrop.cc", "mailnesia.com", "mailcatch.com", "mohmal.com", "fakeinbox.com",
    "fakemailgenerator.com", "dispostable.com", "yopmail.com", "yopmail.net",
    "yopmail.fr", "cool.fr.nf", "jetable.org", "spambog.com", "spambog.de",
    "maileater.com", "emailondeck.com", "33mail.com", "burnermail.io", "anonaddy.com",
    "anonaddy.me", "simplelogin.com", "simplelogin.io", "relay.firefox.com",
    "duck.com", "mozmail.com", "spamgourmet.com", "e4ward.com", "incognitomail.org",
    "mailexpire.com", "mintemail.com", "mailnull.com", "no-spam.ws", "nobulk.com",
    "objectmail.com", "proxymail.eu", "rcpt.at", "safe-mail.net", "selfdestructingmail.com",
    "sneakemail.com", "sogetthis.com", "spamavert.com", "spambox.us", "spamex.com",
    "spamfree24.org", "spamhole.com", "spaml.com", "tempinbox.com", "tempomail.fr",
    "thankyou2010.com", "trbvm.com", "veryrealemail.com", "wegwerfmail.de",
    "wegwerfmail.net", "wh4f.org", "willhackforfood.biz", "willselfdestruct.com",
    "mailforspam.com", "mailtemp.net", "luxusmail.org", "crazymailing.com",
    "dropmail.me", "emltmp.com", "harakirimail.com", "mail-temp.com", "moakt.com",
    "mailto.plus", "fexbox.org", "fexbox.ru", "rteet.com", "vjuum.com", "yoggm.com",
    "tafmail.com", "etempmail.net", "mailpoof.com", "generator.email", "tempmail.plus",
    "disposablemail.com", "33mail.net", "clrmail.com", "tempemail.co", "owlymail.com",
    "minuteinbox.com", "mailsac.com", "inboxbear.com", "byom.de", "einrot.com",
}

# Suffix patterns for the many numbered/short-lived variants (e.g. *.tempmail.*).
_DISPOSABLE_SUFFIX = (
    "mailinator.com", "guerrillamail.com", "temp-mail.io", "tempmail.plus",
    "yopmail.com", "trashmail.com", "sharklasers.com", "33mail.com", "mohmal.com",
)
# Giveaway substrings in the domain label (never present in real business domains).
_BAD_SUBSTR = ("tempmail", "temp-mail", "throwaway", "trashmail", "disposable",
               "10minute", "guerrilla", "fakemail", "fakeinbox", "getnada",
               "mailinator", "spam4", "burnermail", "yopmail", "mailsac")


def is_disposable(domain: str) -> bool:
    d = (domain or "").strip().lower().rstrip(".")
    if not d or d in ALLOW:
        return False
    if d in DISPOSABLE:
        return True
    if any(d == s or d.endswith("." + s) for s in _DISPOSABLE_SUFFIX):
        return True
    label = d.split(".")[0]
    return any(b in d or b in label for b in _BAD_SUBSTR)


def check(email: str) -> tuple[bool, str]:
    """Return (ok, reason). ok=False means refuse the submission. The reason is
    short and user-safe (callers may show it or a generic message)."""
    e = (email or "").strip().lower()
    m = _EMAIL_RE.match(e)
    if not m:
        return False, "invalid"
    domain = m.group(1)
    if "." not in domain or len(domain) > 253:
        return False, "invalid"
    if is_disposable(domain):
        return False, "disposable"
    # crude typo/garbage guard: no consecutive dots, no all-numeric TLD
    tld = domain.rsplit(".", 1)[-1]
    if ".." in e or tld.isdigit():
        return False, "invalid"
    return True, "ok"
