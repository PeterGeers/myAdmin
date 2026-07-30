"""
API tests for invoice_routes.py

Tests invoice upload, duplicate detection, and transaction approval endpoints
including authentication enforcement, input validation, and happy path flows.

Requirements: 6.1, 6.2, 6.4, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import io
import os
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def invoice_auth():
    """
    Mock authentication with Finance_CRUD role for invoice endpoints.
    Provides invoices_create, transactions_create permissions.
    """
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


class TestInvoiceRoutesAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_upload_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated POST to /api/upload should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            data = {'file': (io.BytesIO(b'%PDF-1.4 test'), 'test.pdf')}
            response = client.post(
                '/api/upload',
                data=data,
                content_type='multipart/form-data'
            )
        assert response.status_code in (401, 403)

    def test_approve_transactions_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated POST to /api/approve-transactions should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/approve-transactions',
                json={'transactions': []}
            )
        assert response.status_code in (401, 403)

    def test_upload_options_no_auth_required_returns_200(self, client):
        """OPTIONS request to /api/upload should not require auth (CORS preflight)."""
        response = client.options('/api/upload')
        assert response.status_code == 200


# ============================================================================
# Upload Endpoint - Input Validation Tests
# ============================================================================


class TestUploadValidation:
    """Tests for POST /api/upload input validation."""

    @patch('routes.invoice_routes.InvoiceService')
    def test_upload_no_file_returns_400(self, mock_service_class, client, invoice_auth):
        """Request without file field should return 400."""
        response = client.post(
            '/api/upload',
            headers=invoice_auth,
            data={},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'no file' in data['error'].lower()

    @patch('routes.invoice_routes.InvoiceService')
    def test_upload_empty_filename_returns_400(self, mock_service_class, client, invoice_auth):
        """File with empty filename should return 400."""
        data = {'file': (io.BytesIO(b'content'), '')}
        response = client.post(
            '/api/upload',
            headers=invoice_auth,
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        resp_data = json.loads(response.data)
        assert resp_data['success'] is False
        assert 'no file selected' in resp_data['error'].lower()

    @patch('routes.invoice_routes.InvoiceService')
    def test_upload_invalid_file_type_returns_400(self, mock_service_class, client, invoice_auth):
        """File with disallowed extension should return 400."""
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance
        mock_instance.allowed_file.return_value = False

        data = {'file': (io.BytesIO(b'content'), 'malware.exe')}
        response = client.post(
            '/api/upload',
            headers=invoice_auth,
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        resp_data = json.loads(response.data)
        assert resp_data['success'] is False
        assert 'invalid file type' in resp_data['error'].lower()


# ============================================================================
# Upload Endpoint - Duplicate Detection Tests
# ============================================================================


class TestUploadDuplicateDetection:
    """Tests for duplicate detection during upload."""

    @patch('routes.invoice_routes.InvoiceService')
    def test_upload_duplicate_detected_returns_409(
        self, mock_service_class, client, invoice_auth, tmp_path
    ):
        """Duplicate file detection should return 409 with duplicate info."""
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance
        mock_instance.allowed_file.return_value = True
        mock_instance.upload_to_drive.return_value = {'file_id': 'drive-123'}
        mock_instance.check_early_duplicates.return_value = {
            'has_duplicates': True,
            'message': 'File already exists in folder',
            'duplicate_info': {'existing_file_id': 'drive-456'}
        }

        data = {
            'file': (io.BytesIO(b'%PDF-1.4 test content'), 'invoice.pdf'),
            'folderName': 'Invoices'
        }
        with patch('routes.invoice_routes.UPLOAD_FOLDER', str(tmp_path)):
            response = client.post(
                '/api/upload',
                headers=invoice_auth,
                data=data,
                content_type='multipart/form-data'
            )
        assert response.status_code == 409
        resp_data = json.loads(response.data)
        assert resp_data['success'] is False
        assert resp_data['error'] == 'duplicate_detected'
        assert 'duplicate_info' in resp_data

    @patch('routes.invoice_routes.InvoiceService')
    def test_upload_force_upload_bypasses_duplicate_check(
        self, mock_service_class, client, invoice_auth, tmp_path
    ):
        """forceUpload=true should bypass duplicate detection."""
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance
        mock_instance.allowed_file.return_value = True
        mock_instance.upload_to_drive.return_value = {'file_id': 'drive-123'}
        mock_instance.process_invoice_file.return_value = {
            'folder': 'Vendor A',
            'extracted_text': 'Invoice text',
            'vendor_data': {'name': 'Vendor A'},
            'transactions': [],
            'prepared_transactions': [],
            'template_transactions': [],
            'parser_used': 'ai'
        }

        data = {
            'file': (io.BytesIO(b'%PDF-1.4 test content'), 'invoice.pdf'),
            'folderName': 'Invoices',
            'forceUpload': 'true'
        }
        with patch('routes.invoice_routes.UPLOAD_FOLDER', str(tmp_path)):
            response = client.post(
                '/api/upload',
                headers=invoice_auth,
                data=data,
                content_type='multipart/form-data'
            )
        assert response.status_code == 200
        resp_data = json.loads(response.data)
        assert resp_data['success'] is True
        # Duplicate check should NOT have been called
        mock_instance.check_early_duplicates.assert_not_called()


# ============================================================================
# Upload Endpoint - Happy Path Tests
# ============================================================================


class TestUploadHappyPath:
    """Tests for successful upload flow."""

    @patch('routes.invoice_routes.InvoiceService')
    def test_upload_success_returns_processed_data(
        self, mock_service_class, client, invoice_auth, tmp_path
    ):
        """Successful upload should return processed invoice data."""
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance
        mock_instance.allowed_file.return_value = True
        mock_instance.upload_to_drive.return_value = {'file_id': 'drive-123'}
        mock_instance.check_early_duplicates.return_value = {
            'has_duplicates': False
        }
        mock_instance.process_invoice_file.return_value = {
            'folder': 'Vendor A',
            'extracted_text': 'Invoice #12345',
            'vendor_data': {'name': 'Vendor A', 'kvk': '12345678'},
            'transactions': [{'amount': 100.0}],
            'prepared_transactions': [{'debet': '1000', 'credit': '4000'}],
            'template_transactions': [],
            'parser_used': 'vendor_specific'
        }

        data = {
            'file': (io.BytesIO(b'%PDF-1.4 test content'), 'invoice.pdf'),
            'folderName': 'Invoices'
        }
        with patch('routes.invoice_routes.UPLOAD_FOLDER', str(tmp_path)):
            response = client.post(
                '/api/upload',
                headers=invoice_auth,
                data=data,
                content_type='multipart/form-data'
            )
        assert response.status_code == 200
        resp_data = json.loads(response.data)
        assert resp_data['success'] is True
        assert resp_data['filename'] == 'invoice.pdf'
        assert resp_data['folder'] == 'Vendor A'
        assert resp_data['parserUsed'] == 'vendor_specific'
        assert 'extractedText' in resp_data
        assert 'vendorData' in resp_data
        assert 'transactions' in resp_data

    @patch('routes.invoice_routes.InvoiceService')
    def test_upload_service_exception_returns_500(
        self, mock_service_class, client, invoice_auth, tmp_path
    ):
        """InvoiceService exception should return 500."""
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance
        mock_instance.allowed_file.return_value = True
        mock_instance.upload_to_drive.side_effect = Exception('Drive API error')

        data = {
            'file': (io.BytesIO(b'%PDF-1.4 test content'), 'invoice.pdf'),
            'folderName': 'Invoices'
        }
        with patch('routes.invoice_routes.UPLOAD_FOLDER', str(tmp_path)):
            response = client.post(
                '/api/upload',
                headers=invoice_auth,
                data=data,
                content_type='multipart/form-data'
            )
        assert response.status_code == 500
        resp_data = json.loads(response.data)
        assert resp_data['success'] is False
        assert 'Drive API error' in resp_data['error']


# ============================================================================
# Approve Transactions Endpoint Tests
# ============================================================================


class TestApproveTransactions:
    """Tests for POST /api/approve-transactions."""

    @patch('transaction_logic.TransactionLogic')
    def test_approve_transactions_success(
        self, mock_logic_class, client, invoice_auth
    ):
        """Valid transactions should be saved successfully."""
        mock_instance = MagicMock()
        mock_logic_class.return_value = mock_instance
        mock_instance.save_approved_transactions.return_value = [
            {'id': 1, 'amount': 100.0},
            {'id': 2, 'amount': 200.0}
        ]

        response = client.post(
            '/api/approve-transactions',
            headers=invoice_auth,
            json={'transactions': [
                {'amount': 100.0, 'description': 'Item 1'},
                {'amount': 200.0, 'description': 'Item 2'},
                {'amount': 0.0, 'description': 'Zero line'}
            ]}
        )
        assert response.status_code == 200
        resp_data = json.loads(response.data)
        assert resp_data['success'] is True
        assert len(resp_data['savedTransactions']) == 2
        assert resp_data['skippedCount'] == 1
        assert 'skipped' in resp_data['message']

    @patch('transaction_logic.TransactionLogic')
    def test_approve_transactions_closed_period_returns_400(
        self, mock_logic_class, client, invoice_auth
    ):
        """ClosedPeriodError should return 400."""
        from db_exceptions import ClosedPeriodError

        mock_instance = MagicMock()
        mock_logic_class.return_value = mock_instance
        mock_instance.save_approved_transactions.side_effect = ClosedPeriodError(
            offending_transactions=[{'transaction': 'T001', 'year': 2023}],
            message='Period 2023-Q4 is closed'
        )

        response = client.post(
            '/api/approve-transactions',
            headers=invoice_auth,
            json={'transactions': [{'amount': 100.0}]}
        )
        assert response.status_code == 400
        resp_data = json.loads(response.data)
        assert resp_data['success'] is False
        assert 'closed' in resp_data['error'].lower()

    @patch('transaction_logic.TransactionLogic')
    def test_approve_transactions_generic_error_returns_500(
        self, mock_logic_class, client, invoice_auth
    ):
        """Generic exception should return 500."""
        mock_instance = MagicMock()
        mock_logic_class.return_value = mock_instance
        mock_instance.save_approved_transactions.side_effect = Exception('DB connection lost')

        response = client.post(
            '/api/approve-transactions',
            headers=invoice_auth,
            json={'transactions': [{'amount': 100.0}]}
        )
        assert response.status_code == 500
        resp_data = json.loads(response.data)
        assert resp_data['success'] is False
        assert 'DB connection lost' in resp_data['error']


# ============================================================================
# Temp File Collision Tests (REQ-1.3)
# ============================================================================


class TestTempFileCollision:
    """Verify concurrent uploads with same filename don't collide."""

    @patch('routes.invoice_routes.InvoiceService')
    def test_concurrent_uploads_same_filename_get_unique_temp_paths(
        self, mock_service_class, client, invoice_auth, tmp_path
    ):
        """
        Two uploads of 'invoice.pdf' should produce different temp files.
        Verifies REQ-1.3: temp files are namespaced to avoid collisions.
        """
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance
        mock_instance.allowed_file.return_value = True
        mock_instance.upload_to_drive.return_value = {'file_id': 'drive-123'}
        mock_instance.check_early_duplicates.return_value = {
            'has_duplicates': False,
            'message': '',
            'duplicate_info': None
        }
        mock_instance.process_invoice_file.return_value = {
            'folder': 'Vendor A',
            'extracted_text': 'Invoice text',
            'vendor_data': {'name': 'Vendor A'},
            'transactions': [{'date': '2024-01-01', 'amount': 100, 'description': 'Test'}],
            'prepared_transactions': [],
            'template_transactions': [],
            'parser_used': 'ai'
        }

        saved_paths = []
        original_save = None

        # Capture the temp_path passed to process_invoice_file
        def capture_process_call(temp_path, drive_result, folder_name, tenant):
            saved_paths.append(temp_path)
            return {
                'folder': 'Vendor A',
                'extracted_text': 'Invoice text',
                'vendor_data': {'name': 'Vendor A'},
                'transactions': [{'date': '2024-01-01', 'amount': 100, 'description': 'Test'}],
                'prepared_transactions': [],
                'template_transactions': [],
                'parser_used': 'ai'
            }

        mock_instance.process_invoice_file.side_effect = capture_process_call

        with patch('routes.invoice_routes.UPLOAD_FOLDER', str(tmp_path)):
            # First upload
            data1 = {
                'file': (io.BytesIO(b'%PDF-1.4 first file content'), 'invoice.pdf'),
                'folderName': 'Invoices'
            }
            response1 = client.post(
                '/api/upload',
                headers=invoice_auth,
                data=data1,
                content_type='multipart/form-data'
            )

            # Second upload with same filename
            data2 = {
                'file': (io.BytesIO(b'%PDF-1.4 second file content'), 'invoice.pdf'),
                'folderName': 'Invoices'
            }
            response2 = client.post(
                '/api/upload',
                headers=invoice_auth,
                data=data2,
                content_type='multipart/form-data'
            )

        # Both should succeed
        assert response1.status_code == 200
        assert response2.status_code == 200

        # The temp paths should be different (UUID ensures uniqueness)
        assert len(saved_paths) == 2
        assert saved_paths[0] != saved_paths[1], (
            f"Temp paths should be unique but got same path: {saved_paths[0]}"
        )

        # Both responses should report the original filename (not the unique temp name)
        resp1 = json.loads(response1.data)
        resp2 = json.loads(response2.data)
        assert resp1['filename'] == 'invoice.pdf'
        assert resp2['filename'] == 'invoice.pdf'

    @patch('routes.invoice_routes.InvoiceService')
    def test_temp_filename_contains_tenant_and_uuid(
        self, mock_service_class, client, invoice_auth, tmp_path
    ):
        """
        Temp filename should follow pattern: {tenant}_{uuid8}_{filename}
        Verifies REQ-1.3: tenant prefix + UUID namespacing.
        """
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance
        mock_instance.allowed_file.return_value = True
        mock_instance.upload_to_drive.return_value = {'file_id': 'drive-123'}
        mock_instance.check_early_duplicates.return_value = {
            'has_duplicates': False,
            'message': '',
            'duplicate_info': None
        }

        captured_temp_path = []

        def capture_process(temp_path, drive_result, folder_name, tenant):
            captured_temp_path.append(temp_path)
            return {
                'folder': 'Vendor A',
                'extracted_text': 'text',
                'vendor_data': None,
                'transactions': [],
                'prepared_transactions': [],
                'template_transactions': [],
                'parser_used': 'ai'
            }

        mock_instance.process_invoice_file.side_effect = capture_process

        with patch('routes.invoice_routes.UPLOAD_FOLDER', str(tmp_path)):
            data = {
                'file': (io.BytesIO(b'%PDF-1.4 content'), 'invoice.pdf'),
                'folderName': 'Invoices'
            }
            response = client.post(
                '/api/upload',
                headers=invoice_auth,
                data=data,
                content_type='multipart/form-data'
            )

        assert response.status_code == 200
        assert len(captured_temp_path) == 1

        # Extract just the filename from the temp path
        temp_filename = os.path.basename(captured_temp_path[0])

        # Should match pattern: test-tenant_{8 hex chars}_invoice.pdf
        import re
        pattern = r'^test-tenant_[0-9a-f]{8}_invoice\.pdf$'
        assert re.match(pattern, temp_filename), (
            f"Temp filename '{temp_filename}' doesn't match expected pattern "
            f"'{{tenant}}_{{uuid8}}_{{filename}}'"
        )

    @patch('routes.invoice_routes.InvoiceService')
    def test_cleanup_uses_unique_temp_path(
        self, mock_service_class, client, invoice_auth, tmp_path
    ):
        """
        When duplicate is detected, cleanup should use the unique temp path.
        Verifies REQ-1.3: cleanup of temp files still works correctly.
        """
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance
        mock_instance.allowed_file.return_value = True
        mock_instance.upload_to_drive.return_value = {'file_id': 'drive-123'}
        mock_instance.check_early_duplicates.return_value = {
            'has_duplicates': True,
            'message': 'File already exists',
            'duplicate_info': {'existing_file_id': 'drive-456'}
        }

        with patch('routes.invoice_routes.UPLOAD_FOLDER', str(tmp_path)):
            data = {
                'file': (io.BytesIO(b'%PDF-1.4 content'), 'invoice.pdf'),
                'folderName': 'Invoices'
            }
            response = client.post(
                '/api/upload',
                headers=invoice_auth,
                data=data,
                content_type='multipart/form-data'
            )

        assert response.status_code == 409

        # cleanup_temp_file should have been called with the unique path
        mock_instance.cleanup_temp_file.assert_called_once()
        cleanup_path = mock_instance.cleanup_temp_file.call_args[0][0]
        cleanup_filename = os.path.basename(cleanup_path)

        # Should NOT be just 'invoice.pdf' — should include tenant + uuid
        assert cleanup_filename != 'invoice.pdf'
        assert 'test-tenant_' in cleanup_filename
        assert cleanup_filename.endswith('_invoice.pdf')
