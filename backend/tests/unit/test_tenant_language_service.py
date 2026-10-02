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


def _wire_get_cursor(mock_db, mock_cursor):
    """Configure a mocked DatabaseManager so get_cursor() yields (cursor, conn)."""
    mock_conn = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = (mock_cursor, mock_conn)
    cm.__exit__.return_value = False
    mock_db.get_cursor.return_value = cm
    return mock_conn


def _wire_transaction(mock_db, mock_cursor):
    """Configure a mocked DatabaseManager so transaction() yields (cursor, conn).

    transaction() is the context manager that commits on success / rolls back on
    error, so correct usage of it IS the durability guarantee for a write site.
    """
    mock_conn = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = (mock_cursor, mock_conn)
    cm.__exit__.return_value = False
    mock_db.transaction.return_value = cm
    return mock_conn, cm


@pytest.mark.unit
class TestGetTenantLanguage:
    """Tests for get_tenant_language function."""

    def test_returns_stored_language_en(self):
        """get_tenant_language returns stored 'en' from DB (via get_cursor)."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('en',)

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            _wire_get_cursor(mock_db, mock_cursor)
            result = get_tenant_language('test-tenant')

        assert result == 'en'
        # READ must use the context-managed get_cursor, not raw get_connection
        mock_db.get_cursor.assert_called_once_with(dictionary=False)
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'SELECT default_language' in query
        assert params == ('test-tenant',)

    def test_returns_nl_when_no_result(self):
        """get_tenant_language returns 'nl' when no tenant row found."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            _wire_get_cursor(MockDB.return_value, mock_cursor)
            result = get_tenant_language('unknown-tenant')

        assert result == 'nl'

    def test_returns_nl_when_value_is_none(self):
        """get_tenant_language returns 'nl' when result[0] is None (tuple row)."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (None,)

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            _wire_get_cursor(MockDB.return_value, mock_cursor)
            result = get_tenant_language('tenant-with-null')

        assert result == 'nl'

    def test_returns_nl_on_exception(self):
        """get_tenant_language returns 'nl' on database exception."""
        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_cursor.side_effect = Exception("Connection failed")
            result = get_tenant_language('error-tenant')

        assert result == 'nl'


@pytest.mark.unit
class TestUpdateTenantLanguage:
    """Tests for update_tenant_language function."""

    def test_succeeds_with_valid_language(self):
        """update_tenant_language returns True when update succeeds."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            _wire_transaction(mock_db, mock_cursor)
            result = update_tenant_language('test-tenant', 'en')

        assert result is True
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'UPDATE tenants' in query
        assert params == ('en', 'test-tenant')

    def test_write_commits_via_transaction(self):
        """Commit-durability (Req 3.6): the UPDATE runs inside transaction()
        (which commits on success), proving the write is actually persisted and
        not left uncommitted under a non-committing get_cursor()."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            _, cm = _wire_transaction(mock_db, mock_cursor)
            result = update_tenant_language('test-tenant', 'nl')

        assert result is True
        # The write MUST be committed via the transaction() context manager...
        mock_db.transaction.assert_called_once_with()
        cm.__enter__.assert_called_once()
        cm.__exit__.assert_called_once()
        # ...and it must NOT use the non-committing get_cursor() for a write.
        mock_db.get_cursor.assert_not_called()
        # The committed statement is the UPDATE with the correct params.
        query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'UPDATE tenants' in query
        assert 'SET default_language' in query
        assert params == ('nl', 'test-tenant')

    def test_fails_with_invalid_language_code(self):
        """update_tenant_language returns False for invalid language code."""
        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            result = update_tenant_language('test-tenant', 'fr')

        assert result is False
        MockDB.return_value.transaction.assert_not_called()

    def test_returns_false_when_tenant_not_found(self):
        """update_tenant_language returns False when rowcount == 0."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            _, cm = _wire_transaction(mock_db, mock_cursor)
            result = update_tenant_language('nonexistent-tenant', 'nl')

        assert result is False
        # Even on a zero-row update the statement still runs inside the committing
        # transaction (no error path), so the context manager completes normally.
        cm.__enter__.assert_called_once()
        cm.__exit__.assert_called_once()

    def test_returns_false_on_exception(self):
        """update_tenant_language returns False when the write raises.

        Rollback is owned by transaction() itself (it rolls back on any exception
        propagating out of the with-block), so the service only needs to swallow
        the error and report failure."""
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB write error")

        with patch('services.tenant_language_service.DatabaseManager') as MockDB:
            _wire_transaction(MockDB.return_value, mock_cursor)
            result = update_tenant_language('test-tenant', 'en')

        assert result is False


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
