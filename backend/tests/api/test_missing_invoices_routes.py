"""
API tests for missing_invoices_routes.py

Tests transaction retrieval, receipt upload, and transaction reference
update endpoints including auth enforcement and input validation.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from io import BytesIO
from unittest.mock import patch, MagicMock


@pytest.fixture
def finance_auth():
    """Mock authentication with Finance_CRUD role for invoice endpoints."""
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


class TestMissingInvoicesAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_get_transactions_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get transactions should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/transactions', json={'ids': [1, 2]})
        assert response.status_code in (401, 403)

    def test_upload_receipt_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to upload receipt should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/upload-receipt',
                                   data={'supplierName': 'Test'},
                                   content_type='multipart/form-data')
        assert response.status_code in (401, 403)

    def test_update_transaction_refs_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to update refs should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/update-transaction-refs', json={
                'ids': [1], 'driveUrl': 'https://drive.google.com/file/123'
            })
        assert response.status_code in (401, 403)


# ============================================================================
# Get Transactions Tests
# ============================================================================


class TestGetTransactions:
    """Tests for POST /api/transactions."""

    @patch('routes.missing_invoices_routes.db')
    def test_get_transactions_empty_ids_returns_empty(self, mock_db,
                                                      client, finance_auth):
        """Empty ids list returns empty array."""
        response = client.post(
            '/api/transactions',
            headers=finance_auth,
            json={'ids': []}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == []

    @patch('routes.missing_invoices_routes.db')
    def test_get_transactions_with_ids_success(self, mock_db,
                                               client, finance_auth):
        """Valid ids return transaction data."""
        from datetime import date
        mock_db.execute_query.return_value = [
            {
                'ID': 1,
                'TransactionAmount': 100.50,
                'TransactionDate': date(2024, 1, 15),
                'TransactionDescription': 'Test payment',
                'ReferenceNumber': 'REF001'
            }
        ]

        response = client.post(
            '/api/transactions',
            headers=finance_auth,
            json={'ids': [1]}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 1
        assert data[0]['ID'] == 1
        assert data[0]['TransactionAmount'] == 100.50


# ============================================================================
# Upload Receipt Tests
# ============================================================================


class TestUploadReceipt:
    """Tests for POST /api/upload-receipt."""

    def test_upload_receipt_without_file_returns_400(self, client, finance_auth):
        """Upload without file returns 400."""
        response = client.post(
            '/api/upload-receipt',
            headers=finance_auth,
            data={'supplierName': 'Test Vendor'},
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_upload_receipt_without_supplier_returns_400(self, client, finance_auth):
        """Upload without supplier name returns 400."""
        data = {
            'file': (BytesIO(b'fake pdf content'), 'receipt.pdf')
        }

        response = client.post(
            '/api/upload-receipt',
            headers=finance_auth,
            data=data,
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'error' in result


# ============================================================================
# Update Transaction Refs Tests
# ============================================================================


class TestUpdateTransactionRefs:
    """Tests for POST /api/update-transaction-refs."""

    @patch('routes.missing_invoices_routes.db')
    def test_update_refs_missing_ids_returns_400(self, mock_db,
                                                 client, finance_auth):
        """Missing ids returns 400."""
        response = client.post(
            '/api/update-transaction-refs',
            headers=finance_auth,
            json={'driveUrl': 'https://drive.google.com/file/123'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('routes.missing_invoices_routes.db')
    def test_update_refs_missing_url_returns_400(self, mock_db,
                                                 client, finance_auth):
        """Missing driveUrl returns 400."""
        response = client.post(
            '/api/update-transaction-refs',
            headers=finance_auth,
            json={'ids': [1, 2]}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('routes.missing_invoices_routes.db')
    def test_update_refs_success(self, mock_db, client, finance_auth):
        """Valid update returns success."""
        mock_db.execute_query.return_value = None

        response = client.post(
            '/api/update-transaction-refs',
            headers=finance_auth,
            json={
                'ids': [1, 2],
                'driveUrl': 'https://drive.google.com/file/123',
                'filename': 'receipt.pdf'
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
