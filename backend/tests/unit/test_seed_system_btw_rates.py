"""
Tests for seed_system_btw_rates.py — verifies that the seed script resolves
VAT ledger accounts from the nl.json template instead of hardcoding them.

Requirements: 2.9, 3.7
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, call, patch

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'migrations'))

from migrations.seed_system_btw_rates import (
    _resolve_vat_accounts_from_template,
    _build_system_btw_rates,
    _FALLBACK_ACCOUNTS,
    run_seed,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'src',
    'templates', 'chart_of_accounts', 'nl.json'
)


@pytest.fixture
def real_template_path():
    """Path to the actual nl.json template."""
    return TEMPLATE_PATH


@pytest.fixture
def minimal_template():
    """A minimal nl.json-like template with only VAT accounts."""
    return [
        {
            "Account": "2010",
            "AccountName": "Betaalde BTW",
            "parameters": {"vat_netting": True, "vat_primary": "2010"}
        },
        {
            "Account": "2020",
            "AccountName": "Ontvangen BTW Hoog",
            "parameters": {"vat_netting": True, "vat_primary": "2010"}
        },
        {
            "Account": "2021",
            "AccountName": "Ontvangen BTW Laag",
            "parameters": {"vat_netting": True, "vat_primary": "2010"}
        },
    ]


@pytest.fixture
def custom_numbered_template():
    """A template with non-standard account numbers (different tenant)."""
    return [
        {
            "Account": "5510",
            "AccountName": "Betaalde BTW",
            "parameters": {"vat_netting": True, "vat_primary": "5510"}
        },
        {
            "Account": "5520",
            "AccountName": "Ontvangen BTW Hoog",
            "parameters": {"vat_netting": True, "vat_primary": "5510"}
        },
        {
            "Account": "5521",
            "AccountName": "Ontvangen BTW Laag",
            "parameters": {"vat_netting": True, "vat_primary": "5510"}
        },
    ]


def _write_temp_template(data):
    """Write template data to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.json', delete=False, encoding='utf-8'
    )
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Test: _resolve_vat_accounts_from_template
# ---------------------------------------------------------------------------

class TestResolveVatAccountsFromTemplate:
    """Tests for the template resolution function."""

    def test_resolves_from_real_template(self, real_template_path):
        """Req 2.9: Seed script resolves accounts from nl.json template."""
        result = _resolve_vat_accounts_from_template(real_template_path)
        assert result is not None
        assert result['zero'] == '2010'
        assert result['low'] == '2021'
        assert result['high'] == '2020'

    def test_resolves_from_minimal_template(self, minimal_template):
        """Resolves correctly from a minimal template with only VAT accounts."""
        path = _write_temp_template(minimal_template)
        try:
            result = _resolve_vat_accounts_from_template(path)
            assert result == {'zero': '2010', 'low': '2021', 'high': '2020'}
        finally:
            os.unlink(path)

    def test_resolves_custom_account_numbers(self, custom_numbered_template):
        """Resolves correctly when tenant uses non-standard account numbers."""
        path = _write_temp_template(custom_numbered_template)
        try:
            result = _resolve_vat_accounts_from_template(path)
            assert result == {'zero': '5510', 'low': '5521', 'high': '5520'}
        finally:
            os.unlink(path)

    def test_returns_none_for_missing_file(self):
        """Fallback: returns None when template file does not exist."""
        result = _resolve_vat_accounts_from_template('/nonexistent/path/nl.json')
        assert result is None

    def test_returns_none_for_invalid_json(self):
        """Fallback: returns None when template contains invalid JSON."""
        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        )
        tmp.write('not valid json {{{')
        tmp.close()
        try:
            result = _resolve_vat_accounts_from_template(tmp.name)
            assert result is None
        finally:
            os.unlink(tmp.name)

    def test_returns_none_when_no_vat_netting_flags(self):
        """Fallback: returns None when no accounts have $.vat_netting flag."""
        template = [
            {"Account": "1002", "AccountName": "Bank", "parameters": {"bank_account": True}},
            {"Account": "8001", "AccountName": "Revenue", "parameters": {"revenue_account": True}},
        ]
        path = _write_temp_template(template)
        try:
            result = _resolve_vat_accounts_from_template(path)
            assert result is None
        finally:
            os.unlink(path)

    def test_returns_none_when_partial_vat_accounts(self):
        """Fallback: returns None when only some VAT codes can be resolved."""
        template = [
            {
                "Account": "2010",
                "AccountName": "Betaalde BTW",
                "parameters": {"vat_netting": True, "vat_primary": "2010"}
            },
            # Missing 'Ontvangen BTW Hoog' and 'Ontvangen BTW Laag'
        ]
        path = _write_temp_template(template)
        try:
            result = _resolve_vat_accounts_from_template(path)
            assert result is None
        finally:
            os.unlink(path)

    def test_ignores_accounts_with_null_parameters(self):
        """Accounts with null parameters are skipped."""
        template = [
            {"Account": "1001", "AccountName": "Kas", "parameters": None},
            {
                "Account": "2010",
                "AccountName": "Betaalde BTW",
                "parameters": {"vat_netting": True, "vat_primary": "2010"}
            },
            {
                "Account": "2020",
                "AccountName": "Ontvangen BTW Hoog",
                "parameters": {"vat_netting": True, "vat_primary": "2010"}
            },
            {
                "Account": "2021",
                "AccountName": "Ontvangen BTW Laag",
                "parameters": {"vat_netting": True, "vat_primary": "2010"}
            },
        ]
        path = _write_temp_template(template)
        try:
            result = _resolve_vat_accounts_from_template(path)
            assert result is not None
            assert result['zero'] == '2010'
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Test: _build_system_btw_rates
# ---------------------------------------------------------------------------

class TestBuildSystemBtwRates:
    """Tests for the rate tuple builder."""

    def test_builds_correct_tuples(self):
        """Builds seed tuples with resolved account numbers."""
        accounts = {'zero': '2010', 'low': '2021', 'high': '2020'}
        rates = _build_system_btw_rates(accounts)
        assert len(rates) == 3

        # Check each rate tuple
        zero = [r for r in rates if r[2] == 'zero'][0]
        low = [r for r in rates if r[2] == 'low'][0]
        high = [r for r in rates if r[2] == 'high'][0]

        assert zero[3] == 0.000
        assert zero[4] == '2010'
        assert low[3] == 9.000
        assert low[4] == '2021'
        assert high[3] == 21.000
        assert high[4] == '2020'

    def test_builds_with_custom_accounts(self):
        """Builds seed tuples with non-standard account numbers."""
        accounts = {'zero': '5510', 'low': '5521', 'high': '5520'}
        rates = _build_system_btw_rates(accounts)

        zero = [r for r in rates if r[2] == 'zero'][0]
        low = [r for r in rates if r[2] == 'low'][0]
        high = [r for r in rates if r[2] == 'high'][0]

        assert zero[4] == '5510'
        assert low[4] == '5521'
        assert high[4] == '5520'

    def test_all_tuples_are_system_administration(self):
        """All seed tuples use '_system_' administration."""
        accounts = {'zero': '2010', 'low': '2021', 'high': '2020'}
        rates = _build_system_btw_rates(accounts)
        for rate in rates:
            assert rate[0] == '_system_'
            assert rate[1] == 'btw'


# ---------------------------------------------------------------------------
# Test: run_seed
# ---------------------------------------------------------------------------

class TestRunSeed:
    """Tests for the main run_seed function."""

    def test_uses_template_accounts(self, real_template_path):
        """Req 2.9: run_seed resolves accounts from nl.json template."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = 1  # simulate successful insert

        run_seed(db=mock_db, template_path=real_template_path)

        # Verify execute_query was called with resolved accounts
        calls = mock_db.execute_query.call_args_list
        assert len(calls) == 3

        # Extract ledger accounts from the calls
        inserted_accounts = set()
        for c in calls:
            row = c[0][1]  # second positional arg is the tuple
            inserted_accounts.add(row[4])  # index 4 is ledger_account

        assert '2010' in inserted_accounts  # zero
        assert '2021' in inserted_accounts  # low
        assert '2020' in inserted_accounts  # high

    def test_fallback_when_template_missing(self):
        """Req 2.9: Falls back to hardcoded accounts with warning when template missing."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = 1

        run_seed(db=mock_db, template_path='/nonexistent/path/nl.json')

        calls = mock_db.execute_query.call_args_list
        assert len(calls) == 3

        inserted_accounts = set()
        for c in calls:
            row = c[0][1]
            inserted_accounts.add(row[4])

        # Should use fallback accounts
        assert inserted_accounts == {'2010', '2021', '2020'}

    def test_idempotent_skips_existing(self, real_template_path):
        """Seed is idempotent — skips rows that already exist."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = 0  # simulate INSERT IGNORE skip

        result = run_seed(db=mock_db, template_path=real_template_path)
        assert result == 0  # nothing inserted

    def test_counts_inserted_rows(self, real_template_path):
        """Returns count of actually inserted rows."""
        mock_db = MagicMock()
        # First two succeed, third already exists
        mock_db.execute_query.side_effect = [1, 1, 0]

        result = run_seed(db=mock_db, template_path=real_template_path)
        assert result == 2

    def test_uses_insert_ignore(self, real_template_path):
        """SQL uses INSERT IGNORE for idempotency."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = 1

        run_seed(db=mock_db, template_path=real_template_path)

        sql = mock_db.execute_query.call_args_list[0][0][0]
        assert 'INSERT IGNORE' in sql


# ---------------------------------------------------------------------------
# Test: Preservation — TaxRateService returns same rates after seed (Req 3.7)
# ---------------------------------------------------------------------------

class TestPreservation:
    """
    Req 3.7: Verify that the resolved accounts from the template match
    the previously hardcoded values, ensuring TaxRateService returns
    the same rates and ledger accounts after seed.
    """

    def test_template_resolves_to_same_as_hardcoded(self, real_template_path):
        """
        The real nl.json template should resolve to the same accounts
        as the old hardcoded values, preserving existing behavior.
        """
        resolved = _resolve_vat_accounts_from_template(real_template_path)
        assert resolved is not None
        assert resolved['zero'] == _FALLBACK_ACCOUNTS['zero']
        assert resolved['low'] == _FALLBACK_ACCOUNTS['low']
        assert resolved['high'] == _FALLBACK_ACCOUNTS['high']

    def test_seed_tuples_match_original_hardcoded(self, real_template_path):
        """
        Seed tuples built from the template should produce identical
        data to the original hardcoded SYSTEM_BTW_RATES.
        """
        resolved = _resolve_vat_accounts_from_template(real_template_path)
        rates = _build_system_btw_rates(resolved)

        # Original hardcoded values
        expected = [
            ('_system_', 'btw', 'zero', 0.000, '2010', '2000-01-01', 'BTW 0% - Vrijgesteld'),
            ('_system_', 'btw', 'low', 9.000, '2021', '2000-01-01', 'BTW Laag tarief'),
            ('_system_', 'btw', 'high', 21.000, '2020', '2000-01-01', 'BTW Hoog tarief'),
        ]

        assert rates == expected

    def test_fallback_accounts_match_original(self):
        """Fallback accounts are identical to the original hardcoded values."""
        assert _FALLBACK_ACCOUNTS == {
            'zero': '2010',
            'low': '2021',
            'high': '2020',
        }
