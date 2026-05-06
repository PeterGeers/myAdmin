"""
Integration tests for tenant_language_service.py

Tests language preference CRUD operations and validation of supported languages.
Validates: Requirements 4.3, 8.2, 8.4
"""

import pytest
from unittest.mock import patch, MagicMock


class TestGetTenantLanguage:
    """Tests for get_tenant_language function."""

    def test_get_tenant_language_stored_en_returns_en(self, mock_db):
        """Test get_tenant_language returns stored language code 'en'."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('en',)
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        with patch('services.tenant_language_service.DatabaseManager', return_value=mock_db):
            from services.tenant_language_service import get_tenant_language
            result = get_tenant_language('test-tenant')

        assert result == 'en'
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'SELECT default_language' in query
        assert params == ('test-tenant',)
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_get_tenant_language_no_result_returns_nl(self, mock_db):
        """Test get_tenant_language returns 'nl' when no tenant found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        with patch('services.tenant_language_service.DatabaseManager', return_value=mock_db):
            from services.tenant_language_service import get_tenant_language
            result = get_tenant_language('unknown-tenant')

        assert result == 'nl'

    def test_get_tenant_language_null_value_returns_nl(self, mock_db):
        """Test get_tenant_language returns 'nl' when result[0] is None."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (None,)
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        with patch('services.tenant_language_service.DatabaseManager', return_value=mock_db):
            from services.tenant_language_service import get_tenant_language
            result = get_tenant_language('tenant-with-null')

        assert result == 'nl'

    def test_get_tenant_language_exception_returns_nl(self, mock_db):
        """Test get_tenant_language returns 'nl' on database exception."""
        mock_db.get_connection.side_effect = Exception("Connection failed")

        with patch('services.tenant_language_service.DatabaseManager', return_value=mock_db):
            from services.tenant_language_service import get_tenant_language
            result = get_tenant_language('error-tenant')

        assert result == 'nl'


class TestUpdateTenantLanguage:
    """Tests for update_tenant_language function."""

    def test_update_tenant_language_success_returns_true(self, mock_db):
        """Test update_tenant_language returns True when rowcount > 0."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        with patch('services.tenant_language_service.DatabaseManager', return_value=mock_db):
            from services.tenant_language_service import update_tenant_language
            result = update_tenant_language('test-tenant', 'en')

        assert result is True
        mock_conn.commit.assert_called_once()
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'UPDATE tenants' in query
        assert 'default_language' in query
        assert params == ('en', 'test-tenant')
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_update_tenant_language_invalid_language_returns_false(self, mock_db):
        """Test update_tenant_language returns False for invalid language code."""
        with patch('services.tenant_language_service.DatabaseManager', return_value=mock_db):
            from services.tenant_language_service import update_tenant_language
            result = update_tenant_language('test-tenant', 'fr')

        assert result is False
        # Should not attempt DB connection for invalid language
        mock_db.get_connection.assert_not_called()

    def test_update_tenant_language_tenant_not_found_returns_false(self, mock_db):
        """Test update_tenant_language returns False when rowcount == 0."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        with patch('services.tenant_language_service.DatabaseManager', return_value=mock_db):
            from services.tenant_language_service import update_tenant_language
            result = update_tenant_language('nonexistent-tenant', 'nl')

        assert result is False
        mock_conn.commit.assert_called_once()

    def test_update_tenant_language_exception_returns_false_and_rollbacks(self, mock_db):
        """Test update_tenant_language returns False and rollbacks on exception."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB write error")
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        with patch('services.tenant_language_service.DatabaseManager', return_value=mock_db):
            from services.tenant_language_service import update_tenant_language
            result = update_tenant_language('test-tenant', 'en')

        assert result is False
        mock_conn.rollback.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()


class TestValidateLanguageCode:
    """Tests for validate_language_code function."""

    def test_validate_language_code_nl_returns_true(self):
        """Test validate_language_code returns True for 'nl'."""
        from services.tenant_language_service import validate_language_code
        assert validate_language_code('nl') is True

    def test_validate_language_code_en_returns_true(self):
        """Test validate_language_code returns True for 'en'."""
        from services.tenant_language_service import validate_language_code
        assert validate_language_code('en') is True

    def test_validate_language_code_fr_returns_false(self):
        """Test validate_language_code returns False for unsupported 'fr'."""
        from services.tenant_language_service import validate_language_code
        assert validate_language_code('fr') is False

    def test_validate_language_code_empty_string_returns_false(self):
        """Test validate_language_code returns False for empty string."""
        from services.tenant_language_service import validate_language_code
        assert validate_language_code('') is False

    def test_validate_language_code_uppercase_returns_false(self):
        """Test validate_language_code returns False for uppercase 'NL'."""
        from services.tenant_language_service import validate_language_code
        assert validate_language_code('NL') is False
