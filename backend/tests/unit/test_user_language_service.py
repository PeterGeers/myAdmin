"""
Unit Tests for User Language Service

Tests the user language preference functions that interact with AWS Cognito
custom attributes (custom:preferred_language).
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import services.user_language_service as user_language_service
from services.user_language_service import (
    get_user_language,
    update_user_language,
    validate_language_code,
)


@pytest.fixture(autouse=True)
def reset_cognito_client():
    """Reset the global cognito_client between tests to avoid state leakage."""
    user_language_service.cognito_client = None
    yield
    user_language_service.cognito_client = None


@pytest.fixture
def mock_env():
    """Mock required environment variables."""
    env_vars = {
        'AWS_REGION': 'eu-west-1',
        'AWS_ACCESS_KEY_ID': 'test-key-id',
        'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
        'COGNITO_USER_POOL_ID': 'eu-west-1_TestPool',
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def mock_cognito_client(mock_env):
    """Provide a mocked Cognito client and inject it into the module."""
    mock_client = MagicMock()
    # Set up UserNotFoundException as a proper exception class
    mock_client.exceptions.UserNotFoundException = type(
        'UserNotFoundException', (Exception,), {}
    )
    with patch('services.user_language_service.boto3.client', return_value=mock_client):
        yield mock_client


class TestGetUserLanguage:
    """Tests for get_user_language function."""

    @pytest.mark.unit
    def test_returns_language_from_cognito_attributes(self, mock_cognito_client):
        """get_user_language returns language from Cognito custom attributes."""
        mock_cognito_client.admin_get_user.return_value = {
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user@example.com'},
                {'Name': 'custom:preferred_language', 'Value': 'en'},
            ]
        }

        result = get_user_language('user@example.com')

        assert result == 'en'
        mock_cognito_client.admin_get_user.assert_called_once_with(
            UserPoolId='eu-west-1_TestPool',
            Username='user@example.com',
        )

    @pytest.mark.unit
    def test_returns_nl_when_no_preferred_language_attribute(self, mock_cognito_client):
        """get_user_language defaults to 'nl' when custom:preferred_language is missing."""
        mock_cognito_client.admin_get_user.return_value = {
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user@example.com'},
                {'Name': 'name', 'Value': 'Test User'},
            ]
        }

        result = get_user_language('user@example.com')

        assert result == 'nl'

    @pytest.mark.unit
    def test_returns_nl_when_user_not_found(self, mock_cognito_client):
        """get_user_language returns 'nl' when UserNotFoundException is raised."""
        mock_cognito_client.admin_get_user.side_effect = (
            mock_cognito_client.exceptions.UserNotFoundException('User not found')
        )

        result = get_user_language('nonexistent@example.com')

        assert result == 'nl'

    @pytest.mark.unit
    def test_returns_nl_when_cognito_user_pool_id_not_set(self):
        """get_user_language returns 'nl' when COGNITO_USER_POOL_ID is not set."""
        env_vars = {
            'AWS_REGION': 'eu-west-1',
            'AWS_ACCESS_KEY_ID': 'test-key-id',
            'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
        }
        with patch.dict(os.environ, env_vars, clear=True):
            with patch('services.user_language_service.boto3.client'):
                result = get_user_language('user@example.com')

        assert result == 'nl'

    @pytest.mark.unit
    def test_returns_nl_on_general_exception(self, mock_cognito_client):
        """get_user_language returns 'nl' on a general exception."""
        mock_cognito_client.admin_get_user.side_effect = Exception('Connection timeout')

        result = get_user_language('user@example.com')

        assert result == 'nl'


class TestUpdateUserLanguage:
    """Tests for update_user_language function."""

    @pytest.mark.unit
    def test_succeeds_with_valid_language(self, mock_cognito_client):
        """update_user_language returns True when update succeeds."""
        mock_cognito_client.admin_update_user_attributes.return_value = {}

        result = update_user_language('user@example.com', 'en')

        assert result is True
        mock_cognito_client.admin_update_user_attributes.assert_called_once_with(
            UserPoolId='eu-west-1_TestPool',
            Username='user@example.com',
            UserAttributes=[
                {'Name': 'custom:preferred_language', 'Value': 'en'}
            ],
        )

    @pytest.mark.unit
    def test_fails_with_invalid_language_code(self, mock_cognito_client):
        """update_user_language returns False for invalid language code."""
        result = update_user_language('user@example.com', 'fr')

        assert result is False
        mock_cognito_client.admin_update_user_attributes.assert_not_called()

    @pytest.mark.unit
    def test_returns_false_when_user_not_found(self, mock_cognito_client):
        """update_user_language returns False when UserNotFoundException is raised."""
        mock_cognito_client.admin_update_user_attributes.side_effect = (
            mock_cognito_client.exceptions.UserNotFoundException('User not found')
        )

        result = update_user_language('user@example.com', 'nl')

        assert result is False

    @pytest.mark.unit
    def test_returns_false_when_cognito_user_pool_id_not_set(self):
        """update_user_language returns False when COGNITO_USER_POOL_ID is not set."""
        env_vars = {
            'AWS_REGION': 'eu-west-1',
            'AWS_ACCESS_KEY_ID': 'test-key-id',
            'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
        }
        with patch.dict(os.environ, env_vars, clear=True):
            with patch('services.user_language_service.boto3.client'):
                result = update_user_language('user@example.com', 'en')

        assert result is False


class TestValidateLanguageCode:
    """Tests for validate_language_code function."""

    @pytest.mark.unit
    def test_returns_true_for_nl(self):
        """validate_language_code returns True for 'nl'."""
        assert validate_language_code('nl') is True

    @pytest.mark.unit
    def test_returns_true_for_en(self):
        """validate_language_code returns True for 'en'."""
        assert validate_language_code('en') is True

    @pytest.mark.unit
    def test_returns_false_for_invalid_codes(self):
        """validate_language_code returns False for unsupported language codes."""
        assert validate_language_code('fr') is False
        assert validate_language_code('de') is False
        assert validate_language_code('') is False
        assert validate_language_code('NL') is False
