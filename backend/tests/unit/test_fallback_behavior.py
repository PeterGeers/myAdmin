"""
Integration test: fallback behavior in apply_patterns_to_transactions().

Tests two key fallback scenarios:
1. Reference lookup has no match → verb-matching produces the same result
2. No prediction methods succeed → counter-account field left empty

Validates Requirements: 3.1, 3.2, 3.4, 3.5
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pattern_analyzer import PatternAnalyzer


# ── Helpers ────────────────────────────────────────────────────────────────


def make_pattern(verb, debet="4600", credit="1300", confidence=0.95,
                 occurrences=10, ref=None, admin="TestAdmin", bank="1300"):
    """Create a verb pattern dict. ref defaults to verb if not specified."""
    return {
        "administration": admin,
        "bank_account": bank,
        "verb": verb,
        "verb_company": verb,
        "verb_reference": None,
        "is_compound": False,
        "reference_number": ref or verb,
        "debet_account": debet,
        "credit_account": credit,
        "occurrences": occurrences,
        "confidence": confidence,
        "last_seen": "2024-06-01",
        "sample_description": f"{verb} payment",
    }


def create_analyzer(patterns, known_verbs, bank_account="1300", admin="TestAdmin"):
    """Create a PatternAnalyzer with mocked dependencies (no DB)."""
    analyzer = PatternAnalyzer.__new__(PatternAnalyzer)
    analyzer.is_bank_account = lambda acc, adm: acc == bank_account and adm == admin

    def mock_extract_verb(description, reference_number):
        desc_lower = description.lower()
        for verb in known_verbs:
            if verb.lower() in desc_lower:
                return verb
        return None

    analyzer._extract_verb_from_description = mock_extract_verb
    analyzer.get_filtered_patterns = lambda adm: {
        "reference_patterns": patterns,
        "debet_patterns": {},
        "credit_patterns": {},
    }
    return analyzer


def make_tx(description, credit="1300", debet="", ref="", admin="TestAdmin"):
    """Create a transaction dict."""
    return {
        "TransactionDescription": description,
        "Debet": debet,
        "Credit": credit,
        "ReferenceNumber": ref,
        "administration": admin,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Test: Reference lookup has no match → verb-matching fallback
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFallbackToVerbMatching:
    """
    When reference_lookup returns None, the engine falls back to verb-matching
    and produces the same result as before Phase 1.

    Validates Requirements: 3.1, 3.2
    """

    def test_low_confidence_ref_skips_lookup_uses_verb_matching(self):
        """
        Pattern confidence 0.75 < 0.80 threshold → step 2 skipped → verb-matching.
        """
        patterns = {"TestAdmin_1300_LowRefVendor": make_pattern(
            "LowRefVendor", debet="4300", confidence=0.75, occurrences=4
        )}
        analyzer = create_analyzer(patterns, ["LowRefVendor"])
        transactions = [make_tx("LowRefVendor monthly subscription")]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        tx = updated[0]
        assert tx["Debet"] == "4300"
        assert tx["_prediction_method"] == "verb_matching"
        assert results["prediction_methods"]["verb_matching"] >= 1
        assert results["prediction_methods"]["reference_lookup"] == 0

    def test_ref_predicted_but_not_in_index_falls_back_to_verb_matching(self):
        """
        Pre-populated ReferenceNumber not in index → reference_lookup returns None
        → falls back to verb-matching.

        - Pre-populated ref = "NONEXISTENT-REF" (confidence 1.0 >= 0.80)
        - reference_lookup("NONEXISTENT-REF") → None
        - predict_debet finds GapVendor → Debet = "4400"
        """
        patterns = {"TestAdmin_1300_GapVendor": make_pattern(
            "GapVendor", debet="4400", confidence=0.90, occurrences=6
        )}
        analyzer = create_analyzer(patterns, ["GapVendor"])
        transactions = [make_tx("GapVendor quarterly payment", ref="NONEXISTENT-REF")]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        tx = updated[0]
        assert tx["Debet"] == "4400"
        assert tx["_prediction_method"] == "verb_matching"
        assert tx["ReferenceNumber"] == "NONEXISTENT-REF"
        assert results["prediction_methods"]["verb_matching"] >= 1
        assert results["prediction_methods"]["reference_lookup"] == 0

    def test_verb_matching_result_identical_to_direct_prediction(self):
        """
        Verb-matching fallback produces the SAME counter-account as before Phase 1.
        Validates Requirement: 3.4
        """
        patterns = {"TestAdmin_1300_Ziggo": make_pattern(
            "Ziggo", debet="4610", confidence=0.75, occurrences=12
        )}
        analyzer = create_analyzer(patterns, ["Ziggo"])
        transactions = [make_tx("Ziggo maandelijks abonnement")]

        updated, _ = analyzer.apply_patterns_to_transactions(transactions, "TestAdmin")

        tx = updated[0]
        assert tx["Debet"] == "4610"
        assert tx["_prediction_method"] == "verb_matching"
        assert tx["_uncertain"] is True  # 0.75 < 0.80

    def test_credit_side_verb_matching_fallback(self):
        """
        Fallback works for credit-side predictions (debet is bank account).
        """
        patterns = {"TestAdmin_1300_CustomerA": make_pattern(
            "CustomerA", debet="1300", credit="1400", confidence=0.75, occurrences=9
        )}
        analyzer = create_analyzer(patterns, ["CustomerA"])
        transactions = [make_tx("CustomerA invoice payment", debet="1300", credit="")]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        tx = updated[0]
        assert tx["Credit"] == "1400"
        assert tx["_prediction_method"] == "verb_matching"
        assert results["prediction_methods"]["verb_matching"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Test: No prediction methods succeed → field left empty
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestNoPredictionFieldLeftEmpty:
    """
    When BOTH reference_lookup AND verb-matching fail, the counter-account
    field remains empty and failed_predictions is incremented.

    Validates Requirement: 3.5
    """

    def test_unknown_description_leaves_field_empty(self):
        """Description doesn't match any verb → no prediction, field stays empty."""
        patterns = {"TestAdmin_1300_Ziggo": make_pattern("Ziggo")}
        analyzer = create_analyzer(patterns, ["Ziggo"])
        transactions = [make_tx("Completely unknown merchant ABC")]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        tx = updated[0]
        assert tx["Debet"] == ""
        assert "_prediction_method" not in tx
        assert results["failed_predictions"] == 1

    def test_empty_description_leaves_field_empty(self):
        """Empty description → no prediction possible."""
        patterns = {"TestAdmin_1300_Vendor": make_pattern("Vendor", debet="4500")}
        analyzer = create_analyzer(patterns, ["Vendor"])
        transactions = [make_tx("")]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        tx = updated[0]
        assert tx["Debet"] == ""
        assert "_prediction_method" not in tx
        assert results["failed_predictions"] == 1

    def test_no_bank_account_identified_leaves_field_empty(self):
        """Neither Debet nor Credit is a bank account → no prediction possible."""
        patterns = {"TestAdmin_1300_SomeVendor": make_pattern("SomeVendor", debet="4500")}
        analyzer = create_analyzer(patterns, ["SomeVendor"])
        # Neither 4100 nor 4200 is bank account "1300"
        transactions = [make_tx("SomeVendor payment", debet="4100", credit="4200")]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        tx = updated[0]
        assert "_prediction_method" not in tx
        assert results["failed_predictions"] == 1

    def test_failed_predictions_counter_increments_per_unpredicted_tx(self):
        """Each unpredicted transaction increments failed_predictions."""
        patterns = {"TestAdmin_1300_Ziggo": make_pattern("Ziggo")}
        analyzer = create_analyzer(patterns, ["Ziggo"])

        transactions = [
            make_tx("Random merchant X"),
            make_tx("Another merchant Y"),
            make_tx("Ziggo maandelijks abonnement"),
        ]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        assert results["failed_predictions"] == 2
        assert updated[2]["Debet"] == "4600"

    def test_prediction_method_not_set_when_no_prediction(self):
        """No metadata fields set when no prediction is made."""
        analyzer = create_analyzer({}, [])
        transactions = [make_tx("Random payment")]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        tx = updated[0]
        assert "_prediction_method" not in tx
        assert "_uncertain" not in tx
        assert "_debet_confidence" not in tx
        assert "_credit_confidence" not in tx
        assert results["failed_predictions"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# Test: Batch prediction success rate integrity
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestPredictionSuccessRateIntegrity:
    """
    Verify predictions via verb-matching produce identical results to what
    they would have produced before Phase 1.

    Validates Requirement: 3.4 (prediction success rate ≥ 92% on patterned txs)
    """

    def test_batch_success_rate_above_threshold(self):
        """9 of 10 transactions have matching patterns → success rate ≥ 90%."""
        patterns = {}
        known_verbs = []

        for i in range(1, 10):
            vendor = f"Vendor{i}"
            patterns[f"TestAdmin_1300_{vendor}"] = make_pattern(
                vendor, debet=f"4{i:03d}", confidence=0.85, occurrences=10 + i
            )
            known_verbs.append(vendor)

        analyzer = create_analyzer(patterns, known_verbs)

        transactions = [make_tx(f"Vendor{i} monthly charge") for i in range(1, 10)]
        transactions.append(make_tx("Unknown random merchant"))

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        total = results["total_transactions"]
        successful = total - results["failed_predictions"]
        success_rate = successful / total

        assert success_rate >= 0.90
        assert results["failed_predictions"] == 1

        for i in range(9):
            assert updated[i]["Debet"] == f"4{i+1:03d}"
            assert updated[i]["_prediction_method"] in ("verb_matching", "reference_lookup")

    def test_verb_matching_results_are_deterministic(self):
        """Running the same transactions twice produces identical results."""
        patterns = {"TestAdmin_1300_Stable": make_pattern(
            "Stable", debet="4200", confidence=0.75, occurrences=15
        )}
        analyzer = create_analyzer(patterns, ["Stable"])
        transactions = [make_tx("Stable recurring payment")]

        updated1, results1 = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )
        updated2, results2 = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        assert updated1[0]["Debet"] == updated2[0]["Debet"]
        assert updated1[0]["_prediction_method"] == updated2[0]["_prediction_method"]
        assert results1["failed_predictions"] == results2["failed_predictions"]
