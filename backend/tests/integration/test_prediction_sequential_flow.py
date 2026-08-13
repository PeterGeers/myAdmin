"""
Integration tests for the full sequential prediction flow.

Tests the orchestration in apply_patterns_to_transactions():
  Step 1: predict_reference (extract verb → find matching pattern → predict ReferenceNumber)
  Step 2: predict_account_from_reference (use reference as lookup key for counter-account)
  Step 3: fallback to predict_debet/predict_credit (existing verb matching)

Validates Requirements: 2.1–2.7, 3.1–3.5, 4.4
"""

import sys
import os

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pattern_analyzer import PatternAnalyzer
from pattern_scoring import CONFIDENCE_THRESHOLD_CONFIDENT


# ── Helpers ────────────────────────────────────────────────────────────────


def make_pattern(
    admin="TestAdmin",
    bank="1300",
    verb="KPN",
    ref="KPN",
    debet="4600",
    credit="1300",
    occurrences=12,
    confidence=0.95,
    last_seen="2024-06-01",
    is_compound=False,
    verb_company=None,
    ambiguous=False,
):
    """Create a verb pattern dict matching the expected structure."""
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
        "is_compound": is_compound,
        "verb_company": verb_company or verb,
        "_ambiguous": ambiguous,
    }
    return p


def make_transaction(
    description="",
    debet="",
    credit="",
    reference_number="",
    administration="TestAdmin",
    amount=100.0,
):
    """Create a transaction dict matching the expected format."""
    return {
        "TransactionDescription": description,
        "Debet": debet,
        "Credit": credit,
        "ReferenceNumber": reference_number,
        "administration": administration,
        "TransactionAmount": amount,
        "TransactionDate": "2024-06-15",
        "Ref1": "",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Integration Tests: Full Sequential Prediction Flow
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestSequentialPredictionFlow:
    """
    Integration tests for the full sequential prediction flow via
    apply_patterns_to_transactions().

    Mocks only the data-access layer (get_filtered_patterns, is_bank_account,
    get_bank_accounts, DB, cache) but lets the real prediction logic run.
    """

    @pytest.fixture
    def pattern_data(self):
        """Standard test patterns for the happy path scenarios."""
        return {
            # KPN: high confidence, clear reference → reference lookup will work
            "TestAdmin_1300_KPN": make_pattern(
                verb="KPN",
                ref="KPN",
                debet="4600",
                credit="1300",
                confidence=0.95,
                occurrences=12,
            ),
            # NEWCO: has debet_account for verb matching, but NO reference_number
            # so reference lookup will fail → verb matching fallback
            "TestAdmin_1300_NEWCO": make_pattern(
                verb="NEWCO",
                ref="",
                debet="4200",
                credit="1300",
                confidence=0.90,
                occurrences=8,
            ),
            # LOWCONF: low confidence pattern for uncertain prediction testing
            "TestAdmin_1300_LOWCONF": make_pattern(
                verb="LOWCONF",
                ref="LOWCONF",
                debet="4800",
                credit="1300",
                confidence=0.70,
                occurrences=3,
            ),
            # NOACCOUNT: pattern with no counter-account (both empty)
            "TestAdmin_1300_GHOST": make_pattern(
                verb="GHOST",
                ref="GHOST",
                debet="",
                credit="1300",
                confidence=0.85,
                occurrences=5,
            ),
        }

    @pytest.fixture
    def analyzer(self, pattern_data):
        """Create a PatternAnalyzer with mocked DB/cache and controlled patterns."""
        with patch("pattern_analyzer.DatabaseManager") as mock_db_cls, \
             patch("pattern_analyzer.get_pattern_cache") as mock_cache_fn:

            mock_db = MagicMock()
            mock_db_cls.return_value = mock_db
            mock_cache_fn.return_value = MagicMock()

            analyzer = PatternAnalyzer(test_mode=True)

            # Mock get_filtered_patterns to return our test data
            def mock_get_filtered_patterns(administration, **kwargs):
                return {
                    "reference_patterns": pattern_data,
                    "debet_patterns": {},
                    "credit_patterns": {},
                    "total_transactions": 100,
                    "patterns_discovered": len(pattern_data),
                    "statistics": {},
                    "analysis_date": "2024-06-15",
                    "date_range": {"from": "2023-06-15", "to": "2024-06-15"},
                }

            analyzer.get_filtered_patterns = mock_get_filtered_patterns

            # Mock is_bank_account: only "1300" is a bank account for TestAdmin
            def mock_is_bank_account(account_number, administration):
                if not account_number:
                    return False
                return account_number == "1300" and administration == "TestAdmin"

            analyzer.is_bank_account = mock_is_bank_account

            # Mock get_bank_accounts
            analyzer.get_bank_accounts = lambda: {
                "testadmin_1300": {
                    "iban": "NL00RABO0000001300",
                    "account": "1300",
                    "administration": "TestAdmin",
                }
            }

            yield analyzer

    # ─── Scenario 1: Reference lookup succeeds (happy path) ───

    def test_reference_lookup_succeeds_happy_path(self, analyzer):
        """
        When description mentions 'KPN' and Credit='1300' (bank):
        - Step 1 predicts ReferenceNumber='KPN' (verb extraction finds 'KPN')
        - Step 2 uses 'KPN' as lookup key → finds counter-account '4600'
        - _prediction_method = 'reference_lookup', _uncertain = False

        Validates: Requirements 2.1, 2.2, 2.3, 2.4, 3.1, 3.2
        """
        transactions = [
            make_transaction(
                description="KPN BV INTERNET BETALING",
                credit="1300",
                debet="",
                reference_number="",
            )
        ]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        assert len(updated) == 1
        tx = updated[0]

        # Reference was predicted
        assert tx["ReferenceNumber"] == "KPN"
        # Counter-account was predicted via reference lookup
        assert tx["Debet"] == "4600"
        # Method metadata
        assert tx["_prediction_method"] == "reference_lookup"
        assert tx["_uncertain"] is False
        # Results tracking
        assert results["prediction_methods"]["reference_lookup"] >= 1

    # ─── Scenario 2: Reference lookup fails, verb matching succeeds ───

    def test_verb_matching_fallback_when_reference_lookup_fails(self, analyzer):
        """
        When description mentions 'NEWCO' and Credit='1300' (bank):
        - Step 1 predicts ReferenceNumber → fails (pattern has empty ref)
          OR predicts ref but no index entry exists (empty ref → not in index)
        - Step 2 skipped (no reference available or lookup returns None)
        - Step 3 verb matching finds 'NEWCO' pattern → Debet='4200'
        - _prediction_method = 'verb_matching'

        Validates: Requirements 2.5, 3.1, 3.2, 3.3
        """
        transactions = [
            make_transaction(
                description="NEWCO SERVICES BETALING",
                credit="1300",
                debet="",
                reference_number="",
            )
        ]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        assert len(updated) == 1
        tx = updated[0]

        # Counter-account predicted via verb matching
        assert tx["Debet"] == "4200"
        assert tx["_prediction_method"] == "verb_matching"
        # Results tracking
        assert results["prediction_methods"]["verb_matching"] >= 1

    # ─── Scenario 3: Uncertain prediction (combined confidence < 0.80) ───

    def test_uncertain_flag_when_low_confidence(self, analyzer):
        """
        When reference lookup has combined confidence < 0.80:
        - Pattern 'LOWCONF' has confidence=0.70
        - Even if reference_confidence = 0.95, combined = 0.95 × 0.70 = 0.665 < 0.80
        - _uncertain = True

        Validates: Requirements 4.4
        """
        transactions = [
            make_transaction(
                description="LOWCONF DIENSTEN MAANDELIJKS",
                credit="1300",
                debet="",
                reference_number="",
            )
        ]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        assert len(updated) == 1
        tx = updated[0]

        # If reference lookup worked (ref='LOWCONF' found in index with conf 0.70)
        # Combined confidence will be < 0.80 → uncertain
        if tx.get("_prediction_method") == "reference_lookup":
            assert tx["_uncertain"] is True
            assert tx["Debet"] == "4800"
        elif tx.get("_prediction_method") == "verb_matching":
            # If verb matching took over (because ref confidence was too low for step 2)
            # verb matching confidence is also 0.70 < 0.80
            assert tx["_uncertain"] is True

    # ─── Scenario 4: Pre-populated ReferenceNumber (Task 3.2) ───

    def test_pre_populated_reference_skips_prediction(self, analyzer):
        """
        When ReferenceNumber is already set:
        - Skip step 1 (predict_reference)
        - Use it directly with confidence=1.0 for reference lookup
        - Combined confidence = 1.0 × 0.95 = 0.95 → _uncertain = False
        - _prediction_method = 'reference_lookup'

        Validates: Requirements 2.6
        """
        transactions = [
            make_transaction(
                description="Some random description that doesn't matter",
                credit="1300",
                debet="",
                reference_number="KPN",  # Already populated!
            )
        ]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        assert len(updated) == 1
        tx = updated[0]

        # Reference was NOT re-predicted (already had value)
        assert tx["ReferenceNumber"] == "KPN"
        assert results["predictions_made"]["reference"] == 0
        # Counter-account predicted via reference lookup with confidence 1.0
        assert tx["Debet"] == "4600"
        assert tx["_prediction_method"] == "reference_lookup"
        assert tx["_uncertain"] is False

    # ─── Scenario 5: Both reference lookup and verb matching fail ───

    def test_no_prediction_when_no_patterns_match(self, analyzer):
        """
        When no patterns match at all:
        - Description doesn't extract to any known verb
        - No prediction made, fields remain empty

        Validates: Requirements 3.4, 3.5
        """
        transactions = [
            make_transaction(
                description="12345 67890 UNKNOWN TRANSACTION CODE XYZ123ABC",
                credit="1300",
                debet="",
                reference_number="",
            )
        ]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        assert len(updated) == 1
        tx = updated[0]

        # Nothing predicted - fields remain empty
        assert tx["Debet"] == ""
        assert tx["ReferenceNumber"] == ""
        assert "_prediction_method" not in tx

    # ─── Scenario: Sequential flow order verification ───

    def test_sequential_flow_order_reference_before_account(self, analyzer):
        """
        Verify that reference is predicted FIRST, then used as lookup key.
        The transaction starts with no ReferenceNumber, and both ref + account
        end up predicted.

        Validates: Requirements 2.1, 2.2, 2.7, 3.1
        """
        transactions = [
            make_transaction(
                description="KPN TELECOM FACTUUR MAANDELIJKS",
                credit="1300",
                debet="",
                reference_number="",
            )
        ]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        tx = updated[0]

        # Both reference and account were predicted
        assert tx["ReferenceNumber"] == "KPN"
        assert tx["Debet"] == "4600"
        # Reference was predicted (not pre-populated)
        assert results["predictions_made"]["reference"] >= 1
        # Account came from reference lookup (not verb matching)
        assert tx["_prediction_method"] == "reference_lookup"

    # ─── Scenario: Results aggregation ───

    def test_results_track_prediction_methods(self, analyzer):
        """
        Results dict tracks counts per prediction method.

        Validates: Requirements 3.3, 7.1
        """
        transactions = [
            # This one should use reference_lookup
            make_transaction(
                description="KPN BV INTERNET",
                credit="1300",
                debet="",
                reference_number="",
            ),
            # This one should use verb_matching (NEWCO has no ref)
            make_transaction(
                description="NEWCO SERVICES BETALING",
                credit="1300",
                debet="",
                reference_number="",
            ),
        ]

        updated, results = analyzer.apply_patterns_to_transactions(
            transactions, "TestAdmin"
        )

        # Both should have predictions
        total_predictions = (
            results["prediction_methods"]["reference_lookup"]
            + results["prediction_methods"]["verb_matching"]
        )
        assert total_predictions >= 2

    # ─── Scenario: Confidence threshold constant ───

    def test_confidence_threshold_is_080(self):
        """
        The CONFIDENCE_THRESHOLD_CONFIDENT constant is 0.80.

        Validates: Requirements 4.4
        """
        assert CONFIDENCE_THRESHOLD_CONFIDENT == 0.80
