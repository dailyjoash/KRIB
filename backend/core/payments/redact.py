"""Redaction helpers for payment payloads.

Used both when persisting `PaymentTransaction.raw_callback` and when writing
logs. Keep them pure and side-effect-free so tests can call them directly.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


# Fields whose VALUE must always be redacted regardless of nesting depth.
# These commonly carry phone numbers, emails, payer names, or auth tokens.
_SECRET_KEYS = {
    "phone",
    "phone_number",
    "msisdn",
    "account",
    "email",
    "payer_email",
    "first_name",
    "last_name",
    "full_name",
    "name",
    "address",
    "id_number",
    "passport",
    "card_number",
    "cvv",
    "ssn",
    "authorization",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
}


_PHONE_RE = re.compile(r"\b(?:\+?254|0)?[17]\d{8}\b")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _mask_phone(value: str) -> str:
    return _PHONE_RE.sub(lambda m: m.group(0)[:3] + "***" + m.group(0)[-2:], value)


def _mask_email(value: str) -> str:
    def _mask(m):
        addr = m.group(0)
        local, _, domain = addr.partition("@")
        if not local:
            return "***@" + domain
        return local[0] + "***@" + domain

    return _EMAIL_RE.sub(_mask, value)


def _scrub_scalar(value: Any) -> Any:
    if isinstance(value, str):
        v = _mask_phone(value)
        v = _mask_email(v)
        return v
    return value


def redact_payment_payload(payload: Any, *, depth: int = 0) -> Any:
    """Return a copy of `payload` with sensitive fields masked.

    - Keys in `_SECRET_KEYS` (case-insensitive) get their value replaced with
      a string indicator instead of the raw value.
    - Free-text strings have phone numbers and emails masked.
    - Lists/dicts are traversed recursively.
    - Depth is capped to defend against runaway recursion on hostile input.
    """
    if depth > 8:
        return "<...>"

    if isinstance(payload, Mapping):
        cleaned: dict = {}
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() in _SECRET_KEYS:
                cleaned[key] = "<redacted>"
            else:
                cleaned[key] = redact_payment_payload(value, depth=depth + 1)
        return cleaned

    if isinstance(payload, list):
        return [redact_payment_payload(item, depth=depth + 1) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact_payment_payload(item, depth=depth + 1) for item in payload)

    return _scrub_scalar(payload)


def redact_text(text: str) -> str:
    """Mask phone numbers and email addresses inside a free-text string."""
    if not isinstance(text, str):
        return text
    return _mask_email(_mask_phone(text))
