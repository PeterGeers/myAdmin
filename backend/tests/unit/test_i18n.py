"""
Unit tests for i18n module.

Tests locale detection from X-Language header and Flask-Babel initialization.

Requirements: 1.11, 2.1, 8.1, 8.5
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
from flask import Flask

from i18n import get_locale, init_babel


# ---------------------------------------------------------------------------
# get_locale
# ---------------------------------------------------------------------------

class TestGetLocale:
    """Tests for get_locale function."""

    def _make_app_and_call(self, header_value=None):
        """Helper: create a Flask app context and call get_locale with given header."""
        app = Flask(__name__)
        with app.test_request_context(
            headers={'X-Language': header_value} if header_value is not None else {}
        ):
            return get_locale()

    def test_get_locale_nl_header_returns_nl(self):
        assert self._make_app_and_call('nl') == 'nl'

    def test_get_locale_en_header_returns_en(self):
        assert self._make_app_and_call('en') == 'en'

    def test_get_locale_missing_header_returns_nl(self):
        assert self._make_app_and_call(None) == 'nl'

    def test_get_locale_empty_string_returns_nl(self):
        """Empty string is not in ['nl', 'en'], so falls back to 'nl'."""
        assert self._make_app_and_call('') == 'nl'

    def test_get_locale_unsupported_locale_fr_returns_nl(self):
        assert self._make_app_and_call('fr') == 'nl'

    def test_get_locale_unsupported_locale_de_returns_nl(self):
        assert self._make_app_and_call('de') == 'nl'

    def test_get_locale_nl_nl_returns_nl_fallback(self):
        """'nl-NL' is not exactly 'nl', so falls back to 'nl'."""
        assert self._make_app_and_call('nl-NL') == 'nl'

    def test_get_locale_en_us_returns_nl_fallback(self):
        """'en-US' is not exactly 'en', so falls back to 'nl'."""
        assert self._make_app_and_call('en-US') == 'nl'

    def test_get_locale_malformed_header_returns_nl(self):
        assert self._make_app_and_call('xyz123!@#') == 'nl'

    def test_get_locale_numeric_header_returns_nl(self):
        assert self._make_app_and_call('123') == 'nl'

    def test_get_locale_uppercase_EN_returns_nl_fallback(self):
        """'EN' (uppercase) is not in ['nl', 'en'], so falls back to 'nl'."""
        assert self._make_app_and_call('EN') == 'nl'

    def test_get_locale_uppercase_NL_returns_nl_fallback(self):
        """'NL' (uppercase) is not in ['nl', 'en'], so falls back to 'nl'."""
        assert self._make_app_and_call('NL') == 'nl'


# ---------------------------------------------------------------------------
# init_babel
# ---------------------------------------------------------------------------

class TestInitBabel:
    """Tests for init_babel function."""

    @patch('i18n.Babel')
    def test_init_babel_creates_babel_instance(self, mock_babel_class):
        """init_babel should create a Babel instance with the app."""
        app = Flask(__name__)
        mock_babel_instance = MagicMock()
        mock_babel_class.return_value = mock_babel_instance

        result = init_babel(app)

        mock_babel_class.assert_called_once_with(app, locale_selector=get_locale)
        assert result == mock_babel_instance

    @patch('i18n.Babel')
    def test_init_babel_returns_babel_instance(self, mock_babel_class):
        """init_babel should return the Babel instance."""
        app = Flask(__name__)
        mock_babel_instance = MagicMock()
        mock_babel_class.return_value = mock_babel_instance

        result = init_babel(app)

        assert result is mock_babel_instance
