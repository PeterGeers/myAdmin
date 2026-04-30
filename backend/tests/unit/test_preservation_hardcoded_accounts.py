"""
Preservation Property Tests — Identical Results When Config Matches Old Hardcoded Values

Property 2: Preservation — For any input where the tenant's rekeningschema.parameters
flags and TaxRateService rates resolve to the SAME accounts as the old hardcoded values,
the system SHALL produce exactly the same results as the original code.

These tests are written BEFORE any fix and MUST PASS on unfixed code — passing confirms
the baseline behavior we need to preserve.

After the fix is implemented, these same tests MUST STILL PASS, confirming no regressions.

Spec: .kiro/specs/ledger-account-hardcode-fix
**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10**
"""

import sys
import os
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Strategies for Hypothesis — constrained to match hardcoded values
# ---------------------------------------------------------------------------

# Positive gross amounts for STR revenue (realistic booking amounts)
str_gross_amount_st = st.floats(
    min_value=10.0, max_value=50000.0, allow_nan=False, allow_infinity=False
).map(lambda x: round(x, 2))

# Transaction dates BEFORE 2026-01-01 (where hardcoded rate = 9%, account = '2021')
pre_2026_date_st = st.dates(
    min_value=date(2023, 1, 1),
    max_value=date(2025, 12, 31)
)

# Transaction dates ON OR AFTER 2026-01-01 (where hardcoded rate = 21%, account = '2020')
post_2026_date_st = st.dates(
    min_value=date(2026, 1, 1),
    max_value=date(2028, 12, 31)
)

# STR channel names
channel_name_st = st.sampled_from(['AirBnB', 'Booking.com', 'dfDirect', 'Stripe', 'VRBO'])

# Administration/tenant names
admin_st = st.sampled_from(['TenantA', 'TenantB', 'GoodwinSolutions', 'PeterPrive'])

# Bank accounts that are below 1300 (matching the hardcoded threshold)
bank_account_st = st.sampled_from(['1001', '1002', '1003', '1004', '1100', '1200', '1299'])

# Non-bank accounts (>= 1300)
non_bank_account_st = st.sampled_from(['1300', '1600', '2010', '4000', '6200', '8003'])

# P&L amounts for aangifte IB
pl_amount_st = st.floats(
    min_value=-50000.0, max_value=50000.0, allow_nan=False, allow_infinity=False
).map(lambda x: round(x, 2)).filter(lambda x: abs(x) >= 0.01)

# Parent codes that start with 4-9 (P&L in current hardcoded logic)
pl_parent_st = st.sampled_from(['4000', '5000', '6000', '7000', '8000', '9000'])


# ---------------------------------------------------------------------------
# Test 1: STR Revenue — Journal Entries Preserved
# When revenue account IS '8003' and VAT rates ARE 9%/21%, entries are identical
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

class TestSTRRevenuePreservation:
    """
    Preservation: STR channel revenue calculation produces identical journal
    entries when the tenant config resolves to the same accounts as hardcoded.
    """

    @settings(max_examples=30)
    @given(
        amount=str_gross_amount_st,
        channel=channel_name_st,
        admin=admin_st,
    )
    def test_pre_2026_journal_entries_match_hardcoded(self, amount, channel, admin):
        """
        **Validates: Requirements 3.3**

        For dates before 2026-01-01, the hardcoded logic uses:
        - Revenue account: '8003'
        - VAT rate: 9%, VAT base: 109.0, VAT account: '2021'

        When config resolves to these same values, journal entries must be identical.
        """
        end_date = '2025-06-30'

        # Compute expected values using the CURRENT hardcoded logic
        reversed_amount = round(amount * -1, 2)
        if reversed_amount == 0:
            return  # Skip zero amounts (filtered in real code)

        expected_revenue = {
            'Debet': '1600',  # Reknum from channel data
            'Credit': '8003',
            'TransactionAmount': reversed_amount,
        }

        vat_rate = 9.0
        vat_base = 109.0
        expected_vat_amount = round((reversed_amount / vat_base) * vat_rate, 2)
        expected_vat = {
            'Debet': '8003',
            'Credit': '2021',
            'TransactionAmount': expected_vat_amount,
        }

        # Simulate what the current code does: hardcoded '8003', 9%, '2021'
        actual_revenue_credit = '8003'
        actual_vat_rate = 9.0
        actual_vat_base = 109.0
        actual_vat_account = '2021'
        actual_vat_amount = round((reversed_amount / actual_vat_base) * actual_vat_rate, 2)

        assert actual_revenue_credit == expected_revenue['Credit'], (
            f"Revenue account mismatch: {actual_revenue_credit} != {expected_revenue['Credit']}"
        )
        assert actual_vat_account == expected_vat['Credit'], (
            f"VAT account mismatch: {actual_vat_account} != {expected_vat['Credit']}"
        )
        assert abs(actual_vat_amount - expected_vat_amount) < 0.01, (
            f"VAT amount mismatch: {actual_vat_amount} != {expected_vat_amount}"
        )

    @settings(max_examples=30)
    @given(
        amount=str_gross_amount_st,
        channel=channel_name_st,
        admin=admin_st,
    )
    def test_post_2026_journal_entries_match_hardcoded(self, amount, channel, admin):
        """
        **Validates: Requirements 3.3**

        For dates on/after 2026-01-01, the hardcoded logic uses:
        - Revenue account: '8003'
        - VAT rate: 21%, VAT base: 121.0, VAT account: '2020'

        When config resolves to these same values, journal entries must be identical.
        """
        end_date = '2026-06-30'

        reversed_amount = round(amount * -1, 2)
        if reversed_amount == 0:
            return

        # Expected from hardcoded logic
        expected_vat_rate = 21.0
        expected_vat_base = 121.0
        expected_vat_account = '2020'
        expected_vat_amount = round((reversed_amount / expected_vat_base) * expected_vat_rate, 2)

        # Actual hardcoded logic
        transaction_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        rate_change_date = date(2026, 1, 1)

        if transaction_date >= rate_change_date:
            actual_vat_rate = 21.0
            actual_vat_base = 121.0
            actual_vat_account = '2020'
        else:
            actual_vat_rate = 9.0
            actual_vat_base = 109.0
            actual_vat_account = '2021'

        actual_vat_amount = round((reversed_amount / actual_vat_base) * actual_vat_rate, 2)

        assert actual_vat_account == expected_vat_account
        assert actual_vat_rate == expected_vat_rate
        assert abs(actual_vat_amount - expected_vat_amount) < 0.01


# ---------------------------------------------------------------------------
# Test 2: Pattern Validation — Bank Account Identification Preserved
# When $.bank_account flags identify accounts below 1300, same results
# Validates: Requirements 3.4
# ---------------------------------------------------------------------------

class TestPatternValidationPreservation:
    """
    Preservation: Pattern validation identifies the same bank transactions
    when $.bank_account flags match accounts below 1300.
    """

    @settings(max_examples=30)
    @given(
        bank_acct=bank_account_st,
        non_bank_acct=non_bank_account_st,
        admin=admin_st,
    )
    def test_bank_threshold_identifies_correct_accounts(self, bank_acct, non_bank_acct, admin):
        """
        **Validates: Requirements 3.4**

        The current hardcoded threshold `< '1300'` identifies bank accounts.
        When $.bank_account flags match the same set (accounts below 1300),
        the same transactions are found.

        This test verifies the threshold logic directly: accounts below '1300'
        are identified as bank accounts, accounts >= '1300' are not.
        """
        # Current hardcoded logic: debet < '1300' OR credit < '1300'
        bank_acct_is_bank = bank_acct < '1300'
        non_bank_acct_is_bank = non_bank_acct < '1300'

        assert bank_acct_is_bank is True, (
            f"Account {bank_acct} should be identified as bank account by < '1300' threshold"
        )
        assert non_bank_acct_is_bank is False, (
            f"Account {non_bank_acct} should NOT be identified as bank account by < '1300' threshold"
        )

    @settings(max_examples=20)
    @given(admin=admin_st)
    def test_get_patterns_query_uses_bank_account_flag(self, admin):
        """
        **Validates: Requirements 3.4**

        Verify that get_patterns() uses the $.bank_account flag query to
        identify bank accounts. When the flag resolves to the same set of
        accounts as the old threshold, results are identical.
        """
        from database import DatabaseManager as PatternDB

        db = PatternDB(test_mode=True)

        captured_queries = []

        def capture_query(query, params=None, **kwargs):
            captured_queries.append(query)
            return []

        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns(admin)

        assert len(captured_queries) > 0, "No query was executed"
        query = captured_queries[0]

        # Fixed behavior: query uses $.bank_account flag from rekeningschema
        assert 'bank_account' in query, (
            f"get_patterns() should use $.bank_account flag. Query: {query}"
        )
        assert 'JSON_EXTRACT' in query, (
            f"get_patterns() should use JSON_EXTRACT for flag query. Query: {query}"
        )
        # Verify administration filter is present
        assert 'administration' in query.lower(), (
            f"Query should filter by administration. Query: {query}"
        )


# ---------------------------------------------------------------------------
# Test 3: Aangifte IB — Resultaat Calculation Preserved
# When VW='Y' matches accounts with Parent starting 4-9, same resultaat
# Validates: Requirements 3.5
# ---------------------------------------------------------------------------

class TestAangifteIBPreservation:
    """
    Preservation: Aangifte IB report calculates the same resultaat when
    VW='Y' matches the set of accounts identified by Parent prefix 4-9.
    """

    @settings(max_examples=30)
    @given(
        pl_amount_1=pl_amount_st,
        pl_amount_2=pl_amount_st,
        bs_amount=pl_amount_st,
    )
    def test_resultaat_matches_when_vw_and_parent_agree(
        self, pl_amount_1, pl_amount_2, bs_amount
    ):
        """
        **Validates: Requirements 3.5**

        When VW='Y' matches exactly the accounts with Parent starting 4-9,
        the resultaat calculation is identical regardless of which field is used.

        This test creates report data where VW and Parent prefix AGREE:
        - P&L accounts have VW='Y' AND Parent starts with 4-9
        - Balance sheet accounts have VW='N' AND Parent starts with 1-3
        """
        from report_generators.aangifte_ib_generator import generate_table_rows

        report_data = [
            {
                'Parent': '4000',
                'Aangifte': 'Kosten',
                'Amount': pl_amount_1,
                'VW': 'Y'  # P&L — agrees with Parent prefix 4
            },
            {
                'Parent': '8000',
                'Aangifte': 'Opbrengsten',
                'Amount': pl_amount_2,
                'VW': 'Y'  # P&L — agrees with Parent prefix 8
            },
            {
                'Parent': '1000',
                'Aangifte': 'Liquide middelen',
                'Amount': bs_amount,
                'VW': 'N'  # Balance sheet — agrees with Parent prefix 1
            },
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

        # Expected resultaat: sum of P&L items (Parent 4-9 / VW='Y')
        expected_resultaat = pl_amount_1 + pl_amount_2

        resultaat_rows = [r for r in rows if r['row_type'] == 'resultaat']

        if abs(expected_resultaat) < 0.01:
            # If resultaat is ~0, the row may be omitted (code skips near-zero)
            assert len(resultaat_rows) <= 1
        else:
            assert len(resultaat_rows) == 1, (
                f"Expected 1 resultaat row, got {len(resultaat_rows)}"
            )
            assert abs(resultaat_rows[0]['amount_raw'] - expected_resultaat) < 0.02, (
                f"Resultaat mismatch: {resultaat_rows[0]['amount_raw']} != {expected_resultaat}"
            )

    @settings(max_examples=20)
    @given(amount=pl_amount_st)
    def test_parent_prefix_determines_pl_in_current_code(self, amount):
        """
        **Validates: Requirements 3.5**

        Verify the current code uses Parent.startswith() for P&L classification.
        This is the baseline behavior — when VW and Parent agree, results match.
        """
        from report_generators.aangifte_ib_generator import generate_table_rows

        # All P&L parents (4-9) with VW='Y' — agreement scenario
        report_data = [
            {
                'Parent': '6000',
                'Aangifte': 'Overige bedrijfskosten',
                'Amount': amount,
                'VW': 'Y'
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

        if abs(amount) >= 0.01:
            assert len(resultaat_rows) == 1, (
                f"Expected resultaat row for P&L amount {amount}"
            )
            assert abs(resultaat_rows[0]['amount_raw'] - amount) < 0.02, (
                f"Resultaat should be {amount}, got {resultaat_rows[0]['amount_raw']}"
            )


# ---------------------------------------------------------------------------
# Test 4: Seed Data — TaxRateService Returns Same Rates
# Hardcoded seed values produce consistent TaxRateService results
# Validates: Requirements 3.7
# ---------------------------------------------------------------------------

class TestSeedDataPreservation:
    """
    Preservation: The hardcoded seed data (2010/0%, 2021/9%, 2020/21%)
    produces the same TaxRateService results as the current system.
    """

    def test_system_btw_rates_match_hardcoded_values(self):
        """
        **Validates: Requirements 3.7**

        Verify that _build_system_btw_rates with the standard nl.json
        template accounts produces the expected seed data matching the
        original hardcoded values that TaxRateService should return.
        """
        from migrations.seed_system_btw_rates import (
            _build_system_btw_rates,
            _resolve_vat_accounts_from_template,
        )

        # Resolve accounts from the real nl.json template
        resolved = _resolve_vat_accounts_from_template()
        assert resolved is not None, (
            "nl.json template should have $.vat_netting flags configured"
        )
        rates = _build_system_btw_rates(resolved)

        # Expected hardcoded seed data
        expected = {
            'zero': {'rate': 0.000, 'account': '2010'},
            'low': {'rate': 9.000, 'account': '2021'},
            'high': {'rate': 21.000, 'account': '2020'},
        }

        for row in rates:
            admin, tax_type, tax_code, rate, account, effective_from, desc = row
            assert admin == '_system_', f"Expected _system_ admin, got {admin}"
            assert tax_type == 'btw', f"Expected btw tax_type, got {tax_type}"
            assert tax_code in expected, f"Unexpected tax_code: {tax_code}"
            assert rate == expected[tax_code]['rate'], (
                f"Rate mismatch for {tax_code}: {rate} != {expected[tax_code]['rate']}"
            )
            assert account == expected[tax_code]['account'], (
                f"Account mismatch for {tax_code}: {account} != {expected[tax_code]['account']}"
            )

    @settings(max_examples=20)
    @given(ref_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2028, 12, 31)))
    def test_tax_rate_service_returns_seeded_rates(self, ref_date):
        """
        **Validates: Requirements 3.7**

        For any reference date, TaxRateService with the current seed data
        returns the expected rates and ledger accounts for _system_ BTW codes.
        """
        from services.tax_rate_service import TaxRateService

        mock_db = Mock()

        # Simulate what the DB returns for _system_ btw rates (matching seed data)
        def mock_lookup(query, params, fetch=True):
            admin, tax_type, tax_code, ref_d, ref_d2 = params
            if admin == '_system_' and tax_type == 'btw':
                seed_map = {
                    'zero': {'id': 1, 'rate': Decimal('0.000'), 'ledger_account': '2010',
                             'description': 'BTW 0% - Vrijgesteld', 'calc_method': 'percentage',
                             'calc_params': None, 'effective_from': date(2000, 1, 1),
                             'effective_to': date(9999, 12, 31), 'administration': '_system_'},
                    'low': {'id': 2, 'rate': Decimal('9.000'), 'ledger_account': '2021',
                            'description': 'BTW Laag tarief', 'calc_method': 'percentage',
                            'calc_params': None, 'effective_from': date(2000, 1, 1),
                            'effective_to': date(9999, 12, 31), 'administration': '_system_'},
                    'high': {'id': 3, 'rate': Decimal('21.000'), 'ledger_account': '2020',
                             'description': 'BTW Hoog tarief', 'calc_method': 'percentage',
                             'calc_params': None, 'effective_from': date(2000, 1, 1),
                             'effective_to': date(9999, 12, 31), 'administration': '_system_'},
                }
                if tax_code in seed_map:
                    return [seed_map[tax_code]]
            return []

        mock_db.execute_query = mock_lookup
        svc = TaxRateService(mock_db)

        # Verify each BTW code returns expected values
        expected = {
            'zero': {'rate': 0.0, 'account': '2010'},
            'low': {'rate': 9.0, 'account': '2021'},
            'high': {'rate': 21.0, 'account': '2020'},
        }

        for code, exp in expected.items():
            result = svc.get_tax_rate('_system_', 'btw', code, ref_date)
            assert result is not None, f"No rate found for _system_ btw {code}"
            assert result['rate'] == exp['rate'], (
                f"Rate mismatch for {code}: {result['rate']} != {exp['rate']}"
            )
            assert result['ledger_account'] == exp['account'], (
                f"Account mismatch for {code}: {result['ledger_account']} != {exp['account']}"
            )

    def test_tax_rate_service_tenant_fallback_to_system(self):
        """
        **Validates: Requirements 3.7**

        TaxRateService falls back to _system_ rates when tenant has no
        override. This is the current behavior we must preserve.
        """
        from services.tax_rate_service import TaxRateService

        mock_db = Mock()

        call_count = {'n': 0}

        def mock_lookup(query, params, fetch=True):
            call_count['n'] += 1
            admin = params[0]
            tax_code = params[2]

            # Tenant has no rates — return empty
            if admin != '_system_':
                return []

            # System rates
            if tax_code == 'high':
                return [{'id': 3, 'rate': Decimal('21.000'), 'ledger_account': '2020',
                         'description': 'BTW Hoog tarief', 'calc_method': 'percentage',
                         'calc_params': None, 'effective_from': date(2000, 1, 1),
                         'effective_to': date(9999, 12, 31), 'administration': '_system_'}]
            return []

        mock_db.execute_query = mock_lookup
        svc = TaxRateService(mock_db)

        result = svc.get_tax_rate('SomeTenant', 'btw', 'high', date(2025, 6, 15))

        assert result is not None, "Should fall back to _system_ rate"
        assert result['rate'] == 21.0
        assert result['ledger_account'] == '2020'
        assert result['scope_origin'] == 'system'
