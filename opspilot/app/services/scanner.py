"""Passive external security scanner.

Runs READ-ONLY posture checks against a public domain — TLS/HTTPS, security
response headers, HTTP→HTTPS redirect, and DNS email-authentication (SPF/DMARC)
+ CAA hygiene. It never exploits, brute-forces, logs in, or sends payloads; it
only observes what the domain already exposes publicly. Results are returned as
plain dicts that the security routes persist as SecurityFindings under an
assessment, so the existing scorecard/alerts/remediation flow lights up
automatically.

Safe to run against any domain you are authorized to assess.
"""
from __future__ import annotations

import ssl

import dns.resolver
import httpx

from ..models import FindingSeverity

SEV = FindingSeverity
_UA = {"User-Agent": "BVTech-Pulse-Scanner/1.0 (+https://bvtech.org)"}


def _f(title: str, severity: FindingSeverity, category: str, description: str, recommendation: str) -> dict:
    return {"title": title, "severity": severity, "category": category,
            "description": description, "recommendation": recommendation}


def _clean_domain(raw: str) -> str:
    d = (raw or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p):]
    return d.split("/")[0].split(":")[0].strip()


def _doh(name: str, rtype: str) -> list[str] | None:
    """DNS-over-HTTPS fallback (Cloudflare) for environments where UDP/53 is
    blocked. Returns a list of record data strings, or None if DoH itself failed."""
    try:
        with httpx.Client(timeout=6.0) as c:
            r = c.get("https://cloudflare-dns.com/dns-query",
                      params={"name": name, "type": rtype},
                      headers={"accept": "application/dns-json"})
            if r.status_code != 200:
                return None
            return [a.get("data", "").strip('"') for a in (r.json().get("Answer") or [])]
    except Exception:
        return None


def _txt(name: str) -> list[str]:
    try:
        recs = [b"".join(r.strings).decode("utf-8", "ignore")
                for r in dns.resolver.resolve(name, "TXT", lifetime=5.0)]
        if recs:
            return recs
    except Exception:
        pass
    doh = _doh(name, "TXT")
    return doh if doh is not None else []


def _has_record(name: str, rtype: str) -> bool | None:
    """True/False if a record type exists; None if lookup was inconclusive."""
    try:
        dns.resolver.resolve(name, rtype, lifetime=5.0)
        return True
    except dns.resolver.NoAnswer:
        return False
    except dns.resolver.NXDOMAIN:
        return False
    except Exception:
        doh = _doh(name, rtype)
        return bool(doh) if doh is not None else None


def scan_domain(domain: str) -> dict:
    """Return {domain, https_ok, findings:[...]}. Never raises for scan errors."""
    domain = _clean_domain(domain)
    findings: list[dict] = []
    if not domain or "." not in domain:
        return {"domain": domain, "https_ok": False,
                "findings": [_f("Invalid domain", SEV.LOW, "input",
                                f"'{domain}' is not a valid domain name.", "Enter a bare domain like example.com.")]}

    url = f"https://{domain}"
    headers: dict[str, str] = {}
    https_ok = False
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, verify=True) as c:
            resp = c.get(url, headers=_UA)
            https_ok = True
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except ssl.SSLError as e:
        findings.append(_f(f"TLS certificate failed validation", SEV.HIGH, "tls",
                           f"The HTTPS certificate for {domain} did not validate: {e}",
                           "Install a valid, in-date certificate that covers this exact hostname (free via Let's Encrypt)."))
    except httpx.HTTPError as e:
        findings.append(_f("HTTPS not reachable", SEV.HIGH, "tls",
                           f"Could not establish an HTTPS connection to {domain}: {e}",
                           "Serve the site over HTTPS on port 443 with a valid certificate."))
    except Exception as e:  # noqa: BLE001 — scanner must never crash the request
        findings.append(_f("HTTPS check failed", SEV.MEDIUM, "tls",
                           f"Unexpected error checking {domain}: {e}", "Verify the domain resolves and serves HTTPS."))

    if https_ok:
        header_checks = [
            ("strict-transport-security", "HSTS header missing", SEV.MEDIUM,
             "Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains' so browsers refuse to connect over plain HTTP."),
            ("content-security-policy", "Content-Security-Policy missing", SEV.MEDIUM,
             "Add a Content-Security-Policy to limit where scripts/resources can load from — a core XSS mitigation."),
            ("x-content-type-options", "X-Content-Type-Options missing", SEV.LOW,
             "Add 'X-Content-Type-Options: nosniff' to stop MIME-type sniffing."),
            ("referrer-policy", "Referrer-Policy missing", SEV.LOW,
             "Add 'Referrer-Policy: strict-origin-when-cross-origin' to avoid leaking full URLs to third parties."),
        ]
        for h, title, sev, rec in header_checks:
            if h not in headers:
                findings.append(_f(title, sev, "headers", f"The response from {url} does not set the '{h}' header.", rec))
        # Clickjacking: satisfied by either X-Frame-Options or CSP frame-ancestors
        csp = headers.get("content-security-policy", "")
        if "x-frame-options" not in headers and "frame-ancestors" not in csp:
            findings.append(_f("Clickjacking protection missing", SEV.LOW, "headers",
                               f"{url} sets neither X-Frame-Options nor a CSP frame-ancestors directive, so it can be framed by other sites.",
                               "Add 'X-Frame-Options: DENY' or a CSP 'frame-ancestors' directive."))
        # Server/version banner leakage
        srv = headers.get("server", "")
        if srv and any(ch.isdigit() for ch in srv):
            findings.append(_f(f"Server version disclosed in headers", SEV.LOW, "disclosure",
                               f"The 'Server' header reveals software and version: '{srv}'.",
                               "Suppress or genericize the Server header so attackers can't target known version CVEs."))
        powered = headers.get("x-powered-by", "")
        if powered:
            findings.append(_f("X-Powered-By header discloses tech stack", SEV.LOW, "disclosure",
                               f"The 'X-Powered-By' header reveals: '{powered}'.",
                               "Remove the X-Powered-By header."))

    # HTTP -> HTTPS redirect
    try:
        with httpx.Client(timeout=8.0, follow_redirects=False) as c:
            r = c.get(f"http://{domain}", headers=_UA)
            loc = r.headers.get("location", "")
            if not (r.status_code in (301, 302, 307, 308) and loc.lower().startswith("https")):
                findings.append(_f("HTTP does not redirect to HTTPS", SEV.MEDIUM, "tls",
                                   f"Plain http://{domain} did not issue a redirect to HTTPS, so a visitor's first request can travel unencrypted.",
                                   "Configure a permanent (301) redirect from http:// to https:// for all paths."))
    except Exception:
        pass

    # Email auth — SPF
    spf = [t for t in _txt(domain) if t.lower().startswith("v=spf1")]
    if not spf:
        findings.append(_f("No SPF record — domain can be spoofed", SEV.MEDIUM, "email",
                           f"{domain} publishes no SPF (v=spf1) TXT record, so anyone can forge email 'from' this domain.",
                           "Publish an SPF TXT record listing authorized senders and ending in '-all' (hard fail) or '~all'."))
    elif any("+all" in s for s in spf):
        findings.append(_f("SPF record is dangerously permissive (+all)", SEV.HIGH, "email",
                           f"{domain}'s SPF uses '+all', which authorizes the entire internet to send as this domain.",
                           "Replace '+all' with '-all' and list only legitimate sending sources."))

    # Email auth — DMARC
    dmarc = [t for t in _txt(f"_dmarc.{domain}") if t.lower().startswith("v=dmarc1")]
    if not dmarc:
        findings.append(_f("No DMARC record — spoofed mail isn't blocked", SEV.MEDIUM, "email",
                           f"{domain} has no _dmarc TXT record, so receiving servers have no policy for mail that fails SPF/DKIM.",
                           "Publish a DMARC record. Start at 'p=none' to gather reports, then tighten to 'p=quarantine' and 'p=reject'."))
    elif "p=none" in dmarc[0].lower():
        findings.append(_f("DMARC policy is monitor-only (p=none)", SEV.LOW, "email",
                           f"{domain} publishes DMARC but with 'p=none', which reports on but does not block spoofed mail.",
                           "After reviewing DMARC reports, move the policy to 'p=quarantine' and then 'p=reject'."))

    # CAA hygiene (only flag when we can positively confirm there's none)
    if _has_record(domain, "CAA") is False:
        findings.append(_f("No CAA record", SEV.LOW, "dns",
                           f"{domain} has no DNS CAA record restricting which Certificate Authorities may issue certificates for it.",
                           "Add a CAA record naming your CA so no other CA can mint a certificate for this domain."))

    return {"domain": domain, "https_ok": https_ok, "findings": findings}
