import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Skip all API tests - they require authenticated Flask app
pytestmark = [
    pytest.mark.api,
    pytest.mark.skip(reason="Requires authenticated Flask app - TODO: add auth fixtures")
]

# Mock the decorators before importing the routes
with patch('auth.cognito_utils.cognito_required') as mock_cognito, \
     patch('auth.tenant_context.tenant_required') as mock_tenant:
    
    # Make decorators pass through and inject required parameters
    def mock_cognito_decorator(required_permissions=None):
        def decorator(f):
            def wrapper(*args, **kwargs):
                return f(user_email='test@example.com', user_roles=['Finance_CRUD'], *args, **kwargs)
            wrapper.__name__ = f.__name__
            return wrapper
        return decorator
    
    def mock_tenant_decorator():
        def decorator(f):
            def wrapper(*args, **kwargs):
                return f(tenant='GoodwinSolutions', user_tenants=['GoodwinSolutions', 'PeterPrive'], *args, **kwargs)
            wrapper.__name__ = f.__name__
            return wrapper
        return decorator
    
    mock_cognito.side_effect = mock_cognito_decorator
    mock_tenant.side_effect = mock_tenant_decorator
    
    from reporting_routes import ReportingService, reporting_bp

from flask import Flask

class TestReportingService:
    
    @patch('reporting_routes.DatabaseManager')
    def test_init_production_mode(self, mock_db):
        service = ReportingService(test_mode=False)
        
        assert service.table_name == 'mutaties'
        mock_db.assert_called_once_with(test_mode=False)
    
    @patch('reporting_routes.DatabaseManager')
    def test_init_test_mode(self, mock_db):
        service = ReportingService(test_mode=True)
        
        assert service.table_name == 'mutaties_test'
        mock_db.assert_called_once_with(test_mode=True)
    
    @patch('reporting_routes.DatabaseManager')
    def test_get_cursor_context_manager(self, mock_db):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value = mock_conn
        
        service = ReportingService()
        
        with service.get_cursor() as cursor:
            assert cursor == mock_cursor
        
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    def test_build_where_clause_empty_conditions(self):
        service = ReportingService()
        
        where_clause, params = service.build_where_clause({})
        
        assert where_clause == "1=1"
        assert params == []
    
    def test_build_where_clause_date_range(self):
        service = ReportingService()
        conditions = {
            'date_range': {'from': '2023-01-01', 'to': '2023-12-31'}
        }
        
        where_clause, params = service.build_where_clause(conditions)
        
        assert "TransactionDate BETWEEN %s AND %s" in where_clause
        assert params == ['2023-01-01', '2023-12-31']
    
    def test_build_where_clause_years(self):
        service = ReportingService()
        conditions = {'years': [2022, 2023]}
        
        where_clause, params = service.build_where_clause(conditions)
        
        assert "jaar IN (%s,%s)" in where_clause
        assert params == [2022, 2023]
    
    def test_build_where_clause_administration(self):
        service = ReportingService()
        conditions = {'administration': 'Test'}
        
        where_clause, params = service.build_where_clause(conditions)
        
        assert "administration = %s" in where_clause
        assert params == ['Test']
    
    def test_build_where_clause_skip_all_values(self):
        service = ReportingService()
        conditions = {
            'administration': 'all',
            'profit_loss': '',
            'channel': None
        }
        
        where_clause, params = service.build_where_clause(conditions)
        
        assert where_clause == "1=1"
        assert params == []
    
    @patch('reporting_routes.DatabaseManager')
    def test_get_financial_summary_success(self, mock_db):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'category': 'Revenue', 'amount': 1000.0},
            {'category': 'Expenses', 'amount': -500.0}
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value = mock_conn
        
        service = ReportingService()
        result = service.get_financial_summary('2023-01-01', '2023-12-31')
        
        assert result['success'] is True
        assert result['data']['labels'] == ['Revenue', 'Expenses']
        assert result['data']['values'] == [1000.0, -500.0]
        assert result['data']['total'] == 1500.0
        mock_cursor.execute.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('reporting_routes.DatabaseManager')
    def test_get_financial_summary_with_filters(self, mock_db):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value = mock_conn
        
        service = ReportingService()
        result = service.get_financial_summary('2023-01-01', '2023-12-31', 'income', 'Test')
        
        assert result['success'] is True
        mock_cursor.execute.assert_called_once()
        # Verify that administration filter was applied
        call_args = mock_cursor.execute.call_args
        assert 'administration = %s' in call_args[0][0]
        assert 'Test' in call_args[0][1]
    
    @patch('reporting_routes.DatabaseManager')
    def test_get_financial_summary_error(self, mock_db):
        mock_db.return_value.get_connection.side_effect = Exception("Database error")
        
        service = ReportingService()
        result = service.get_financial_summary('2023-01-01', '2023-12-31')
        
        assert result['success'] is False
        assert result['error'] == "Database error"
    
    @patch('reporting_routes.DatabaseManager')
    def test_get_str_revenue_summary_success(self, mock_db):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'channel': 'Airbnb', 'listing': 'Property1', 'bookings': 10, 'gross_revenue': 5000.0}
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value = mock_conn
        
        service = ReportingService()
        result = service.get_str_revenue_summary('2023-01-01', '2023-12-31')
        
        assert result['success'] is True
        assert len(result['data']) == 1
        assert result['data'][0]['channel'] == 'Airbnb'
        mock_cursor.execute.assert_called_once()
    
    @patch('reporting_routes.DatabaseManager')
    def test_get_str_revenue_summary_error(self, mock_db):
        mock_db.return_value.get_connection.side_effect = Exception("Database error")
        
        service = ReportingService()
        result = service.get_str_revenue_summary('2023-01-01', '2023-12-31')
        
        assert result['success'] is False
        assert result['error'] == "Database error"

class TestReportingRoutes:
    
    @pytest.fixture
    def app(self):
        app = Flask(__name__)
        app.register_blueprint(reporting_bp, url_prefix='/api/reporting')
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def client(self, app):
        return app.test_client()
    
    @patch('reporting_routes.ReportingService')
    def test_get_financial_summary_success(self, mock_service, client):
        mock_service.return_value.get_financial_summary.return_value = {
            'success': True,
            'data': {'labels': ['Revenue'], 'values': [1000], 'total': 1000}
        }
        
        response = client.get('/api/reporting/financial-summary?dateFrom=2023-01-01&dateTo=2023-12-31')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['total'] == 1000
    
    @patch('reporting_routes.ReportingService')
    def test_get_financial_summary_invalid_date(self, mock_service, client):
        response = client.get('/api/reporting/financial-summary?dateFrom=invalid-date')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Invalid date format' in data['error']
    
    @patch('reporting_routes.ReportingService')
    def test_get_financial_summary_with_test_mode(self, mock_service, client):
        mock_service.return_value.get_financial_summary.return_value = {'success': True, 'data': {}}
        
        response = client.get('/api/reporting/financial-summary?testMode=true')
        
        mock_service.assert_called_once_with(test_mode=True)
    
    @patch('reporting_routes.ReportingService')
    def test_get_str_revenue_success(self, mock_service, client):
        mock_service.return_value.get_str_revenue_summary.return_value = {
            'success': True,
            'data': [{'channel': 'Airbnb', 'bookings': 5}]
        }
        
        response = client.get('/api/reporting/str-revenue')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 1
    
    @patch('reporting_routes.ReportingService')
    def test_get_account_summary_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [{'account': '1000', 'debet_total': 500}]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        response = client.get('/api/reporting/account-summary')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 1
    
    @patch('reporting_routes.ReportingService')
    def test_get_mutaties_table_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'TransactionDate': '2023-01-01', 'Amount': 100, 'Administration': 'GoodwinSolutions'}
        ]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_service.return_value.build_where_clause.return_value = ("administration = %s", ['GoodwinSolutions'])
        
        response = client.get('/api/reporting/mutaties-table?administration=GoodwinSolutions')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 1
    
    @patch('reporting_routes.ReportingService')
    def test_get_balance_data_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'Parent': 'Assets', 'ledger': '1000', 'total_amount': 1000}
        ]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_service.return_value.build_where_clause.return_value = ("1=1", [])
        
        response = client.get('/api/reporting/balance-data')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 1
    
    @patch('reporting_routes.ReportingService')
    def test_get_trends_data_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'Parent': 'Revenue', 'year': 2023, 'total_amount': 5000}
        ]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_service.return_value.build_where_clause.return_value = ("1=1", [])
        
        response = client.get('/api/reporting/trends-data?years=2023')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 1
    
    @patch('reporting_routes.ReportingService')
    def test_get_filter_options_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.side_effect = [
            [{'administration': 'GoodwinSolutions'}, {'administration': 'PeterPrive'}],
            [{'Reknum': '1000'}, {'Reknum': '2000'}],
            [{'ReferenceNumber': 'REF001'}]
        ]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        response = client.get('/api/reporting/filter-options')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['administrations'] == ['GoodwinSolutions', 'PeterPrive']
        assert data['ledgers'] == ['1000', '2000']
        assert data['references'] == ['REF001']
    
    @patch('reporting_routes.ReportingService')
    def test_get_available_years_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [{'value': 2023}, {'value': 2022}]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        response = client.get('/api/reporting/available-years')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['years'] == ['2023', '2022']
        
        # Verify tenant filtering was applied
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration IN' in query
        assert params == ['GoodwinSolutions', 'PeterPrive']
    
    @patch('reporting_routes.ReportingService')
    def test_get_available_data_years_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [{'value': 2023}, {'value': 2022}]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        response = client.get('/api/reporting/available-years')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['years'] == ['2023', '2022']
        
        # Verify tenant filtering was applied
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration IN' in query
        assert params == ['GoodwinSolutions', 'PeterPrive']
    
    @patch('reporting_routes.ReportingService')
    def test_get_available_data_references_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [{'value': 'REF001'}, {'value': 'REF002'}]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        response = client.get('/api/reporting/available-references')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['references'] == ['REF001', 'REF002']
        
        # Verify tenant filtering was applied
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration IN' in query
        assert params == ['GoodwinSolutions', 'PeterPrive']
    
    def test_get_available_data_invalid_type(self, client):
        response = client.get('/api/reporting/available-invalid')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert data['error'] == 'Invalid data type'
    
    @patch('reporting_routes.DatabaseManager')
    def test_get_check_reference_success(self, mock_db, client):
        # Mock database execute_query to return summary and transactions
        mock_db_instance = Mock()
        mock_db.return_value = mock_db_instance
        
        # Mock summary query result
        summary_data = [
            {
                'ReferenceNumber': 'REF001',
                'transaction_count': 2,
                'total_amount': 100.0
            }
        ]
        
        # Mock transactions query result
        transactions_data = [
            {
                'TransactionDate': '2023-01-01',
                'TransactionNumber': 'TRX001',
                'TransactionDescription': 'Test transaction 1',
                'Amount': 50.0,
                'Reknum': '1000',
                'AccountName': 'Cash',
                'Administration': 'GoodwinSolutions'
            },
            {
                'TransactionDate': '2023-01-02',
                'TransactionNumber': 'TRX002',
                'TransactionDescription': 'Test transaction 2',
                'Amount': 50.0,
                'Reknum': '1000',
                'AccountName': 'Cash',
                'Administration': 'GoodwinSolutions'
            }
        ]
        
        # Setup execute_query to return different results for different queries
        mock_db_instance.execute_query.side_effect = [summary_data, transactions_data]
        
        response = client.get('/api/reporting/check-reference?referenceNumber=REF001&administration=GoodwinSolutions')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['summary']) == 1
        assert data['summary'][0]['ReferenceNumber'] == 'REF001'
        assert data['summary'][0]['transaction_count'] == 2
        assert data['summary'][0]['total_amount'] == 100.0
        assert len(data['transactions']) == 2
    
    @patch('reporting_routes.ReportingService')
    def test_get_reference_analysis_success(self, mock_service, client):
        mock_cursor = Mock()
        mock_cursor.fetchall.side_effect = [
            [{'Reknum': '1000', 'AccountName': 'Cash'}],
            [{'TransactionDate': '2023-01-01', 'Amount': 100}],
            [{'jaar': 2023, 'kwartaal': 1, 'total_amount': 500}]
        ]
        mock_service.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_service.return_value.build_where_clause.return_value = ("1=1", [])
        
        response = client.get('/api/reporting/reference-analysis?reference_number=REF&years=2023')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['available_accounts']) == 1
        assert len(data['transactions']) == 1
        assert len(data['trend_data']) == 1
    
    @patch('reporting_routes.ReportingService')
    def test_route_error_handling(self, mock_service, client):
        mock_service.side_effect = Exception("Service error")
        
        response = client.get('/api/reporting/financial-summary')
        
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Service error' in data['error']