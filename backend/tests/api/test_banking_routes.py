"""
API tests for banking_routes.py

Tests banking transaction processing endpoints including auth enforcement,
file scanning, processing, saving, lookups, mutaties, and updates.

Reference: .kiro/specs/code-quality-fixes-2026-06/tasks.md Task 20.1
"""
import pytest
import json
from unittest.mock import patch, MagicMock

from db_exceptions import ClosedPeriodError


@pytest.fixture
def banking_auth():
    """Mock authentication with Finance_CRUD role for banking endpoints."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Finance_CRUD']):
        mock_creds.return_value = ('test@example.com', ['Finance_CRUD'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


@pytest.mark.api
class TestBankingAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    @pytest.mark.parametrize("method,url,json_data", [
        ('GET', '/api/banking/scan-files', None),
        ('POST', '/api/banking/process-files', {'files': []}),
        ('POST', '/api/banking/save-transactions', {}),
        ('GET', '/api/banking/lookups', None),
        ('GET', '/api/banking/mutaties', None),
        ('POST', '/api/banking/update-mutatie', {}),
        ('POST', '/api/banking/insert-mutatie', {}),
    ])
    def test_unauthenticated_returns_401_or_403(self, client, method, url, json_data):
        """Unauthenticated requests to banking endpoints should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            if method == 'GET':
                response = client.get(url)
            else:
                response = client.post(url, json=json_data)
        assert response.status_code in (401, 403)


# ============================================================================
# Scan Files Tests
# ============================================================================


@pytest.mark.api
class TestBankingScanFiles:
    """Tests for GET /api/banking/scan-files."""

    @patch('routes.banking_routes.banking_service')
    def test_scan_files_success(self, mock_service, client, banking_auth):
        """Authenticated user can scan for banking files."""
        mock_service.scan_banking_files.return_value = {
            'success': True,
            'files': [{'name': 'transactions_2024.csv', 'path': '/downloads/transactions_2024.csv'}],
            'count': 1
        }
        response = client.get('/api/banking/scan-files', headers=banking_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1

    @patch('routes.banking_routes.banking_service')
    def test_scan_files_with_folder_param(self, mock_service, client, banking_auth):
        """Scan files passes folder parameter to service."""
        mock_service.scan_banking_files.return_value = {'success': True, 'files': [], 'count': 0}
        response = client.get('/api/banking/scan-files?folder=/custom/path', headers=banking_auth)
        assert response.status_code == 200
        mock_service.scan_banking_files.assert_called_once_with('/custom/path')

    @patch('routes.banking_routes.banking_service')
    def test_scan_files_service_failure(self, mock_service, client, banking_auth):
        """Service failure returns 500."""
        mock_service.scan_banking_files.return_value = {'success': False, 'error': 'Directory not found'}
        response = client.get('/api/banking/scan-files', headers=banking_auth)
        assert response.status_code == 500

    @patch('routes.banking_routes.banking_service')
    def test_scan_files_exception(self, mock_service, client, banking_auth):
        """Unhandled exception returns 500 with error message."""
        mock_service.scan_banking_files.side_effect = Exception('Disk error')
        response = client.get('/api/banking/scan-files', headers=banking_auth)
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'Disk error' in data['error']


# ============================================================================
# Process Files Tests
# ============================================================================


@pytest.mark.api
class TestBankingProcessFiles:
    """Tests for POST /api/banking/process-files."""

    @patch('routes.banking_routes.banking_service')
    def test_process_files_success(self, mock_service, client, banking_auth):
        """Authenticated user can process banking files."""
        mock_service.process_banking_files.return_value = {
            'success': True, 'transactions': [{'id': 1, 'amount': 100.00}], 'count': 1
        }
        response = client.post(
            '/api/banking/process-files', headers=banking_auth,
            json={'files': ['/path/to/file.csv'], 'test_mode': True}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.banking_routes.banking_service')
    def test_process_files_access_denied(self, mock_service, client, banking_auth):
        """Access denied returns 403."""
        mock_service.process_banking_files.return_value = {
            'success': False, 'error': 'Access denied for this tenant'
        }
        response = client.post(
            '/api/banking/process-files', headers=banking_auth,
            json={'files': ['/path/to/file.csv']}
        )
        assert response.status_code == 403

    @patch('routes.banking_routes.banking_service')
    def test_process_files_bad_request(self, mock_service, client, banking_auth):
        """Non-access-denied failure returns 400."""
        mock_service.process_banking_files.return_value = {
            'success': False, 'error': 'Invalid file format'
        }
        response = client.post(
            '/api/banking/process-files', headers=banking_auth,
            json={'files': ['/path/to/bad.txt']}
        )
        assert response.status_code == 400

    @patch('routes.banking_routes.banking_service')
    def test_process_files_exception(self, mock_service, client, banking_auth):
        """Unhandled exception returns 500."""
        mock_service.process_banking_files.side_effect = RuntimeError('Parse error')
        response = client.post(
            '/api/banking/process-files', headers=banking_auth,
            json={'files': ['/path/to/file.csv']}
        )
        assert response.status_code == 500


# ============================================================================
# Save Transactions Tests
# ============================================================================


@pytest.mark.api
class TestBankingSaveTransactions:
    """Tests for POST /api/banking/save-transactions."""

    @patch('routes.banking_routes.banking_service')
    def test_save_transactions_success(self, mock_service, client, banking_auth):
        """Successfully save approved transactions."""
        mock_service.save_transactions.return_value = {'success': True, 'saved': 5, 'duplicates': 1}
        response = client.post(
            '/api/banking/save-transactions', headers=banking_auth,
            json={'transactions': [{'date': '2024-01-15', 'amount': 100.00}], 'test_mode': True}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['saved'] == 5

    @patch('routes.banking_routes.banking_service')
    def test_save_transactions_closed_period(self, mock_service, client, banking_auth):
        """Saving to closed period returns 400."""
        mock_service.save_transactions.side_effect = ClosedPeriodError(
            [{'transaction': {'date': '2023-01-01'}, 'year': 2023}]
        )
        response = client.post(
            '/api/banking/save-transactions', headers=banking_auth,
            json={'transactions': [{'date': '2023-01-01', 'amount': 50}]}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.banking_routes.banking_service')
    def test_save_transactions_exception(self, mock_service, client, banking_auth):
        """Unhandled exception returns 500."""
        mock_service.save_transactions.side_effect = Exception('DB connection lost')
        response = client.post(
            '/api/banking/save-transactions', headers=banking_auth,
            json={'transactions': []}
        )
        assert response.status_code == 500


# ============================================================================
# Lookups Tests
# ============================================================================


@pytest.mark.api
class TestBankingLookups:
    """Tests for GET /api/banking/lookups."""

    @patch('routes.banking_routes.banking_service')
    def test_lookups_success(self, mock_service, client, banking_auth):
        """Retrieve mapping data for account codes."""
        mock_service.get_lookups.return_value = {
            'success': True, 'accounts': [{'code': '1000', 'name': 'Kas'}]
        }
        response = client.get('/api/banking/lookups', headers=banking_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'accounts' in data

    @patch('routes.banking_routes.banking_service')
    def test_lookups_service_failure(self, mock_service, client, banking_auth):
        """Service failure returns 500."""
        mock_service.get_lookups.return_value = {'success': False, 'error': 'Database error'}
        response = client.get('/api/banking/lookups', headers=banking_auth)
        assert response.status_code == 500


# ============================================================================
# Mutaties Tests
# ============================================================================


@pytest.mark.api
class TestBankingMutaties:
    """Tests for GET /api/banking/mutaties."""

    @patch('routes.banking_routes.banking_service')
    def test_mutaties_success(self, mock_service, client, banking_auth):
        """Retrieve mutaties with default filters."""
        mock_service.get_mutaties.return_value = {
            'success': True, 'data': [{'ID': 1, 'Amount': 100}], 'total': 1
        }
        response = client.get('/api/banking/mutaties', headers=banking_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.banking_routes.banking_service')
    def test_mutaties_with_filters(self, mock_service, client, banking_auth):
        """Filter parameters are passed to the service layer."""
        mock_service.get_mutaties.return_value = {'success': True, 'data': [], 'total': 0}
        response = client.get(
            '/api/banking/mutaties?years=2024,2023&limit=50&offset=10', headers=banking_auth
        )
        assert response.status_code == 200
        filters = mock_service.get_mutaties.call_args[0][0]
        assert '2024' in filters['years']
        assert '2023' in filters['years']
        assert filters['limit'] == '50'
        assert filters['offset'] == '10'

    @patch('routes.banking_routes.banking_service')
    def test_mutaties_access_denied(self, mock_service, client, banking_auth):
        """Access denied returns 403."""
        mock_service.get_mutaties.return_value = {'success': False, 'error': 'Access denied'}
        response = client.get('/api/banking/mutaties', headers=banking_auth)
        assert response.status_code == 403

    @patch('routes.banking_routes.banking_service')
    def test_mutaties_exception(self, mock_service, client, banking_auth):
        """Unhandled exception returns 500."""
        mock_service.get_mutaties.side_effect = Exception('Query timeout')
        response = client.get('/api/banking/mutaties', headers=banking_auth)
        assert response.status_code == 500


# ============================================================================
# Update Mutatie Tests
# ============================================================================


@pytest.mark.api
class TestBankingUpdateMutatie:
    """Tests for POST /api/banking/update-mutatie."""

    @patch('database.DatabaseManager')
    @patch('routes.banking_routes.banking_service')
    def test_update_mutatie_success(self, mock_service, mock_db_class, client, banking_auth):
        """Successfully update a mutatie record."""
        mock_service.update_mutatie.return_value = {'success': True, 'message': 'Record updated'}
        mock_db_class.return_value.execute_query.return_value = []  # No closed period
        response = client.post(
            '/api/banking/update-mutatie', headers=banking_auth,
            json={'ID': 42, 'TransactionDate': '2024-06-15', 'TransactionAmount': 100.00}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.banking_routes.banking_service')
    def test_update_mutatie_no_id(self, mock_service, client, banking_auth):
        """Missing ID returns 400."""
        response = client.post(
            '/api/banking/update-mutatie', headers=banking_auth,
            json={'Description': 'No ID provided'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'No ID provided' in data['error']

    @patch('database.DatabaseManager')
    @patch('routes.banking_routes.banking_service')
    def test_update_mutatie_not_found(self, mock_service, mock_db_class, client, banking_auth):
        """Updating non-existent record returns 404."""
        mock_service.update_mutatie.return_value = {'success': False, 'error': 'Record not found'}
        mock_db_class.return_value.execute_query.return_value = []
        response = client.post(
            '/api/banking/update-mutatie', headers=banking_auth,
            json={'ID': 9999, 'TransactionAmount': 0}
        )
        assert response.status_code == 404

    @patch('database.DatabaseManager')
    @patch('routes.banking_routes.banking_service')
    def test_update_mutatie_closed_period(self, mock_service, mock_db_class, client, banking_auth):
        """Updating record in closed period returns 400."""
        mock_db_class.return_value.execute_query.return_value = [{'year': 2023}]
        response = client.post(
            '/api/banking/update-mutatie', headers=banking_auth,
            json={'ID': 42, 'TransactionDate': '2023-06-15', 'TransactionAmount': 100.00}
        )
        assert response.status_code == 400


# ============================================================================
# Insert Mutatie Tests
# ============================================================================


@pytest.mark.api
class TestBankingInsertMutatie:
    """Tests for POST /api/banking/insert-mutatie."""

    @patch('database.DatabaseManager')
    def test_insert_mutatie_success(self, mock_db_class, client, banking_auth):
        """Successfully insert a new mutatie record."""
        mock_db = mock_db_class.return_value
        mock_db.execute_query.return_value = []  # No closed period
        mock_db.insert_transaction.return_value = True
        response = client.post(
            '/api/banking/insert-mutatie', headers=banking_auth,
            json={'TransactionDate': '2024-07-01', 'TransactionAmount': 250.00}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('database.DatabaseManager')
    def test_insert_mutatie_closed_period(self, mock_db_class, client, banking_auth):
        """Inserting into closed period returns 400."""
        mock_db_class.return_value.execute_query.return_value = [{'year': 2023}]
        response = client.post(
            '/api/banking/insert-mutatie', headers=banking_auth,
            json={'TransactionDate': '2023-03-15', 'TransactionAmount': 100.00}
        )
        assert response.status_code == 400

    @patch('database.DatabaseManager')
    def test_insert_mutatie_db_failure(self, mock_db_class, client, banking_auth):
        """Database insert failure returns 500."""
        mock_db = mock_db_class.return_value
        mock_db.execute_query.return_value = []
        mock_db.insert_transaction.return_value = False
        response = client.post(
            '/api/banking/insert-mutatie', headers=banking_auth,
            json={'TransactionDate': '2024-07-01', 'TransactionAmount': 50.00}
        )
        assert response.status_code == 500


# ============================================================================
# Check Accounts Tests
# ============================================================================


@pytest.mark.api
class TestBankingCheckAccounts:
    """Tests for GET /api/banking/check-accounts."""

    @patch('routes.banking_routes.banking_service')
    def test_check_accounts_success(self, mock_service, client, banking_auth):
        """Successfully check account balances."""
        mock_service.check_accounts.return_value = {
            'success': True, 'accounts': [{'code': '1000', 'balance': 5000.00}]
        }
        response = client.get('/api/banking/check-accounts', headers=banking_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.banking_routes.banking_service')
    def test_check_accounts_with_end_date(self, mock_service, client, banking_auth):
        """End date parameter is passed to service."""
        mock_service.check_accounts.return_value = {'success': True, 'accounts': []}
        response = client.get('/api/banking/check-accounts?end_date=2024-06-30', headers=banking_auth)
        assert response.status_code == 200
        mock_service.check_accounts.assert_called_once_with('test-tenant', '2024-06-30')

    @patch('routes.banking_routes.banking_service')
    def test_check_accounts_failure(self, mock_service, client, banking_auth):
        """Service failure returns 500."""
        mock_service.check_accounts.return_value = {'success': False, 'error': 'Query failed'}
        response = client.get('/api/banking/check-accounts', headers=banking_auth)
        assert response.status_code == 500


# ============================================================================
# Apply Patterns Tests
# ============================================================================


@pytest.mark.api
class TestBankingApplyPatterns:
    """Tests for POST /api/banking/apply-patterns."""

    @patch('routes.banking_routes.banking_service')
    def test_apply_patterns_success(self, mock_service, client, banking_auth):
        """Apply pattern matching to transactions."""
        mock_service.apply_patterns.return_value = {
            'success': True,
            'transactions': [{'id': 1, 'predicted_debet': '4000', 'confidence': 0.95}]
        }
        response = client.post(
            '/api/banking/apply-patterns', headers=banking_auth,
            json={'transactions': [{'description': 'ALBERT HEIJN'}], 'use_enhanced': True}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.banking_routes.banking_service')
    def test_apply_patterns_exception(self, mock_service, client, banking_auth):
        """Unhandled exception returns 500."""
        mock_service.apply_patterns.side_effect = Exception('Pattern DB error')
        response = client.post(
            '/api/banking/apply-patterns', headers=banking_auth,
            json={'transactions': []}
        )
        assert response.status_code == 500
