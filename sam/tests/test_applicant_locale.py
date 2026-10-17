"""
Member Application Form (application-app) — task 5.1 tests.

Pins the applicant **locale** normalization + record-persistence contract (R6b/D12; design Phase 5).
The single authority for a client-supplied locale is ``applicant_locale``:

  * ``normalize_locale(value)``    — coerce any value to ``nl``/``en``, default+fallback ``nl``
  * ``locale_record_patch(value)`` — the ``{"locale": <normalized>}`` fragment persisted on record
  * ``locale_of_record(record)``   — read the persisted locale back, re-normalized, default ``nl``

These cover the four R6b clauses this task owns: ``en``/``nl`` accepted (R6b.1), invalid → ``nl``
fallback and missing → ``nl`` default (R6b.2), and the value persisted on + read back from the
record (R6b.4). The applicant-facing copy that this value *drives* (form labels, confirmation
email, R6b.3) and the staff locale independence (R6b.5) are their own consumers (Phases 4/6);
this task is the pure value authority they all call.

Validates: Requirements R6b.1, R6b.2, R6b.4
"""

from __future__ import annotations

import os
import sys

import pytest

# repo root on sys.path (mirrors the other sam/tests modules) so `sam.members...` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.applicant_locale import (
    DEFAULT_LOCALE,
    LOCALE_RECORD_KEY,
    SUPPORTED_LOCALES,
    locale_of_record,
    locale_record_patch,
    normalize_locale,
)


# ── R6b.1 — the supported set (nl/en), nl the default ────────────────────────────────


class TestSupportedSet:
    def test_supported_locales_are_nl_and_en(self):
        assert set(SUPPORTED_LOCALES) == {"nl", "en"}

    def test_default_locale_is_nl(self):
        assert DEFAULT_LOCALE == "nl"


# ── R6b.1 — a supported value is accepted and returned canonical ─────────────────────


class TestAcceptsSupported:
    @pytest.mark.parametrize("value", ["nl", "en"])
    def test_supported_value_returned_as_is(self, value):
        assert normalize_locale(value) == value

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("EN", "en"), ("NL", "nl"), ("En", "en"), (" en ", "en"), ("  NL", "nl")],
    )
    def test_supported_value_matched_case_and_whitespace_insensitively(self, raw, expected):
        # Wrong-case / padded but genuinely supported → canonical lower-case form (R6b.1).
        assert normalize_locale(raw) == expected


# ── R6b.2 — absent / blank / unsupported / non-string → nl fallback (never raises) ───


class TestFallsBackToNl:
    @pytest.mark.parametrize(
        "value",
        [
            None,          # missing locale (default, R6b.2)
            "",            # blank
            "   ",         # whitespace-only
            "de",          # supported-looking but unsupported
            "fr",
            "english",     # language name, not a code
            "nl-NL",       # region-tagged, not the bare supported code
            "xx",
            123,           # non-string
            ["nl"],        # non-string container
            {"locale": "nl"},
            object(),
        ],
    )
    def test_unsupported_or_missing_value_falls_back_to_nl(self, value):
        assert normalize_locale(value) == "nl"

    def test_fallback_never_raises(self):
        # R6b.2: a fallback, not an error — the call is total.
        for value in (None, "", "zz", 0, [], {}):
            assert normalize_locale(value) in SUPPORTED_LOCALES


# ── R6b.4 — the record-persistence contract: patch written, value read back ──────────


class TestRecordPersistenceContract:
    def test_patch_carries_normalized_value_under_locale_key(self):
        assert locale_record_patch("en") == {LOCALE_RECORD_KEY: "en"}
        assert LOCALE_RECORD_KEY == "locale"

    def test_patch_normalizes_before_persisting(self):
        # An invalid submitted locale is stored as nl, not the raw value (R6b.2 + R6b.4).
        assert locale_record_patch("de") == {"locale": "nl"}
        assert locale_record_patch(None) == {"locale": "nl"}
        assert locale_record_patch(" EN ") == {"locale": "en"}

    def test_patch_merges_as_top_level_record_attribute(self):
        # The create spine merges the patch into the record it writes — a flat sibling of
        # status/member_id, not nested (R6b.4, D12).
        record = {"member_id": "m-1", "status": "application", "personal": {"name": "Jo"}}
        record.update(locale_record_patch("en"))
        assert record["locale"] == "en"
        assert record["status"] == "application"  # patch touches only the locale key

    def test_locale_read_back_off_record(self):
        assert locale_of_record({"locale": "en"}) == "en"
        assert locale_of_record({"locale": "nl"}) == "nl"

    def test_read_back_round_trips_the_patch(self):
        for submitted, expected in [("en", "en"), ("nl", "nl"), ("de", "nl"), (None, "nl")]:
            record = {"member_id": "m", "status": "application"}
            record.update(locale_record_patch(submitted))
            assert locale_of_record(record) == expected

    def test_record_missing_locale_key_reads_as_nl(self):
        # A record that predates this field has no locale key → nl (R6b.4 robustness).
        assert locale_of_record({"member_id": "m", "status": "application"}) == "nl"

    def test_record_with_out_of_band_value_reads_as_nl(self):
        # An unsupported stored value re-normalizes to nl on read.
        assert locale_of_record({"locale": "zz"}) == "nl"
        assert locale_of_record({"locale": None}) == "nl"

    def test_none_record_reads_as_nl(self):
        assert locale_of_record(None) == "nl"
        assert locale_of_record("not-a-record") == "nl"
