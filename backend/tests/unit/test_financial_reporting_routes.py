"""
Unit tests for financial_reporting_routes.py

Tests the financial reporting endpoints:
- GET /balance-data - Balance data grouped by Parent/ledger
- GET /trends-data - P&L trends by year
- GET /reference-analysis - Reference analysis with trend and accounts

Task 49 of Phase 7: Missing Test Coverage
"""

import sys
import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from functools import wraps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ── Auth decorator mocks ───────────────────────────────────────────────────


def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['Finance_CRUD']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'TestTenant'
            kwargs['user_tenants'] = ['TestTenant', 'OtherTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """Create Flask test client with patched auth decorators."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
        import importlib
        import routes.financial_reporting_routes as frr
        importlib.reload(frr)
        frr.set_test_mode(True)

        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(frr.financial_reporting_bp)

        with app.test_client() as c:
            with app.app_context():
                yield c


@pytest.fixture
def mock_cursor():
    """Create a mock cursor with fetchall."""
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    return cursor


# ── FinancialReportingService unit tests ───────────────────────────────────


class TestFinancialReportingService:

    def test_build_where_clause_empty(self):
        """Empty conditions produce 1=1 WHERE clause."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=True)
        clause, params = service.build_where_clause({})
        assert clause == "1=1"
        assert params == []

    def test_build_where_clause_administration(self):
        """Administration condition produces correct clause."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=True)
        clause, params = service.build_where_clause({'administration': 'TestTenant'})
        assert 'administration = %s' in clause
        assert params == ['TestTenant']

    def test_build_where_clause_date_range(self):
        """Date range condition produces BETWEEN clause."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=True)
        clause, params = service.build_where_clause({
            'date_range': {'from': '2025-01-01', 'to': '2025-12-31'}
        })
        assert 'TransactionDate BETWEEN %s AND %s' in clause
        assert params == ['2025-01-01', '2025-12-31']

    def test_build_where_clause_date_range_to_only(self):
        """Date range with only 'to' produces <= clause."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=True)
        clause, params = service.build_where_clause({
            'date_range': {'from': None, 'to': '2025-06-30'}
        })
        assert 'TransactionDate <= %s' in clause
        assert params == ['2025-06-30']

    def test_build_where_clause_years(self):
        """Years condition produces IN clause."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=True)
        clause, params = service.build_where_clause({'years': [2024, 2025]})
        assert 'jaar IN (%s,%s)' in clause
        assert params == [2024, 2025]

    def test_build_where_clause_profit_loss(self):
        """Profit/loss condition produces VW clause."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=True)
        clause, params = service.build_where_clause({'profit_loss': 'Y'})
        assert 'VW = %s' in clause
        assert params == ['Y']

    def test_build_where_clause_ignores_all_value(self):
        """'all' value is skipped in WHERE clause."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=True)
        clause, params = service.build_where_clause({'profit_loss': 'all'})
        assert clause == "1=1"
        assert params == []

    def test_table_name_test_mode(self):
        """Test mode uses mutaties_test table."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=True)
        assert service.table_name == 'mutaties_test'

    def test_table_name_production_mode(self):
        """Production mode uses mutaties table."""
        from routes.financial_reporting_routes import FinancialReportingService
        with patch('routes.financial_reporting_routes.DatabaseManager'):
            service = FinancialReportingService(test_mode=False)
        assert service.table_name == 'mutaties'


# ── GET /balance-data ──────────────────────────────────────────────────────


class TestBalanceDataEndpoint:

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_success_single_admin(self, mock_service_cls, client):
        """GET /balance-data returns balance data for single admin."""
        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance
        mock_instance.build_where_clause.return_value = ("administration = %s", ['TestTenant'])
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'Parent': 'Revenue', 'ledger': '8000', 'total_amount': 50000.0}
        ]
        mock_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)

        resp = client.get('/balance-data?administration=TestTenant')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'data' in data

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_unauthorized_admin_returns_403(self, mock_service_cls, client):
        """GET /balance-data with unauthorized admin returns 403."""
        resp = client.get('/balance-data?administration=ForbiddenTenant')
        assert resp.status_code == 403
        data = resp.get_json()
        assert data['success'] is False
        assert 'Access denied' in data['error']

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_default_admin_uses_tenant(self, mock_service_cls, client):
        """GET /balance-data without admin uses current tenant."""
        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance
        mock_instance.build_where_clause.return_value = ("administration = %s", ['TestTenant'])
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)

        resp = client.get('/balance-data')
        assert resp.status_code == 200


# ── GET /trends-data ───────────────────────────────────────────────────────


class TestTrendsDataEndpoint:

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_success(self, mock_service_cls, client):
        """GET /trends-data returns trend data."""
        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance
        mock_instance.build_where_clause.return_value = ("1=1", [])
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'Parent': 'Revenue', 'ledger': '8000', 'year': 2025, 'total_amount': 50000.0}
        ]
        mock_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)

        resp = client.get('/trends-data?years=2024,2025&administration=TestTenant')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_unauthorized_admin_returns_403(self, mock_service_cls, client):
        """GET /trends-data with unauthorized admin returns 403."""
        resp = client.get('/trends-data?administration=ForbiddenTenant')
        assert resp.status_code == 403

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_error_returns_500(self, mock_service_cls, client):
        """GET /trends-data returns 500 on internal error."""
        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance
        mock_instance.build_where_clause.side_effect = RuntimeError('DB Error')

        resp = client.get('/trends-data?administration=TestTenant')
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['success'] is False


# ── GET /reference-analysis ────────────────────────────────────────────────


class TestReferenceAnalysisEndpoint:

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_success_without_reference(self, mock_service_cls, client):
        """GET /reference-analysis without reference returns available accounts."""
        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance
        mock_instance.build_where_clause.return_value = ("1=1", [])
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'Reknum': '8000', 'AccountName': 'Revenue'}
        ]
        mock_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)

        resp = client.get('/reference-analysis?administration=TestTenant')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'available_accounts' in data
        assert 'transactions' in data
        assert 'trend_data' in data

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_unauthorized_admin_returns_403(self, mock_service_cls, client):
        """GET /reference-analysis with unauthorized admin returns 403."""
        resp = client.get('/reference-analysis?administration=ForbiddenTenant')
        assert resp.status_code == 403

    @patch('routes.financial_reporting_routes.FinancialReportingService')
    def test_with_reference_returns_transactions(self, mock_service_cls, client):
        """GET /reference-analysis with reference returns transactions and trend."""
        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance
        mock_instance.build_where_clause.return_value = ("administration = %s", ['TestTenant'])
        mock_cursor = MagicMock()
        # First call: available_accounts, second: transactions, third: trend_data
        mock_cursor.fetchall.side_effect = [
            [{'Reknum': '8000', 'AccountName': 'Revenue'}],
            [{'TransactionDate': '2025-01-15', 'Amount': 1000.0}],
            [{'jaar': 2025, 'kwartaal': 1, 'total_amount': 3000.0}]
        ]
        mock_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)

        resp = client.get(
            '/reference-analysis?administration=TestTenant&reference_number=INV-001'
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
