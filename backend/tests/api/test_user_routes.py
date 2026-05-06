"""
API tests for user_routes.py

Tests user language preference endpoints including auth enforcement,
getting language, and updating language with validation.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestUserRoutesAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_get_language_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get language should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/user/language')
        assert response.status_code in (401, 403)

    def test_update_language_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to update language should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.put('/api/user/language', json={'language': 'nl'})
        assert response.status_code in (401, 403)


# ============================================================================
# Get Language Tests
# ============================================================================


class TestGetLanguage:
    """Tests for GET /api/user/language."""

    @patch('routes.user_routes.get_user_language')
    def test_get_language_success(self, mock_get_lang, client, mock_auth):
        """Authenticated user can get their language preference."""
        mock_get_lang.return_value = 'nl'

        response = client.get(
            '/api/user/language',
            headers=mock_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['language'] == 'nl'

    @patch('routes.user_routes.get_user_language')
    def test_get_language_default_en(self, mock_get_lang, client, mock_auth):
        """Default language is returned when not set."""
        mock_get_lang.return_value = 'en'

        response = client.get(
            '/api/user/language',
            headers=mock_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['language'] == 'en'


# ============================================================================
# Update Language Tests
# ============================================================================


class TestUpdateLanguage:
    """Tests for PUT /api/user/language."""

    @patch('routes.user_routes.update_user_language')
    @patch('routes.user_routes.validate_language_code')
    def test_update_language_success(self, mock_validate, mock_update,
                                     client, mock_auth):
        """Valid language update succeeds."""
        mock_validate.return_value = True
        mock_update.return_value = True

        response = client.put(
            '/api/user/language',
            headers=mock_auth,
            json={'language': 'en'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['language'] == 'en'

    @patch('routes.user_routes.validate_language_code')
    def test_update_language_invalid_code_returns_400(self, mock_validate,
                                                      client, mock_auth):
        """Invalid language code returns 400."""
        mock_validate.return_value = False

        response = client.put(
            '/api/user/language',
            headers=mock_auth,
            json={'language': 'xx'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_update_language_missing_field_returns_400(self, client, mock_auth):
        """Missing language field returns 400."""
        response = client.put(
            '/api/user/language',
            headers=mock_auth,
            json={}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_update_language_no_body_returns_error(self, client, mock_auth):
        """No request body returns error status."""
        response = client.put(
            '/api/user/language',
            headers=mock_auth,
            content_type='application/json'
        )

        # Route catches JSON decode error as Exception, returns 500
        assert response.status_code in (400, 500)
