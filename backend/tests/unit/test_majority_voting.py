"""
Unit tests for majority voting in analyze_reference_patterns().

Tests verify that the majority voting algorithm correctly classifies patterns:
- ≥ 90% agreement → pattern stored with confidence = majority_ratio, _ambiguous = False
- < 90% agreement → pattern marked _ambiguous = True, confidence = 0.0
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from pattern_detection import analyze_reference_patterns


def _make_transaction(debet: str, credit: str, description: str = "AIRBNB BETALING", date: str = "2025-01-15"):
    """Helper to create a transaction dict with required fields."""
    return {
        "Debet": debet,
        "Credit": credit,
        "TransactionDescription": description,
        "ReferenceNumber": f"Rabo {date}",
        "TransactionDate": date,
    }


def _is_bank_account(account, administration):
    """Mock bank account check — only '1002' is a bank account."""
    return account == "1002"


class TestMajorityVoting95Percent:
    """Task 9.4: 95% agreement → pattern stored with confidence=0.95, _ambiguous=False"""

    def test_95_percent_agreement_stores_pattern(self):
        """19 out of 20 transactions have the same accounts → confidence ≈ 0.95"""
        transactions = []

        # 19 transactions with (debet=1002, credit=1600)
        for i in range(19):
            transactions.append(_make_transaction("1002", "1600"))

        # 1 transaction with (debet=1002, credit=8003)
        transactions.append(_make_transaction("1002", "8003"))

        result = analyze_reference_patterns(transactions, "TestAdmin", _is_bank_account)

        company_key = "TestAdmin_1002_AIRBNB"
        assert company_key in result, f"Expected key '{company_key}' in result. Keys: {list(result.keys())}"

        pattern = result[company_key]
        assert pattern["_ambiguous"] is False
        assert abs(pattern["confidence"] - 0.95) < 0.01, f"Expected confidence ≈ 0.95, got {pattern['confidence']}"
        assert pattern["debet_account"] == "1002"
        assert pattern["credit_account"] == "1600"


class TestMajorityVoting5050Split:
    """Task 9.5: 50/50 split → pattern marked _ambiguous=True"""

    def test_50_50_split_marks_ambiguous(self):
        """5 vs 5 transactions → no majority → _ambiguous=True"""
        transactions = []

        # 5 transactions with (debet=1002, credit=1600)
        for i in range(5):
            transactions.append(_make_transaction("1002", "1600"))

        # 5 transactions with (debet=1002, credit=8003)
        for i in range(5):
            transactions.append(_make_transaction("1002", "8003"))

        result = analyze_reference_patterns(transactions, "TestAdmin", _is_bank_account)

        company_key = "TestAdmin_1002_AIRBNB"
        assert company_key in result, f"Expected key '{company_key}' in result. Keys: {list(result.keys())}"

        pattern = result[company_key]
        assert pattern["_ambiguous"] is True
        assert pattern["confidence"] == 0.0


class TestMajorityVotingExactly90Percent:
    """Task 9.6: exactly 90% boundary → pattern stored"""

    def test_exactly_90_percent_meets_threshold(self):
        """9 out of 10 transactions → majority_ratio = 0.90 → meets threshold"""
        transactions = []

        # 9 transactions with (debet=1002, credit=1600)
        for i in range(9):
            transactions.append(_make_transaction("1002", "1600"))

        # 1 transaction with (debet=1002, credit=8003)
        transactions.append(_make_transaction("1002", "8003"))

        result = analyze_reference_patterns(transactions, "TestAdmin", _is_bank_account)

        company_key = "TestAdmin_1002_AIRBNB"
        assert company_key in result, f"Expected key '{company_key}' in result. Keys: {list(result.keys())}"

        pattern = result[company_key]
        assert pattern["_ambiguous"] is False
        assert abs(pattern["confidence"] - 0.9) < 0.01, f"Expected confidence = 0.9, got {pattern['confidence']}"
        assert pattern["debet_account"] == "1002"
        assert pattern["credit_account"] == "1600"


class TestMajorityVoting89Percent:
    """Task 9.7: 89% → pattern marked ambiguous"""

    def test_89_percent_below_threshold_marks_ambiguous(self):
        """89 out of 100 transactions → majority_ratio = 0.89 < 0.90 → ambiguous"""
        transactions = []

        # 89 transactions with (debet=1002, credit=1600)
        for i in range(89):
            transactions.append(_make_transaction("1002", "1600"))

        # 11 transactions with (debet=1002, credit=8003)
        for i in range(11):
            transactions.append(_make_transaction("1002", "8003"))

        result = analyze_reference_patterns(transactions, "TestAdmin", _is_bank_account)

        company_key = "TestAdmin_1002_AIRBNB"
        assert company_key in result, f"Expected key '{company_key}' in result. Keys: {list(result.keys())}"

        pattern = result[company_key]
        assert pattern["_ambiguous"] is True
        assert pattern["confidence"] == 0.0


class TestCompoundVerbsRegressionConfidence:
    """Task 9.8: Compound verbs (e.g., BOOKING|5620035) still produce individual patterns with confidence 1.0"""

    def test_compound_verbs_produce_individual_patterns_with_confidence_1(self):
        """Each unique compound verb gets its own pattern entry with confidence = 1.0.

        Descriptions like "Booking.com 5620035 Betaling" produce compound verb "BOOKING|5620035".
        Three different reference numbers produce three separate compound key entries.
        """
        transactions = [
            _make_transaction("1002", "4100", "Booking.com 5620035 Betaling", "2025-01-10"),
            _make_transaction("1002", "4100", "Booking.com 7831042 Betaling", "2025-01-12"),
            _make_transaction("1002", "4100", "Booking.com 9912756 Betaling", "2025-01-14"),
        ]

        result = analyze_reference_patterns(transactions, "TestAdmin", _is_bank_account)

        # Each compound verb should produce its own key
        key1 = "TestAdmin_1002_BOOKING|5620035"
        key2 = "TestAdmin_1002_BOOKING|7831042"
        key3 = "TestAdmin_1002_BOOKING|9912756"

        for key in [key1, key2, key3]:
            assert key in result, f"Expected compound key '{key}' in result. Keys: {list(result.keys())}"
            pattern = result[key]
            assert pattern["confidence"] == 1.0, f"Expected confidence 1.0 for compound key '{key}', got {pattern['confidence']}"
            assert pattern["is_compound"] is True, f"Expected is_compound=True for '{key}'"

    def test_compound_verbs_with_mixed_accounts_still_confidence_1(self):
        """Compound verbs are stored directly, bypassing majority voting — each keeps confidence 1.0."""
        transactions = [
            _make_transaction("1002", "4100", "Booking.com 5620035 Betaling", "2025-01-10"),
            _make_transaction("1002", "4200", "Booking.com 5620035 Betaling", "2025-01-12"),
        ]

        result = analyze_reference_patterns(transactions, "TestAdmin", _is_bank_account)

        key = "TestAdmin_1002_BOOKING|5620035"
        assert key in result, f"Expected compound key '{key}' in result. Keys: {list(result.keys())}"
        # The compound key always stores the LAST seen accounts with confidence 1.0
        assert result[key]["confidence"] == 1.0


class TestZeroConflictSimpleVerbConfidence:
    """Task 9.9: Zero-conflict simple verbs still get confidence 1.0"""

    def test_all_transactions_same_accounts_confidence_is_1(self):
        """10 transactions with identical accounts → majority_ratio = 10/10 = 1.0"""
        transactions = []
        for i in range(10):
            transactions.append(_make_transaction("1002", "1600", "AIRBNB BETALING", f"2025-01-{i+1:02d}"))

        result = analyze_reference_patterns(transactions, "TestAdmin", _is_bank_account)

        company_key = "TestAdmin_1002_AIRBNB"
        assert company_key in result, f"Expected key '{company_key}' in result. Keys: {list(result.keys())}"

        pattern = result[company_key]
        assert pattern["confidence"] == 1.0, f"Expected confidence 1.0, got {pattern['confidence']}"
        assert pattern["_ambiguous"] is False
        assert pattern["_minority_count"] == 0
        assert pattern["debet_account"] == "1002"
        assert pattern["credit_account"] == "1600"


class TestGoodwinSolutionsAirbnbIntegration:
    """Task 9.10: Integration test — full pattern analysis for GoodwinSolutions produces AIRBNB pattern with Credit=1600"""

    def test_airbnb_pattern_with_923_majority_and_4_outliers(self):
        """
        Realistic scenario: 923 transactions with credit=1600 vs 4 with credit=8003.
        The majority (923/927 ≈ 99.5%) wins, pattern stored with high confidence.
        """
        transactions = []

        # 923 transactions with the majority accounts (debet=1002, credit=1600)
        for i in range(923):
            transactions.append(
                _make_transaction("1002", "1600", "AIRBNB BETALING", f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}")
            )

        # 4 outlier transactions with (debet=1002, credit=8003) — the miscoded ones
        for i in range(4):
            transactions.append(
                _make_transaction("1002", "8003", "AIRBNB BETALING", f"2025-12-{20 + i:02d}")
            )

        result = analyze_reference_patterns(transactions, "GoodwinSolutions", _is_bank_account)

        company_key = "GoodwinSolutions_1002_AIRBNB"
        assert company_key in result, f"Expected key '{company_key}' in result. Keys: {list(result.keys())}"

        pattern = result[company_key]

        # Credit account should be the majority (1600), not the outlier (8003)
        assert pattern["credit_account"] == "1600", f"Expected credit_account='1600', got '{pattern['credit_account']}'"

        # Confidence should be 923/927 ≈ 0.9957
        expected_confidence = 923 / 927
        assert abs(pattern["confidence"] - expected_confidence) < 0.001, (
            f"Expected confidence ≈ {expected_confidence:.4f}, got {pattern['confidence']}"
        )

        # Not ambiguous — majority is well above 90%
        assert pattern["_ambiguous"] is False

        # Debet account is the bank account
        assert pattern["debet_account"] == "1002"

        # Occurrences should be the total count
        assert pattern["occurrences"] == 927, f"Expected 927 occurrences, got {pattern['occurrences']}"
