"""Declarative **field-format validator registry** (R7, D16; design §5 seam c).

A field may carry an optional ``FieldFormat {checker, params}`` attribute (R7.1) naming a
PLATFORM-DEFINED checker token. This module is the single home of that token set: a
module-level ``REGISTRY`` mapping each token to a pure checker function

    ``Callable[[Any, Mapping[str, Any]], FieldError | None]``

returning ``None`` when the value is acceptable, or a :class:`FieldError` (machine ``code`` +
English ``detail``) describing the failure so it can be merged into the shared
``{field: FieldError}`` map by the one generic validation step (R7.5, task 3.4).

Why this is a registry and not two inline validators (D16)
----------------------------------------------------------
The v1 *need* is only two entries — ``EMAIL`` (a regex, reusing the existing platform email
pattern) and ``IBAN`` (ISO 13616 mod-97 checksum — a regex can check shape but cannot verify
the checksum, so it is NOT a regex). Building the config-driven registry for just these two is
a deliberate, recorded EXCEPTION to the rule-of-three (steering 35): the committed
events/webshop roadmap will carry the same "attach a checker to a field" need, so the registry
is built now and the members application is simply its FIRST caller. It is built members-local
with a module-agnostic seam; extraction to ``sam/shared`` is deferred to the second consumer.

Platform-defined, tenant-attached (R7.7)
----------------------------------------
The checker SET is platform-defined here — a tenant picks a KNOWN token, it cannot author code.
*Attaching* a token to a field is tenant config on the ``config#fields`` row (the ``format``
sub-object), read back by ``projection_config_reader._build_format`` (task 3.3). An unknown /
malformed token degrades to ``None`` at read time (R7.3) so it never reaches this registry; a
caller that still looks up an unknown token uses :func:`get_checker`, which returns ``None``
(no crash — a stray token is simply not enforced).

``DATE`` / ``PHONE`` / … remain open for extension: add a checker function and a
``REGISTRY`` entry; nothing else changes (R7.6).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from .error_codes import (
    VALIDATION_INVALID_EMAIL,
    VALIDATION_INVALID_IBAN,
    FieldError,
)

__all__ = [
    "REGISTRY",
    "FormatChecker",
    "check_email",
    "check_iban",
    "get_checker",
    "known_tokens",
]

#: A format checker: given a field VALUE and the field's ``format.params`` mapping, return
#: ``None`` when the value is acceptable or a :class:`FieldError` describing the failure. A
#: checker is PURE (no I/O) and NEVER raises on user input — a malformed value is a returned
#: error, not an exception.
FormatChecker = Callable[[Any, Mapping[str, Any]], "FieldError | None"]


# ── Platform-defined token constants ──────────────────────────────────────────────────
#: The ``EMAIL`` checker token (R7.6) — a regex format check.
EMAIL = "EMAIL"
#: The ``IBAN`` checker token (R7.6) — ISO 13616 mod-97 checksum (NOT a regex).
IBAN = "IBAN"


# ── EMAIL — reuse the existing platform email pattern ─────────────────────────────────
#
# This is the SAME regex the Flask plane already uses for server-side email validation
# (``backend/src/services/contact_service.py`` ``EMAIL_PATTERN`` and
# ``backend/src/routes/landing_page_routes/public_endpoints.py`` ``_EMAIL_PATTERN``):
# ``local@domain.tld`` with at least one dot in the domain. Reusing the established pattern
# keeps one email-shape contract across both planes (R7.6 — "reuse the existing pattern").
_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def check_email(value: Any, params: Mapping[str, Any]) -> FieldError | None:
    """``EMAIL`` checker — the value must be a well-formed email address (R7.6).

    ``params`` is unused for EMAIL (the shape is fixed by the platform pattern). A non-string or
    a string that does not match the platform pattern yields a :class:`FieldError`; an
    acceptable address yields ``None``. Leading/trailing whitespace is tolerated (stripped
    before matching), mirroring the Flask ``_validate_email`` precedent.
    """
    if not isinstance(value, str) or not _EMAIL_PATTERN.match(value.strip()):
        return FieldError(
            code=VALIDATION_INVALID_EMAIL,
            detail="must be a valid email address",
        )
    return None


# ── IBAN — ISO 13616 mod-97 checksum (NOT a regex) ────────────────────────────────────

#: ISO 13616 length-by-country would be the strict gate; v1 keeps a conservative structural
#: envelope (2 letters + 2 check digits + up to 30 alphanumerics) and relies on the mod-97
#: checksum for correctness — the checksum is what a regex cannot do (R6.2/R7.6).
_IBAN_STRUCTURE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}$")


def _iban_mod97(compact: str) -> int:
    """Return the ISO 13616 / ISO 7064 mod-97 remainder of a compact (no-space) IBAN.

    Move the first four characters to the end, map each letter to its two-digit value
    (``A``=10 … ``Z``=35), then take the whole numeric string mod 97. A valid IBAN yields ``1``.
    Computed digit-by-digit so an arbitrarily long IBAN never overflows (pure-Python big ints
    make overflow a non-issue, but the running remainder keeps the intermediate small).
    """
    rearranged = compact[4:] + compact[:4]
    remainder = 0
    for ch in rearranged:
        # 'A'-'Z' -> "10".."35"; '0'-'9' -> the digit itself.
        chunk = str(ord(ch) - 55) if ch.isalpha() else ch
        for digit in chunk:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder


def check_iban(value: Any, params: Mapping[str, Any]) -> FieldError | None:
    """``IBAN`` checker — ISO 13616 structure + **mod-97 checksum** (R6.2/R7.6).

    Spaces are tolerated and case is normalised (``NL91 ABNA 0417 1643 00`` ≡
    ``NL91ABNA0417164300``) before validation. The value must be a string matching the
    structural envelope AND pass the mod-97 checksum (remainder 1); anything else yields a
    :class:`FieldError`. ``params`` is unused in v1 (a country-length table is a future
    extension). Never raises on user input.
    """
    if not isinstance(value, str):
        return _iban_error()
    compact = value.replace(" ", "").upper()
    if not _IBAN_STRUCTURE.match(compact):
        return _iban_error()
    if _iban_mod97(compact) != 1:
        return _iban_error()
    return None


def _iban_error() -> FieldError:
    return FieldError(
        code=VALIDATION_INVALID_IBAN,
        detail="must be a valid IBAN (ISO 13616 mod-97 checksum)",
    )


# ── The platform-defined registry (R7.6/R7.7) ─────────────────────────────────────────
#: Token → checker. The platform-defined checker SET; EMAIL and IBAN are v1's two entries,
#: the first callers of a seam the events/webshop roadmap will reuse (D16). Add a token here
#: (plus its checker function) to extend — no other wiring changes.
REGISTRY: dict[str, FormatChecker] = {
    EMAIL: check_email,
    IBAN: check_iban,
}


def get_checker(token: str) -> FormatChecker | None:
    """Return the checker for a token, or ``None`` for an unknown token.

    The lookup is tolerant (no ``KeyError``): the reader already degrades an unknown/malformed
    ``format`` token to ``None`` at config-read time (R7.3), so a token reaching here should be
    known — but a defensive ``None`` means a stray token is simply not enforced rather than
    crashing the validation step (R7.5).
    """
    if not isinstance(token, str):
        return None
    return REGISTRY.get(token)


def known_tokens() -> frozenset[str]:
    """The platform-defined token set — the tokens a tenant may attach to a field (R7.7).

    Used by the Flask projection validator (task 8.3) to fail loud at Save when a tenant
    attaches a ``format.checker`` that is not a platform-known token.
    """
    return frozenset(REGISTRY)
