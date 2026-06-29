"""Outbound email.

If SMTP is configured (SMTP_HOST set), messages are sent via smtplib. If not,
they are logged to stdout and the call returns False — so every environment runs
without crashing, and a real mail server can be dropped in later via env vars.
send() never raises; delivery failures are swallowed and logged.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..core.config import get_settings


def _from_addr(s) -> str:
    return s.SMTP_FROM or s.SUPPORT_EMAIL


def send(to: str, subject: str, body: str, attachments: list[tuple] | None = None) -> bool:
    """Send a plain-text email, optionally with attachments. Each attachment is a
    (filename, content_str_or_bytes, mimetype) tuple, e.g.
    ('report.csv', csv_text, 'text/csv'). Returns True if handed to SMTP."""
    s = get_settings()
    if not s.email_enabled:
        extra = f" attachments={[a[0] for a in attachments]}" if attachments else ""
        print(f"[email:disabled] to={to} subject={subject!r}{extra} "
              f"(set SMTP_HOST to enable real delivery)")
        return False
    try:
        msg = EmailMessage()
        msg["From"] = _from_addr(s)
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        for fname, content, mimetype in (attachments or []):
            data = content.encode() if isinstance(content, str) else content
            maintype, _, subtype = (mimetype or "application/octet-stream").partition("/")
            msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream",
                               filename=fname)
        with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=20) as smtp:
            if s.SMTP_STARTTLS:
                smtp.starttls()
            if s.SMTP_USER:
                smtp.login(s.SMTP_USER, s.SMTP_PASSWORD or "")
            smtp.send_message(msg)
        print(f"[email:sent] to={to} subject={subject!r}")
        return True
    except Exception as exc:  # never let email break a request flow
        print(f"[email:error] to={to} subject={subject!r} err={exc}")
        return False


# --------------------------------------------------------------------------- #
# Composed messages
# --------------------------------------------------------------------------- #
def send_invite(to: str, full_name: str | None, temp_password: str, role: str) -> bool:
    s = get_settings()
    name = full_name or to
    body = (
        f"Hi {name},\n\n"
        f"An account has been created for you on BVTech OpsPilot ({role}).\n\n"
        f"Sign in:  {s.PUBLIC_BASE_URL}\n"
        f"Email:    {to}\n"
        f"Temp password: {temp_password}\n\n"
        "Please sign in and change your password right away, then enable MFA.\n\n"
        "— BVTech LLC"
    )
    return send(to, "Your BVTech OpsPilot account", body)


def send_signup_confirmation(to: str, name: str) -> bool:
    s = get_settings()
    body = (
        f"Hi {name},\n\n"
        "Thanks for requesting access to BVTech OpsPilot. Our team will review "
        "your request and reach out shortly.\n\n"
        f"Questions? Reply to this email or contact {s.SUPPORT_EMAIL}.\n\n"
        "— BVTech LLC"
    )
    return send(to, "We received your BVTech OpsPilot request", body)


def send_signup_notice(name: str, email: str, company: str | None, message: str | None) -> bool:
    s = get_settings()
    body = (
        "New OpsPilot access request:\n\n"
        f"Name:    {name}\n"
        f"Email:   {email}\n"
        f"Company: {company or '-'}\n"
        f"Message: {message or '-'}\n\n"
        f"Review in the dashboard: {s.PUBLIC_BASE_URL}/dashboard"
    )
    return send(s.SUPPORT_EMAIL, f"New OpsPilot signup: {name}", body)
