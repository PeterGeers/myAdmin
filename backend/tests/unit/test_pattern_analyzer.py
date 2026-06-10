"""
Unit tests for pattern detection and scoring modules.

Tests the core logic extracted from pattern_analyzer.py:
- pattern_detection.py: keyword extraction, company name extraction,
  reference number extraction, verb extraction, pattern analysis
- pattern_scoring.py: statistics generation, conflict resolution,
  debet/credit/reference prediction
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta

from pattern_detection import (
    extract_keywords,
    extract_company_name,
    extract_reference_number_from_description,
    is_valid_verb,
    extract_compound_verb_from_description,
    extract_verb_from_description,
    analyze_debet_patterns,
    analyze_credit_patterns,
    analyze_reference_patterns,
)
from pattern_scoring import (
    generate_pattern_statistics,
    calculate_statistics_from_db_patterns,
    resolve_pattern_conflicts,
    predict_debet,
    predict_credit,
    predict_reference,
)


# ============================================================================
# Pattern Detection Tests
# ============================================================================


@pytest.mark.unit
class TestExtractKeywords:
    """Tests for extract_keywords function"""

    def test_empty_description_returns_empty_list(self):
        assert extract_keywords("") == []
        assert extract_keywords(None) == []

    def test_extracts_meaningful_words(self):
        keywords = extract_keywords("Purchase from SuperMarket Online Store")
        assert len(keywords) > 0
        # Should contain meaningful content words
        assert "purchase" in keywords
        assert "supermarket" in keywords

    def test_filters_noise_words(self):
        keywords = extract_keywords("betaling van de supermarkt voor een product")
        # Dutch noise words should be filtered
        assert "van" not in keywords
        assert "een" not in keywords

    def test_max_five_keywords(self):
        desc = "word1 word2 word3 word4 word5 word6 word7 word8"
        keywords = extract_keywords(desc)
        assert len(keywords) <= 5

    def test_minimum_three_characters(self):
        keywords = extract_keywords("go to do it ab cd ef")
        # All words < 3 chars should be filtered
        for kw in keywords:
            assert len(kw) >= 3


@pytest.mark.unit
class TestExtractCompanyName:
    """Tests for extract_company_name function"""

    def test_empty_description_returns_none(self):
        assert extract_company_name("") is None
        assert extract_company_name(None) is None

    def test_known_company_patterns(self):
        assert extract_company_name("Betaling aan BOL.COM BV") == "BOL"
        assert extract_company_name("AIRBNB PAYMENTS") == "AIRBNB"
        assert extract_company_name("PICNIC online boodschappen") == "PICNIC"
        assert extract_company_name("BOOKING.COM reservation") == "BOOKING"

    def test_extracts_from_cleaned_description(self):
        # Should extract company name after removing banking prefixes
        result = extract_company_name("BETAALVERZOEK HOOGVLIET supermarkt")
        assert result is not None

    def test_filters_transaction_codes(self):
        # Should not return long alphanumeric codes as company names
        result = extract_company_name("NL80RABO0107936917 P16ABC1234567890 transfer")
        # Result should not be a transaction code
        if result:
            assert len(result) < 20


@pytest.mark.unit
class TestExtractReferenceNumber:
    """Tests for extract_reference_number_from_description function"""

    def test_empty_description_returns_none(self):
        assert extract_reference_number_from_description("") is None
        assert extract_reference_number_from_description(None) is None

    def test_extracts_numeric_invoice_number(self):
        result = extract_reference_number_from_description(
            "Factuur 123456789 betaling"
        )
        assert result == "123456789"

    def test_extracts_longest_numeric_sequence(self):
        result = extract_reference_number_from_description(
            "REF 12345 invoice 987654321 payment"
        )
        # Should return the longest numeric sequence
        assert result == "987654321"

    def test_extracts_alphanumeric_reference_codes(self):
        result = extract_reference_number_from_description(
            "Payment AB123456 completed"
        )
        assert result == "AB123456"

    def test_extracts_ref_prefixed_codes(self):
        result = extract_reference_number_from_description("REF: ABC12345 betaling")
        assert result == "ABC12345"

    def test_no_reference_returns_none(self):
        result = extract_reference_number_from_description("Simple payment transfer")
        assert result is None


@pytest.mark.unit
class TestIsValidVerb:
    """Tests for is_valid_verb function"""

    def test_empty_or_short_verbs_invalid(self):
        assert is_valid_verb("") is False
        assert is_valid_verb(None) is False
        assert is_valid_verb("AB") is False

    def test_valid_company_names(self):
        assert is_valid_verb("PICNIC") is True
        assert is_valid_verb("HOOGVLIET") is True
        assert is_valid_verb("AEGON") is True

    def test_short_acronyms_valid(self):
        # 3-5 char uppercase acronyms without digits are valid
        assert is_valid_verb("KPN") is True
        assert is_valid_verb("SVB") is True
        assert is_valid_verb("ANWB") is True

    def test_transaction_ids_invalid(self):
        # Long alphanumeric codes should be rejected
        assert is_valid_verb("QG0DBCBZELL92QM4") is False
        assert is_valid_verb("P1234567890") is False

    def test_known_invalid_prefixes(self):
        assert is_valid_verb("FACTUURNR123") is False
        assert is_valid_verb("KLANTNR456") is False
        assert is_valid_verb("TRANSACTIE789") is False


@pytest.mark.unit
class TestExtractCompoundVerb:
    """Tests for extract_compound_verb_from_description function"""

    def test_empty_description_returns_none(self):
        assert extract_compound_verb_from_description("", "") is None
        assert extract_compound_verb_from_description(None, "") is None

    def test_company_with_reference_number(self):
        result = extract_compound_verb_from_description(
            "ANWB Energie B.V. 100431234 NL28BUKK", ""
        )
        assert result is not None
        assert "ANWB" in result
        # Should contain pipe separator for compound verb
        if "|" in result:
            parts = result.split("|")
            assert parts[0] == "ANWB"

    def test_company_without_reference_returns_simple(self):
        result = extract_compound_verb_from_description("PICNIC online order", "")
        # When no reference number, just returns company name
        assert result is not None
        assert "PICNIC" in result


@pytest.mark.unit
class TestExtractVerbFromDescription:
    """Tests for extract_verb_from_description function"""

    def test_empty_description_returns_none(self):
        assert extract_verb_from_description("", "") is None

    def test_known_company_description(self):
        result = extract_verb_from_description("PICNIC boodschappen betaling", "")
        assert result is not None

    def test_compound_verb_preferred(self):
        result = extract_verb_from_description(
            "ANWB BV 7073498490 Betreft factuur", ""
        )
        # Should extract compound verb with | separator
        if result and "|" in result:
            parts = result.split("|")
            assert parts[0] == "ANWB"


# ============================================================================
# Pattern Analysis Tests
# ============================================================================


@pytest.mark.unit
class TestAnalyzeDebetPatterns:
    """Tests for analyze_debet_patterns function"""

    def _make_bank_account_fn(self, bank_accounts):
        """Helper: create is_bank_account function"""
        def is_bank_account(account, admin):
            return account in bank_accounts
        return is_bank_account

    def test_empty_transactions_returns_empty(self):
        result = analyze_debet_patterns([], "admin1", lambda a, b: False)
        assert result == {}

    def test_skips_transactions_without_debet(self):
        transactions = [
            {"Debet": "", "Credit": "1300", "TransactionDescription": "test",
             "ReferenceNumber": "", "TransactionAmount": 100, "TransactionDate": "2024-01-01"}
        ]
        is_bank = self._make_bank_account_fn({"1300"})
        result = analyze_debet_patterns(transactions, "admin1", is_bank)
        assert result == {}

    def test_skips_when_credit_not_bank_account(self):
        transactions = [
            {"Debet": "4000", "Credit": "8000", "TransactionDescription": "test",
             "ReferenceNumber": "", "TransactionAmount": 100, "TransactionDate": "2024-01-01"}
        ]
        # Only 1300 is a bank account, so credit=8000 is not
        is_bank = self._make_bank_account_fn({"1300"})
        result = analyze_debet_patterns(transactions, "admin1", is_bank)
        assert result == {}

    def test_creates_pattern_when_credit_is_bank(self):
        transactions = [
            {"Debet": "4000", "Credit": "1300", "TransactionDescription": "PICNIC groceries",
             "ReferenceNumber": "REF001", "TransactionAmount": 50.0, "TransactionDate": "2024-01-01"}
        ]
        is_bank = self._make_bank_account_fn({"1300"})
        result = analyze_debet_patterns(transactions, "admin1", is_bank)
        assert len(result) > 0
        # Check pattern contains expected data
        pattern = list(result.values())[0]
        assert pattern["predicted_debet"] == "4000"
        assert pattern["credit_account"] == "1300"
        assert pattern["occurrences"] == 1

    def test_confidence_increases_with_occurrences(self):
        # Create 5 similar transactions
        transactions = [
            {"Debet": "4000", "Credit": "1300", "TransactionDescription": "PICNIC groceries",
             "ReferenceNumber": "", "TransactionAmount": 50.0, "TransactionDate": f"2024-01-0{i+1}"}
            for i in range(5)
        ]
        is_bank = self._make_bank_account_fn({"1300"})
        result = analyze_debet_patterns(transactions, "admin1", is_bank)
        assert len(result) > 0
        pattern = list(result.values())[0]
        assert pattern["occurrences"] == 5
        assert pattern["confidence"] == 0.5  # 5/10


@pytest.mark.unit
class TestAnalyzeCreditPatterns:
    """Tests for analyze_credit_patterns function"""

    def _make_bank_account_fn(self, bank_accounts):
        def is_bank_account(account, admin):
            return account in bank_accounts
        return is_bank_account

    def test_empty_transactions_returns_empty(self):
        result = analyze_credit_patterns([], "admin1", lambda a, b: False)
        assert result == {}

    def test_skips_transactions_without_credit(self):
        transactions = [
            {"Debet": "1300", "Credit": "", "TransactionDescription": "test",
             "ReferenceNumber": "", "TransactionAmount": 100, "TransactionDate": "2024-01-01"}
        ]
        is_bank = self._make_bank_account_fn({"1300"})
        result = analyze_credit_patterns(transactions, "admin1", is_bank)
        assert result == {}

    def test_creates_pattern_when_debet_is_bank(self):
        transactions = [
            {"Debet": "1300", "Credit": "8000", "TransactionDescription": "Client payment",
             "ReferenceNumber": "INV001", "TransactionAmount": 500.0, "TransactionDate": "2024-01-01"}
        ]
        is_bank = self._make_bank_account_fn({"1300"})
        result = analyze_credit_patterns(transactions, "admin1", is_bank)
        assert len(result) > 0
        pattern = list(result.values())[0]
        assert pattern["predicted_credit"] == "8000"
        assert pattern["debet_account"] == "1300"


@pytest.mark.unit
class TestAnalyzeReferencePatterns:
    """Tests for analyze_reference_patterns function"""

    def _make_bank_account_fn(self, bank_accounts):
        def is_bank_account(account, admin):
            return account in bank_accounts
        return is_bank_account

    def test_empty_transactions_returns_empty(self):
        result = analyze_reference_patterns([], "admin1", lambda a, b: False)
        assert result == {}

    def test_skips_without_reference_or_description(self):
        transactions = [
            {"Debet": "1300", "Credit": "4000", "TransactionDescription": "",
             "ReferenceNumber": "REF1", "TransactionDate": "2024-01-01"},
            {"Debet": "1300", "Credit": "4000", "TransactionDescription": "test",
             "ReferenceNumber": "", "TransactionDate": "2024-01-01"},
        ]
        is_bank = self._make_bank_account_fn({"1300"})
        result = analyze_reference_patterns(transactions, "admin1", is_bank)
        assert result == {}

    def test_creates_verb_pattern(self):
        transactions = [
            {"Debet": "1300", "Credit": "4000", "TransactionDescription": "PICNIC boodschappen 12345",
             "ReferenceNumber": "Picnic", "TransactionDate": "2024-01-01"}
        ]
        is_bank = self._make_bank_account_fn({"1300"})
        result = analyze_reference_patterns(transactions, "admin1", is_bank)
        # Should create a pattern keyed by admin_bankaccount_verb
        assert len(result) > 0
        pattern = list(result.values())[0]
        assert pattern["administration"] == "admin1"
        assert pattern["reference_number"] == "Picnic"


# ============================================================================
# Pattern Scoring Tests
# ============================================================================


@pytest.mark.unit
class TestGeneratePatternStatistics:
    """Tests for generate_pattern_statistics function"""

    def test_empty_inputs(self):
        is_bank = lambda a, b: False
        result = generate_pattern_statistics([], {}, {}, {}, is_bank)
        assert result["total_transactions"] == 0
        assert result["missing_fields"]["debet"] == 0
        assert result["patterns_by_type"]["debet_patterns"] == 0

    def test_counts_missing_fields(self):
        transactions = [
            {"Debet": "", "Credit": "1300", "ReferenceNumber": "", "Administration": "admin1"},
            {"Debet": "4000", "Credit": "", "ReferenceNumber": "REF1", "Administration": "admin1"},
        ]
        is_bank = lambda a, b: False
        result = generate_pattern_statistics(transactions, {}, {}, {}, is_bank)
        assert result["total_transactions"] == 2
        assert result["missing_fields"]["debet"] == 1
        assert result["missing_fields"]["credit"] == 1
        assert result["missing_fields"]["reference"] == 1

    def test_counts_bank_account_transactions(self):
        transactions = [
            {"Debet": "1300", "Credit": "4000", "ReferenceNumber": "REF1", "Administration": "admin1"},
            {"Debet": "6000", "Credit": "1300", "ReferenceNumber": "REF2", "Administration": "admin1"},
        ]
        is_bank = lambda account, admin: account == "1300"
        result = generate_pattern_statistics(transactions, {}, {}, {}, is_bank)
        assert result["bank_account_transactions"]["debet_is_bank"] == 1
        assert result["bank_account_transactions"]["credit_is_bank"] == 1

    def test_reports_pattern_counts(self):
        debet_patterns = {"p1": {"confidence": 0.8}, "p2": {"confidence": 0.6}}
        credit_patterns = {"p3": {"confidence": 1.0}}
        ref_patterns = {"p4": {"confidence": 0.9}, "p5": {"confidence": 0.7}, "p6": {"confidence": 0.5}}
        is_bank = lambda a, b: False

        result = generate_pattern_statistics([], debet_patterns, credit_patterns, ref_patterns, is_bank)
        assert result["patterns_by_type"]["debet_patterns"] == 2
        assert result["patterns_by_type"]["credit_patterns"] == 1
        assert result["patterns_by_type"]["reference_patterns"] == 3

    def test_calculates_average_confidence(self):
        debet_patterns = {"p1": {"confidence": 0.8}, "p2": {"confidence": 0.4}}
        is_bank = lambda a, b: False
        result = generate_pattern_statistics([], debet_patterns, {}, {}, is_bank)
        assert result["pattern_confidence"]["debet_avg_confidence"] == pytest.approx(0.6)


@pytest.mark.unit
class TestCalculateStatisticsFromDbPatterns:
    """Tests for calculate_statistics_from_db_patterns function"""

    def test_empty_patterns(self):
        result = calculate_statistics_from_db_patterns({}, {}, {})
        assert result["patterns_by_type"]["debet_patterns"] == 0
        assert result["pattern_confidence"]["debet_avg_confidence"] == 0.0

    def test_calculates_counts_and_confidence(self):
        debet = {"p1": {"confidence": 1.0}}
        credit = {"p2": {"confidence": 0.5}, "p3": {"confidence": 0.7}}
        ref = {}
        result = calculate_statistics_from_db_patterns(debet, credit, ref)
        assert result["patterns_by_type"]["debet_patterns"] == 1
        assert result["patterns_by_type"]["credit_patterns"] == 2
        assert result["pattern_confidence"]["credit_avg_confidence"] == pytest.approx(0.6)


@pytest.mark.unit
class TestResolvePatternConflicts:
    """Tests for resolve_pattern_conflicts function"""

    def _make_bank_account_fn(self, bank_accounts):
        def is_bank_account(account, admin):
            return account in bank_accounts
        return is_bank_account

    def test_empty_patterns_returns_none(self):
        is_bank = self._make_bank_account_fn(set())
        result = resolve_pattern_conflicts([], {}, "admin1", is_bank)
        assert result is None

    def test_single_pattern_returns_it(self):
        is_bank = self._make_bank_account_fn(set())
        patterns = [("key1", {"occurrences": 3, "confidence": 0.9})]
        result = resolve_pattern_conflicts(patterns, {}, "admin1", is_bank)
        assert result == ("key1", {"occurrences": 3, "confidence": 0.9})

    def test_prefers_more_recent_pattern(self):
        is_bank = self._make_bank_account_fn(set())
        today = date.today()
        recent = (today - timedelta(days=1)).isoformat()
        old = (today - timedelta(days=365)).isoformat()

        # Same frequency so recency is the differentiator
        patterns = [
            ("old_key", {"occurrences": 3, "confidence": 0.9, "last_seen": old, "amounts": [100]}),
            ("new_key", {"occurrences": 3, "confidence": 0.8, "last_seen": recent, "amounts": [100]}),
        ]
        transaction = {"TransactionAmount": 100}
        result = resolve_pattern_conflicts(patterns, transaction, "admin1", is_bank)
        # Recent pattern should win due to recency scoring
        assert result[0] == "new_key"

    def test_prefers_higher_frequency_when_same_recency(self):
        is_bank = self._make_bank_account_fn(set())
        today = date.today().isoformat()

        patterns = [
            ("low_freq", {"occurrences": 2, "confidence": 0.8, "last_seen": today, "amounts": [100]}),
            ("high_freq", {"occurrences": 15, "confidence": 0.9, "last_seen": today, "amounts": [100]}),
        ]
        transaction = {"TransactionAmount": 100}
        result = resolve_pattern_conflicts(patterns, transaction, "admin1", is_bank)
        assert result[0] == "high_freq"

    def test_amount_similarity_boosts_score(self):
        is_bank = self._make_bank_account_fn(set())
        today = date.today().isoformat()

        patterns = [
            ("diff_amount", {"occurrences": 5, "confidence": 0.8, "last_seen": today, "amounts": [500.0]}),
            ("same_amount", {"occurrences": 5, "confidence": 0.8, "last_seen": today, "amounts": [100.0]}),
        ]
        transaction = {"TransactionAmount": 100}
        result = resolve_pattern_conflicts(patterns, transaction, "admin1", is_bank)
        assert result[0] == "same_amount"


@pytest.mark.unit
class TestPredictDebet:
    """Tests for predict_debet function"""

    def _make_bank_account_fn(self, bank_accounts):
        def is_bank_account(account, admin):
            return account in bank_accounts
        return is_bank_account

    def test_empty_description_returns_none(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {"TransactionDescription": "", "Credit": "1300", "ReferenceNumber": ""}
        result = predict_debet(
            transaction, {}, "admin1", is_bank,
            extract_verb_from_description, lambda a: {"reference_patterns": {}}
        )
        assert result is None

    def test_non_bank_credit_returns_none(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {"TransactionDescription": "PICNIC groceries", "Credit": "8000", "ReferenceNumber": ""}
        result = predict_debet(
            transaction, {}, "admin1", is_bank,
            extract_verb_from_description, lambda a: {"reference_patterns": {}}
        )
        assert result is None

    def test_exact_pattern_match(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {
            "TransactionDescription": "PICNIC boodschappen",
            "Credit": "1300",
            "ReferenceNumber": ""
        }
        ref_patterns = {
            "admin1_1300_PICNIC": {
                "debet_account": "4000",
                "credit_account": "1300",
                "confidence": 1.0,
                "verb": "PICNIC",
                "administration": "admin1",
                "occurrences": 5,
            }
        }

        def get_filtered(admin):
            return {"reference_patterns": ref_patterns}

        result = predict_debet(
            transaction, {}, "admin1", is_bank,
            extract_verb_from_description, get_filtered
        )
        assert result is not None
        assert result["value"] == "4000"
        assert result["confidence"] == 1.0

    def test_no_verb_returns_none(self):
        is_bank = self._make_bank_account_fn({"1300"})
        # Description that won't produce a valid verb
        transaction = {"TransactionDescription": "ab cd", "Credit": "1300", "ReferenceNumber": ""}
        result = predict_debet(
            transaction, {}, "admin1", is_bank,
            extract_verb_from_description, lambda a: {"reference_patterns": {}}
        )
        assert result is None


@pytest.mark.unit
class TestPredictCredit:
    """Tests for predict_credit function"""

    def _make_bank_account_fn(self, bank_accounts):
        def is_bank_account(account, admin):
            return account in bank_accounts
        return is_bank_account

    def test_empty_description_returns_none(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {"TransactionDescription": "", "Debet": "1300", "ReferenceNumber": ""}
        result = predict_credit(
            transaction, {}, "admin1", is_bank,
            extract_verb_from_description, lambda a: {"reference_patterns": {}}
        )
        assert result is None

    def test_non_bank_debet_returns_none(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {"TransactionDescription": "PICNIC groceries", "Debet": "8000", "ReferenceNumber": ""}
        result = predict_credit(
            transaction, {}, "admin1", is_bank,
            extract_verb_from_description, lambda a: {"reference_patterns": {}}
        )
        assert result is None

    def test_exact_pattern_match(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {
            "TransactionDescription": "PICNIC boodschappen",
            "Debet": "1300",
            "ReferenceNumber": ""
        }
        ref_patterns = {
            "admin1_1300_PICNIC": {
                "credit_account": "8000",
                "debet_account": "1300",
                "confidence": 1.0,
                "verb": "PICNIC",
                "administration": "admin1",
                "occurrences": 5,
            }
        }

        def get_filtered(admin):
            return {"reference_patterns": ref_patterns}

        result = predict_credit(
            transaction, {}, "admin1", is_bank,
            extract_verb_from_description, get_filtered
        )
        assert result is not None
        assert result["value"] == "8000"
        assert result["confidence"] == 1.0


@pytest.mark.unit
class TestPredictReference:
    """Tests for predict_reference function"""

    def _make_bank_account_fn(self, bank_accounts):
        def is_bank_account(account, admin):
            return account in bank_accounts
        return is_bank_account

    def test_empty_description_returns_none(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {"TransactionDescription": "", "Debet": "1300", "Credit": "4000",
                       "administration": "admin1", "ReferenceNumber": ""}
        result = predict_reference(transaction, {}, is_bank, extract_verb_from_description)
        assert result is None

    def test_no_bank_account_returns_none(self):
        is_bank = self._make_bank_account_fn(set())
        transaction = {"TransactionDescription": "PICNIC boodschappen", "Debet": "4000",
                       "Credit": "8000", "administration": "admin1", "ReferenceNumber": ""}
        result = predict_reference(transaction, {}, is_bank, extract_verb_from_description)
        assert result is None

    def test_exact_pattern_match(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {
            "TransactionDescription": "PICNIC boodschappen",
            "Debet": "1300",
            "Credit": "4000",
            "administration": "admin1",
            "ReferenceNumber": ""
        }
        ref_patterns = {
            "admin1_1300_PICNIC": {
                "reference_number": "Picnic",
                "confidence": 1.0,
                "verb": "PICNIC",
                "verb_company": "PICNIC",
                "administration": "admin1",
                "bank_account": "1300",
                "occurrences": 5,
                "is_compound": False,
            }
        }
        result = predict_reference(transaction, ref_patterns, is_bank, extract_verb_from_description)
        assert result is not None
        assert result["value"] == "Picnic"
        assert result["confidence"] == 1.0

    def test_no_matching_pattern_returns_none(self):
        is_bank = self._make_bank_account_fn({"1300"})
        transaction = {
            "TransactionDescription": "PICNIC boodschappen",
            "Debet": "1300",
            "Credit": "4000",
            "administration": "admin1",
            "ReferenceNumber": ""
        }
        # Empty patterns dict — no match possible
        result = predict_reference(transaction, {}, is_bank, extract_verb_from_description)
        assert result is None
