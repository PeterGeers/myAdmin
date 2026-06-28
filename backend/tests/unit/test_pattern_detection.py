"""
Unit tests for pattern_detection.py

Tests pattern detection against known bank descriptions:
- extract_keywords() - Keyword extraction
- extract_company_name() - Company name detection
- extract_reference_number_from_description() - Reference number extraction
- is_valid_verb() - Verb validation
- extract_verb_from_description() - Compound verb extraction
- analyze_debet_patterns() - Debet pattern analysis
- analyze_credit_patterns() - Credit pattern analysis
- analyze_reference_patterns() - Reference/verb pattern analysis

Task 53 of Phase 7: Missing Test Coverage
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pattern_detection import (
    extract_keywords,
    extract_company_name,
    extract_reference_number_from_description,
    is_valid_verb,
    extract_verb_from_description,
    extract_compound_verb_from_description,
    analyze_debet_patterns,
    analyze_credit_patterns,
    analyze_reference_patterns,
)


# ── extract_keywords ───────────────────────────────────────────────────────


class TestExtractKeywords:

    def test_empty_string(self):
        """Empty string returns empty list."""
        assert extract_keywords('') == []

    def test_none_input(self):
        """None input returns empty list."""
        assert extract_keywords(None) == []

    def test_extracts_meaningful_words(self):
        """Extracts words >= 3 chars, skipping noise."""
        result = extract_keywords('Betaling aan bol.com voor bestelling')
        assert 'betaling' in result
        assert 'bestelling' in result
        # Noise words should be filtered
        assert 'aan' not in result
        assert 'voor' not in result

    def test_max_five_keywords(self):
        """Returns at most 5 keywords."""
        result = extract_keywords(
            'one two three four five six seven eight nine ten eleven'
        )
        assert len(result) <= 5

    def test_filters_short_words(self):
        """Words shorter than 3 chars are filtered."""
        result = extract_keywords('a ab abc abcd')
        assert 'a' not in result
        assert 'ab' not in result
        assert 'abc' in result


# ── extract_company_name ───────────────────────────────────────────────────


class TestExtractCompanyName:

    def test_none_input(self):
        """None returns None."""
        assert extract_company_name(None) is None

    def test_empty_input(self):
        """Empty string returns None."""
        assert extract_company_name('') is None

    def test_known_company_airbnb(self):
        """Recognizes AIRBNB in description."""
        assert extract_company_name('Betaling van Airbnb Payments') == 'AIRBNB'

    def test_known_company_bolcom(self):
        """Recognizes BOL.COM in description."""
        assert extract_company_name('iDEAL betaling bol.com webshop') == 'BOL'

    def test_known_company_picnic(self):
        """Recognizes PICNIC in description."""
        assert extract_company_name('PINBETALING Picnic BV Amsterdam') == 'PICNIC'

    def test_known_company_booking(self):
        """Recognizes BOOKING.COM in description."""
        assert extract_company_name('Overboeking Booking.com Amsterdam NLD') == 'BOOKING'

    def test_known_company_anwb(self):
        """Recognizes ANWB in description."""
        assert extract_company_name('ANWB Energie B.V. 100431234') == 'ANWB'

    def test_extracts_from_cleaned_description(self):
        """Extracts company name from cleaned banking description."""
        result = extract_company_name('BEA NR:2937 HOOGVLIET 12-06-2025')
        assert result == 'HOOGVLIET'

    def test_filters_transaction_codes(self):
        """Does not return transaction codes as company names."""
        # A long alphanumeric code should not be a company name
        result = extract_company_name('BEA NR:XJ93 P16ABCDEF12345678')
        assert result != 'P16ABCDEF12345678'


# ── extract_reference_number_from_description ──────────────────────────────


class TestExtractReferenceNumber:

    def test_none_input(self):
        """None returns None."""
        assert extract_reference_number_from_description(None) is None

    def test_empty_input(self):
        """Empty string returns None."""
        assert extract_reference_number_from_description('') is None

    def test_extracts_numeric_invoice(self):
        """Extracts 6+ digit numeric sequence."""
        result = extract_reference_number_from_description(
            'ANWB Energie BV 100431234 NL28BUKK'
        )
        assert result == '100431234'

    def test_extracts_longest_numeric(self):
        """Returns the longest numeric sequence."""
        result = extract_reference_number_from_description(
            'REF 123456 FACTUUR 7073498490'
        )
        assert result == '7073498490'

    def test_extracts_alphanumeric_ref(self):
        """Extracts alphanumeric reference like INV1234567."""
        result = extract_reference_number_from_description(
            'Payment for INV1234567 received'
        )
        assert result is not None
        assert '1234567' in result

    def test_no_reference_found(self):
        """Returns None when no reference pattern matches."""
        result = extract_reference_number_from_description('Kleine kas opname')
        assert result is None


# ── is_valid_verb ──────────────────────────────────────────────────────────


class TestIsValidVerb:

    def test_none_invalid(self):
        """None is invalid."""
        assert is_valid_verb(None) is False

    def test_short_string_invalid(self):
        """Strings < 3 chars are invalid."""
        assert is_valid_verb('AB') is False

    def test_valid_company_name(self):
        """Real company names are valid."""
        assert is_valid_verb('HOOGVLIET') is True
        assert is_valid_verb('PICNIC') is True
        assert is_valid_verb('AIRBNB') is True

    def test_valid_short_acronym(self):
        """Short acronyms (3-5 chars) without digits are valid."""
        assert is_valid_verb('SVB') is True
        assert is_valid_verb('KPN') is True
        assert is_valid_verb('TMC') is True

    def test_transaction_code_invalid(self):
        """Long alphanumeric codes are invalid."""
        assert is_valid_verb('QG0DBCBZELL92QM4') is False
        assert is_valid_verb('P1600000000') is False

    def test_invoice_prefix_invalid(self):
        """Transaction prefixes are invalid."""
        assert is_valid_verb('FACTUURNR123') is False
        assert is_valid_verb('KLANTNR456') is False

    def test_no_vowels_long_string_invalid(self):
        """Long strings without vowels (not short acronyms) are invalid."""
        assert is_valid_verb('BCDFGH') is False


# ── extract_verb_from_description ──────────────────────────────────────────


class TestExtractVerbFromDescription:

    def test_none_input(self):
        """None description returns None."""
        assert extract_verb_from_description(None, '') is None

    def test_known_company_compound_verb(self):
        """Extracts compound verb for known company with reference."""
        result = extract_verb_from_description(
            'ANWB Energie B.V. 100431234 NL28BUKK', ''
        )
        assert result is not None
        assert 'ANWB' in result
        assert '100431234' in result

    def test_simple_company_no_reference(self):
        """Returns simple company name when no reference found."""
        result = extract_verb_from_description(
            'BEA PINBETALING HOOGVLIET AMSTERDAM NLD', ''
        )
        assert result == 'HOOGVLIET'


# ── analyze_debet_patterns ─────────────────────────────────────────────────


class TestAnalyzeDebetPatterns:

    def _always_bank(self, account, admin):
        """Test helper: every account is a bank account."""
        return True

    def _only_1300_is_bank(self, account, admin):
        """Test helper: only 1300 is a bank account."""
        return account == '1300'

    def test_empty_transactions(self):
        """Empty input returns empty patterns."""
        result = analyze_debet_patterns([], 'Admin', self._always_bank)
        assert result == {}

    def test_creates_pattern_from_bank_credit(self):
        """Creates debet pattern when credit is a bank account."""
        transactions = [
            {
                'Debet': '4000',
                'Credit': '1300',
                'TransactionDescription': 'PICNIC betaling',
                'ReferenceNumber': 'INV001',
                'TransactionAmount': 50.0,
                'TransactionDate': '2025-06-01'
            }
        ]
        result = analyze_debet_patterns(transactions, 'Admin', self._only_1300_is_bank)
        assert len(result) > 0
        # The pattern should predict debet=4000
        pattern = list(result.values())[0]
        assert pattern['predicted_debet'] == '4000'
        assert pattern['credit_account'] == '1300'

    def test_skips_when_credit_not_bank(self):
        """Does not create pattern when credit is NOT a bank account."""
        transactions = [
            {
                'Debet': '4000',
                'Credit': '8000',
                'TransactionDescription': 'Revenue',
                'ReferenceNumber': '',
                'TransactionAmount': 100.0,
                'TransactionDate': '2025-06-01'
            }
        ]
        result = analyze_debet_patterns(transactions, 'Admin', self._only_1300_is_bank)
        assert result == {}

    def test_confidence_increases_with_occurrences(self):
        """Confidence increases with repeated patterns."""
        transactions = [
            {
                'Debet': '4000', 'Credit': '1300',
                'TransactionDescription': 'PICNIC betaling',
                'ReferenceNumber': '', 'TransactionAmount': 50.0,
                'TransactionDate': '2025-01-01'
            }
        ] * 10
        result = analyze_debet_patterns(transactions, 'Admin', self._only_1300_is_bank)
        pattern = list(result.values())[0]
        assert pattern['confidence'] == 1.0  # 10/10 = max


# ── analyze_credit_patterns ────────────────────────────────────────────────


class TestAnalyzeCreditPatterns:

    def _only_1300_is_bank(self, account, admin):
        return account == '1300'

    def test_empty_transactions(self):
        """Empty input returns empty patterns."""
        result = analyze_credit_patterns([], 'Admin', self._only_1300_is_bank)
        assert result == {}

    def test_creates_pattern_from_bank_debet(self):
        """Creates credit pattern when debet is a bank account."""
        transactions = [
            {
                'Debet': '1300',
                'Credit': '8000',
                'TransactionDescription': 'AIRBNB payout',
                'ReferenceNumber': 'PAY-123',
                'TransactionAmount': 200.0,
                'TransactionDate': '2025-06-01'
            }
        ]
        result = analyze_credit_patterns(transactions, 'Admin', self._only_1300_is_bank)
        assert len(result) > 0
        pattern = list(result.values())[0]
        assert pattern['predicted_credit'] == '8000'
        assert pattern['debet_account'] == '1300'

    def test_skips_when_debet_not_bank(self):
        """Does not create pattern when debet is NOT a bank account."""
        transactions = [
            {
                'Debet': '4000', 'Credit': '8000',
                'TransactionDescription': 'Internal',
                'ReferenceNumber': '', 'TransactionAmount': 100.0,
                'TransactionDate': '2025-06-01'
            }
        ]
        result = analyze_credit_patterns(transactions, 'Admin', self._only_1300_is_bank)
        assert result == {}


# ── analyze_reference_patterns ─────────────────────────────────────────────


class TestAnalyzeReferencePatterns:

    def _only_1300_is_bank(self, account, admin):
        return account == '1300'

    def test_empty_transactions(self):
        """Empty input returns empty patterns."""
        result = analyze_reference_patterns([], 'Admin', self._only_1300_is_bank)
        assert result == {}

    def test_creates_verb_pattern(self):
        """Creates verb-based pattern from transactions with known companies."""
        transactions = [
            {
                'Debet': '1300', 'Credit': '4000',
                'TransactionDescription': 'ANWB Energie B.V. 100431234',
                'ReferenceNumber': 'ANWB-Energie',
                'TransactionAmount': 150.0,
                'TransactionDate': '2025-06-01'
            }
        ]
        result = analyze_reference_patterns(transactions, 'GoodwinSolutions', self._only_1300_is_bank)
        assert len(result) > 0
        # Should contain a pattern for ANWB
        has_anwb = any('ANWB' in key for key in result.keys())
        assert has_anwb

    def test_skips_when_no_bank_account(self):
        """Skips transactions without a bank account."""
        transactions = [
            {
                'Debet': '4000', 'Credit': '8000',
                'TransactionDescription': 'Internal transfer',
                'ReferenceNumber': 'INT-001',
                'TransactionAmount': 100.0,
                'TransactionDate': '2025-06-01'
            }
        ]
        result = analyze_reference_patterns(transactions, 'Admin', self._only_1300_is_bank)
        assert result == {}

    def test_skips_empty_description(self):
        """Skips transactions with empty description."""
        transactions = [
            {
                'Debet': '1300', 'Credit': '8000',
                'TransactionDescription': '',
                'ReferenceNumber': 'REF',
                'TransactionAmount': 100.0,
                'TransactionDate': '2025-06-01'
            }
        ]
        result = analyze_reference_patterns(transactions, 'Admin', self._only_1300_is_bank)
        assert result == {}

    def test_skips_empty_reference(self):
        """Skips transactions with empty reference number."""
        transactions = [
            {
                'Debet': '1300', 'Credit': '8000',
                'TransactionDescription': 'ANWB betaling',
                'ReferenceNumber': '',
                'TransactionAmount': 100.0,
                'TransactionDate': '2025-06-01'
            }
        ]
        result = analyze_reference_patterns(transactions, 'Admin', self._only_1300_is_bank)
        assert result == {}

    def test_compound_verb_pattern(self):
        """Creates compound verb pattern (company|reference) for vendors with reference."""
        transactions = [
            {
                'Debet': '1300', 'Credit': '4000',
                'TransactionDescription': 'ANWB Energie 7073498490 betaling maand',
                'ReferenceNumber': 'ANWB-Energy',
                'TransactionAmount': 89.50,
                'TransactionDate': '2025-03-01'
            }
        ]
        result = analyze_reference_patterns(transactions, 'TestAdmin', self._only_1300_is_bank)
        # Should have compound key with pipe separator
        has_compound = any('|' in p.get('verb', '') for p in result.values())
        assert has_compound
