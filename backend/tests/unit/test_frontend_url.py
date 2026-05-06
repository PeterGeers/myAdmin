"""
Unit tests for utils/frontend_url.py

Tests URL resolution for different environments (dev, staging, production)
and environment-based configuration switching.

Requirements: 4.9, 8.1, 8.5
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask


@pytest.fixture
def flask_app():
    """Create a minimal Flask app for request context."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


class TestGetFrontendUrl:
    """Tests for get_frontend_url function."""

    def test_production_env_var_set_returns_env_value(self, mock_env, flask_app):
        """When FRONTEND_URL env var is set, it should be returned."""
        with patch.dict('os.environ', {'FRONTEND_URL': 'https://app.myadmin.nl'}):
            from utils.frontend_url import get_frontend_url
            with flask_app.test_request_context():
                result = get_frontend_url()
        assert result == 'https://app.myadmin.nl'

    def test_production_env_var_strips_trailing_slash(self, mock_env, flask_app):
        """FRONTEND_URL with trailing slash should be stripped."""
        with patch.dict('os.environ', {'FRONTEND_URL': 'https://app.myadmin.nl/'}):
            from utils.frontend_url import get_frontend_url
            with flask_app.test_request_context():
                result = get_frontend_url()
        assert result == 'https://app.myadmin.nl'

    def test_dev_referer_header_used_when_no_env_var(self, mock_env, flask_app):
        """When no FRONTEND_URL, Referer header should be used for dev."""
        with patch.dict('os.environ', {}, clear=False):
            # Remove FRONTEND_URL if present
            import os
            os.environ.pop('FRONTEND_URL', None)

            from utils.frontend_url import get_frontend_url
            with flask_app.test_request_context(
                headers={'Referer': 'http://localhost:3000/dashboard'}
            ):
                result = get_frontend_url()
        assert result == 'http://localhost:3000'

    def test_dev_referer_https_scheme(self, mock_env, flask_app):
        """Referer with https scheme should be handled correctly."""
        with patch.dict('os.environ', {}, clear=False):
            import os
            os.environ.pop('FRONTEND_URL', None)

            from utils.frontend_url import get_frontend_url
            with flask_app.test_request_context(
                headers={'Referer': 'https://staging.myadmin.nl/invoices'}
            ):
                result = get_frontend_url()
        assert result == 'https://staging.myadmin.nl'

    def test_fallback_localhost_when_no_env_and_no_referer(self, mock_env, flask_app):
        """When no FRONTEND_URL and no Referer, fallback to localhost:3000."""
        with patch.dict('os.environ', {}, clear=False):
            import os
            os.environ.pop('FRONTEND_URL', None)

            from utils.frontend_url import get_frontend_url
            with flask_app.test_request_context():
                result = get_frontend_url()
        assert result == 'http://localhost:3000'

    def test_fallback_when_referer_has_invalid_scheme(self, mock_env, flask_app):
        """Referer with non-http/https scheme should be ignored."""
        with patch.dict('os.environ', {}, clear=False):
            import os
            os.environ.pop('FRONTEND_URL', None)

            from utils.frontend_url import get_frontend_url
            with flask_app.test_request_context(
                headers={'Referer': 'ftp://files.example.com/data'}
            ):
                result = get_frontend_url()
        assert result == 'http://localhost:3000'

    def test_fallback_when_outside_request_context(self, mock_env):
        """When called outside Flask request context, should fallback gracefully."""
        with patch.dict('os.environ', {}, clear=False):
            import os
            os.environ.pop('FRONTEND_URL', None)

            from utils.frontend_url import get_frontend_url
            result = get_frontend_url()
        assert result == 'http://localhost:3000'

    def test_env_var_takes_priority_over_referer(self, mock_env, flask_app):
        """FRONTEND_URL env var should take priority over Referer header."""
        with patch.dict('os.environ', {'FRONTEND_URL': 'https://production.myadmin.nl'}):
            from utils.frontend_url import get_frontend_url
            with flask_app.test_request_context(
                headers={'Referer': 'http://localhost:3000/page'}
            ):
                result = get_frontend_url()
        assert result == 'https://production.myadmin.nl'
