"""
API tests for duplicate_detection_routes.py

Tests duplicate transaction detection endpoints including auth enforcement,
checking for duplicates, logging decisions, and handling decisions.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def finance_auth():
    """Mock authentication with Finance_CRUD role for duplicate detection endpoints."""
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


class TestDuplicateDetectionAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_check_duplicate_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to check duplicates should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/check-duplicate', json={
                'referenceNumber': 'REF001',
                'transactionDate': '2024-01-01',
                'transactionAmount': 100.00
            })
        assert response.status_code in (401, 403)

    def test_log_decision_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to log decision should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/log-duplicate-decision', json={
                'decision': 'continue'
            })
        assert response.status_code in (401, 403)

    def test_handle_decision_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to handle decision should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/handle-duplicate-decision', json={
                'decision': 'continue',
                'duplicateInfo': {},
                'transactions': [],
                'fileData': {}
            })
        assert response.status_code in (401, 403)


# ============================================================================
# Check Duplicate Tests
# ============================================================================


class TestCheckDuplicate:
    """Tests for POST /api/check-duplicate."""

    @patch('routes.duplicate_detection_routes.DuplicateChecker')
    @patch('routes.duplicate_detection_routes.DatabaseManager')
    def test_check_duplicate_success(self, mock_db_class, mock_checker_class,
                                     client, finance_auth):
        """Valid duplicate check returns success with duplicate info."""
        mock_checker = MagicMock()
        mock_checker_class.return_value = mock_checker
        mock_checker.check_for_duplicates.return_value = []
        mock_checker.format_duplicate_info.return_value = {
            'has_duplicates': False,
            'duplicate_count': 0,
            'existing_transactions': [],
            'requires_user_decision': False
        }

        response = client.post(
            '/api/check-duplicate',
            headers=finance_auth,
            json={
                'referenceNumber': 'REF001',
                'transactionDate': '2024-01-01',
                'transactionAmount': 100.00
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'duplicateInfo' in data

    @patch('routes.duplicate_detection_routes.DuplicateChecker')
    @patch('routes.duplicate_detection_routes.DatabaseManager')
    def test_check_duplicate_missing_field_returns_400(
        self, mock_db_class, mock_checker_class, client, finance_auth
    ):
        """Missing required field returns 400."""
        response = client.post(
            '/api/check-duplicate',
            headers=finance_auth,
            json={
                'referenceNumber': 'REF001',
                'transactionDate': '2024-01-01'
                # Missing transactionAmount
            }
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Log Decision Tests
# ============================================================================


class TestLogDuplicateDecision:
    """Tests for POST /api/log-duplicate-decision."""

    @patch('routes.duplicate_detection_routes.DuplicateChecker')
    @patch('routes.duplicate_detection_routes.DatabaseManager')
    def test_log_decision_success(self, mock_db_class, mock_checker_class,
                                  client, finance_auth):
        """Valid decision logging returns success."""
        mock_checker = MagicMock()
        mock_checker_class.return_value = mock_checker
        mock_checker.log_duplicate_decision.return_value = True

        response = client.post(
            '/api/log-duplicate-decision',
            headers=finance_auth,
            json={
                'decision': 'continue',
                'duplicateInfo': {'existing_transaction_id': '123'},
                'newTransactionData': {'amount': 100}
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.duplicate_detection_routes.DuplicateChecker')
    @patch('routes.duplicate_detection_routes.DatabaseManager')
    def test_log_decision_missing_decision_returns_400(
        self, mock_db_class, mock_checker_class, client, finance_auth
    ):
        """Missing decision field returns 400."""
        response = client.post(
            '/api/log-duplicate-decision',
            headers=finance_auth,
            json={
                'newTransactionData': {'amount': 100}
            }
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Handle Decision Tests
# ============================================================================


class TestHandleDuplicateDecision:
    """Tests for POST /api/handle-duplicate-decision."""

    @patch('routes.duplicate_detection_routes.DatabaseManager')
    def test_handle_decision_missing_required_field_returns_400(
        self, mock_db_class, client, finance_auth
    ):
        """Missing required field returns 400."""
        response = client.post(
            '/api/handle-duplicate-decision',
            headers=finance_auth,
            json={
                'decision': 'continue',
                'duplicateInfo': {},
                # Missing transactions and fileData
            }
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.duplicate_detection_routes.DatabaseManager')
    def test_handle_decision_invalid_decision_returns_400(
        self, mock_db_class, client, finance_auth
    ):
        """Invalid decision value returns 400."""
        response = client.post(
            '/api/handle-duplicate-decision',
            headers=finance_auth,
            json={
                'decision': 'invalid_value',
                'duplicateInfo': {},
                'transactions': [],
                'fileData': {}
            }
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
