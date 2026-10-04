"""Unit tests for DatabaseBankingQueriesMixin (DB / money, banking lookups).

The mixin provides the banking processor's domain queries. It only depends on
``self.execute_query`` (from DatabaseManager), so we exercise it in isolation via a
tiny harness class with a mocked ``execute_query`` — no real DatabaseManager pooling
machinery, no DB. The focus is the branch-y bits:

- the optional ``administration`` tenant filter (present vs absent) — a tenant-scoping
  concern: when a tenant is given, the query MUST carry ``administration = %s`` and the
  tenant value MUST be in the params,
- SQL shape (parameterized ``%s``, canonical ``rekeningschema``/``parameters`` source),
- the error-wrapping branch of ``check_duplicate_transactions``.

Methods already covered by ``tests/database/test_database.py`` (bank-account lookups,
sequences, the duplicate-detection property tests) are not duplicated here; this file
fills the remaining gaps (credit-card / exchange-rate / patterns / recent / previous).
"""

from unittest.mock import MagicMock

import pytest

from database_banking_queries import DatabaseBankingQueriesMixin
from db_exceptions import DatabaseError


class _BankingQueriesHarness(DatabaseBankingQueriesMixin):
    """Minimal host exposing the mixin with a mocked execute_query."""

    def __init__(self):
        self.execute_query = MagicMock(return_value=[])


@pytest.fixture
def db():
    return _BankingQueriesHarness()


def _last_sql(db):
    return db.execute_query.call_args[0][0]


def _last_params(db):
    call = db.execute_query.call_args[0]
    return call[1] if len(call) > 1 else None


# ---------------------------------------------------------------------------
# get_credit_card_lookups
# ---------------------------------------------------------------------------

class TestGetCreditCardLookups:
    def test_with_tenant_filter_scopes_query(self, db):
        db.execute_query.return_value = [
            {"cc_bank_iban": "NL99VISA", "Account": "1024", "card_number": "1234", "administration": "T1"}
        ]
        result = db.get_credit_card_lookups(administration="T1")

        assert result[0]["Account"] == "1024"
        sql = _last_sql(db)
        assert "credit_card" in sql
        assert "administration = %s" in sql
        assert _last_params(db) == ("T1",)

    def test_without_tenant_returns_all(self, db):
        db.get_credit_card_lookups()
        sql = _last_sql(db)
        assert "administration = %s" not in sql
        # No params tuple passed when unfiltered.
        assert _last_params(db) is None


# ---------------------------------------------------------------------------
# get_exchange_rate_account
# ---------------------------------------------------------------------------

class TestGetExchangeRateAccount:
    def test_with_tenant_filter(self, db):
        db.execute_query.return_value = [{"Account": "9100", "administration": "T1"}]
        result = db.get_exchange_rate_account(administration="T1")

        assert result[0]["Account"] == "9100"
        assert "exchange_rate_account" in _last_sql(db)
        assert _last_params(db) == ("T1",)

    def test_without_tenant(self, db):
        db.get_exchange_rate_account()
        assert "administration = %s" not in _last_sql(db)


# ---------------------------------------------------------------------------
# get_patterns (tenant-scoped; references itself 3x in params)
# ---------------------------------------------------------------------------

class TestGetPatterns:
    def test_passes_administration_three_times(self, db):
        """Pattern query filters by administration in the outer + two subqueries."""
        db.get_patterns("TenantA")
        sql = _last_sql(db)
        assert "vw_readreferences" in sql
        assert "bank_account" in sql
        # administration appears in outer WHERE + two IN-subqueries → 3 bind params.
        assert _last_params(db) == ("TenantA", "TenantA", "TenantA")


# ---------------------------------------------------------------------------
# get_recent_transactions
# ---------------------------------------------------------------------------

class TestGetRecentTransactions:
    def test_with_tenant_filter_binds_admin_and_limit(self, db):
        db.get_recent_transactions(limit=50, administration="T1")
        sql = _last_sql(db)
        assert "administration = %s" in sql
        assert _last_params(db) == ("T1", 50)

    def test_without_tenant_binds_only_limit(self, db):
        db.get_recent_transactions(limit=25)
        sql = _last_sql(db)
        assert "administration = %s" not in sql
        assert _last_params(db) == (25,)

    def test_respects_custom_table_name(self, db):
        db.get_recent_transactions(table_name="mutaties_archive")
        assert "mutaties_archive" in _last_sql(db)


# ---------------------------------------------------------------------------
# get_previous_transactions
# ---------------------------------------------------------------------------

class TestGetPreviousTransactions:
    def test_wraps_reference_in_like_wildcards(self, db):
        db.execute_query.return_value = [{"Omschrijving": "x"}]
        result = db.get_previous_transactions("REF001", limit=3)

        assert result == [{"Omschrijving": "x"}]
        params = _last_params(db)
        assert params == ("%REF001%", 3)
        assert "LIKE %s" in _last_sql(db)

    def test_empty_results_returns_empty_list(self, db):
        db.execute_query.return_value = None
        assert db.get_previous_transactions("NOPE") == []


# ---------------------------------------------------------------------------
# get_used_transaction_numbers
# ---------------------------------------------------------------------------

class TestGetUsedTransactionNumbers:
    def test_binds_ref1(self, db):
        db.get_used_transaction_numbers("NL80RABO0107936917")
        assert _last_params(db) == ("NL80RABO0107936917",)
        assert "Ref1 = %s" in _last_sql(db)


# ---------------------------------------------------------------------------
# get_existing_sequences (admin-filter branch not covered in db suite)
# ---------------------------------------------------------------------------

class TestGetExistingSequences:
    def test_extracts_existing_values(self, db):
        db.execute_query.return_value = [{"existing": "001"}, {"existing": "002"}]
        result = db.get_existing_sequences("NL80RABO0107936917")
        assert result == ["001", "002"]

    def test_appends_administration_filter_when_given(self, db):
        db.get_existing_sequences("NL80RABO0107936917", administration="T1")
        sql = _last_sql(db)
        params = _last_params(db)
        assert "administration = %s" in sql
        assert params == ("NL80RABO0107936917", "T1")


# ---------------------------------------------------------------------------
# check_duplicate_transactions error wrapping
# ---------------------------------------------------------------------------

class TestCheckDuplicateTransactions:
    def test_returns_matches(self, db):
        db.execute_query.return_value = [{"ID": 1, "TransactionAmount": 150.0}]
        result = db.check_duplicate_transactions("REF", "2024-01-15", 150.0)
        assert result[0]["ID"] == 1
        # 0.01 tolerance comparison lives in the SQL.
        assert "ABS(TransactionAmount - %s)" in _last_sql(db)

    def test_no_matches_returns_empty_list(self, db):
        db.execute_query.return_value = None
        assert db.check_duplicate_transactions("REF", "2024-01-15", 150.0) == []

    def test_database_error_is_wrapped_as_runtime_error(self, db):
        db.execute_query.side_effect = DatabaseError("connection lost")
        with pytest.raises(RuntimeError, match="Database connection failed during duplicate check"):
            db.check_duplicate_transactions("REF", "2024-01-15", 150.0)

    def test_unexpected_error_is_wrapped(self, db):
        db.execute_query.side_effect = ValueError("boom")
        with pytest.raises(RuntimeError, match="Duplicate check failed"):
            db.check_duplicate_transactions("REF", "2024-01-15", 150.0)
