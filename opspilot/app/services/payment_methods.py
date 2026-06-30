"""v0.59 Multi-method payments — give clients every way to pay an invoice.

Stripe (card) is the existing online-checkout flow. On top of it this module
adds *self-serve* payment rails the MSP configures once in Settings and that then
render on every invoice the client opens:

  * PayPal (PayPal.me deep link, amount pre-filled)
  * Venmo  (pay deep link)
  * Cash App ($cashtag deep link, amount pre-filled)
  * Zelle  (email/phone instructions)
  * Bank wire / ACH (printed beneficiary + routing/account instructions)
  * Check by mail (payee + mailing address)
  * QuickBooks (a "Pay in QuickBooks" link or note)
  * Other / custom (a fully free-form method — any rail not listed above)

Everything is stored on ONE platform vault row (provider="payment_methods"). The
config is plain-by-design: wire/Zelle/PayPal details are *meant* to be shown to
the payer, so they're displayed (not masked) — there are no API secrets here.
A method is "live" only when its required fields are filled in, so a client never
sees a half-configured option.

`pay_options(cfg, invoice_ctx)` returns the browser-ready list for an invoice,
with amounts and a memo (the invoice number) pre-filled into each deep link.
"""
from __future__ import annotations

from urllib.parse import quote, quote_plus

# Each method: required fields gate whether it shows; `fields` documents the full
# editable set for the settings UI. `secret` is never True here (see module doc).
METHODS = {
    "paypal": {
        "label": "PayPal", "emoji": "🅿️",
        "fields": ["paypal_handle", "paypal_email"],
        "required_any": [["paypal_handle"], ["paypal_email"]],
    },
    "venmo": {
        "label": "Venmo", "emoji": "🟦",
        "fields": ["venmo_handle"], "required": ["venmo_handle"],
    },
    "cashapp": {
        "label": "Cash App", "emoji": "💚",
        "fields": ["cashapp_cashtag"], "required": ["cashapp_cashtag"],
    },
    "zelle": {
        "label": "Zelle", "emoji": "⚡",
        "fields": ["zelle_handle", "zelle_name"], "required": ["zelle_handle"],
    },
    "bank_wire": {
        "label": "Bank Wire / ACH", "emoji": "🏦",
        "fields": ["bank_name", "bank_beneficiary", "bank_routing", "bank_account",
                   "bank_swift", "bank_address"],
        "required": ["bank_routing", "bank_account"],
    },
    "check": {
        "label": "Check by Mail", "emoji": "✉️",
        "fields": ["check_payee", "check_address"], "required": ["check_payee", "check_address"],
    },
    "quickbooks": {
        "label": "QuickBooks", "emoji": "💵",
        "fields": ["quickbooks_pay_url", "quickbooks_note"],
        "required_any": [["quickbooks_pay_url"], ["quickbooks_note"]],
    },
    "other": {
        "label": "Other", "emoji": "💳",
        "fields": ["other_label", "other_url", "other_instructions"],
        "required_any": [["other_url"], ["other_instructions"]],
    },
}

# Every settings field across all methods, plus the global note (drives the UI).
ALL_FIELDS = [f for m in METHODS.values() for f in m["fields"]] + ["methods_note"]


def _v(cfg: dict, key: str) -> str:
    val = (cfg or {}).get(key)
    return str(val).strip() if val not in (None, "") else ""


def _has_required(cfg: dict, meta: dict) -> bool:
    if "required" in meta:
        return all(_v(cfg, k) for k in meta["required"])
    if "required_any" in meta:
        return any(all(_v(cfg, k) for k in group) for group in meta["required_any"])
    return False


def enabled_methods(cfg: dict | None) -> list[str]:
    """Keys of the methods that are fully configured (so safe to show clients)."""
    cfg = cfg or {}
    return [k for k, meta in METHODS.items() if _has_required(cfg, meta)]


def _amount(invoice_ctx: dict) -> str:
    """Two-decimal amount string for deep links (e.g. '1500.00')."""
    try:
        return f"{float(invoice_ctx.get('total') or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _memo(invoice_ctx: dict) -> str:
    num = invoice_ctx.get("number") or f"#{invoice_ctx.get('id', '')}"
    return f"Invoice {num}".strip()


def _instr(*pairs) -> list[dict]:
    """Build a label/value instruction list, dropping empty values."""
    return [{"label": l, "value": v} for l, v in pairs if v]


def _build_one(key: str, cfg: dict, ctx: dict) -> dict | None:
    amt, memo = _amount(ctx), _memo(ctx)
    meta = METHODS[key]
    base = {"key": key, "label": meta["label"], "emoji": meta["emoji"]}

    if key == "paypal":
        handle = _v(cfg, "paypal_handle").lstrip("@")
        if handle:
            return {**base, "kind": "link",
                    "url": f"https://www.paypal.com/paypalme/{quote(handle)}/{amt}",
                    "button": f"Pay {amt} with PayPal"}
        email = _v(cfg, "paypal_email")
        return {**base, "kind": "instructions",
                "instructions": _instr(("Send PayPal to", email)),
                "note": f"Reference: {memo}"}

    if key == "venmo":
        handle = _v(cfg, "venmo_handle").lstrip("@")
        url = ("https://venmo.com/?txn=pay"
               f"&recipients={quote(handle)}&amount={amt}&note={quote_plus(memo)}")
        return {**base, "kind": "link", "url": url, "button": f"Pay {amt} with Venmo"}

    if key == "cashapp":
        tag = _v(cfg, "cashapp_cashtag").lstrip("$")
        return {**base, "kind": "link",
                "url": f"https://cash.app/${quote(tag)}/{amt}",
                "button": f"Pay {amt} with Cash App"}

    if key == "zelle":
        return {**base, "kind": "instructions",
                "instructions": _instr(("Send Zelle to", _v(cfg, "zelle_handle")),
                                       ("Recipient name", _v(cfg, "zelle_name"))),
                "note": f"Amount: {amt} · Reference: {memo}"}

    if key == "bank_wire":
        return {**base, "kind": "instructions",
                "instructions": _instr(("Bank", _v(cfg, "bank_name")),
                                       ("Beneficiary", _v(cfg, "bank_beneficiary")),
                                       ("Routing / ABA", _v(cfg, "bank_routing")),
                                       ("Account", _v(cfg, "bank_account")),
                                       ("SWIFT/BIC", _v(cfg, "bank_swift")),
                                       ("Bank address", _v(cfg, "bank_address"))),
                "note": f"Amount: {amt} · Reference: {memo}"}

    if key == "check":
        return {**base, "kind": "instructions",
                "instructions": _instr(("Payable to", _v(cfg, "check_payee")),
                                       ("Mail to", _v(cfg, "check_address"))),
                "note": f"Amount: {amt} · Memo: {memo}"}

    if key == "quickbooks":
        url = _v(cfg, "quickbooks_pay_url")
        if url:
            return {**base, "kind": "link", "url": url, "button": "Pay in QuickBooks"}
        return {**base, "kind": "instructions", "instructions": [],
                "note": _v(cfg, "quickbooks_note")}

    if key == "other":
        label = _v(cfg, "other_label") or "Other"
        url = _v(cfg, "other_url")
        out = {**base, "label": label}
        if url:
            return {**out, "kind": "link", "url": url, "button": f"Pay via {label}"}
        return {**out, "kind": "instructions", "instructions": [],
                "note": _v(cfg, "other_instructions")}
    return None


def pay_options(cfg: dict | None, invoice_ctx: dict) -> list[dict]:
    """Browser-ready pay options for one invoice (Stripe handled separately)."""
    cfg = cfg or {}
    opts = []
    for key in enabled_methods(cfg):
        built = _build_one(key, cfg, invoice_ctx)
        if built:
            opts.append(built)
    return opts
