"""
Unit tests for reference account index and prediction functions.

Validates Requirements:
- 1.1–1.5: Reference-to-Account Lookup Structure
- 2.2–2.4: Sequential Prediction Flow (reference lookup step)
- 4.1–4.5: Confidence Scoring for Reference Lookup
- 6.1–6.4: Compound Verb Handling in Reference Lookup
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pattern_scoring import (
    build_reference_account_index,
    predict_account_from_reference,
    CONFIDENCE_THRESHOLD_CONFIDENT,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def make_pattern(
    admin="TestAdmin",
    bank="1300",
    verb="KPN",
    ref="KPN",
    debet="4600",
    credit="1300",
    occurrences=5,
    confidence=0.95,
    last_seen="2024-06-01",
    ambiguous=False,
):
    """Create a pattern dict matching the verb pattern structure."""
    p = {
        "administration": admin,
        "bank_account": bank,
        "verb": verb,
        "reference_number": ref,
        "debet_account": debet,
        "credit_account": credit,
        "occurrences": occurrences,
        "confidence": confidence,
        "last_seen": last_seen,
    }
    if ambiguous:
        p["_ambiguous"] = True
    return p


# ══════════════════════════════════════════════════════════════════════════════
# Tests for build_reference_account_index()
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildReferenceAccountIndex:
    """Tests for building the reference-code-keyed index from verb patterns."""

    def test_single_pattern_creates_correct_index_entry(self):
        """Single pattern with valid ref creates correct index entry."""
        patterns = {
            "TestAdmin_1300_KPN": make_pattern()
        }

        result = build_reference_account_index(patterns)

        assert "TestAdmin_1300_KPN" in result
        entry = result["TestAdmin_1300_KPN"]
        assert entry["counter_account"] == "4600"
        assert entry["occurrences"] == 5
        assert entry["confidence"] == 0.95
        assert entry["last_seen"] == "2024-06-01"
        assert entry["source_verb"] == "KPN"

    def test_multiple_verbs_same_ref_keeps_highest_occurrences(self):
        """When multiple verbs share the same reference, keep highest occurrences."""
        patterns = {
            "TestAdmin_1300_KPN-Mobile": make_pattern(
                verb="KPN-Mobile", ref="KPN", occurrences=3, confidence=0.90
            ),
            "TestAdmin_1300_KPN-Internet": make_pattern(
                verb="KPN-Internet", ref="KPN", occurrences=8, confidence=0.92
            ),
        }

        result = build_reference_account_index(patterns)

        assert "TestAdmin_1300_KPN" in result
        entry = result["TestAdmin_1300_KPN"]
        # Should keep the one with 8 occurrences
        assert entry["occurrences"] == 8
        assert entry["source_verb"] == "KPN-Internet"
        assert entry["confidence"] == 0.92

    def test_ambiguous_pattern_is_skipped(self):
        """Patterns marked as _ambiguous=True are skipped."""
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(ambiguous=True)
        }

        result = build_reference_account_index(patterns)

        assert len(result) == 0

    def test_empty_reference_is_skipped(self):
        """Patterns with empty reference_number are skipped."""
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(ref="")
        }

        result = build_reference_account_index(patterns)

        assert len(result) == 0

    def test_whitespace_only_reference_is_skipped(self):
        """Patterns with whitespace-only reference_number are skipped."""
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(ref="   ")
        }

        result = build_reference_account_index(patterns)

        assert len(result) == 0

    def test_zero_confidence_is_skipped(self):
        """Patterns with confidence <= 0 are skipped."""
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(confidence=0)
        }

        result = build_reference_account_index(patterns)

        assert len(result) == 0

    def test_negative_confidence_is_skipped(self):
        """Patterns with negative confidence are skipped."""
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(confidence=-0.5)
        }

        result = build_reference_account_index(patterns)

        assert len(result) == 0

    def test_bank_account_equals_debet_derives_credit_as_counter(self):
        """When bank_account == debet_account, counter_account is credit_account."""
        # bank_account "1300" == debet_account "1300" → counter = credit "4600"
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(
                bank="1300", debet="1300", credit="4600"
            )
        }

        result = build_reference_account_index(patterns)

        entry = result["TestAdmin_1300_KPN"]
        assert entry["counter_account"] == "4600"

    def test_bank_account_equals_credit_derives_debet_as_counter(self):
        """When bank_account == credit_account, counter_account is debet_account."""
        # bank_account "1300" == credit_account "1300" → counter = debet "4600"
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(
                bank="1300", debet="4600", credit="1300"
            )
        }

        result = build_reference_account_index(patterns)

        entry = result["TestAdmin_1300_KPN"]
        assert entry["counter_account"] == "4600"

    def test_bank_account_matches_neither_debet_nor_credit_is_skipped(self):
        """When bank_account matches neither debet nor credit, pattern is skipped."""
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(
                bank="1300", debet="4600", credit="8000"
            )
        }

        result = build_reference_account_index(patterns)

        assert len(result) == 0

    def test_empty_other_account_is_skipped(self):
        """When the derived counter_account is empty, pattern is skipped."""
        # bank_account "1300" == debet "1300" → credit is "" → skip
        patterns = {
            "TestAdmin_1300_KPN": make_pattern(
                bank="1300", debet="1300", credit=""
            )
        }

        result = build_reference_account_index(patterns)

        assert len(result) == 0

    def test_empty_patterns_dict_returns_empty_index(self):
        """Empty input returns empty index."""
        result = build_reference_account_index({})

        assert result == {}


# ══════════════════════════════════════════════════════════════════════════════
# Tests for predict_account_from_reference()
# ══════════════════════════════════════════════════════════════════════════════


class TestPredictAccountFromReference:
    """Tests for predicting counter-account using reference code lookup."""

    @pytest.fixture
    def sample_index(self):
        """A reference account index with a few entries."""
        return {
            "TestAdmin_1300_KPN": {
                "counter_account": "4600",
                "occurrences": 10,
                "confidence": 0.95,
                "last_seen": "2024-06-01",
                "source_verb": "KPN",
            },
            "TestAdmin_1300_Picnic": {
                "counter_account": "4100",
                "occurrences": 7,
                "confidence": 0.80,
                "last_seen": "2024-05-15",
                "source_verb": "Picnic",
            },
            "TestAdmin_1300_ASR|Zorgverzekering": {
                "counter_account": "4700",
                "occurrences": 4,
                "confidence": 0.90,
                "last_seen": "2024-04-01",
                "source_verb": "ASR|Zorgverzekering",
            },
        }

    def test_match_found_returns_correct_dict(self, sample_index):
        """When a match exists, returns dict with prediction details."""
        result = predict_account_from_reference(
            reference_code="KPN",
            reference_confidence=0.95,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result is not None
        assert result["value"] == "4600"
        assert result["reference_code"] == "KPN"
        assert result["method"] == "reference_lookup"
        assert result["lookup_confidence"] == 0.95

    def test_no_match_returns_none(self, sample_index):
        """When no match exists in the index, returns None."""
        result = predict_account_from_reference(
            reference_code="Unknown",
            reference_confidence=0.95,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result is None

    def test_empty_reference_code_returns_none(self, sample_index):
        """Empty reference_code returns None."""
        result = predict_account_from_reference(
            reference_code="",
            reference_confidence=1.0,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result is None

    def test_whitespace_only_reference_code_returns_none(self, sample_index):
        """Whitespace-only reference_code returns None."""
        result = predict_account_from_reference(
            reference_code="   ",
            reference_confidence=1.0,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result is None

    def test_none_reference_code_returns_none(self, sample_index):
        """None reference_code returns None."""
        result = predict_account_from_reference(
            reference_code=None,
            reference_confidence=1.0,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result is None

    def test_combined_confidence_above_threshold_not_uncertain(self, sample_index):
        """Combined confidence 0.9 × 0.95 = 0.855 → uncertain=False."""
        result = predict_account_from_reference(
            reference_code="KPN",
            reference_confidence=0.9,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        expected_combined = 0.9 * 0.95  # 0.855
        assert result["confidence"] == pytest.approx(expected_combined)
        assert result["uncertain"] is False

    def test_combined_confidence_below_threshold_is_uncertain(self, sample_index):
        """Combined confidence 0.7 × 0.80 = 0.56 → uncertain=True."""
        result = predict_account_from_reference(
            reference_code="Picnic",
            reference_confidence=0.7,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        expected_combined = 0.7 * 0.80  # 0.56
        assert result["confidence"] == pytest.approx(expected_combined)
        assert result["uncertain"] is True

    def test_compound_verb_used_as_full_key(self, sample_index):
        """Compound verb 'ASR|Zorgverzekering' used as full lookup key (no splitting)."""
        result = predict_account_from_reference(
            reference_code="ASR|Zorgverzekering",
            reference_confidence=1.0,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result is not None
        assert result["value"] == "4700"
        assert result["reference_code"] == "ASR|Zorgverzekering"

    def test_compound_verb_company_only_does_not_match(self, sample_index):
        """Company-only part of compound verb does NOT match (no fallback)."""
        result = predict_account_from_reference(
            reference_code="ASR",
            reference_confidence=1.0,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result is None

    def test_reference_confidence_one_combined_equals_lookup(self, sample_index):
        """When reference_confidence = 1.0 (pre-populated), combined = lookup_confidence."""
        result = predict_account_from_reference(
            reference_code="KPN",
            reference_confidence=1.0,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result["confidence"] == 0.95  # 1.0 × 0.95
        assert result["lookup_confidence"] == 0.95

    def test_method_always_reference_lookup(self, sample_index):
        """Method field is always 'reference_lookup'."""
        result = predict_account_from_reference(
            reference_code="KPN",
            reference_confidence=0.85,
            bank_account="1300",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result["method"] == "reference_lookup"

    def test_confidence_threshold_constant_is_080(self):
        """The CONFIDENCE_THRESHOLD_CONFIDENT constant is 0.80."""
        assert CONFIDENCE_THRESHOLD_CONFIDENT == 0.80

    def test_different_administration_no_match(self, sample_index):
        """Patterns for one admin don't leak to another (tenant isolation)."""
        result = predict_account_from_reference(
            reference_code="KPN",
            reference_confidence=1.0,
            bank_account="1300",
            administration="OtherAdmin",
            reference_account_index=sample_index,
        )

        assert result is None

    def test_different_bank_account_no_match(self, sample_index):
        """Patterns for one bank account don't match a different bank account."""
        result = predict_account_from_reference(
            reference_code="KPN",
            reference_confidence=1.0,
            bank_account="1100",
            administration="TestAdmin",
            reference_account_index=sample_index,
        )

        assert result is None
