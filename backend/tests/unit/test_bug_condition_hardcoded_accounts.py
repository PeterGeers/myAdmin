"""
Bug Condition Exploration Tests — Hardcoded Account Resolution

Property 1: Bug Condition — All account resolution SHOULD use authoritative sources
(rekeningschema.parameters flags, TaxRateService, VW field) instead of hardcoded values.

These tests encode the EXPECTED (correct) behavior. They are written BEFORE any fix
and MUST FAIL on unfixed code — failure confirms the bug exists in each code path.

DO NOT attempt to fix the test or the code when it fails.

After the fix is implemented, these same tests will PASS, confirming the fix works.

Spec: .kiro/specs/ledger-account-hardcode-fix
Requirements: 2.3, 2.4, 2.5, 2.6, 2.7, 2.8
"""

import sys
import os
import inspect
import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock, call
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Strategies for Hypothesis
# ---------------------------------------------------------------------------

# Non-standard account numbers that differ from the hardcoded defaults
non_standard_revenue_account_st = st.sampled_from([
    '8100', '8200', '8500', '9001', '7777', '8888'
])

non_standard_vat_account_st = st.sampled_from([
    '2050', '2100', '2200', '2300', '2500', '2999'
])

# Transaction dates spanning before and after the hardcoded 2026-01-01 boundary
transaction_date_st = st.dates(
    min_value=date(2023, 1, 1),
    max_value=date(2028, 12, 31)
)

# VAT rates that differ from the hardcoded 9% and 21%
vat_rate_st = st.sampled_from([6.0, 9.0, 12.0, 15.0, 19.0, 21.0, 25.0])

# Vendor names for transaction logic tests
vendor_name_st = st.sampled_from([
    'TestVendor', 'Acme Corp', 'SupplierX', 'RandomShop',
    'OfficeDepot', 'CloudService', 'SaaSProvider'
])

# Administration/tenant names
admin_st = st.sampled_from([
    'TenantA', 'TenantB', 'CustomTenant', 'GoodwinSolutions'
])


# ---------------------------------------------------------------------------
# Test 1: STR Routes — Revenue Account Resolution
# Bug: hardcoded '8003' instead of querying $.str_revenue_account flag
# Requirement: 2.3
# ---------------------------------------------------------------------------

class TestSTRRevenueAccountResolution:
    """
    STR channel routes SHOULD resolve the revenue account from
    rekeningschema.parameters $.str_revenue_account flag, not hardcode '8003'.
    """

    def test_str_revenue_source_has_no_hardcoded_8003(self):
        """
        EXPECTED: The source code does NOT contain hardcoded '8003'.
        FAILS on unfixed code because '8003' is hardcoded as the revenue account.
        """
        from str_channel_routes import calculate_str_channel_revenue
        source = inspect.getsource(calculate_str_channel_revenue)

        has_hardcoded_8003 = "'8003'" in source or '"8003"' in source

        assert not has_hardcoded_8003, (
            "BUG: STR route hardcodes revenue account '8003' instead of "
            "querying rekeningschema for $.str_revenue_account flag"
        )

    def test_str_revenue_queries_rekeningschema_flag(self):
        """
        EXPECTED: The source code queries rekeningschema for
        $.str_revenue_account flag. FAILS on unfixed code.
        """
        from str_channel_routes import calculate_str_channel_revenue
        source = inspect.getsource(calculate_str_channel_revenue)

        has_flag_query = 'str_revenue_account' in source

        assert has_flag_query, (
            "BUG: STR route does not query rekeningschema.parameters for "
            "$.str_revenue_account flag to resolve the revenue account"
        )


# ---------------------------------------------------------------------------
# Test 2: STR Routes — VAT Rate Resolution
# Bug: date-branching on date(2026, 1, 1) instead of TaxRateService
# Requirement: 2.4
# ---------------------------------------------------------------------------

class TestSTRVATRateResolution:
    """
    STR channel routes SHOULD resolve VAT rate from TaxRateService,
    not use hardcoded date-branching on date(2026, 1, 1).
    """

    def test_str_vat_calls_tax_rate_service(self):
        """
        EXPECTED: The code calls TaxRateService.get_tax_rate() to determine
        the VAT rate. FAILS on unfixed code because the code uses
        hardcoded date comparison with date(2026, 1, 1).
        """
        # Inspect the source code of calculate_str_channel_revenue
        from str_channel_routes import calculate_str_channel_revenue
        source = inspect.getsource(calculate_str_channel_revenue)

        # BUG CONDITION: The source code contains hardcoded date branching
        has_date_branching = 'date(2026' in source or 'rate_change_date' in source
        has_tax_service = 'TaxRateService' in source or 'tax_rate_service' in source

        assert not has_date_branching, (
            "BUG: STR route uses hardcoded date-branching (date(2026, 1, 1)) "
            "for VAT rate instead of calling TaxRateService.get_tax_rate()"
        )
        assert has_tax_service, (
            "BUG: STR route does not use TaxRateService for VAT rate resolution"
        )

    def test_str_vat_no_hardcoded_accounts(self):
        """
        EXPECTED: VAT accounts are resolved from TaxRateService, not hardcoded.
        FAILS on unfixed code because '2020' and '2021' are hardcoded.
        """
        from str_channel_routes import calculate_str_channel_revenue
        source = inspect.getsource(calculate_str_channel_revenue)

        # BUG CONDITION: Hardcoded VAT account numbers in source
        has_hardcoded_2020 = "'2020'" in source or '"2020"' in source
        has_hardcoded_2021 = "'2021'" in source or '"2021"' in source

        assert not has_hardcoded_2020, (
            "BUG: STR route hardcodes VAT account '2020' instead of "
            "resolving from TaxRateService"
        )
        assert not has_hardcoded_2021, (
            "BUG: STR route hardcodes VAT account '2021' instead of "
            "resolving from TaxRateService"
        )


# ---------------------------------------------------------------------------
# Test 3: Transaction Logic — No Gamma Fallback
# Bug: silent fallback to "Gamma" transactions when 0 results found
# Requirement: 2.5
# ---------------------------------------------------------------------------

class TestTransactionLogicGammaFallback:
    """
    get_last_transactions() SHOULD return an error dict when no booking
    history exists, not silently fall back to "Gamma" transactions.
    """

    @settings(max_examples=20)
    @given(vendor=vendor_name_st, admin=admin_st)
    def test_zero_results_returns_error_not_gamma(self, vendor, admin):
        """
        EXPECTED: When no transactions found for a vendor, return an error dict
        with 'error': True. FAILS on unfixed code because it falls back to Gamma.
        """
        from transaction_logic import TransactionLogic
        from contextlib import contextmanager

        tl = TransactionLogic(test_mode=True)

        # Mock the database cursor to return 0 results for vendor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor

        # First query (vendor search): 0 results
        mock_cursor.fetchall.return_value = []

        @contextmanager
        def mock_get_cursor(**kwargs):
            yield mock_cursor, mock_conn

        tl.db = MagicMock()
        tl.db.get_cursor = mock_get_cursor

        result = tl.get_last_transactions(vendor, administration=admin)

        # BUG CONDITION: If result is a list (not an error dict), the code
        # silently fell back to Gamma transactions
        assert isinstance(result, dict), (
            f"BUG: get_last_transactions() returned a list (Gamma fallback) "
            f"instead of an error dict when no booking history exists for "
            f"vendor '{vendor}'. Got: {result}"
        )
        assert result.get('error') is True, (
            f"BUG: get_last_transactions() should return {{'error': True, ...}} "
            f"when no booking history exists. Got: {result}"
        )


# ---------------------------------------------------------------------------
# Test 4: Transaction Logic — Single Result VAT Account
# Bug: hardcoded '2010' VAT account for single-result case
# Requirement: 2.5
# ---------------------------------------------------------------------------

class TestTransactionLogicSingleResultVAT:
    """
    When exactly 1 transaction is found, the VAT account SHOULD come from
    TaxRateService, not be hardcoded as '2010'.
    """

    @settings(max_examples=20)
    @given(
        vendor=vendor_name_st,
        admin=admin_st,
        expected_vat_account=non_standard_vat_account_st,
    )
    def test_single_result_vat_from_service_not_hardcoded(
        self, vendor, admin, expected_vat_account
    ):
        """
        EXPECTED: When 1 transaction found, the created VAT line uses
        TaxRateService to resolve the VAT account. FAILS on unfixed code
        because it hardcodes '2010'.
        """
        from transaction_logic import TransactionLogic
        from contextlib import contextmanager

        tl = TransactionLogic(test_mode=True)

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor

        # Return exactly 1 result
        single_result = {
            'ID': 1, 'TransactionNumber': vendor,
            'TransactionDate': '2025-06-15',
            'TransactionDescription': f'{vendor} invoice',
            'TransactionAmount': 121.0,
            'Debet': '4100', 'Credit': '1300',
            'ReferenceNumber': vendor, 'Ref1': '', 'Ref2': '',
            'Ref3': '', 'Ref4': '', 'Administration': admin
        }
        mock_cursor.fetchall.return_value = [single_result]

        # Mock TaxRateService to return the expected VAT account
        mock_tax_svc = Mock()
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 21.0,
            'ledger_account': expected_vat_account,
            'description': 'BTW hoog'
        }

        @contextmanager
        def mock_get_cursor(**kwargs):
            yield mock_cursor, mock_conn

        tl.db = MagicMock()
        tl.db.get_cursor = mock_get_cursor

        with patch('services.tax_rate_service.TaxRateService', return_value=mock_tax_svc):
            result = tl.get_last_transactions(vendor, administration=admin)

        # Should have 2 results (original + created VAT line)
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        assert len(result) == 2, f"Expected 2 results, got {len(result)}"

        # The second (VAT) line should NOT have hardcoded '2010'
        vat_line = result[1]
        assert vat_line['Debet'] != '2010', (
            f"BUG: get_last_transactions() hardcodes VAT account '2010' "
            f"for single-result case instead of resolving from TaxRateService. "
            f"VAT line Debet = '{vat_line['Debet']}'"
        )
        # Verify it used the TaxRateService-resolved account
        assert vat_line['Debet'] == expected_vat_account, (
            f"VAT line should use account from TaxRateService "
            f"(expected '{expected_vat_account}', got '{vat_line['Debet']}')"
        )


# ---------------------------------------------------------------------------
# Test 5: Transaction Logic — No Vendor-Specific Overrides
# Bug: Coursera/Netflix-specific hardcoded account overrides
# Requirement: 2.5
# ---------------------------------------------------------------------------

class TestTransactionLogicVendorOverrides:
    """
    get_last_transactions() SHOULD NOT have vendor-specific hardcoded
    account overrides for Coursera, Netflix, or any other vendor.
    """

    def test_no_coursera_override_in_source(self):
        """
        EXPECTED: No Coursera-specific account overrides exist.
        FAILS on unfixed code because Coursera override exists.
        """
        from transaction_logic import TransactionLogic
        source = inspect.getsource(TransactionLogic.get_last_transactions)

        assert 'coursera' not in source.lower(), (
            "BUG: get_last_transactions() contains Coursera-specific "
            "hardcoded account overrides (6200/1600). Vendor-specific "
            "overrides should be removed — use DB accounts as template."
        )

    def test_no_netflix_override_in_source(self):
        """
        EXPECTED: No Netflix-specific account overrides exist.
        FAILS on unfixed code because Netflix override exists.
        """
        from transaction_logic import TransactionLogic
        source = inspect.getsource(TransactionLogic.get_last_transactions)

        assert 'netflix' not in source.lower(), (
            "BUG: get_last_transactions() contains Netflix-specific "
            "hardcoded account overrides (6400/1600). Vendor-specific "
            "overrides should be removed — use DB accounts as template."
        )

    def test_no_hardcoded_expense_accounts_in_overrides(self):
        """
        EXPECTED: No hardcoded expense account numbers (6200, 6400) in
        vendor-specific override blocks.
        """
        from transaction_logic import TransactionLogic
        source = inspect.getsource(TransactionLogic.get_last_transactions)

        # These specific accounts are only used in vendor overrides
        has_6200 = "'6200'" in source or '"6200"' in source
        has_6400 = "'6400'" in source or '"6400"' in source

        assert not has_6200, (
            "BUG: Hardcoded expense account '6200' found in "
            "get_last_transactions() — likely a vendor-specific override"
        )
        assert not has_6400, (
            "BUG: Hardcoded expense account '6400' found in "
            "get_last_transactions() — likely a vendor-specific override"
        )


# ---------------------------------------------------------------------------
# Test 6: Pattern Validation — Bank Account Flag
# Bug: hardcoded '< 1300' threshold instead of $.bank_account flag
# Requirement: 2.6
# ---------------------------------------------------------------------------

class TestPatternValidationBankAccountFlag:
    """
    get_patterns() SHOULD query rekeningschema for $.bank_account flag
    instead of using hardcoded '< 1300' threshold.
    """

    def test_get_patterns_uses_flag_not_threshold(self):
        """
        EXPECTED: get_patterns() query uses JSON_EXTRACT(parameters, '$.bank_account')
        instead of '< 1300'. FAILS on unfixed code because it uses the threshold.
        """
        from database import DatabaseManager as PatternDB

        source = inspect.getsource(PatternDB.get_patterns)

        has_threshold = "< '1300'" in source or "< 1300" in source or '<1300' in source
        has_flag_query = 'bank_account' in source and 'JSON_EXTRACT' in source

        assert not has_threshold, (
            "BUG: get_patterns() uses hardcoded threshold '< 1300' to identify "
            "bank accounts instead of querying rekeningschema for "
            "$.bank_account flag"
        )
        assert has_flag_query, (
            "BUG: get_patterns() does not query rekeningschema.parameters "
            "$.bank_account flag to identify bank accounts"
        )

    @settings(max_examples=10)
    @given(admin=admin_st)
    def test_get_patterns_query_contains_bank_account_flag(self, admin):
        """
        EXPECTED: The SQL query executed by get_patterns() references
        $.bank_account flag. FAILS on unfixed code.
        """
        from database import DatabaseManager as PatternDB

        db = PatternDB(test_mode=True)

        # Mock execute_query to capture the SQL
        captured_queries = []
        original_execute = db.execute_query

        def capture_query(query, params=None, **kwargs):
            captured_queries.append(query)
            return []

        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns(admin)

        assert len(captured_queries) > 0, "No query was executed"

        query = captured_queries[0]
        assert 'bank_account' in query, (
            f"BUG: get_patterns() query does not reference $.bank_account flag. "
            f"Query: {query}"
        )
        assert "< '1300'" not in query and '< 1300' not in query, (
            f"BUG: get_patterns() query uses hardcoded '< 1300' threshold. "
            f"Query: {query}"
        )


# ---------------------------------------------------------------------------
# Test 7: Aangifte IB — VW Field for P&L Classification
# Bug: Parent.startswith(('4','5','6','7','8','9')) instead of VW = 'Y'
# Requirement: 2.8
# ---------------------------------------------------------------------------

class TestAangifteIBVWField:
    """
    generate_table_rows() SHOULD use VW = 'Y' for P&L classification,
    not Parent.startswith(('4','5','6','7','8','9')).
    """

    def test_uses_vw_field_not_parent_prefix(self):
        """
        EXPECTED: Source code uses item.get('VW') == 'Y' for P&L detection.
        FAILS on unfixed code because it uses Parent.startswith().
        """
        from report_generators.aangifte_ib_generator import generate_table_rows
        source = inspect.getsource(generate_table_rows)

        has_parent_startswith = 'startswith' in source and (
            "'4'" in source or "'5'" in source or "'6'" in source
        )
        has_vw_check = "VW" in source and "'Y'" in source

        assert not has_parent_startswith, (
            "BUG: generate_table_rows() uses Parent.startswith() for P&L "
            "classification instead of VW = 'Y'"
        )
        assert has_vw_check, (
            "BUG: generate_table_rows() does not use VW field for P&L "
            "classification"
        )

    def test_vw_and_parent_disagree_uses_vw(self):
        """
        EXPECTED: When VW and Parent prefix disagree, VW wins.
        
        Scenario: Account with Parent='3500' (would be excluded by prefix check
        since 3 is not in 4-9) but VW='Y' (is a P&L account).
        
        FAILS on unfixed code because Parent.startswith() excludes it.
        """
        from report_generators.aangifte_ib_generator import generate_table_rows

        # Report data where VW and Parent prefix DISAGREE:
        # - Parent '3500' starts with '3' → excluded by prefix check (not 4-9)
        # - But VW = 'Y' → IS a P&L account
        report_data = [
            {
                'Parent': '3500',
                'Aangifte': 'Special P&L Item',
                'Amount': 500.0,
                'VW': 'Y'  # This IS a P&L account despite Parent prefix
            },
            {
                'Parent': '1000',
                'Aangifte': 'Balance Sheet Item',
                'Amount': 1000.0,
                'VW': 'N'  # This is NOT a P&L account
            }
        ]

        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []

        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='TestTenant',
            user_tenants=['TestTenant']
        )

        # Find the resultaat row
        resultaat_rows = [r for r in rows if r['row_type'] == 'resultaat']

        # The resultaat should include the 500.0 from the VW='Y' item
        # On unfixed code, Parent '3500' starts with '3' which is NOT in
        # ('4','5','6','7','8','9'), so it would be EXCLUDED → resultaat = 0
        # On fixed code, VW='Y' means it IS P&L → resultaat = 500.0
        assert len(resultaat_rows) == 1, (
            "BUG: No resultaat row generated. The P&L item with VW='Y' and "
            "Parent='3500' was likely excluded because Parent prefix '3' is "
            "not in ('4','5','6','7','8','9')"
        )
        assert resultaat_rows[0]['amount_raw'] == 500.0, (
            f"BUG: Resultaat should be 500.0 (from VW='Y' item) but got "
            f"{resultaat_rows[0]['amount_raw']}. The code likely uses "
            f"Parent.startswith() instead of VW='Y' for P&L classification."
        )

    @settings(max_examples=20)
    @given(
        pl_amount=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False),
        bs_amount=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False),
    )
    def test_resultaat_uses_vw_not_parent_for_various_amounts(
        self, pl_amount, bs_amount
    ):
        """
        EXPECTED: Resultaat calculation uses VW='Y' to identify P&L accounts.
        
        Generate report data where:
        - A P&L account has VW='Y' but Parent prefix '3' (not in 4-9)
        - A balance sheet account has VW='N' but Parent prefix '4' (in 4-9)
        
        If code uses Parent prefix: resultaat = bs_amount (wrong)
        If code uses VW field: resultaat = pl_amount (correct)
        """
        from report_generators.aangifte_ib_generator import generate_table_rows

        report_data = [
            {
                'Parent': '3500',       # Prefix '3' NOT in 4-9
                'Aangifte': 'P&L via VW',
                'Amount': pl_amount,
                'VW': 'Y'              # IS P&L
            },
            {
                'Parent': '4000',       # Prefix '4' IS in 4-9
                'Aangifte': 'BS via VW',
                'Amount': bs_amount,
                'VW': 'N'              # NOT P&L (balance sheet)
            }
        ]

        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []

        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='TestTenant',
            user_tenants=['TestTenant']
        )

        resultaat_rows = [r for r in rows if r['row_type'] == 'resultaat']

        # With VW-based logic: resultaat = pl_amount (only VW='Y' items)
        # With Parent-based logic: resultaat = bs_amount (only Parent 4-9 items)
        # These are different values, so we can detect which logic is used
        if resultaat_rows:
            resultaat_value = resultaat_rows[0]['amount_raw']
            # The resultaat should equal pl_amount (VW='Y' item), not bs_amount
            assert abs(resultaat_value - pl_amount) < 0.01, (
                f"BUG: Resultaat = {resultaat_value}, expected {pl_amount} "
                f"(from VW='Y' item). Got {bs_amount} instead, which means "
                f"the code uses Parent prefix instead of VW field."
            )
        else:
            # If no resultaat row, the P&L item was excluded entirely
            assert False, (
                f"BUG: No resultaat row. The VW='Y' item with amount "
                f"{pl_amount} was excluded, likely because Parent '3500' "
                f"doesn't start with 4-9."
            )
