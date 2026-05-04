"""
Unit tests for DatabaseManager credit card and exchange rate lookup methods.

Tests get_credit_card_lookups() and get_exchange_rate_account() methods
added to DatabaseManager for the credit card processing feature.
"""
import pytest
from unittest.mock import patch, MagicMock

from database import DatabaseManager


class TestGetCreditCardLookups:
    """Tests for DatabaseManager.get_credit_card_lookups()"""

    @pytest.fixture
    def db(self):
        """Create a DatabaseManager instance with mocked connection pool."""
        with patch.object(DatabaseManager, '__init__', lambda self, *a, **kw: None):
            instance = DatabaseManager.__new__(DatabaseManager)
            instance.execute_query = MagicMock()
            return instance

    def test_returns_correct_keys(self, db):
        """get_credit_card_lookups() returns dicts with cc_bank_iban, Account, card_number, administration."""
        db.execute_query.return_value = [
            {'cc_bank_iban': 'NL80RABO0107936917', 'Account': '2001', 'card_number': '6416', 'administration': 'TestTenant'}
        ]

        result = db.get_credit_card_lookups()

        assert len(result) == 1
        row = result[0]
        assert row['cc_bank_iban'] == 'NL80RABO0107936917'
        assert row['Account'] == '2001'
        assert row['card_number'] == '6416'
        assert row['administration'] == 'TestTenant'

    def test_no_filter_without_administration(self, db):
        """Without administration parameter, query has no administration filter."""
        db.execute_query.return_value = []

        db.get_credit_card_lookups()

        call_args = db.execute_query.call_args
        query = call_args[0][0]
        assert "JSON_EXTRACT(parameters, '$.credit_card') = true" in query
        assert "'$.cc_bank_iban'" in query
        assert "'$.card_number'" in query
        assert "administration = %s" not in query
        # Should be called with just the query, no params tuple
        assert len(call_args[0]) == 1

    def test_filters_by_administration(self, db):
        """With administration parameter, query includes AND administration = %s."""
        db.execute_query.return_value = []

        db.get_credit_card_lookups(administration='TestTenant')

        call_args = db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "AND administration = %s" in query
        assert params == ('TestTenant',)

    def test_empty_result_returns_empty_list(self, db):
        """When no credit card accounts exist, returns empty list."""
        db.execute_query.return_value = []

        result = db.get_credit_card_lookups()

        assert result == []

    def test_multiple_results(self, db):
        """Returns multiple credit card accounts when available."""
        db.execute_query.return_value = [
            {'cc_bank_iban': 'NL71RABO0148034454', 'Account': '2001', 'card_number': '6416', 'administration': 'TenantA'},
            {'cc_bank_iban': 'NL80RABO0107936917', 'Account': '2002', 'card_number': '1234', 'administration': 'TenantB'},
        ]

        result = db.get_credit_card_lookups()

        assert len(result) == 2


class TestGetExchangeRateAccount:
    """Tests for DatabaseManager.get_exchange_rate_account()"""

    @pytest.fixture
    def db(self):
        """Create a DatabaseManager instance with mocked connection pool."""
        with patch.object(DatabaseManager, '__init__', lambda self, *a, **kw: None):
            instance = DatabaseManager.__new__(DatabaseManager)
            instance.execute_query = MagicMock()
            return instance

    def test_returns_correct_keys(self, db):
        """get_exchange_rate_account() returns dicts with Account, administration."""
        db.execute_query.return_value = [
            {'Account': '4910', 'administration': 'TestTenant'}
        ]

        result = db.get_exchange_rate_account()

        assert len(result) == 1
        row = result[0]
        assert row['Account'] == '4910'
        assert row['administration'] == 'TestTenant'

    def test_no_filter_without_administration(self, db):
        """Without administration parameter, query has no administration filter."""
        db.execute_query.return_value = []

        db.get_exchange_rate_account()

        call_args = db.execute_query.call_args
        query = call_args[0][0]
        assert "JSON_EXTRACT(parameters, '$.exchange_rate_account') = true" in query
        assert "administration = %s" not in query
        assert len(call_args[0]) == 1

    def test_filters_by_administration(self, db):
        """With administration parameter, query includes AND administration = %s."""
        db.execute_query.return_value = []

        db.get_exchange_rate_account(administration='TestTenant')

        call_args = db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "AND administration = %s" in query
        assert params == ('TestTenant',)

    def test_empty_result_returns_empty_list(self, db):
        """When no exchange rate account exists, returns empty list."""
        db.execute_query.return_value = []

        result = db.get_exchange_rate_account()

        assert result == []
