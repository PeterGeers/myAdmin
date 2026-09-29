"""
Integration tests for user_language_service.py

Tests Cognito attribute updates for language preference and language validation.
Validates: Requirements 4.5, 8.2, 8.4
"""

import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Registry env driving deterministic email-mode pool resolution to the TEST pool.
# The migrated service resolves the target pool through the shared registry-backed
# resolver, so tests that exercise the admin ops must pin the registry rather than
# depend on the ambient backend .env. Mirrors TestUserLanguagePoolResolution below.
_TEST_POOL_ID = 'eu-west-1_xyrlzfqbl'
_TEST_ISSUER = f'https://cognito-idp.eu-west-1.amazonaws.com/{_TEST_POOL_ID}'
REGISTRY_TEST_ENV = {
    'COGNITO_POOL_KEYS': 'TEST',
    'TEST_COGNITO_ISSUER': _TEST_ISSUER,
    'TEST_COGNITO_JWKS_URI': f'{_TEST_ISSUER}/.well-known/jwks.json',
    'TEST_COGNITO_CLIENT_ID': 'test-client-id',
    'TEST_COGNITO_POOL_LABEL': 'myAdmin-test',
    'COGNITO_USER_POOL_ID': 'eu-west-1_Hdp40eWmu',
    'COGNITO_CLIENT_ID': 'prod-client-id',
    'AWS_REGION': 'eu-west-1',
    'AWS_ACCESS_KEY_ID': 'test-key-id',
    'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
    'TEST_MODE': 'true',
}


class TestGetUserLanguage:
    """Tests for get_user_language function."""

    def test_get_user_language_stored_en_returns_en(self):
        """Test get_user_language returns stored language from the Cognito attribute
        on the registry-resolved pool (email mode), not the legacy pool var."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        pool_ids = []
        mock_client.admin_get_user.side_effect = lambda **kwargs: (
            pool_ids.append(kwargs.get('UserPoolId')),
            {
                'Username': 'test@example.com',
                'UserAttributes': [
                    {'Name': 'email', 'Value': 'test@example.com'},
                    {'Name': 'custom:preferred_language', 'Value': 'en'},
                ],
            },
        )[1]

        with patch.dict('os.environ', REGISTRY_TEST_ENV, clear=True):
            with patch('services.user_language_service.boto3.client', return_value=mock_client):
                from services.user_language_service import get_user_language
                result = get_user_language('test@example.com')
        module.cognito_client = None

        assert result == 'en'
        # Email-mode resolution probes admin_get_user, then the read calls it again;
        # every admin_get_user call must target the registry-resolved TEST pool.
        assert pool_ids  # at least the read happened
        assert all(pid == _TEST_POOL_ID for pid in pool_ids)

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
        """Test get_user_language returns the 'nl' default when the pool cannot be
        resolved: with no registry (COGNITO_POOL_KEYS) and no legacy
        COGNITO_USER_POOL_ID, the resolver raises and no admin op runs."""
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

    def test_update_user_language_success_returns_true(self):
        """Test update_user_language returns True and targets the registry-resolved
        pool (email mode), not the legacy pool var, on successful update."""
        import services.user_language_service as module
        module.cognito_client = None

        mock_client = MagicMock()
        update_kwargs = {}
        # admin_get_user is the resolver's email-mode probe (user found -> resolves
        # to the single registered TEST pool); the update then targets that pool.
        mock_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'custom:preferred_language', 'Value': 'en'},
            ],
        }
        mock_client.admin_update_user_attributes.side_effect = (
            lambda **kwargs: (update_kwargs.update(kwargs), {})[1]
        )

        with patch.dict('os.environ', REGISTRY_TEST_ENV, clear=True):
            with patch('services.user_language_service.boto3.client', return_value=mock_client):
                from services.user_language_service import update_user_language
                result = update_user_language('test@example.com', 'en')
        module.cognito_client = None

        assert result is True
        assert update_kwargs.get('UserPoolId') == _TEST_POOL_ID
        assert update_kwargs.get('Username') == 'test@example.com'
        assert update_kwargs.get('UserAttributes') == [
            {'Name': 'custom:preferred_language', 'Value': 'en'}
        ]

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


class TestUserLanguagePoolResolution:
    """Migration coverage: preferred-language read/write resolve the target pool
    through the shared registry-backed resolver (email mode), not the legacy
    single-pool ``COGNITO_USER_POOL_ID`` var.

    Bugfix ``cognito-admin-pool-resolution`` (RCA R1 + R2). These tests assert the
    NEW pool-resolution source while confirming the ``"nl"``-default / ``False``
    failure contracts are unchanged.

    Validates: Requirements 2.1, 2.3, 2.4, 3.3
    """

    # Registry configured for the TEST pool (the dev-container config validation
    # uses); the legacy var still points at PROD to prove admin ops no longer read it.
    TEST_POOL_ID = 'eu-west-1_xyrlzfqbl'
    PROD_POOL_ID = 'eu-west-1_Hdp40eWmu'
    TEST_ISSUER = f'https://cognito-idp.eu-west-1.amazonaws.com/{TEST_POOL_ID}'

    REGISTRY_TEST_ENV = {
        'COGNITO_POOL_KEYS': 'TEST',
        'TEST_COGNITO_ISSUER': TEST_ISSUER,
        'TEST_COGNITO_JWKS_URI': f'{TEST_ISSUER}/.well-known/jwks.json',
        'TEST_COGNITO_CLIENT_ID': 'test-client-id',
        'TEST_COGNITO_POOL_LABEL': 'myAdmin-test',
        # Legacy var points at PROD — the migrated code must NOT read it.
        'COGNITO_USER_POOL_ID': PROD_POOL_ID,
        'COGNITO_CLIENT_ID': 'prod-client-id',
        'AWS_REGION': 'eu-west-1',
        'AWS_ACCESS_KEY_ID': 'test-key-id',
        'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
        'TEST_MODE': 'true',
    }

    def _capturing_client(self):
        """Mocked cognito-idp client recording the UserPoolId of each admin call.

        ``admin_get_user`` succeeds (user found) so the resolver's email-mode probe
        resolves to the single registered pool; the recorded ``UserPoolId`` proves
        which pool the op acted on.
        """
        client = MagicMock()
        calls: dict = {}

        def _record(name):
            def _side_effect(*args, **kwargs):
                calls[name] = kwargs.get('UserPoolId')
                if name == 'admin_get_user':
                    return {
                        'Username': 'test@example.com',
                        'UserAttributes': [
                            {'Name': 'custom:preferred_language', 'Value': 'en'},
                        ],
                    }
                return {}
            return _side_effect

        client.admin_get_user.side_effect = _record('admin_get_user')
        client.admin_update_user_attributes.side_effect = _record(
            'admin_update_user_attributes'
        )
        client.exceptions.UserNotFoundException = type(
            'UserNotFoundException', (ClientError,), {}
        )
        return client, calls

    def test_get_user_language_resolves_registry_pool_not_legacy_var(self):
        """Read resolves the TEST registry pool (email mode), never the legacy PROD
        var. Validates: Requirements 2.1, 2.4."""
        import services.user_language_service as module
        module.cognito_client = None
        client, calls = self._capturing_client()

        with patch.dict('os.environ', self.REGISTRY_TEST_ENV, clear=True):
            with patch(
                'services.user_language_service.boto3.client', return_value=client
            ):
                from services.user_language_service import get_user_language
                result = get_user_language('test@example.com')
        module.cognito_client = None

        assert result == 'en'
        assert calls.get('admin_get_user') == self.TEST_POOL_ID
        assert calls.get('admin_get_user') != self.PROD_POOL_ID

    def test_update_user_language_resolves_registry_pool_not_legacy_var(self):
        """Write resolves the TEST registry pool (email mode), never the legacy PROD
        var. Validates: Requirements 2.1, 2.4, 3.3."""
        import services.user_language_service as module
        module.cognito_client = None
        client, calls = self._capturing_client()

        with patch.dict('os.environ', self.REGISTRY_TEST_ENV, clear=True):
            with patch(
                'services.user_language_service.boto3.client', return_value=client
            ):
                from services.user_language_service import update_user_language
                result = update_user_language('test@example.com', 'en')
        module.cognito_client = None

        assert result is True
        assert calls.get('admin_update_user_attributes') == self.TEST_POOL_ID
        assert calls.get('admin_update_user_attributes') != self.PROD_POOL_ID

    def test_get_user_language_unresolvable_pool_returns_nl(self):
        """A pool-resolution failure (registry absent AND legacy var unset) maps to
        the preserved ``"nl"`` default, without an admin_get_user call.
        Validates: Requirements 3.3."""
        import services.user_language_service as module
        module.cognito_client = None
        client, calls = self._capturing_client()

        # No COGNITO_POOL_KEYS and no COGNITO_USER_POOL_ID -> PoolResolutionError.
        with patch.dict('os.environ', {'AWS_REGION': 'eu-west-1'}, clear=True):
            with patch(
                'services.user_language_service.boto3.client', return_value=client
            ):
                from services.user_language_service import get_user_language
                result = get_user_language('test@example.com')
        module.cognito_client = None

        assert result == 'nl'
        assert 'admin_get_user' not in calls

    def test_update_user_language_unresolvable_pool_returns_false(self):
        """A pool-resolution failure maps to the preserved ``False`` return, without
        an admin_update_user_attributes call. Validates: Requirements 3.3."""
        import services.user_language_service as module
        module.cognito_client = None
        client, calls = self._capturing_client()

        with patch.dict('os.environ', {'AWS_REGION': 'eu-west-1'}, clear=True):
            with patch(
                'services.user_language_service.boto3.client', return_value=client
            ):
                from services.user_language_service import update_user_language
                result = update_user_language('test@example.com', 'en')
        module.cognito_client = None

        assert result is False
        assert 'admin_update_user_attributes' not in calls
