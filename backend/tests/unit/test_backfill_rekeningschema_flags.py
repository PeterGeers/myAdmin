"""
Tests for the backfill_rekeningschema_flags migration script.

Validates:
- Migration is idempotent (running twice produces same result)
- Existing parameters values are preserved (vat_netting, vat_primary, etc.)
- New flags are correctly set based on account roles
- Migration handles tenants with different account numbering
- btw_rate is correctly assigned (high/low/zero)

Requirements: 2.8, 2.10
"""

import json
import os
import sys
import pytest
from unittest.mock import Mock, patch, call

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_db(tenants=None, execute_side_effects=None):
    """
    Create a mock DatabaseManager.

    Args:
        tenants: list of administration names returned by get_all_tenants query
        execute_side_effects: list of return values for successive execute_query calls
    """
    db = Mock()
    if tenants is not None:
        # First call is get_all_tenants
        tenant_rows = [{'administration': t} for t in tenants]
        if execute_side_effects:
            db.execute_query.side_effect = [tenant_rows] + execute_side_effects
        else:
            db.execute_query.return_value = tenant_rows
    return db


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestMigrationImports:
    """Verify the migration module is importable and has expected functions."""

    def test_module_importable(self):
        from migrations.backfill_rekeningschema_flags import run_migration
        assert callable(run_migration)

    def test_has_get_all_tenants(self):
        from migrations.backfill_rekeningschema_flags import get_all_tenants
        assert callable(get_all_tenants)

    def test_has_backfill_tenant(self):
        from migrations.backfill_rekeningschema_flags import backfill_tenant
        assert callable(backfill_tenant)

    def test_has_backfill_bank_account_flag(self):
        from migrations.backfill_rekeningschema_flags import backfill_bank_account_flag
        assert callable(backfill_bank_account_flag)

    def test_has_backfill_expense_account_flag(self):
        from migrations.backfill_rekeningschema_flags import backfill_expense_account_flag
        assert callable(backfill_expense_account_flag)

    def test_has_backfill_revenue_account_flag(self):
        from migrations.backfill_rekeningschema_flags import backfill_revenue_account_flag
        assert callable(backfill_revenue_account_flag)

    def test_has_backfill_str_revenue_account_flag(self):
        from migrations.backfill_rekeningschema_flags import backfill_str_revenue_account_flag
        assert callable(backfill_str_revenue_account_flag)

    def test_has_backfill_btw_rate_flag(self):
        from migrations.backfill_rekeningschema_flags import backfill_btw_rate_flag
        assert callable(backfill_btw_rate_flag)


# ---------------------------------------------------------------------------
# get_all_tenants
# ---------------------------------------------------------------------------

class TestGetAllTenants:
    """Test tenant discovery."""

    def test_returns_tenant_names(self):
        from migrations.backfill_rekeningschema_flags import get_all_tenants
        db = Mock()
        db.execute_query.return_value = [
            {'administration': 'TenantA'},
            {'administration': 'TenantB'},
        ]
        result = get_all_tenants(db)
        assert result == ['TenantA', 'TenantB']

    def test_returns_empty_list_when_no_tenants(self):
        from migrations.backfill_rekeningschema_flags import get_all_tenants
        db = Mock()
        db.execute_query.return_value = []
        result = get_all_tenants(db)
        assert result == []

    def test_returns_empty_list_when_none(self):
        from migrations.backfill_rekeningschema_flags import get_all_tenants
        db = Mock()
        db.execute_query.return_value = None
        result = get_all_tenants(db)
        assert result == []


# ---------------------------------------------------------------------------
# SQL generation / flag setting
# ---------------------------------------------------------------------------

class TestJsonSetFlag:
    """Test the _json_set_flag helper generates correct SQL."""

    def test_boolean_flag_generates_cast_json(self):
        from migrations.backfill_rekeningschema_flags import _json_set_flag
        db = Mock()
        db.execute_query.return_value = 3

        result = _json_set_flag(
            db, 'TestTenant', "VW = 'N'", [], 'bank_account', True
        )

        assert result == 3
        sql_call = db.execute_query.call_args
        sql = sql_call[0][0]
        params = sql_call[0][1]

        # SQL should use JSON_SET with COALESCE
        assert 'JSON_SET' in sql
        assert 'COALESCE(parameters' in sql
        assert '$.bank_account' in sql
        assert 'administration = %s' in sql
        # Params: value_param ('true') + administration + where_params
        assert 'true' in params
        assert 'TestTenant' in params

    def test_string_flag_generates_plain_param(self):
        from migrations.backfill_rekeningschema_flags import _json_set_flag
        db = Mock()
        db.execute_query.return_value = 2

        result = _json_set_flag(
            db, 'TestTenant', "VW = 'Y'", [], 'btw_rate', 'high'
        )

        assert result == 2
        sql_call = db.execute_query.call_args
        params = sql_call[0][1]
        assert 'high' in params

    def test_dry_run_does_not_execute(self):
        from migrations.backfill_rekeningschema_flags import _json_set_flag
        db = Mock()

        result = _json_set_flag(
            db, 'TestTenant', "VW = 'N'", [], 'bank_account', True,
            dry_run=True
        )

        assert result == 0
        db.execute_query.assert_not_called()

    def test_returns_zero_when_no_rows_affected(self):
        from migrations.backfill_rekeningschema_flags import _json_set_flag
        db = Mock()
        db.execute_query.return_value = None

        result = _json_set_flag(
            db, 'TestTenant', "VW = 'N'", [], 'bank_account', True
        )
        assert result == 0


# ---------------------------------------------------------------------------
# Bank account flag
# ---------------------------------------------------------------------------

class TestBackfillBankAccountFlag:
    """Test bank account flag backfill logic."""

    def test_sql_uses_pattern_and_vw_and_belastingaangifte(self):
        from migrations.backfill_rekeningschema_flags import backfill_bank_account_flag
        db = Mock()
        db.execute_query.return_value = 2

        backfill_bank_account_flag(db, 'TestTenant')

        sql = db.execute_query.call_args[0][0]
        assert "VW = 'N'" in sql
        assert 'Pattern = 1' in sql
        assert "Belastingaangifte = 'Liquide middelen'" in sql
        assert '$.bank_account' in sql

    def test_skips_accounts_already_flagged(self):
        """SQL should include condition to skip already-flagged accounts."""
        from migrations.backfill_rekeningschema_flags import backfill_bank_account_flag
        db = Mock()
        db.execute_query.return_value = 0

        backfill_bank_account_flag(db, 'TestTenant')

        sql = db.execute_query.call_args[0][0]
        # Should check that bank_account is NULL or not true
        assert 'JSON_EXTRACT(parameters' in sql
        assert 'bank_account' in sql


# ---------------------------------------------------------------------------
# Expense account flag
# ---------------------------------------------------------------------------

class TestBackfillExpenseAccountFlag:
    """Test expense account flag backfill logic."""

    def test_sql_uses_vw_y_and_excludes_revenue_parent(self):
        from migrations.backfill_rekeningschema_flags import backfill_expense_account_flag
        db = Mock()
        db.execute_query.return_value = 15

        backfill_expense_account_flag(db, 'TestTenant')

        sql = db.execute_query.call_args[0][0]
        assert "VW = 'Y'" in sql
        assert "Parent NOT LIKE '8%'" in sql
        assert '$.expense_account' in sql


# ---------------------------------------------------------------------------
# Revenue account flag
# ---------------------------------------------------------------------------

class TestBackfillRevenueAccountFlag:
    """Test revenue account flag backfill logic."""

    def test_sql_uses_vw_y_and_revenue_indicators(self):
        from migrations.backfill_rekeningschema_flags import backfill_revenue_account_flag
        db = Mock()
        db.execute_query.return_value = 6

        backfill_revenue_account_flag(db, 'TestTenant')

        sql = db.execute_query.call_args[0][0]
        assert "VW = 'Y'" in sql
        assert "Opbrengsten" in sql
        assert '$.revenue_account' in sql


# ---------------------------------------------------------------------------
# STR revenue account flag
# ---------------------------------------------------------------------------

class TestBackfillStrRevenueAccountFlag:
    """Test STR revenue account (singleton) flag backfill logic."""

    def test_sql_matches_verhuur_by_name(self):
        from migrations.backfill_rekeningschema_flags import backfill_str_revenue_account_flag
        db = Mock()
        db.execute_query.return_value = 1

        backfill_str_revenue_account_flag(db, 'TestTenant')

        sql = db.execute_query.call_args[0][0]
        assert '%verhuur%' in sql.lower() or 'verhuur' in sql.lower()
        assert '$.str_revenue_account' in sql

    def test_warns_when_multiple_accounts_match(self):
        """Singleton flag should warn if more than 1 account matches."""
        from migrations.backfill_rekeningschema_flags import backfill_str_revenue_account_flag
        db = Mock()
        db.execute_query.return_value = 3  # 3 rows — unexpected

        import logging
        with patch.object(logging.getLogger('migrations.backfill_rekeningschema_flags'),
                          'warning') as mock_warn:
            backfill_str_revenue_account_flag(db, 'TestTenant')
            # Should have logged a warning about multiple matches
            assert mock_warn.called


# ---------------------------------------------------------------------------
# BTW rate flag
# ---------------------------------------------------------------------------

class TestBackfillBtwRateFlag:
    """Test btw_rate flag assignment logic."""

    def test_sets_low_for_verhuur(self):
        from migrations.backfill_rekeningschema_flags import backfill_btw_rate_flag
        db = Mock()
        # Three calls: low, zero, high
        db.execute_query.side_effect = [1, 0, 0]

        total = backfill_btw_rate_flag(db, 'TestTenant')

        # First call should be for 'low' rate
        first_sql = db.execute_query.call_args_list[0][0][0]
        assert '%verhuur%' in first_sql.lower() or 'verhuur' in first_sql.lower()
        assert total == 1

    def test_sets_zero_for_interest_and_dividend(self):
        from migrations.backfill_rekeningschema_flags import backfill_btw_rate_flag
        db = Mock()
        db.execute_query.side_effect = [0, 3, 0]

        total = backfill_btw_rate_flag(db, 'TestTenant')

        # Second call should be for 'zero' rate
        second_sql = db.execute_query.call_args_list[1][0][0]
        assert 'rente' in second_sql.lower() or 'dividend' in second_sql.lower()
        assert total == 3

    def test_sets_high_for_remaining_revenue(self):
        from migrations.backfill_rekeningschema_flags import backfill_btw_rate_flag
        db = Mock()
        db.execute_query.side_effect = [0, 0, 2]

        total = backfill_btw_rate_flag(db, 'TestTenant')

        # Third call should be for 'high' rate
        third_sql = db.execute_query.call_args_list[2][0][0]
        third_params = db.execute_query.call_args_list[2][0][1]
        assert 'high' in third_params
        assert total == 2

    def test_only_touches_accounts_without_btw_rate(self):
        """All btw_rate queries should check that $.btw_rate IS NULL."""
        from migrations.backfill_rekeningschema_flags import backfill_btw_rate_flag
        db = Mock()
        db.execute_query.side_effect = [0, 0, 0]

        backfill_btw_rate_flag(db, 'TestTenant')

        for call_args in db.execute_query.call_args_list:
            sql = call_args[0][0]
            assert 'btw_rate' in sql
            assert 'IS NULL' in sql


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Verify migration is idempotent — running twice produces same result."""

    def test_second_run_updates_zero_rows(self):
        """
        When all flags are already set, the WHERE clauses should match 0 rows.
        """
        from migrations.backfill_rekeningschema_flags import backfill_tenant
        db = Mock()
        # All updates return 0 (no rows matched — already flagged)
        db.execute_query.return_value = 0

        total = backfill_tenant(db, 'TestTenant')
        assert total == 0

    def test_sql_where_clauses_exclude_already_flagged(self):
        """
        Each backfill function's SQL should include a condition that
        skips accounts where the flag is already set.
        """
        from migrations.backfill_rekeningschema_flags import (
            backfill_bank_account_flag,
            backfill_expense_account_flag,
            backfill_revenue_account_flag,
            backfill_str_revenue_account_flag,
        )
        db = Mock()
        db.execute_query.return_value = 0

        for fn in [backfill_bank_account_flag, backfill_expense_account_flag,
                    backfill_revenue_account_flag, backfill_str_revenue_account_flag]:
            fn(db, 'TestTenant')
            sql = db.execute_query.call_args[0][0]
            # Each should have a guard against re-setting
            assert 'JSON_EXTRACT(parameters' in sql, \
                f"{fn.__name__} SQL missing idempotency guard"


# ---------------------------------------------------------------------------
# Preservation of existing parameters
# ---------------------------------------------------------------------------

class TestPreservation:
    """Verify existing parameters values are preserved."""

    def test_uses_json_set_not_json_object(self):
        """
        JSON_SET merges into existing JSON; JSON_OBJECT would overwrite.
        All UPDATE statements must use JSON_SET(COALESCE(parameters, '{}'), ...).
        """
        from migrations.backfill_rekeningschema_flags import (
            backfill_bank_account_flag,
            backfill_expense_account_flag,
            backfill_revenue_account_flag,
            backfill_str_revenue_account_flag,
            backfill_btw_rate_flag,
        )
        db = Mock()
        db.execute_query.return_value = 0

        for fn in [backfill_bank_account_flag, backfill_expense_account_flag,
                    backfill_revenue_account_flag, backfill_str_revenue_account_flag]:
            fn(db, 'TestTenant')
            sql = db.execute_query.call_args[0][0]
            assert 'JSON_SET' in sql, f"{fn.__name__} must use JSON_SET"
            assert 'COALESCE(parameters' in sql, \
                f"{fn.__name__} must use COALESCE for NULL safety"
            assert 'JSON_OBJECT' not in sql, \
                f"{fn.__name__} must NOT use JSON_OBJECT (would overwrite)"

        # btw_rate makes 3 calls
        db.execute_query.side_effect = [0, 0, 0]
        backfill_btw_rate_flag(db, 'TestTenant')
        for call_args in db.execute_query.call_args_list[-3:]:
            sql = call_args[0][0]
            assert 'JSON_SET' in sql
            assert 'COALESCE(parameters' in sql


# ---------------------------------------------------------------------------
# Different account numbering
# ---------------------------------------------------------------------------

class TestDifferentAccountNumbering:
    """Verify migration works for tenants with non-standard numbering."""

    def test_bank_account_matches_by_role_not_number(self):
        """
        Bank accounts are identified by Pattern=true, VW='N',
        Belastingaangifte='Liquide middelen' — NOT by account number.
        """
        from migrations.backfill_rekeningschema_flags import backfill_bank_account_flag
        db = Mock()
        db.execute_query.return_value = 0

        backfill_bank_account_flag(db, 'CustomTenant')

        sql = db.execute_query.call_args[0][0]
        # Should NOT contain hardcoded account numbers like '1002', '1003'
        assert "'1002'" not in sql
        assert "'1003'" not in sql
        assert "'1004'" not in sql
        # Should NOT use Account LIKE '1%' or Account < '1300'
        assert "< '1300'" not in sql

    def test_expense_account_matches_by_vw_and_parent_not_number(self):
        """Expense accounts identified by VW='Y' and Parent NOT 8xxx."""
        from migrations.backfill_rekeningschema_flags import backfill_expense_account_flag
        db = Mock()
        db.execute_query.return_value = 0

        backfill_expense_account_flag(db, 'CustomTenant')

        sql = db.execute_query.call_args[0][0]
        # Should NOT contain hardcoded account numbers
        assert "'4000'" not in sql
        assert "'4099'" not in sql

    def test_str_revenue_matches_by_name_not_number(self):
        """STR revenue account identified by AccountName, not '8003'."""
        from migrations.backfill_rekeningschema_flags import backfill_str_revenue_account_flag
        db = Mock()
        db.execute_query.return_value = 0

        backfill_str_revenue_account_flag(db, 'CustomTenant')

        sql = db.execute_query.call_args[0][0]
        assert "'8003'" not in sql
        assert 'verhuur' in sql.lower()


# ---------------------------------------------------------------------------
# run_migration integration
# ---------------------------------------------------------------------------

class TestRunMigration:
    """Test the top-level run_migration function."""

    def test_processes_all_tenants(self):
        from migrations.backfill_rekeningschema_flags import run_migration
        db = Mock()
        # get_all_tenants returns 2 tenants; all updates return 0
        db.execute_query.return_value = [
            {'administration': 'TenantA'},
            {'administration': 'TenantB'},
        ]

        # After the first call (get_all_tenants), all subsequent calls
        # are UPDATE statements returning 0
        call_count = [0]
        original_return = [
            [{'administration': 'TenantA'}, {'administration': 'TenantB'}]
        ]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_return[0]
            return 0

        db.execute_query.side_effect = side_effect

        result = run_migration(db=db)
        assert result == 0  # No rows updated (all already flagged)

    def test_returns_zero_when_no_tenants(self):
        from migrations.backfill_rekeningschema_flags import run_migration
        db = Mock()
        db.execute_query.return_value = []

        result = run_migration(db=db)
        assert result == 0

    def test_dry_run_does_not_modify_database(self):
        from migrations.backfill_rekeningschema_flags import run_migration
        db = Mock()
        db.execute_query.return_value = [
            {'administration': 'TenantA'},
        ]

        run_migration(db=db, dry_run=True)

        # Only the get_all_tenants SELECT should have been called
        # No UPDATE statements should have been executed
        assert db.execute_query.call_count == 1
        first_sql = db.execute_query.call_args_list[0][0][0]
        assert 'SELECT' in first_sql
