"""
Property-based tests for btw_processor module.

Uses Hypothesis to verify correctness properties from the design document.
Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant

Requirements: 3.5
Reference: .kiro/specs/missing-py-tests/design.md
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from unittest.mock import patch, MagicMock

from btw_processor import BTWProcessor


# Valid BTW account numbers used in the system
BTW_ACCOUNTS = ['2010', '2020', '2021']
RECEIVED_ACCOUNTS = ['2020', '2021']  # Accounts that count as "received BTW"
ALL_ACCOUNTS = ['2010', '2020', '2021', '8001', '8002', '4000']


# Strategy: generate a single balance/quarter data entry
balance_entry_st = st.fixed_dictionaries({
    'Reknum': st.sampled_from(BTW_ACCOUNTS),
    'AccountName': st.sampled_from(['BTW Af te dragen', 'BTW Hoog', 'BTW Laag']),
    'amount': st.floats(
        min_value=-100000.0, max_value=100000.0,
        allow_nan=False, allow_infinity=False,
    ),
})

quarter_entry_st = st.fixed_dictionaries({
    'Reknum': st.sampled_from(ALL_ACCOUNTS),
    'AccountName': st.sampled_from([
        'BTW Af te dragen', 'BTW Hoog', 'BTW Laag',
        'Revenue High', 'Revenue Low', 'Expenses',
    ]),
    'amount': st.floats(
        min_value=-100000.0, max_value=100000.0,
        allow_nan=False, allow_infinity=False,
    ),
})


# ---------------------------------------------------------------------------
# Property 5: BTW Debit-Credit Balance Invariant
# Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant
# Validates: Requirements 3.5
# ---------------------------------------------------------------------------

class TestBtwBalanceInvariant:
    """
    Property 5: BTW Debit-Credit Balance Invariant

    For any set of transactions within a closed accounting period where the sum
    of debit amounts equals the sum of credit amounts, the BTW processor's
    _calculate_btw_amounts SHALL preserve this balance invariant in its output
    (total VAT receivable minus total VAT payable equals the net VAT position).

    The key invariant: prepaid_btw == received_btw - total_balance

    Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant
    **Validates: Requirements 3.5**
    """

    @pytest.fixture(autouse=True)
    def setup_processor(self, mock_db):
        """Create BTWProcessor with mocked DatabaseManager."""
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            self.processor = BTWProcessor(test_mode=True)
        self.mock_db = mock_db

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        balance_data=st.lists(balance_entry_st, min_size=0, max_size=10),
        quarter_data=st.lists(quarter_entry_st, min_size=0, max_size=10),
    )
    def test_prepaid_equals_received_minus_balance(self, balance_data, quarter_data):
        """
        Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant

        For any combination of balance_data and quarter_data entries,
        the output always satisfies: prepaid_btw == received_btw - total_balance.
        """
        result = self.processor._calculate_btw_amounts(balance_data, quarter_data)

        # Core invariant: prepaid = received - total_balance
        expected_prepaid = result['received_btw'] - result['total_balance']
        assert abs(result['prepaid_btw'] - expected_prepaid) < 1e-9, (
            f"Invariant violated: prepaid_btw ({result['prepaid_btw']}) != "
            f"received_btw ({result['received_btw']}) - "
            f"total_balance ({result['total_balance']})"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        balance_data=st.lists(balance_entry_st, min_size=0, max_size=10),
        quarter_data=st.lists(quarter_entry_st, min_size=0, max_size=10),
    )
    def test_total_balance_equals_sum_of_balance_data(self, balance_data, quarter_data):
        """
        Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant

        The total_balance output always equals the sum of all amount values
        in balance_data.
        """
        result = self.processor._calculate_btw_amounts(balance_data, quarter_data)

        expected_total = sum(row['amount'] for row in balance_data)
        assert abs(result['total_balance'] - expected_total) < 1e-9, (
            f"total_balance ({result['total_balance']}) != "
            f"sum of balance_data amounts ({expected_total})"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        balance_data=st.lists(balance_entry_st, min_size=0, max_size=10),
        quarter_data=st.lists(quarter_entry_st, min_size=0, max_size=10),
    )
    def test_received_btw_only_includes_received_accounts(
        self, balance_data, quarter_data
    ):
        """
        Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant

        The received_btw output only sums amounts from quarter_data entries
        whose Reknum is in the received accounts set (2020, 2021).
        """
        result = self.processor._calculate_btw_amounts(balance_data, quarter_data)

        expected_received = sum(
            row['amount'] for row in quarter_data
            if row['Reknum'] in RECEIVED_ACCOUNTS
        )
        assert abs(result['received_btw'] - expected_received) < 1e-9, (
            f"received_btw ({result['received_btw']}) != "
            f"sum of received account amounts ({expected_received})"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        balance_data=st.lists(balance_entry_st, min_size=0, max_size=10),
        quarter_data=st.lists(quarter_entry_st, min_size=0, max_size=10),
    )
    def test_payment_instruction_matches_balance_sign(
        self, balance_data, quarter_data
    ):
        """
        Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant

        The payment_instruction always reflects the sign of total_balance:
        - Non-negative balance -> 'te ontvangen'
        - Negative balance -> 'te betalen'
        """
        result = self.processor._calculate_btw_amounts(balance_data, quarter_data)

        if result['total_balance'] >= 0:
            assert 'te ontvangen' in result['payment_instruction'], (
                f"Expected 'te ontvangen' for balance "
                f"{result['total_balance']}, "
                f"got: {result['payment_instruction']}"
            )
        else:
            assert 'te betalen' in result['payment_instruction'], (
                f"Expected 'te betalen' for balance "
                f"{result['total_balance']}, "
                f"got: {result['payment_instruction']}"
            )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        balance_data=st.lists(balance_entry_st, min_size=0, max_size=10),
        quarter_data=st.lists(quarter_entry_st, min_size=0, max_size=10),
    )
    def test_output_always_contains_required_keys(self, balance_data, quarter_data):
        """
        Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant

        The output dictionary always contains all four required keys
        regardless of input data.
        """
        result = self.processor._calculate_btw_amounts(balance_data, quarter_data)

        required_keys = {
            'total_balance', 'received_btw', 'prepaid_btw', 'payment_instruction',
        }
        assert required_keys.issubset(result.keys()), (
            f"Missing keys: {required_keys - set(result.keys())}"
        )
        # Numeric values are always numeric
        assert isinstance(result['total_balance'], (int, float))
        assert isinstance(result['received_btw'], (int, float))
        assert isinstance(result['prepaid_btw'], (int, float))
        assert isinstance(result['payment_instruction'], str)
