"""
Property-based tests for InvoiceService._determine_parser_used.

Uses Hypothesis to verify correctness properties from the design document.
Feature: vendor-parser-cleanup

Properties tested:
- Property 4: parser_used field correctness (Requirements 4.1, 4.2, 4.3, 4.4, 5.5, 6.6)

Reference: .kiro/specs/vendor-parser-cleanup/design.md
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.invoice_service import InvoiceService


# ---------------------------------------------------------------------------
# Strategy helpers for Property 4
# ---------------------------------------------------------------------------

# Valid amounts (> 0) representing successful AI extraction
positive_amount_st = st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False)

# Zero or negative amounts representing failed AI extraction
zero_amount_st = st.just(0) | st.just(0.0)

# Random string amounts that could be valid or invalid
string_amount_st = st.text(
    alphabet=st.characters(whitelist_categories=('N',), whitelist_characters='.-'),
    min_size=0,
    max_size=10,
)

# Generate random folder names
folder_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=30,
)

# Generate random descriptions
description_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=0,
    max_size=100,
)

# The ONLY valid parser_used values
VALID_PARSER_USED_VALUES = {"ai", "ai_failed", "csv_rule"}


# ---------------------------------------------------------------------------
# Strategy: Generate random transaction lists
# ---------------------------------------------------------------------------

# A transaction dict with a positive amount (AI success scenario)
ai_success_tx_st = st.fixed_dictionaries({
    'amount': positive_amount_st.map(lambda x: round(x, 2)),
    'date': st.dates().map(lambda d: d.strftime('%Y-%m-%d')),
    'description': description_st,
    'ref': folder_name_st,
})

# A transaction dict with zero amount (AI failed scenario)
ai_failed_tx_st = st.fixed_dictionaries({
    'amount': zero_amount_st,
    'date': st.dates().map(lambda d: d.strftime('%Y-%m-%d')),
    'description': description_st,
    'ref': folder_name_st,
})

# A transaction dict with parser_used_hint='csv_rule' (CSV rule scenario)
csv_rule_tx_st = st.fixed_dictionaries({
    'amount': st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False).map(lambda x: round(x, 2)),
    'date': st.dates().map(lambda d: d.strftime('%Y-%m-%d')),
    'description': description_st,
    'ref': folder_name_st,
    'parser_used_hint': st.just('csv_rule'),
})

# A result dict with 'ai_data' key (image AI scenario)
result_with_ai_data_st = st.fixed_dictionaries({
    'txt': st.just('some text'),
    'folder': folder_name_st,
    'ai_data': st.fixed_dictionaries({
        'total_amount': positive_amount_st.map(lambda x: round(x, 2)),
    }),
})

# A result dict without 'ai_data' key (normal processing)
result_without_ai_data_st = st.fixed_dictionaries({
    'txt': st.just('some text'),
    'folder': folder_name_st,
})

# Combined result strategy
any_result_st = st.one_of(result_with_ai_data_st, result_without_ai_data_st)

# Combined transaction strategy (one of the scenarios)
any_transaction_st = st.one_of(ai_success_tx_st, ai_failed_tx_st, csv_rule_tx_st)

# Transaction list strategy (empty or with transactions)
transaction_list_st = st.one_of(
    st.just([]),  # empty transactions
    st.lists(any_transaction_st, min_size=1, max_size=5),
)


def _create_invoice_service():
    """Create an InvoiceService instance with mocked dependencies."""
    with patch('services.invoice_service.DatabaseManager') as mock_db_class, \
         patch('services.invoice_service.PDFProcessor') as mock_proc_class, \
         patch('services.invoice_service.TransactionLogic') as mock_tl_class:
        mock_db_class.return_value = MagicMock()
        mock_proc_class.return_value = MagicMock()
        mock_tl_class.return_value = MagicMock()
        service = InvoiceService(test_mode=True)
    return service


# ---------------------------------------------------------------------------
# Property 4: parser_used field correctness
# Feature: vendor-parser-cleanup, Property 4: parser_used field correctness
# Validates: Requirements 4.1, 4.2, 4.3, 4.4, 5.5, 6.6
# ---------------------------------------------------------------------------

class TestParserUsedFieldCorrectness:
    """
    Property 4: parser_used field correctness

    For any invoice processing result, the parser_used field SHALL be one of
    exactly three values: "ai" (when AI extraction succeeds with amount > 0),
    "ai_failed" (when AI returns zero amount or raises exception), or
    "csv_rule" (when a CSV aggregation rule is applied). No other value SHALL
    ever appear.

    Feature: vendor-parser-cleanup, Property 4: parser_used field correctness
    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 5.5, 6.6**
    """

    @settings(max_examples=100)
    @given(transactions=transaction_list_st, result=any_result_st)
    def test_parser_used_always_in_valid_set(self, transactions, result):
        """
        For any combination of transactions and result, _determine_parser_used
        SHALL always return a value in {"ai", "ai_failed", "csv_rule"}.

        Feature: vendor-parser-cleanup, Property 4: parser_used field correctness
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 5.5, 6.6**
        """
        service = _create_invoice_service()
        parser_used = service._determine_parser_used(transactions, result)

        assert parser_used in VALID_PARSER_USED_VALUES, (
            f"parser_used='{parser_used}' is not in the valid set "
            f"{VALID_PARSER_USED_VALUES}. "
            f"transactions={transactions}, result keys={list(result.keys())}"
        )

    @settings(max_examples=100)
    @given(result=any_result_st)
    def test_empty_transactions_returns_ai_failed(self, result):
        """
        When transactions list is empty, _determine_parser_used SHALL return
        "ai_failed".

        Feature: vendor-parser-cleanup, Property 4: parser_used field correctness
        **Validates: Requirements 4.2, 5.5**
        """
        service = _create_invoice_service()
        parser_used = service._determine_parser_used([], result)

        assert parser_used == 'ai_failed', (
            f"Expected 'ai_failed' for empty transactions, got '{parser_used}'"
        )

    @settings(max_examples=100, derandomize=True)
    @given(tx=csv_rule_tx_st, result=any_result_st)
    def test_csv_rule_hint_returns_csv_rule(self, tx, result):
        """
        When first transaction has parser_used_hint='csv_rule',
        _determine_parser_used SHALL return "csv_rule".

        Feature: vendor-parser-cleanup, Property 4: parser_used field correctness
        **Validates: Requirements 4.3, 6.6**
        """
        service = _create_invoice_service()
        parser_used = service._determine_parser_used([tx], result)

        assert parser_used == 'csv_rule', (
            f"Expected 'csv_rule' for transaction with parser_used_hint='csv_rule', "
            f"got '{parser_used}'"
        )

    @settings(max_examples=100)
    @given(tx=ai_success_tx_st, result=result_without_ai_data_st)
    def test_positive_amount_returns_ai(self, tx, result):
        """
        When first transaction has amount > 0 and no csv_rule hint,
        _determine_parser_used SHALL return "ai".

        Feature: vendor-parser-cleanup, Property 4: parser_used field correctness
        **Validates: Requirements 4.1**
        """
        service = _create_invoice_service()
        parser_used = service._determine_parser_used([tx], result)

        assert parser_used == 'ai', (
            f"Expected 'ai' for transaction with amount={tx['amount']} > 0, "
            f"got '{parser_used}'"
        )

    @settings(max_examples=100)
    @given(tx=ai_failed_tx_st, result=result_without_ai_data_st)
    def test_zero_amount_returns_ai_failed(self, tx, result):
        """
        When first transaction has amount == 0 and no csv_rule hint,
        _determine_parser_used SHALL return "ai_failed".

        Feature: vendor-parser-cleanup, Property 4: parser_used field correctness
        **Validates: Requirements 4.2, 5.5**
        """
        service = _create_invoice_service()
        parser_used = service._determine_parser_used([tx], result)

        assert parser_used == 'ai_failed', (
            f"Expected 'ai_failed' for transaction with amount={tx['amount']} == 0, "
            f"got '{parser_used}'"
        )

    @settings(max_examples=100)
    @given(tx=ai_success_tx_st, result=result_with_ai_data_st)
    def test_ai_data_in_result_returns_ai(self, tx, result):
        """
        When result contains 'ai_data' key (image AI pre-extraction),
        _determine_parser_used SHALL return "ai".

        Feature: vendor-parser-cleanup, Property 4: parser_used field correctness
        **Validates: Requirements 4.1, 4.4**
        """
        # Remove parser_used_hint if present to test ai_data path
        tx_copy = {k: v for k, v in tx.items() if k != 'parser_used_hint'}
        service = _create_invoice_service()
        parser_used = service._determine_parser_used([tx_copy], result)

        assert parser_used == 'ai', (
            f"Expected 'ai' when result has 'ai_data' key, got '{parser_used}'"
        )
