"""v0.57 Stripe payments — let clients pay an invoice online, auto-reconcile.

Creates a Stripe Checkout Session for a Pulse invoice and verifies inbound
webhooks (HMAC, per Stripe's scheme) to mark the invoice paid. stdlib HTTP; the
`_post` call is overridden in tests so session construction + webhook
verification are validated offline.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib import error, parse
from urllib import request as urlrequest

API = "https://api.stripe.com/v1"


class StripeError(Exception):
    pass


def _post(secret_key: str, path: str, form: dict) -> dict:
    body = parse.urlencode(form).encode()
    req = urlrequest.Request(f"{API}/{path}", data=body, method="POST", headers={
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlrequest.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise StripeError(f"Stripe HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        raise StripeError(f"Stripe request failed: {e}")


def checkout_session_form(invoice, success_url: str, cancel_url: str) -> dict:
    """Build the form for a one-line Checkout Session that charges the invoice total."""
    amount_cents = int(round(float(invoice.total or 0) * 100))
    if amount_cents <= 0:
        raise StripeError("invoice total must be greater than zero")
    label = f"Invoice {invoice.number or invoice.id}"
    return {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(invoice.id),
        "metadata[invoice_id]": str(invoice.id),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": (invoice.currency or "usd").lower(),
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]": label,
    }


def create_checkout(secret_key: str, invoice, success_url: str, cancel_url: str) -> dict:
    form = checkout_session_form(invoice, success_url, cancel_url)
    res = _post(secret_key, "checkout/sessions", form)
    return {"id": res.get("id"), "url": res.get("url")}


def verify_webhook(payload: bytes, sig_header: str, signing_secret: str,
                   tolerance: int = 300, now: int | None = None) -> dict:
    """Verify a Stripe webhook signature and return the parsed event.

    Stripe-Signature looks like `t=<ts>,v1=<hex>`; the signed payload is
    `<ts>.<raw body>` HMAC-SHA256'd with the signing secret. Raises on mismatch.
    """
    if not sig_header or not signing_secret:
        raise StripeError("missing signature or signing secret")
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts = parts.get("t")
    sent = parts.get("v1")
    if not ts or not sent:
        raise StripeError("malformed Stripe-Signature header")
    body = payload if isinstance(payload, (bytes, bytearray)) else str(payload).encode()
    signed = f"{ts}.".encode() + body
    expected = hmac.new(signing_secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sent):
        raise StripeError("signature mismatch")
    cur = now if now is not None else int(time.time())
    if abs(cur - int(ts)) > tolerance:
        raise StripeError("timestamp outside tolerance")
    return json.loads(body.decode())


def invoice_id_from_event(event: dict) -> int | None:
    """Pull our invoice id out of a checkout.session.completed / paid event."""
    obj = (event.get("data") or {}).get("object") or {}
    meta = obj.get("metadata") or {}
    raw = meta.get("invoice_id") or obj.get("client_reference_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None
