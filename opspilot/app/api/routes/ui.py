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


@router.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return _templates.TemplateResponse("login.html", _ctx(request))


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return _templates.TemplateResponse("signup.html", _ctx(request))


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return _templates.TemplateResponse("dashboard.html", _ctx(request))


@router.get("/portal", response_class=HTMLResponse)
def portal(request: Request):
    return _templates.TemplateResponse("portal.html", _ctx(request))


@router.get("/invoice/{invoice_id}", response_class=HTMLResponse)
def invoice_view(invoice_id: int, request: Request):
    return _templates.TemplateResponse("invoice.html", _ctx(request, invoice_id=invoice_id))
