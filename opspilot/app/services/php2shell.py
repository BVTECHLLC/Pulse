"""PHP2Shell exposure assessment (v1.94) — CVE-2026-109618 / CVE-2026-109619.

Two memory-safety bugs in PHP's request startup, disclosed 21 Oct 2026: an
out-of-memory fatal error during multipart / session-upload-progress handling
leaves global state (unserializer bookkeeping, PS(id), the fatal-error
backtrace, OPcache map_ptr) pointing at freed memory, and the NEXT request on
the same worker reuses it — pre-auth RCE or heap disclosure. Every PHP from
5.4 up is affected; mod_php is worst because it fires before app code runs.
Fixed in 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12. 8.1 and older are end-of-life and
get no official binaries.

This module is PASSIVE: it reads what a site already sends to every browser
(headers, cookies, the homepage HTML) and never sends an exploit payload. It
can say "PHP version X is unpatched" or "PHP is present but its version is
hidden" — it can't prove a site safe, only that it isn't advertising a
vulnerable build.
"""
from __future__ import annotations

import re

FIXED = {(8, 2): 35, (8, 3): 36, (8, 4): 27, (8, 5): 12}
FIXED_LABEL = "8.2.35 / 8.3.36 / 8.4.27 / 8.5.12"

_VER_RE = re.compile(r"PHP/(\d+)\.(\d+)\.(\d+)", re.I)
_CMS_SIGNS = (
    ("WordPress", re.compile(r'generator"\s+content="WordPress|/wp-content/|/wp-includes/', re.I)),
    ("Drupal", re.compile(r'generator"\s+content="Drupal|Drupal\.settings|/sites/default/files/', re.I)),
    ("Joomla", re.compile(r'generator"\s+content="Joomla|/media/jui/|/media/system/js/', re.I)),
    ("Magento", re.compile(r"Mage\.Cookies|/static/frontend/Magento", re.I)),
    ("PrestaShop", re.compile(r"prestashop", re.I)),
    ("Laravel", re.compile(r"laravel_session|XSRF-TOKEN.*laravel", re.I)),
)


def assess_version(major: int, minor: int, patch: int) -> dict:
    """Verdict for a known PHP version."""
    ver = f"{major}.{minor}.{patch}"
    if (major, minor) < (5, 4):
        return {"version": ver, "status": "eol_unaffected",
                "detail": "Older than 5.4 — predates these bugs, but is itself years "
                          "past end-of-life and riddled with other known flaws."}
    need = FIXED.get((major, minor))
    if need is None:
        if (major, minor) < (8, 2):
            return {"version": ver, "status": "vulnerable_eol",
                    "detail": f"PHP {major}.{minor} is end-of-life: affected, and no "
                              "official patched release exists. Upgrade to a supported "
                              f"branch ({FIXED_LABEL})."}
        return {"version": ver, "status": "unknown_branch",
                "detail": "Newer branch than this checker knows — confirm with the "
                          "PHP security advisory."}
    if patch >= need:
        return {"version": ver, "status": "patched",
                "detail": f"PHP {ver} includes the PHP2Shell fix ({major}.{minor}.{need}+)."}
    return {"version": ver, "status": "vulnerable",
            "detail": f"PHP {ver} is VULNERABLE — upgrade to {major}.{minor}.{need} or later."}


def fingerprint(headers: dict, body: str) -> dict:
    """Find PHP signals in a response. `headers` keys are lower-case; values
    may be lists (Set-Cookie)."""
    def _all(name):
        v = headers.get(name)
        return v if isinstance(v, list) else ([v] if v else [])

    signals: list[str] = []
    version = None
    for name in ("x-powered-by", "server"):
        for v in _all(name):
            m = _VER_RE.search(v)
            if m:
                version = tuple(int(x) for x in m.groups())
                signals.append(f"{name}: {v[:80]}")
            elif "php" in v.lower():
                signals.append(f"{name}: {v[:80]}")
    for c in _all("set-cookie"):
        if c.upper().startswith("PHPSESSID"):
            signals.append("cookie: PHPSESSID")
    cms = [name for name, rx in _CMS_SIGNS if rx.search(body or "")]
    signals += [f"platform: {c}" for c in cms]
    behind_cf = bool(headers.get("cf-ray")) or "cloudflare" in str(headers.get("server", "")).lower()
    return {"php_detected": bool(signals), "version": version, "cms": cms,
            "signals": signals, "behind_cloudflare": behind_cf}


def report(host: str, headers: dict, body: str) -> dict:
    """Full verdict for one site from its homepage response."""
    fp = fingerprint(headers, body)
    out = {"host": host, "cves": ["CVE-2026-109618", "CVE-2026-109619"],
           "fixed_versions": FIXED_LABEL, **fp}
    if fp["version"]:
        a = assess_version(*fp["version"])
        out.update(verdict=a["status"], version=a["version"], detail=a["detail"])
    elif fp["php_detected"]:
        out.update(verdict="php_version_hidden",
                   detail="This site runs PHP (" + ", ".join(fp["signals"][:3]) + ") "
                          "but hides its version. It is exposed unless the PHP runtime "
                          f"was upgraded to {FIXED_LABEL} on or after 21 Oct 2026 — "
                          "ask your host to confirm the exact PHP version.")
    else:
        out.update(verdict="no_php_detected",
                   detail="No PHP signals on the homepage (static site or another "
                          "stack). Not proof — check any admin, store or API "
                          "subdomains too.")
    steps = []
    if out["verdict"] in ("vulnerable", "vulnerable_eol", "php_version_hidden"):
        steps = ["Upgrade the PHP runtime itself (plugin/theme updates do NOT fix this).",
                 "Until patched: put the site behind a WAF with PHP2Shell rules "
                 "(Cloudflare's free managed ruleset includes them).",
                 "Until patched: set session.upload_progress.enabled = 0 in php.ini "
                 "or the FPM pool (not via ini_set) and restart workers.",
                 "After patching: look for new admin users, unknown files in uploads "
                 "folders and unexpected cron jobs — exploitation began 17 Oct."]
        if fp["behind_cloudflare"]:
            steps.insert(1, "Cloudflare detected — keep its WAF on, but it is a "
                            "seatbelt, not the fix.")
    out["next_steps"] = steps
    return out
