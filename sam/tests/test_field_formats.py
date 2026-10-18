"""S5 — Member Application Form, task 3.2: the ``FieldFormat`` validator REGISTRY.

Pins the platform-defined checker set (R7.6/R7.7): a module-level ``REGISTRY`` mapping a token
to a pure checker ``(value, params) -> FieldError | None``, with ``EMAIL`` (regex, reusing the
existing platform email pattern) and ``IBAN`` (ISO 13616 mod-97 checksum — NOT a regex) as its
first two entries. Each checker returns ``None`` for an acceptable value and a
:class:`FieldError` (machine ``code`` + English ``detail``) for a bad one, so the one generic
validation step (task 3.4) can merge it into the shared ``{field: FieldError}`` map.

Validates: Requirements 7.6, 7.7
"""

from __future__ import annotations

import pytest

from sam.members.domain.error_codes import (
    VALIDATION_INVALID_EMAIL,
    VALIDATION_INVALID_IBAN,
    FieldError,
)
from sam.members.domain.field_formats import (
    EMAIL,
    IBAN,
    REGISTRY,
    check_email,
    check_iban,
    get_checker,
    known_tokens,
)


# ── Registry shape: platform-defined token set (R7.6/R7.7) ────────────────────────────


class TestRegistryShape:
    def test_registry_first_entries_are_email_and_iban(self):
        # R7.6: EMAIL and IBAN are the first two entries of the platform-defined registry.
        assert EMAIL == "EMAIL" and IBAN == "IBAN"
        assert REGISTRY[EMAIL] is check_email
        assert REGISTRY[IBAN] is check_iban

    def test_known_tokens_is_the_platform_defined_set(self):
        # R7.7: the checker SET is platform-defined (a tenant picks a known token).
        assert known_tokens() == frozenset({"EMAIL", "IBAN"})

    def test_get_checker_resolves_known_token(self):
        assert get_checker("EMAIL") is check_email
        assert get_checker("IBAN") is check_iban

    def test_get_checker_unknown_token_degrades_to_none(self):
        # A stray/unknown token is simply not enforced (never a KeyError) — supports R7.3.
        assert get_checker("DATE") is None
        assert get_checker("") is None
        assert get_checker(None) is None  # type: ignore[arg-type]

    def test_every_registry_value_is_callable(self):
        assert all(callable(fn) for fn in REGISTRY.values())


# ── EMAIL checker — valid + invalid (R7.6) ────────────────────────────────────────────


class TestCheckEmail:
    @pytest.mark.parametrize(
        "value",
        [
            "user@example.com",
            "first.last@example.com",
            "user+tag@example.co.uk",
            "a_b-c%d@sub.example.org",
            "  spaced@example.com  ",  # surrounding whitespace tolerated (stripped)
        ],
    )
    def test_valid_email_returns_none(self, value):
        assert check_email(value, {}) is None

    @pytest.mark.parametrize(
        "value",
        [
            "not-an-email",
            "missing-at.example.com",
            "no-domain@",
            "@no-local.com",
            "no-tld@example",
            "two@@example.com",
            "spaces in@example.com",
            "",
            "   ",
            None,
            12345,
        ],
    )
    def test_invalid_email_returns_field_error(self, value):
        err = check_email(value, {})
        assert isinstance(err, FieldError)
        assert err.code == VALIDATION_INVALID_EMAIL
        assert err.detail  # human fallback present


# ── IBAN checker — valid + invalid, mod-97 checksum (R7.6) ────────────────────────────


class TestCheckIban:
    @pytest.mark.parametrize(
        "value",
        [
            "NL91ABNA0417164300",            # canonical NL example
            "NL91 ABNA 0417 1643 00",        # spaces tolerated
            "nl91 abna 0417 1643 00",        # lower-case normalised
            "DE89370400440532013000",        # DE example
            "GB82WEST12345698765432",        # GB example
            "FR1420041010050500013M02606",   # FR example (letter in BBAN)
        ],
    )
    def test_valid_iban_returns_none(self, value):
        assert check_iban(value, {}) is None

    @pytest.mark.parametrize(
        "value",
        [
            "NL91ABNA0417164301",   # last digit flipped → mod-97 fails
            "DE89370400440532013001",  # checksum broken
            "GB00WEST12345698765432",  # wrong check digits
            "ZZ00",                 # structurally too short / bad checksum
            "1234567890",           # no country prefix
            "NL91-ABNA-0417164300",  # stray punctuation
            "",
            "   ",
            None,
            42,
        ],
    )
    def test_invalid_iban_returns_field_error(self, value):
        err = check_iban(value, {})
        assert isinstance(err, FieldError)
        assert err.code == VALIDATION_INVALID_IBAN
        assert err.detail

    def test_single_transposition_is_caught_by_mod97(self):
        # The mod-97 checksum catches a single transposition a regex cannot — the whole point
        # of IBAN being a checksum, not a regex (R6.2/R7.6).
        good = "NL91ABNA0417164300"
        transposed = "NL91ABNA0417163400"  # swap two BBAN digits
        assert check_iban(good, {}) is None
        assert check_iban(transposed, {}) is not None


# ── Checkers are callable via the registry the way the generic step will call them ────


class TestRegistryDispatch:
    def test_dispatch_email_through_registry(self):
        assert REGISTRY["EMAIL"]("user@example.com", {}) is None
        assert REGISTRY["EMAIL"]("nope", {}) is not None

    def test_dispatch_iban_through_registry(self):
        assert REGISTRY["IBAN"]("NL91ABNA0417164300", {}) is None
        assert REGISTRY["IBAN"]("NL91ABNA0417164301", {}) is not None
