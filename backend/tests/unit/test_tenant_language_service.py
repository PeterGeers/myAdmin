"""
Unit tests for tenant_language_service.py

Tests language preference CRUD operations and validation of supported languages.
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.tenant_language_service import (
    get_tenant_language,
    update_tenant_language,
    validate_language_code,
)


@pytest.mark.unit
class TestGetTenantLanguage:
    """Tests for get_tenant_language function."""

    def test_returns_stored_language_en(self):
        """get_tenant_language returns stored 'en' from DB."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('en',)
        mock_conn.cursor.return_value = mock_cursor

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_connection.return_value = mock_conn
            result = get_tenant_language('test-tenant')

        assert result == 'en'
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'SELECT default_language' in query
        assert params == ('test-tenant',)
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_returns_nl_when_no_result(self):
        """get_tenant_language returns 'nl' when no tenant row found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_connection.return_value = mock_conn
            result = get_tenant_language('unknown-tenant')

        assert result == 'nl'

    def test_returns_nl_when_value_is_none(self):
        """get_tenant_language returns 'nl' when result[0] is None."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (None,)
        mock_conn.cursor.return_value = mock_cursor

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_connection.return_value = mock_conn
            result = get_tenant_language('tenant-with-null')

        assert result == 'nl'

    def test_returns_nl_on_exception(self):
        """get_tenant_language returns 'nl' on database exception."""
        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_connection.side_effect = Exception("Connection failed")
            result = get_tenant_language('error-tenant')

        assert result == 'nl'


@pytest.mark.unit
class TestUpdateTenantLanguage:
    """Tests for update_tenant_language function."""

    def test_succeeds_with_valid_language(self):
        """update_tenant_language returns True when update succeeds."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value = mock_cursor

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_connection.return_value = mock_conn
            result = update_tenant_language('test-tenant', 'en')

        assert result is True
        mock_conn.commit.assert_called_once()
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'UPDATE tenants' in query
        assert params == ('en', 'test-tenant')
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_fails_with_invalid_language_code(self):
        """update_tenant_language returns False for invalid language code."""
        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            result = update_tenant_language('test-tenant', 'fr')

        assert result is False
        MockDB.return_value.get_connection.assert_not_called()

    def test_returns_false_when_tenant_not_found(self):
        """update_tenant_language returns False when rowcount == 0."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0
        mock_conn.cursor.return_value = mock_cursor

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_connection.return_value = mock_conn
            result = update_tenant_language('nonexistent-tenant', 'nl')

        assert result is False
        mock_conn.commit.assert_called_once()

    def test_returns_false_on_exception_and_rolls_back(self):
        """update_tenant_language returns False and calls rollback on exception."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB write error")
        mock_conn.cursor.return_value = mock_cursor

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_connection.return_value = mock_conn
            result = update_tenant_language('test-tenant', 'en')

        assert result is False
        mock_conn.rollback.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()


@pytest.mark.unit
class TestValidateLanguageCode:
    """Tests for validate_language_code function."""

    def test_returns_true_for_nl(self):
        """validate_language_code returns True for 'nl'."""
        assert validate_language_code('nl') is True

    def test_returns_true_for_en(self):
        """validate_language_code returns True for 'en'."""
        assert validate_language_code('en') is True

    def test_returns_false_for_other_codes(self):
        """validate_language_code returns False for unsupported codes."""
        assert validate_language_code('fr') is False
        assert validate_language_code('de') is False
        assert validate_language_code('') is False
        assert validate_language_code('NL') is False
