"""
API tests for tax_routes.py

Tests BTW (VAT) and Toeristenbelasting (Tourist Tax) route endpoints
including authentication enforcement, input validation, and happy path flows.

Requirements: 6.1, 6.2, 6.3, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def finance_auth():
    """
    Mock authentication with Finance_CRUD role for BTW endpoints.
    Provides btw_read, btw_process, transactions_create permissions.
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


@pytest.fixture
def str_auth():
    """
    Mock authentication with STR_CRUD role for tourist tax endpoints.
    Provides str_read, reports_read permissions.
    """
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['STR_CRUD']):
        mock_creds.return_value = ('test@example.com', ['STR_CRUD'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestTaxRoutesAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_btw_generate_report_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to BTW generate-report should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/btw/generate-report',
                json={'administration': 'test', 'year': 2024, 'quarter': 1}
            )
        assert response.status_code in (401, 403)

    def test_btw_save_transaction_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to BTW save-transaction should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/btw/save-transaction',
                json={'transaction': {'amount': 100}}
            )
        assert response.status_code in (401, 403)

    def test_btw_upload_report_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to BTW upload-report should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/btw/upload-report',
                json={'html_content': '<html></html>', 'filename': 'test.html'}
            )
        assert response.status_code in (401, 403)

    def test_toeristenbelasting_generate_report_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to tourist tax generate-report should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/toeristenbelasting/generate-report',
                json={'year': 2024}
            )
        assert response.status_code in (401, 403)

    def test_toeristenbelasting_available_years_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to available-years should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/toeristenbelasting/available-years')
        assert response.status_code in (401, 403)

    def test_btw_generate_report_insufficient_permissions_returns_403(self, client):
        """User without btw_read/btw_process permissions should get 403."""
        with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
             patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
             patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
             patch('auth.tenant_context.get_current_tenant', return_value='test-tenant'), \
             patch('auth.role_cache.get_tenant_roles', return_value=['STR_Read']):
            mock_creds.return_value = ('test@example.com', ['STR_Read'], None)

            response = client.post(
                '/api/btw/generate-report',
                headers={
                    'Authorization': 'Bearer test-token',
                    'X-Tenant': 'test-tenant'
                },
                json={'administration': 'test', 'year': 2024, 'quarter': 1}
            )
        assert response.status_code == 403


# ============================================================================
# BTW Generate Report - Input Validation Tests
# ============================================================================


class TestBTWGenerateReportValidation:
    """Tests for POST /api/btw/generate-report input validation."""

    @patch('routes.tax_routes.get_cache')
    @patch('routes.tax_routes.DatabaseManager')
    def test_btw_generate_report_missing_administration_returns_400(
        self, mock_db_class, mock_cache, client, finance_auth
    ):
        """Missing administration field should return 400."""
        response = client.post(
            '/api/btw/generate-report',
            headers=finance_auth,
            json={'year': 2024, 'quarter': 1}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'required' in data['error'].lower()

    @patch('routes.tax_routes.get_cache')
    @patch('routes.tax_routes.DatabaseManager')
    def test_btw_generate_report_missing_year_returns_400(
        self, mock_db_class, mock_cache, client, finance_auth
    ):
        """Missing year field should return 400."""
        response = client.post(
            '/api/btw/generate-report',
            headers=finance_auth,
            json={'administration': 'test', 'quarter': 1}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.tax_routes.get_cache')
    @patch('routes.tax_routes.DatabaseManager')
    def test_btw_generate_report_missing_quarter_returns_400(
        self, mock_db_class, mock_cache, client, finance_auth
    ):
        """Missing quarter field should return 400."""
        response = client.post(
            '/api/btw/generate-report',
            headers=finance_auth,
            json={'administration': 'test', 'year': 2024}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# BTW Save Transaction Tests
# ============================================================================


class TestBTWSaveTransaction:
    """Tests for POST /api/btw/save-transaction."""

    @patch('routes.tax_routes.BTWProcessor')
    def test_btw_save_transaction_missing_transaction_returns_400(
        self, mock_btw_proc, client, finance_auth
    ):
        """Missing transaction data should return 400."""
        response = client.post(
            '/api/btw/save-transaction',
            headers=finance_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'required' in data['error'].lower()

    @patch('routes.tax_routes.BTWProcessor')
    def test_btw_save_transaction_success(
        self, mock_btw_proc, client, finance_auth
    ):
        """Valid transaction data should be saved successfully."""
        mock_instance = MagicMock()
        mock_btw_proc.return_value = mock_instance
        mock_instance.save_btw_transaction.return_value = {
            'success': True,
            'transaction_id': 123
        }

        response = client.post(
            '/api/btw/save-transaction',
            headers=finance_auth,
            json={'transaction': {'amount': 1000, 'description': 'BTW Q1'}}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.tax_routes.BTWProcessor')
    def test_btw_save_transaction_processor_error_returns_500(
        self, mock_btw_proc, client, finance_auth
    ):
        """Processor exception should return 500."""
        mock_instance = MagicMock()
        mock_btw_proc.return_value = mock_instance
        mock_instance.save_btw_transaction.side_effect = Exception('DB error')

        response = client.post(
            '/api/btw/save-transaction',
            headers=finance_auth,
            json={'transaction': {'amount': 1000}}
        )
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# BTW Upload Report Tests
# ============================================================================


class TestBTWUploadReport:
    """Tests for POST /api/btw/upload-report."""

    @patch('routes.tax_routes.BTWProcessor')
    @patch('auth.tenant_context.get_current_tenant', return_value='test-tenant')
    def test_btw_upload_report_missing_html_content_returns_400(
        self, mock_tenant, mock_btw_proc, client, finance_auth
    ):
        """Missing html_content should return 400."""
        response = client.post(
            '/api/btw/upload-report',
            headers=finance_auth,
            json={'filename': 'test.html'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.tax_routes.BTWProcessor')
    @patch('auth.tenant_context.get_current_tenant', return_value='test-tenant')
    def test_btw_upload_report_missing_filename_returns_400(
        self, mock_tenant, mock_btw_proc, client, finance_auth
    ):
        """Missing filename should return 400."""
        response = client.post(
            '/api/btw/upload-report',
            headers=finance_auth,
            json={'html_content': '<html></html>'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.tax_routes.BTWProcessor')
    def test_btw_upload_report_no_administration_returns_400(
        self, mock_btw_proc, client, finance_auth
    ):
        """Missing administration context should return 400.
        
        The cognito_required decorator calls get_current_tenant first for role
        resolution, then the route calls it again for business logic. We use
        side_effect to return tenant for the decorator, then None for the route.
        """
        call_count = {'n': 0}

        def tenant_side_effect(req):
            call_count['n'] += 1
            # First call is from the decorator, return valid tenant
            if call_count['n'] == 1:
                return 'test-tenant'
            # Second call is from the route handler, return None
            return None

        with patch('auth.tenant_context.get_current_tenant', side_effect=tenant_side_effect):
            response = client.post(
                '/api/btw/upload-report',
                headers=finance_auth,
                json={'html_content': '<html></html>', 'filename': 'test.html'}
            )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.tax_routes.BTWProcessor')
    @patch('auth.tenant_context.get_current_tenant', return_value='test-tenant')
    def test_btw_upload_report_success(
        self, mock_tenant, mock_btw_proc, client, finance_auth
    ):
        """Valid upload request should succeed."""
        mock_instance = MagicMock()
        mock_btw_proc.return_value = mock_instance
        mock_instance.upload_report_to_drive.return_value = {
            'success': True,
            'file_id': 'drive-file-123'
        }

        response = client.post(
            '/api/btw/upload-report',
            headers=finance_auth,
            json={'html_content': '<html>report</html>', 'filename': 'BTW_Q1.html'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Toeristenbelasting Generate Report Tests
# ============================================================================


class TestToeristenbelastingGenerateReport:
    """Tests for POST /api/toeristenbelasting/generate-report."""

    @patch('routes.tax_routes.ToeristenbelastingProcessor')
    def test_toeristenbelasting_generate_report_missing_year_returns_400(
        self, mock_processor, client, str_auth
    ):
        """Missing year field should return 400."""
        response = client.post(
            '/api/toeristenbelasting/generate-report',
            headers=str_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'year' in data['error'].lower()

    @patch('routes.tax_routes.ToeristenbelastingProcessor')
    def test_toeristenbelasting_generate_report_success(
        self, mock_processor, client, str_auth
    ):
        """Valid tourist tax report generation should return success."""
        mock_instance = MagicMock()
        mock_processor.return_value = mock_instance
        mock_instance.generate_toeristenbelasting_report.return_value = {
            'success': True,
            'html_report': '<html>tourist tax report</html>',
            'total_tax': 500.0
        }

        response = client.post(
            '/api/toeristenbelasting/generate-report',
            headers=str_auth,
            json={'year': 2024}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.tax_routes.ToeristenbelastingProcessor')
    def test_toeristenbelasting_generate_report_processor_failure_returns_500(
        self, mock_processor, client, str_auth
    ):
        """Processor returning failure should return 500."""
        mock_instance = MagicMock()
        mock_processor.return_value = mock_instance
        mock_instance.generate_toeristenbelasting_report.return_value = {
            'success': False,
            'error': 'No data found for year'
        }

        response = client.post(
            '/api/toeristenbelasting/generate-report',
            headers=str_auth,
            json={'year': 2024}
        )
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.tax_routes.ToeristenbelastingProcessor')
    def test_toeristenbelasting_generate_report_exception_returns_500(
        self, mock_processor, client, str_auth
    ):
        """Processor exception should return 500."""
        mock_instance = MagicMock()
        mock_processor.return_value = mock_instance
        mock_instance.generate_toeristenbelasting_report.side_effect = Exception('DB error')

        response = client.post(
            '/api/toeristenbelasting/generate-report',
            headers=str_auth,
            json={'year': 2024}
        )
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Toeristenbelasting Available Years Tests
# ============================================================================


class TestToeristenbelastingAvailableYears:
    """Tests for GET /api/toeristenbelasting/available-years."""

    def test_toeristenbelasting_available_years_success(self, client, str_auth):
        """Authenticated request should return list of available years."""
        response = client.get(
            '/api/toeristenbelasting/available-years',
            headers=str_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'years' in data
        assert len(data['years']) == 4
        # Years should be strings
        for year in data['years']:
            assert isinstance(year, str)
            assert int(year) > 2000
