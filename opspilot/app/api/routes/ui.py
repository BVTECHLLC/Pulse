"""Server-rendered HTML pages. Auth is enforced client-side via /api/auth/me
plus the API itself rejecting unauthenticated calls — pages are shells that
fetch their data. Sensitive data never ships in the HTML itself."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ...core.config import get_settings

router = APIRouter(tags=["ui"])
_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
_s = get_settings()


def _ctx(request: Request, **extra):
    return {"request": request, "app_name": _s.APP_NAME, "version": _s.APP_VERSION, **extra}


# HTML shells must NEVER be cached: the footer version + the JS they load are tied
# to the running build, so a cached page makes a freshly deployed site look stale
# (and can pin clients to an old installer flow). `no-store` defeats both the
# browser cache and any intermediary (e.g. Cloudflare) so a new deploy is visible
# on the very next request. Static assets (/static) keep their own caching.
def _page(name: str, request: Request, **extra) -> HTMLResponse:
    resp = _templates.TemplateResponse(name, _ctx(request, **extra))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@router.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return _page("login.html", request)


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return _page("signup.html", request)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return _page("dashboard.html", request)


@router.get("/portal", response_class=HTMLResponse)
def portal(request: Request):
    return _page("portal.html", request)


@router.get("/academy", response_class=HTMLResponse)
def academy_page(request: Request):
    """Pulse Cyber Academy (v1.2) — mobile-first gamified security training for
    staff and client users alike. The page itself is public shell; every API it
    calls requires a session, and the JS bounces to login on 401."""
    return _page("academy.html", request)


@router.get("/invoice/{invoice_id}", response_class=HTMLResponse)
def invoice_view(invoice_id: int, request: Request):
    return _page("invoice.html", request, invoice_id=invoice_id)


@router.get("/report/{client_id}", response_class=HTMLResponse)
def report_view(client_id: int, request: Request):
    return _page("report.html", request, client_id=client_id)


@router.get("/remote/{token}", response_class=HTMLResponse)
def remote_view(token: str, request: Request):
    return _page("remote.html", request, token=token)


@router.get("/status", response_class=HTMLResponse)
def status_page(request: Request):
    """Public, branded uptime/incident page an MSP can share with its clients.
    The shell fetches /api/status/public; if the page isn't enabled the API
    returns 404 and the page shows a neutral 'not available' message."""
    return _page("status.html", request)


@router.get("/developers", response_class=HTMLResponse)
def developers(request: Request):
    """Branded developer hub: how to authenticate, the event catalog, webhook
    signature verification, inbound ingest, and a link to the live OpenAPI."""
    return _page("developers.html", request)


@router.get("/api/openapi.json")
def openapi_schema(request: Request):
    """The full machine-readable API schema, so any tool (Postman, Zapier, Make,
    a code generator) can import the entire Pulse API. Public by design — it
    describes the surface, never data; every endpoint still enforces auth."""
    return request.app.openapi()
