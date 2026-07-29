"""PUBLIC free-tools API — the server-side half of bvtech.org/tools/.

Unauthenticated by design (the tools are a public good), so every endpoint is
hardened instead: strict per-IP rate limiting, an SSRF guard that refuses
private/reserved targets, tight timeouts, and CORS pinned to bvtech.org.
Nothing here touches the database or the authenticated app surface.
"""
import ipaddress
import re
import socket
import ssl
import time
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/api/public-tools", tags=["public-tools"])

_ALLOWED_ORIGINS = {"https://bvtech.org", "https://www.bvtech.org"}
_RATE: dict = {}          # ip -> [window_start, count]
_RATE_MAX = 20            # requests / minute / ip


def _cors(request: Request, resp: Response) -> None:
    origin = request.headers.get("origin", "")
    if origin in _ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"


def _limited(request: Request) -> bool:
    ip = (request.headers.get("cf-connecting-ip")
          or (request.client.host if request.client else "?"))
    now = time.time()
    win = _RATE.get(ip)
    if not win or now - win[0] > 60:
        _RATE[ip] = [now, 1]
        if len(_RATE) > 10000:      # bounded memory
            _RATE.clear()
        return False
    win[1] += 1
    return win[1] > _RATE_MAX


def _safe_host(host: str) -> str | None:
    """Validate a user-supplied hostname and refuse anything that resolves to
    private/reserved space (SSRF guard). Returns the cleaned hostname."""
    host = (host or "").strip().lower()
    host = re.sub(r"^[a-z]+://", "", host).split("/")[0].split(":")[0]
    if not re.fullmatch(r"[a-z0-9.-]{3,253}", host) or ".." in host:
        return None
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return None
    return host


def _guard(request: Request, resp: Response, host: str | None = None):
    """Shared preamble -> error dict or None. Also sets CORS headers."""
    _cors(request, resp)
    if _limited(request):
        return {"error": "rate limit: 20 requests/minute — try again shortly"}
    if host is not None and not _safe_host(host):
        return {"error": "that doesn't look like a public hostname"}
    return None


@router.options("/{rest:path}", include_in_schema=False)
def _preflight(rest: str, request: Request, resp: Response):
    _cors(request, resp)
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "content-type"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return {}


@router.get("/whoami")
def whoami(request: Request, resp: Response):
    """What's-my-IP: echo the caller's public address and user agent."""
    err = _guard(request, resp)
    if err:
        return err
    return {"ip": (request.headers.get("cf-connecting-ip")
                   or (request.client.host if request.client else "unknown")),
            "user_agent": request.headers.get("user-agent", "")[:300]}


@router.get("/ssl-check")
def ssl_check(host: str, request: Request, resp: Response):
    """Live TLS certificate report for any public HTTPS host."""
    err = _guard(request, resp, host)
    if err:
        return err
    h = _safe_host(host)
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((h, 443), timeout=6) as sock:
            with ctx.wrap_socket(sock, server_hostname=h) as tls:
                cert = tls.getpeercert()
                proto = tls.version()
        exp = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                                ).replace(tzinfo=timezone.utc)
        days = (exp - datetime.now(timezone.utc)).days
        sans = [v for k, v in cert.get("subjectAltName", ()) if k == "DNS"][:25]
        issuer = {k: v for pair in cert.get("issuer", ()) for k, v in pair}
        subject = {k: v for pair in cert.get("subject", ()) for k, v in pair}
        return {"host": h, "valid": True, "tls_version": proto,
                "subject": subject.get("commonName", ""),
                "issuer": issuer.get("organizationName")
                or issuer.get("commonName", ""),
                "not_after": exp.isoformat(), "days_left": days,
                "sans": sans,
                "verdict": ("expired" if days < 0 else "critical" if days <= 7
                            else "warning" if days <= 30 else "ok")}
    except ssl.SSLCertVerificationError as e:
        return {"host": h, "valid": False,
                "error": f"certificate failed verification: {e.verify_message or e}"[:200]}
    except OSError as e:
        return {"host": h, "valid": False,
                "error": f"could not reach {h}:443 ({e})"[:200]}


@router.get("/dns-check")
def dns_check(domain: str, request: Request, resp: Response):
    """Email-security posture for a domain: MX, SPF, DMARC (+ verdicts)."""
    err = _guard(request, resp, domain)
    if err:
        return err
    d = _safe_host(domain)
    import dns.resolver  # dnspython

    def q(name, rtype):
        try:
            return [r.to_text().strip('"') for r in
                    dns.resolver.resolve(name, rtype, lifetime=5)]
        except Exception:  # noqa: BLE001
            return []
    mx = q(d, "MX")
    txt = q(d, "TXT")
    spf = next((t for t in txt if t.lower().startswith("v=spf1")), "")
    dmarc = next((t for t in q(f"_dmarc.{d}", "TXT")
                  if t.lower().startswith("v=dmarc1")), "")
    pol = (re.search(r"\bp=(\w+)", dmarc or "") or [None, ""])[1]
    checks = [
        {"name": "MX records", "ok": bool(mx),
         "detail": f"{len(mx)} mail server(s)" if mx else "no MX — domain can't receive mail"},
        {"name": "SPF", "ok": bool(spf),
         "detail": spf[:120] if spf else "missing — anyone can spoof this domain's mail"},
        {"name": "SPF strictness", "ok": spf.endswith("-all"),
         "detail": "hard fail (-all)" if spf.endswith("-all")
         else "soft/none — spoofed mail may still land" if spf else "n/a"},
        {"name": "DMARC", "ok": bool(dmarc),
         "detail": dmarc[:120] if dmarc else "missing — no policy for auth failures"},
        {"name": "DMARC enforcement", "ok": pol in ("quarantine", "reject"),
         "detail": f"p={pol}" if pol else "n/a"},
    ]
    score = sum(1 for c in checks if c["ok"])
    return {"domain": d, "checks": checks, "score": score, "out_of": len(checks),
            "grade": "A" if score == 5 else "B" if score == 4 else
            "C" if score == 3 else "D" if score == 2 else "F"}


_SEC_HEADERS = [
    ("strict-transport-security", "HSTS", "forces HTTPS on every future visit"),
    ("content-security-policy", "CSP", "blocks injected scripts (XSS)"),
    ("x-content-type-options", "X-Content-Type-Options", "stops MIME sniffing"),
    ("x-frame-options", "X-Frame-Options", "stops clickjacking iframes"),
    ("referrer-policy", "Referrer-Policy", "limits URL leakage to other sites"),
    ("permissions-policy", "Permissions-Policy", "limits camera/mic/geo access"),
]


@router.get("/headers-check")
def headers_check(host: str, request: Request, resp: Response):
    """Security-header report card for any public site (HEAD-ish GET)."""
    err = _guard(request, resp, host)
    if err:
        return err
    h = _safe_host(host)
    try:
        t0 = time.time()
        req = urllib.request.Request(
            f"https://{h}/", method="GET",
            headers={"User-Agent": "BVTech-HeaderCheck/1.0 (+https://bvtech.org/tools/)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            got = {k.lower(): v for k, v in r.headers.items()}
            status = r.status
        ms = int((time.time() - t0) * 1000)
    except OSError as e:
        return {"host": h, "error": f"could not fetch https://{h}/ ({e})"[:200]}
    checks = [{"header": label, "ok": key in got, "why": why,
               "value": got.get(key, "")[:140]}
              for key, label, why in _SEC_HEADERS]
    score = sum(1 for c in checks if c["ok"])
    return {"host": h, "status": status, "response_ms": ms, "checks": checks,
            "score": score, "out_of": len(checks),
            "grade": "A" if score >= 6 else "B" if score == 5 else
            "C" if score == 4 else "D" if score >= 2 else "F"}


# --------------------------------------------------------------------------- #
# v1.62 LEAD CAPTURE — turn free-tool traffic into pipeline.
#
# The 24 tools on bvtech.org draw real local businesses running real checks
# (SSL expiry, breached passwords, the Security Scoreboard). Until now every
# one of them left anonymously. This optional endpoint - "email me my full
# report" - lands the visitor in the CRM as an INBOUND lead (higher intent
# than any cold scrape), tagged with the tool they used and what it found, so
# the outbound engine follows up automatically. DB work is lazy-imported so
# the rest of this module stays database-free by design.
# --------------------------------------------------------------------------- #
import json as _json_lc
from urllib import request as _urlreq_lc

_EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", re.I)
_LEAD_RATE: dict = {}
_LEAD_MAX = 5             # lead submissions / 10 min / ip (anti-abuse)


def _lead_limited(request: Request) -> bool:
    ip = (request.headers.get("cf-connecting-ip")
          or (request.client.host if request.client else "?"))
    now = time.time()
    win = _LEAD_RATE.get(ip)
    if not win or now - win[0] > 600:
        _LEAD_RATE[ip] = [now, 1]
        if len(_LEAD_RATE) > 10000:
            _LEAD_RATE.clear()
        return False
    win[1] += 1
    return win[1] > _LEAD_MAX


@router.post("/lead")
async def capture_lead(request: Request, resp: Response):
    """Public lead intake from the free tools. Body: {email, name?, company?,
    tool, result?, consent?}. Creates/updates a CRM inbound lead and notifies
    staff. Best-effort + safe: never leaks whether an email already existed."""
    _cors(request, resp)
    if _lead_limited(request):
        return {"ok": False, "error": "Too many submissions - try again in a few minutes."}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    email = str(body.get("email") or "").strip().lower()[:255]
    if not _EMAIL_RE.fullmatch(email):
        return {"ok": False, "error": "Please enter a valid email address."}
    name = str(body.get("name") or "").strip()[:200] or None
    company = str(body.get("company") or "").strip()[:200] or None
    tool = str(body.get("tool") or "free tool").strip()[:80]
    result = str(body.get("result") or "").strip()[:400] or None
    ip = (request.headers.get("cf-connecting-ip")
          or (request.client.host if request.client else "?"))

    from ...core.db import SessionLocal
    from ...models import CrmContact, Notification
    from ...services import crm, outbound
    db = SessionLocal()
    try:
        existing = (db.query(CrmContact)
                    .filter(CrmContact.email.ilike(email)).first())
        note = f"Used the {tool} at bvtech.org" + (f" - result: {result}" if result else "")
        is_new = existing is None
        if existing is None:
            contact = CrmContact(
                name=name or email.split("@")[0], email=email, company=company,
                source="tool", status="new", score=72, market=None,
                tags=["Website Tool Lead", tool], notes=note)
            db.add(contact)
            db.flush()
        else:
            contact = existing
            # a customer or opted-out person using a tool is NOT re-solicited
            if not contact.do_not_contact and (contact.status or "") not in (
                    "customer", "client", "won"):
                contact.status = "new"
                contact.score = max(contact.score or 0, 72)
                tags = list(contact.tags or [])
                for t in ("Website Tool Lead", tool):
                    if t not in tags:
                        tags.append(t)
                contact.tags = tags
                if company and not contact.company:
                    contact.company = company
        crm.log_activity(db, contact, "tool", subject=f"Tool: {tool}",
                         body=(note + f" (ip {ip})")[:1000], direction="inbound",
                         meta={"campaign": "inbound_tool", "tool": tool}, commit=False)
        try:
            db.add(Notification(
                client_id=None, target_user_id=None, kind="content",
                severity="info",
                message=(f"🌐 New inbound lead from the {tool}: {email}"
                         + (f" ({company})" if company else "")
                         + (f" - {result}" if result else "")
                         + (". Already in CRM - re-engaged." if not is_new else "."))[:1000]))
        except Exception:  # noqa: BLE001
            pass
        db.commit()

        # Optional instant auto-reply through the M365 mailbox, if configured.
        # Never cold-pitch an existing customer or an opted-out contact - they
        # get logged and the team is notified, but no automated solicitation.
        _solicit = (not contact.do_not_contact
                    and (contact.status or "new") not in ("customer", "client", "won"))
        sent = False
        try:
            send_fn, _ = outbound.resolve_send_fn(db)
            if send_fn is not None and _solicit:
                first = (name or "there").split(" ")[0]
                subject = f"Your {tool} results from BVTech"
                greet = (f"Hi {first},\n\n"
                         f"Thanks for using the {tool} on bvtech.org"
                         + (f" - here's what it flagged: {result}.\n\n" if result else ".\n\n")
                         + "I'm Jordan, founder of BVTech, a Texas MSP that's kept local "
                         "businesses secure and running since 2013. If you'd like, I'll do a "
                         "free 15-minute review of where you stand and hand you the full "
                         "findings - no pitch, and you keep the list either way.\n\n"
                         "Grab any slot that suits you: bvtech.org/book\n\n"
                         "- Jordan Polasek, BVTech LLC")
                send_fn(email, subject, greet)
                sent = True
                # Count this as sequence touch 1 so the outbound engine continues
                # at the value-add follow-up instead of re-sending the intro.
                crm.log_activity(db, contact, "email", subject=subject,
                                 body=greet[:1000], direction="outbound",
                                 meta={"campaign": "bvtech_acq", "step": 0,
                                       "via": "tool_autoreply"}, commit=True)
        except Exception:  # noqa: BLE001
            sent = False
        return {"ok": True, "emailed": sent,
                "message": "Thanks - your results are on the way, and a BVTech "
                           "specialist will follow up shortly."}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"ok": False, "error": "Something went wrong saving that - please try again."}
    finally:
        db.close()
