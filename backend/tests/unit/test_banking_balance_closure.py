"""
Unit tests for banking balance closure functionality.

Tests the _get_opening_balance_date helper, check_banking_accounts and
check_sequence_numbers closure-aware behavior, and the
/api/banking/opening-balance-date endpoint.

Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock, call
from functools import wraps

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from banking_processor import _get_opening_balance_date, BankingProcessor


# ---------------------------------------------------------------------------
# Tests for _get_opening_balance_date
# ---------------------------------------------------------------------------

class TestGetOpeningBalanceDate:

    def test_single_closure_returns_next_year_jan_1(self):
        """Single closure (year 2024) → returns '2025-01-01'"""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [{'last_closed_year': 2024}]

        result = _get_opening_balance_date(mock_db, 'TestAdmin')

        assert result == '2025-01-01'
        mock_db.execute_query.assert_called_once()

    def test_multiple_closures_uses_max_year(self):
        """Multiple closures (2023, 2024) → returns '2025-01-01' (MAX picks 2024)"""
        mock_db = MagicMock()
        # The SQL uses MAX(year), so the DB returns the max directly
        mock_db.execute_query.return_value = [{'last_closed_year': 2024}]

        result = _get_opening_balance_date(mock_db, 'TestAdmin')

        assert result == '2025-01-01'

    def test_no_closures_returns_none(self):
        """No closures → returns None"""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [{'last_closed_year': None}]

        result = _get_opening_balance_date(mock_db, 'TestAdmin')

        assert result is None

    def test_empty_result_returns_none(self):
        """Empty query result → returns None"""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []

        result = _get_opening_balance_date(mock_db, 'TestAdmin')

        assert result is None

    def test_database_error_returns_none(self):
        """Database error → returns None (graceful fallback)"""
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = Exception("Connection refused")

        result = _get_opening_balance_date(mock_db, 'TestAdmin')

        assert result is None


# ---------------------------------------------------------------------------
# Tests for check_banking_accounts with closure awareness
# ---------------------------------------------------------------------------

class TestCheckBankingAccountsClosure:

    @pytest.fixture
    def mock_db(self):
        mock_instance = MagicMock()
        mock_instance.execute_query.return_value = []
        mock_instance.get_bank_account_lookups.return_value = []
        return mock_instance

    @pytest.fixture
    def processor(self, mock_db):
        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            proc = BankingProcessor(test_mode=True)
        return proc

    def test_with_closure_query_includes_date_lower_bound(self, processor):
        """With closure: verify query includes TransactionDate >= '2025-01-01'"""
        processor.db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL80RABO0107936917', 'Account': '1600', 'administration': 'TestAdmin'}
        ]

        processor.db.execute_query.side_effect = [
            # Balance query
            [{'Reknum': '1600', 'administration': 'TestAdmin', 'calculated_balance': 500.00, 'account_name': 'Bank'}],
            # Last transactions
            []
        ]

        with patch('banking_checks._get_opening_balance_date', return_value='2025-01-01'):
            processor.check_banking_accounts(administration='TestAdmin')

        # Check the balance query (first execute_query call) includes the date filter
        balance_call = processor.db.execute_query.call_args_list[0]
        query_str = balance_call[0][0]
        params = balance_call[0][1]

        assert 'TransactionDate >= %s' in query_str
        assert '2025-01-01' in params

    def test_without_closure_no_date_lower_bound(self, processor):
        """Without closure: verify query has no lower date bound (preservation)"""
        processor.db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL80RABO0107936917', 'Account': '1600', 'administration': 'TestAdmin'}
        ]

        processor.db.execute_query.side_effect = [
            [{'Reknum': '1600', 'administration': 'TestAdmin', 'calculated_balance': 500.00, 'account_name': 'Bank'}],
            []
        ]

        with patch('banking_checks._get_opening_balance_date', return_value=None):
            processor.check_banking_accounts(administration='TestAdmin')

        balance_call = processor.db.execute_query.call_args_list[0]
        query_str = balance_call[0][0]

        assert 'TransactionDate >= %s' not in query_str

    def test_with_closure_and_end_date_both_bounds_applied(self, processor):
        """With closure + end_date: verify both bounds applied"""
        processor.db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL80RABO0107936917', 'Account': '1600', 'administration': 'TestAdmin'}
        ]

        processor.db.execute_query.side_effect = [
            [{'Reknum': '1600', 'administration': 'TestAdmin', 'calculated_balance': 300.00, 'account_name': 'Bank'}],
            []
        ]

        with patch('banking_checks._get_opening_balance_date', return_value='2025-01-01'):
            processor.check_banking_accounts(end_date='2025-06-30', administration='TestAdmin')

        balance_call = processor.db.execute_query.call_args_list[0]
        query_str = balance_call[0][0]
        params = balance_call[0][1]

        assert 'TransactionDate <= %s' in query_str
        assert 'TransactionDate >= %s' in query_str
        assert '2025-06-30' in params
        assert '2025-01-01' in params


# ---------------------------------------------------------------------------
# Tests for check_sequence_numbers with closure awareness
# ---------------------------------------------------------------------------

class TestCheckSequenceNumbersClosure:

    @pytest.fixture
    def processor(self):
        return BankingProcessor(test_mode=True)

    @pytest.fixture
    def mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    def test_with_closure_start_date_overridden(self, processor, mock_connection):
        """With closure: verify start_date is overridden to opening_balance_date"""
        mock_conn, mock_cursor = mock_connection

        mock_cursor.fetchone.return_value = {'rekeningNummer': 'NL80RABO0107936917'}
        mock_cursor.fetchall.return_value = [
            {'TransactionDate': '2025-01-15', 'TransactionDescription': 'Test', 'Ref2': '1', 'TransactionAmount': 100.00}
        ]

        with patch.object(processor.db, 'get_connection', return_value=mock_conn), \
             patch('banking_checks._get_opening_balance_date', return_value='2025-01-01'):

            result = processor.check_sequence_numbers('1600', 'TestAdmin', start_date='2024-01-01')

        # The start_date in the result should be the opening_balance_date, not the parameter
        assert result['start_date'] == '2025-01-01'

        # Verify the query used the overridden date
        seq_query_call = mock_cursor.execute.call_args_list[-1]  # last execute is the sequence query
        params = seq_query_call[0][1]
        assert '2025-01-01' in params

    def test_without_closure_start_date_used_as_is(self, processor, mock_connection):
        """Without closure: verify start_date parameter is used as-is (preservation)"""
        mock_conn, mock_cursor = mock_connection

        mock_cursor.fetchone.return_value = {'rekeningNummer': 'NL80RABO0107936917'}
        mock_cursor.fetchall.return_value = [
            {'TransactionDate': '2024-06-15', 'TransactionDescription': 'Test', 'Ref2': '1', 'TransactionAmount': 100.00}
        ]

        with patch.object(processor.db, 'get_connection', return_value=mock_conn), \
             patch('banking_checks._get_opening_balance_date', return_value=None):

            result = processor.check_sequence_numbers('1600', 'TestAdmin', start_date='2024-01-01')

        # The original start_date parameter should be preserved
        assert result['start_date'] == '2024-01-01'

        # Verify the query used the original parameter
        seq_query_call = mock_cursor.execute.call_args_list[-1]
        params = seq_query_call[0][1]
        assert '2024-01-01' in params


# ---------------------------------------------------------------------------
# Tests for /api/banking/opening-balance-date endpoint
# ---------------------------------------------------------------------------

def _passthrough_cognito(required_permissions=None, required_roles=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['Banking_Read']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'TestAdmin'
            kwargs['user_tenants'] = ['TestAdmin']
            return f(*args, **kwargs)
        return wrapper
    return decorator


class TestOpeningBalanceDateEndpoint:

    @pytest.fixture
    def client(self):
        """Create Flask test client with mocked auth decorators"""
        from flask import Flask

        with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
             patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
            import importlib
            import routes.banking_routes as br
            importlib.reload(br)
            # Set up the banking_service so the route module doesn't fail
            br.banking_service = MagicMock()
            br.banking_service.test_mode = True

            app = Flask(__name__)
            app.config['TESTING'] = True
            app.register_blueprint(br.banking_bp)
            yield app.test_client()

    def test_with_closure_returns_date_and_year(self, client):
        """With closure → returns opening_balance_date and last_closed_year"""
        with patch('banking_checks._get_opening_balance_date', return_value='2025-01-01'), \
             patch('banking_processor._get_opening_balance_date', return_value='2025-01-01'), \
             patch('database.DatabaseManager'):

            resp = client.get('/api/banking/opening-balance-date')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['opening_balance_date'] == '2025-01-01'
        assert data['last_closed_year'] == 2024

    def test_without_closure_returns_nulls(self, client):
        """Without closure → returns nulls"""
        with patch('banking_checks._get_opening_balance_date', return_value=None), \
             patch('banking_processor._get_opening_balance_date', return_value=None), \
             patch('database.DatabaseManager'):

            resp = client.get('/api/banking/opening-balance-date')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['opening_balance_date'] is None
        assert data['last_closed_year'] is None
