"""
Preservation Property Tests — Balance Closure-Aware Fix

Property 3: Preservation — Non-Balance-Sheet and Non-Boundary Queries Unchanged

These tests are written BEFORE the fix and MUST PASS on UNFIXED code.
They establish the baseline behavior that must be preserved after the fix.

After the fix is implemented, these same tests MUST STILL PASS, confirming
no regressions were introduced.

Spec: .kiro/specs/balance-closure-aware-fix
**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Preservation scope from design:
    All inputs where the bug condition does NOT hold are unaffected:
    - P&L queries (VW='Y') use period-based filtering regardless of closure state
    - Administrations with no closures use jaar <= target_year (full cumulation)
    - Querying a closed year returns jaar == target_year data only
    - Tenant isolation (administration = %s) always enforced
    - Fallback when year_closure_status table is empty
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from functools import wraps
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Years for testing
year_st = st.integers(min_value=2020, max_value=2027)

# Administration / tenant names
admin_st = st.sampled_from(['AdminA', 'AdminB', 'AdminC'])

# Account numbers (balance sheet VW='N')
balance_account_st = st.sampled_from(['1000', '1100', '1300', '1600', '2000'])

# Account numbers (P&L VW='Y')
pl_account_st = st.sampled_from(['4000', '4100', '6000', '6200', '8000'])

# Parent categories
parent_st = st.sampled_from(['Assets', 'Liabilities', 'Revenue', 'Expenses'])

# Account names
account_name_st = st.sampled_from(['Bank', 'Debtors', 'Sales', 'Costs', 'Equipment'])

# Amounts (non-zero)
amount_st = st.floats(min_value=-50000.0, max_value=50000.0,
                      allow_nan=False, allow_infinity=False).filter(lambda x: abs(x) > 0.01)

# Batch sizes
batch_size_st = st.integers(min_value=1, max_value=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cache_dataframe(rows):
    """Build a DataFrame matching the MutatiesCache schema from row dicts."""
    columns = ['Aangifte', 'TransactionNumber', 'TransactionDate',
               'TransactionDescription', 'Amount', 'Reknum', 'AccountName',
               'Parent', 'VW', 'jaar', 'kwartaal', 'maand', 'week',
               'ReferenceNumber', 'administration', 'Ref3', 'Ref4']
    if not rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows)
    # Ensure all columns exist
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]


def make_row(vw, jaar, amount, admin, reknum='1000', account_name='Bank',
             parent='Assets', aangifte='IB'):
    """Create a single row dict for the cache DataFrame."""
    return {
        'Aangifte': aangifte,
        'TransactionNumber': f'T-{jaar}-{reknum}',
        'TransactionDate': pd.Timestamp(f'{jaar}-06-15'),
        'TransactionDescription': f'Transaction {jaar}',
        'Amount': amount,
        'Reknum': reknum,
        'AccountName': account_name,
        'Parent': parent,
        'VW': vw,
        'jaar': jaar,
        'kwartaal': 2,
        'maand': 6,
        'week': 24,
        'ReferenceNumber': 'REF001',
        'administration': admin,
        'Ref3': '',
        'Ref4': '',
    }


def _passthrough_cognito(required_permissions=None, required_roles=None):
    """Mock cognito_required decorator that passes through."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['actuals_read']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    """Mock tenant_required decorator that passes through."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'AdminA'
            kwargs['user_tenants'] = ['AdminA', 'AdminB', 'AdminC']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def create_test_app_with_cache(cache_df, closed_years=None):
    """Create a Flask test app with mocked auth and a pre-loaded cache.

    Args:
        cache_df: DataFrame to use as cache data
        closed_years: list of closed year integers (default: empty)

    Returns:
        Flask test client
    """
    if closed_years is None:
        closed_years = []

    from flask import Flask

    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
        import importlib
        import actuals_routes as ar
        importlib.reload(ar)

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(ar.actuals_bp)

    # Mock cache and db
    mock_cache = MagicMock()
    mock_cache.get_data.return_value = cache_df

    mock_db = MagicMock()
    # Mock _get_closed_years to return the specified closed years
    mock_db.execute_query.return_value = [{'year': y} for y in closed_years]

    return app.test_client(), mock_cache, mock_db


# ===========================================================================
# Test Suite 1: P&L Queries (VW='Y') Unaffected by Closure State
# Validates: Requirements 3.1
# ===========================================================================

class TestPLQueriesPreservation:
    """
    P&L (VW='Y') queries use period-based filtering (year filter) regardless
    of whether closures exist. The actuals-profitloss endpoint filters by
    jaar.isin(year_list), never cumulating across years.

    These tests PASS on UNFIXED code and MUST continue to pass after the fix.
    """

    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2022, max_value=2026),
        amount1=amount_st,
        amount2=amount_st,
    )
    def test_pl_query_returns_only_target_year_data(
        self, target_year, amount1, amount2
    ):
        """
        **Validates: Requirements 3.1**

        For VW='Y' queries via actuals-profitloss, only data matching the
        requested year is returned, regardless of closure state.
        """
        # Build cache with P&L data across multiple years
        rows = [
            make_row('Y', target_year, amount1, 'AdminA', '4000', 'Sales', 'Revenue'),
            make_row('Y', target_year - 1, amount2, 'AdminA', '4000', 'Sales', 'Revenue'),
            make_row('Y', target_year + 1, 100.0, 'AdminA', '4000', 'Sales', 'Revenue'),
        ]
        cache_df = make_cache_dataframe(rows)

        # Even with closures defined, P&L should not be affected
        closed_years = [target_year - 1]

        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-profitloss?years={target_year}&administration=AdminA'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # Property: only target_year data returned
        for record in data['data']:
            assert record['jaar'] == target_year, (
                f"P&L query returned jaar={record['jaar']}, "
                f"expected only {target_year}"
            )


    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2022, max_value=2026),
        amount=amount_st,
    )
    def test_pl_query_with_closures_same_as_without(
        self, target_year, amount
    ):
        """
        **Validates: Requirements 3.1**

        P&L queries produce the same result whether or not closures exist
        for the administration. Closure state is irrelevant for VW='Y'.
        """
        rows = [
            make_row('Y', target_year, amount, 'AdminA', '4000', 'Sales', 'Revenue'),
            make_row('Y', target_year, amount * 0.5, 'AdminA', '6000', 'Costs', 'Expenses'),
        ]
        cache_df = make_cache_dataframe(rows)

        # Run with no closures
        client_no_closure, mock_cache1, mock_db1 = create_test_app_with_cache(
            cache_df, closed_years=[]
        )
        with patch('actuals_routes.get_cache', return_value=mock_cache1), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db1):
            resp_no_closure = client_no_closure.get(
                f'/actuals-profitloss?years={target_year}&administration=AdminA'
            )

        # Run with closures
        client_with_closure, mock_cache2, mock_db2 = create_test_app_with_cache(
            cache_df, closed_years=[target_year - 1]
        )
        with patch('actuals_routes.get_cache', return_value=mock_cache2), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db2):
            resp_with_closure = client_with_closure.get(
                f'/actuals-profitloss?years={target_year}&administration=AdminA'
            )

        # Property: results are identical regardless of closure state
        data_no = resp_no_closure.get_json()['data']
        data_with = resp_with_closure.get_json()['data']
        assert data_no == data_with, (
            "P&L results differ based on closure state — "
            "closures should NOT affect VW='Y' queries"
        )


# ===========================================================================
# Test Suite 2: No-Closure Administrations — Full Cumulation Preserved
# Validates: Requirements 3.5
# ===========================================================================

class TestNoCLosureFallbackPreservation:
    """
    When year_closure_status has no entries for the administration, balance
    sheet queries (VW='N') use jaar <= target_year (full cumulation). This
    is the correct behavior when no OpeningBalance records exist.

    These tests PASS on UNFIXED code and MUST continue to pass after the fix.
    """

    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2023, max_value=2026),
        amount_prior=amount_st,
        amount_target=amount_st,
    )
    def test_no_closures_balance_cumulates_all_years(
        self, target_year, amount_prior, amount_target
    ):
        """
        **Validates: Requirements 3.5**

        With no closures, actuals-balance (non-per_year) returns data
        cumulated from all years <= target_year.
        """
        rows = [
            make_row('N', target_year - 1, amount_prior, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', target_year, amount_target, 'AdminA', '1000', 'Bank', 'Assets'),
            # Future year should NOT be included
            make_row('N', target_year + 1, 999.0, 'AdminA', '1000', 'Bank', 'Assets'),
        ]
        cache_df = make_cache_dataframe(rows)

        # No closures
        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-balance?years={target_year}&administration=AdminA'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # Property: result includes cumulated amount from prior + target year
        expected_total = round(amount_prior + amount_target, 2)
        actual_records = data['data']

        # Find account 1000
        account_records = [r for r in actual_records if r['Reknum'] == '1000']

        if abs(expected_total) > 0.01:
            assert len(account_records) == 1, (
                f"Expected 1 record for account 1000, got {len(account_records)}"
            )
            actual_total = round(account_records[0]['Amount'], 2)
            assert actual_total == expected_total, (
                f"No-closure balance should cumulate all years <= {target_year}: "
                f"expected {expected_total}, got {actual_total}"
            )


    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2023, max_value=2026),
        amount_prior=amount_st,
        amount_target=amount_st,
    )
    def test_no_closures_per_year_mode_cumulates(
        self, target_year, amount_prior, amount_target
    ):
        """
        **Validates: Requirements 3.5**

        With no closures, actuals-balance per_year=true for an open year
        returns jaar <= year (full cumulation since all years are open).
        """
        rows = [
            make_row('N', target_year - 1, amount_prior, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', target_year, amount_target, 'AdminA', '1000', 'Bank', 'Assets'),
        ]
        cache_df = make_cache_dataframe(rows)

        # No closures — all years treated as open
        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-balance?years={target_year}&administration=AdminA&per_year=true'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # Property: result for target_year includes cumulated prior years
        expected_total = round(amount_prior + amount_target, 2)
        results = data['data']
        account_records = [r for r in results
                          if r['Reknum'] == '1000' and r['jaar'] == target_year]

        if abs(expected_total) > 0.01:
            assert len(account_records) == 1, (
                f"Expected 1 record for account 1000 year {target_year}, "
                f"got {len(account_records)}"
            )
            actual_total = round(account_records[0]['Amount'], 2)
            assert actual_total == expected_total, (
                f"No-closure per_year mode should cumulate: "
                f"expected {expected_total}, got {actual_total}"
            )


    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2023, max_value=2026),
        amount=amount_st,
    )
    def test_empty_closure_table_fallback_to_cumulative(
        self, target_year, amount
    ):
        """
        **Validates: Requirements 3.5**

        When _get_closed_years returns empty list (table empty or unreachable),
        all years are treated as open and full cumulation is used.
        """
        rows = [
            make_row('N', target_year - 2, amount * 0.3, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', target_year - 1, amount * 0.5, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', target_year, amount, 'AdminA', '1000', 'Bank', 'Assets'),
        ]
        cache_df = make_cache_dataframe(rows)

        # Simulate empty closure table
        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-balance?years={target_year}&administration=AdminA'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # Property: total includes ALL years <= target_year
        expected_total = round(amount * 0.3 + amount * 0.5 + amount, 2)
        results = data['data']
        account_records = [r for r in results if r['Reknum'] == '1000']

        if abs(expected_total) > 0.01:
            assert len(account_records) == 1
            actual_total = round(account_records[0]['Amount'], 2)
            assert actual_total == expected_total, (
                f"Empty closure table should fallback to full cumulation: "
                f"expected {expected_total}, got {actual_total}"
            )


# ===========================================================================
# Test Suite 3: Closed Year Queries — Single Year Data Only
# Validates: Requirements 3.2
# ===========================================================================

class TestClosedYearQueryPreservation:
    """
    When querying a year that is itself closed, actuals-balance per_year=true
    returns only data for jaar == target_year. This is already correct
    behavior and must remain unchanged.

    These tests PASS on UNFIXED code and MUST continue to pass after the fix.
    """

    @settings(max_examples=30, deadline=None)
    @given(
        closed_year=st.integers(min_value=2021, max_value=2024),
        amount_closed=amount_st,
        amount_other=amount_st,
    )
    def test_closed_year_returns_only_that_year(
        self, closed_year, amount_closed, amount_other
    ):
        """
        **Validates: Requirements 3.2**

        When target_year is in closed_years, per_year mode returns only
        transactions from that specific year (jaar == target_year).
        """
        rows = [
            make_row('N', closed_year - 1, amount_other, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', closed_year, amount_closed, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', closed_year + 1, amount_other * 0.5, 'AdminA', '1000', 'Bank', 'Assets'),
        ]
        cache_df = make_cache_dataframe(rows)

        # target_year is closed
        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[closed_year]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-balance?years={closed_year}&administration=AdminA&per_year=true'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # Property: closed year returns only that year's amount
        results = data['data']
        account_records = [r for r in results
                          if r['Reknum'] == '1000' and r['jaar'] == closed_year]

        if abs(amount_closed) > 0.01:
            assert len(account_records) == 1, (
                f"Expected 1 record for closed year {closed_year}, "
                f"got {len(account_records)}"
            )
            actual_amount = round(account_records[0]['Amount'], 2)
            expected_amount = round(amount_closed, 2)
            assert actual_amount == expected_amount, (
                f"Closed year should return only jaar=={closed_year} data: "
                f"expected {expected_amount}, got {actual_amount}"
            )


    @settings(max_examples=30, deadline=None)
    @given(
        closed_year=st.integers(min_value=2021, max_value=2024),
        amount=amount_st,
    )
    def test_closed_year_excludes_prior_year_data(
        self, closed_year, amount
    ):
        """
        **Validates: Requirements 3.2**

        For a closed year, prior year data is NOT included in the result.
        The closed year is self-contained.
        """
        rows = [
            make_row('N', closed_year - 1, 5000.0, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', closed_year, amount, 'AdminA', '1000', 'Bank', 'Assets'),
        ]
        cache_df = make_cache_dataframe(rows)

        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[closed_year]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-balance?years={closed_year}&administration=AdminA&per_year=true'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        results = data['data']
        account_records = [r for r in results if r['Reknum'] == '1000']

        if abs(amount) > 0.01:
            # Should NOT include prior year's 5000.0
            assert len(account_records) == 1
            actual = round(account_records[0]['Amount'], 2)
            assert actual == round(amount, 2), (
                f"Closed year should NOT include prior years: "
                f"expected {round(amount, 2)}, got {actual}"
            )

    @settings(max_examples=30, deadline=None)
    @given(
        closed_year=st.integers(min_value=2021, max_value=2024),
    )
    def test_closed_years_reported_in_response(self, closed_year):
        """
        **Validates: Requirements 3.2**

        The closedYears array in the per_year response includes the correct
        years from _get_closed_years.
        """
        rows = [
            make_row('N', closed_year, 100.0, 'AdminA', '1000', 'Bank', 'Assets'),
        ]
        cache_df = make_cache_dataframe(rows)

        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[closed_year]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-balance?years={closed_year}&administration=AdminA&per_year=true'
            )

        assert resp.status_code == 200
        data = resp.get_json()

        # Property: closedYears includes target year
        assert closed_year in data['closedYears'], (
            f"closedYears should include {closed_year}, got {data['closedYears']}"
        )


# ===========================================================================
# Test Suite 4: Tenant Isolation — No Cross-Tenant Data Leakage
# Validates: Requirements 3.3
# ===========================================================================

class TestTenantIsolationPreservation:
    """
    All queries enforce tenant isolation via administration filtering.
    No cross-tenant data leakage occurs regardless of closure state.

    These tests PASS on UNFIXED code and MUST continue to pass after the fix.
    """

    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2022, max_value=2026),
        amount_a=amount_st,
        amount_b=amount_st,
    )
    def test_balance_query_isolates_tenants(
        self, target_year, amount_a, amount_b
    ):
        """
        **Validates: Requirements 3.3**

        When querying actuals-balance for AdminA, data from AdminB is never
        included in the result.
        """
        rows = [
            make_row('N', target_year, amount_a, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', target_year, amount_b, 'AdminB', '1000', 'Bank', 'Assets'),
        ]
        cache_df = make_cache_dataframe(rows)

        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-balance?years={target_year}&administration=AdminA'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        results = data['data']
        account_records = [r for r in results if r['Reknum'] == '1000']

        if abs(amount_a) > 0.01:
            assert len(account_records) == 1
            actual = round(account_records[0]['Amount'], 2)
            # Property: only AdminA's data is in the result
            assert actual == round(amount_a, 2), (
                f"Tenant isolation violated: expected AdminA amount "
                f"{round(amount_a, 2)}, got {actual} "
                f"(AdminB amount was {round(amount_b, 2)})"
            )


    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2022, max_value=2026),
        amount_a=amount_st,
        amount_b=amount_st,
    )
    def test_pl_query_isolates_tenants(
        self, target_year, amount_a, amount_b
    ):
        """
        **Validates: Requirements 3.3**

        When querying actuals-profitloss for AdminA, data from AdminB is
        never included in the result.
        """
        rows = [
            make_row('Y', target_year, amount_a, 'AdminA', '4000', 'Sales', 'Revenue'),
            make_row('Y', target_year, amount_b, 'AdminB', '4000', 'Sales', 'Revenue'),
        ]
        cache_df = make_cache_dataframe(rows)

        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-profitloss?years={target_year}&administration=AdminA'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        results = data['data']
        account_records = [r for r in results if r['Reknum'] == '4000']

        if abs(amount_a) > 0.01:
            assert len(account_records) == 1
            actual = round(account_records[0]['Amount'], 2)
            assert actual == round(amount_a, 2), (
                f"P&L tenant isolation violated: expected AdminA amount "
                f"{round(amount_a, 2)}, got {actual}"
            )

    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2022, max_value=2026),
        amount_a=amount_st,
        amount_b=amount_st,
    )
    def test_per_year_balance_isolates_tenants(
        self, target_year, amount_a, amount_b
    ):
        """
        **Validates: Requirements 3.3**

        When querying actuals-balance per_year=true for AdminA, data from
        AdminB is never included in the result.
        """
        rows = [
            make_row('N', target_year, amount_a, 'AdminA', '1000', 'Bank', 'Assets'),
            make_row('N', target_year, amount_b, 'AdminB', '1000', 'Bank', 'Assets'),
        ]
        cache_df = make_cache_dataframe(rows)

        client, mock_cache, mock_db = create_test_app_with_cache(
            cache_df, closed_years=[]
        )

        with patch('actuals_routes.get_cache', return_value=mock_cache), \
             patch('actuals_routes.DatabaseManager', return_value=mock_db):
            resp = client.get(
                f'/actuals-balance?years={target_year}&administration=AdminA&per_year=true'
            )

        assert resp.status_code == 200
        data = resp.get_json()
        results = data['data']
        account_records = [r for r in results
                          if r['Reknum'] == '1000' and r['jaar'] == target_year]

        if abs(amount_a) > 0.01:
            assert len(account_records) == 1
            actual = round(account_records[0]['Amount'], 2)
            assert actual == round(amount_a, 2), (
                f"Per-year tenant isolation violated: expected AdminA amount "
                f"{round(amount_a, 2)}, got {actual}"
            )


    @settings(max_examples=30, deadline=None)
    @given(
        target_year=st.integers(min_value=2022, max_value=2026),
        amount=amount_st,
    )
    def test_aangifte_ib_isolates_tenants(
        self, target_year, amount
    ):
        """
        **Validates: Requirements 3.3**

        MutatiesCache.query_aangifte_ib() enforces tenant isolation via
        administration exact match filtering.
        """
        from mutaties_cache import MutatiesCache

        rows = [
            make_row('N', target_year, amount, 'AdminA', '1000', 'Bank', 'Assets', 'IB'),
            make_row('N', target_year, 9999.0, 'AdminB', '1000', 'Bank', 'Assets', 'IB'),
        ]
        cache_df = make_cache_dataframe(rows)

        cache = MutatiesCache()
        cache.data = cache_df

        result = cache.query_aangifte_ib(
            year=target_year,
            administration='AdminA',
            user_tenants=['AdminA', 'AdminB'],
        )

        # Property: only AdminA data in result
        total_amount = sum(r['Amount'] for r in result)
        assert round(total_amount, 2) == round(amount, 2), (
            f"Aangifte IB tenant isolation violated: expected {round(amount, 2)}, "
            f"got {round(total_amount, 2)} (AdminB had 9999.0)"
        )
