"""
Integration tests for user_language_service.py

Tests Cognito attribute updates for language preference and language validation.
Validates: Requirements 4.5, 8.2, 8.4
"""

import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


class TestGetUserLanguage:
    """Tests for get_user_language function."""

    def test_get_user_language_stored_en_returns_en(self, mock_env):
        """Test get_user_language returns stored language from Cognito attribute."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        mock_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'test@example.com'},
                {'Name': 'custom:preferred_language', 'Value': 'en'},
            ],
        }

        with patch('services.user_language_service.boto3.client', return_value=mock_client):
            from services.user_language_service import get_user_language
            result = get_user_language('test@example.com')

        assert result == 'en'
        mock_client.admin_get_user.assert_called_once_with(
            UserPoolId='us-east-1_test',
            Username='test@example.com'
        )

    def test_get_user_language_no_attribute_returns_nl(self, mock_env):
        """Test get_user_language returns 'nl' when attribute not set."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        mock_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'test@example.com'},
            ],
        }

        with patch('services.user_language_service.boto3.client', return_value=mock_client):
            from services.user_language_service import get_user_language
            result = get_user_language('test@example.com')

        assert result == 'nl'

    def test_get_user_language_no_pool_id_returns_nl(self):
        """Test get_user_language returns 'nl' when COGNITO_USER_POOL_ID not set."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()

        with patch.dict('os.environ', {}, clear=True):
            with patch('services.user_language_service.boto3.client', return_value=mock_client):
                from services.user_language_service import get_user_language
                result = get_user_language('test@example.com')

        assert result == 'nl'
        mock_client.admin_get_user.assert_not_called()

    def test_get_user_language_user_not_found_returns_nl(self, mock_env):
        """Test get_user_language returns 'nl' on UserNotFoundException."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        error_response = {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}}
        mock_client.exceptions.UserNotFoundException = type(
            'UserNotFoundException', (ClientError,), {}
        )
        mock_client.admin_get_user.side_effect = mock_client.exceptions.UserNotFoundException(
            error_response, 'AdminGetUser'
        )

        with patch('services.user_language_service.boto3.client', return_value=mock_client):
            from services.user_language_service import get_user_language
            result = get_user_language('nonexistent@example.com')

        assert result == 'nl'

    def test_get_user_language_generic_exception_returns_nl(self, mock_env):
        """Test get_user_language returns 'nl' on generic exception."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        # Set up a real exception class so the except clause works
        mock_client.exceptions.UserNotFoundException = type(
            'UserNotFoundException', (ClientError,), {}
        )
        mock_client.admin_get_user.side_effect = Exception("Network error")

        with patch('services.user_language_service.boto3.client', return_value=mock_client):
            from services.user_language_service import get_user_language
            result = get_user_language('test@example.com')

        assert result == 'nl'


class TestUpdateUserLanguage:
    """Tests for update_user_language function."""

    def test_update_user_language_success_returns_true(self, mock_env):
        """Test update_user_language returns True on successful update."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        mock_client.admin_update_user_attributes.return_value = {}

        with patch('services.user_language_service.boto3.client', return_value=mock_client):
            from services.user_language_service import update_user_language
            result = update_user_language('test@example.com', 'en')

        assert result is True
        mock_client.admin_update_user_attributes.assert_called_once_with(
            UserPoolId='us-east-1_test',
            Username='test@example.com',
            UserAttributes=[
                {'Name': 'custom:preferred_language', 'Value': 'en'}
            ]
        )

    def test_update_user_language_invalid_language_returns_false(self, mock_env):
        """Test update_user_language returns False for invalid language code."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()

        with patch('services.user_language_service.boto3.client', return_value=mock_client):
            from services.user_language_service import update_user_language
            result = update_user_language('test@example.com', 'fr')

        assert result is False
        mock_client.admin_update_user_attributes.assert_not_called()

    def test_update_user_language_no_pool_id_returns_false(self):
        """Test update_user_language returns False when COGNITO_USER_POOL_ID not set."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()

        with patch.dict('os.environ', {}, clear=True):
            with patch('services.user_language_service.boto3.client', return_value=mock_client):
                from services.user_language_service import update_user_language
                result = update_user_language('test@example.com', 'en')

        assert result is False
        mock_client.admin_update_user_attributes.assert_not_called()

    def test_update_user_language_user_not_found_returns_false(self, mock_env):
        """Test update_user_language returns False on UserNotFoundException."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        error_response = {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}}
        mock_client.exceptions.UserNotFoundException = type(
            'UserNotFoundException', (ClientError,), {}
        )
        mock_client.admin_update_user_attributes.side_effect = (
            mock_client.exceptions.UserNotFoundException(error_response, 'AdminUpdateUserAttributes')
        )

        with patch('services.user_language_service.boto3.client', return_value=mock_client):
            from services.user_language_service import update_user_language
            result = update_user_language('test@example.com', 'nl')

        assert result is False

    def test_update_user_language_generic_exception_returns_false(self, mock_env):
        """Test update_user_language returns False on generic exception."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        # Set up a real exception class so the except clause works
        mock_client.exceptions.UserNotFoundException = type(
            'UserNotFoundException', (ClientError,), {}
        )
        mock_client.admin_update_user_attributes.side_effect = Exception("Service unavailable")

        with patch('services.user_language_service.boto3.client', return_value=mock_client):
            from services.user_language_service import update_user_language
            result = update_user_language('test@example.com', 'en')

        assert result is False


class TestValidateLanguageCode:
    """Tests for validate_language_code function."""

    def test_validate_language_code_nl_returns_true(self):
        """Test validate_language_code returns True for 'nl'."""
        from services.user_language_service import validate_language_code
        assert validate_language_code('nl') is True

    def test_validate_language_code_en_returns_true(self):
        """Test validate_language_code returns True for 'en'."""
        from services.user_language_service import validate_language_code
        assert validate_language_code('en') is True

    def test_validate_language_code_fr_returns_false(self):
        """Test validate_language_code returns False for unsupported 'fr'."""
        from services.user_language_service import validate_language_code
        assert validate_language_code('fr') is False

    def test_validate_language_code_empty_string_returns_false(self):
        """Test validate_language_code returns False for empty string."""
        from services.user_language_service import validate_language_code
        assert validate_language_code('') is False

    def test_validate_language_code_uppercase_returns_false(self):
        """Test validate_language_code returns False for uppercase 'NL'."""
        from services.user_language_service import validate_language_code
        assert validate_language_code('NL') is False
