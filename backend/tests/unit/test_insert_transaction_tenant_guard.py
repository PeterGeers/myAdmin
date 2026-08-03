"""
Unit tests for insert_transaction tenant guard.

Task 9.3: Validates that insert_transaction raises ValueError
when the Administration field is missing or empty.

Feature: banking-pattern-prediction-bugs (Fix 1: Tenant Parameter Threading)
"""

import pytest
from unittest.mock import patch, MagicMock

import database


class TestInsertTransactionTenantGuard:
    """insert_transaction must reject transactions without a valid Administration value."""

    def _create_db_instance(self):
        """Create a DatabaseManager instance without connecting to a real DB."""
        db = database.DatabaseManager.__new__(database.DatabaseManager)
        db.test_mode = True
        db.config = {
            "host": "localhost",
            "user": "test",
            "password": "test",
            "database": "test",
            "port": 3306,
        }
        return db

    def test_insert_transaction_raises_without_administration(self):
        """insert_transaction raises ValueError when Administration is missing entirely."""
        db = self._create_db_instance()

        transaction_no_admin = {
            "TransactionNumber": "TEST001",
            "TransactionDate": "2025-01-15",
            "TransactionDescription": "Test transaction",
            "TransactionAmount": 100.0,
            "Debet": "1002",
            "Credit": "1600",
            "ReferenceNumber": "REF001",
        }

        with pytest.raises(ValueError, match="Administration is required"):
            db.insert_transaction(transaction_no_admin)

    def test_insert_transaction_raises_with_empty_string_administration(self):
        """insert_transaction raises ValueError when Administration is an empty string."""
        db = self._create_db_instance()

        transaction_empty_admin = {
            "TransactionNumber": "TEST002",
            "TransactionDate": "2025-01-15",
            "TransactionDescription": "Test transaction",
            "TransactionAmount": 50.0,
            "Debet": "1002",
            "Credit": "1600",
            "ReferenceNumber": "REF002",
            "Administration": "",
        }

        with pytest.raises(ValueError, match="Administration is required"):
            db.insert_transaction(transaction_empty_admin)

    def test_insert_transaction_raises_with_none_administration(self):
        """insert_transaction raises ValueError when Administration is explicitly None."""
        db = self._create_db_instance()

        transaction_none_admin = {
            "TransactionNumber": "TEST003",
            "TransactionDate": "2025-01-15",
            "TransactionDescription": "Test transaction",
            "TransactionAmount": 75.0,
            "Debet": "1002",
            "Credit": "1600",
            "ReferenceNumber": "REF003",
            "Administration": None,
        }

        with pytest.raises(ValueError, match="Administration is required"):
            db.insert_transaction(transaction_none_admin)

    def test_insert_transaction_accepts_lowercase_administration(self):
        """insert_transaction accepts the lowercase 'administration' key as well."""
        db = self._create_db_instance()
        db.execute_query = MagicMock(return_value=True)

        transaction_lowercase = {
            "TransactionNumber": "TEST004",
            "TransactionDate": "2025-01-15",
            "TransactionDescription": "Test transaction",
            "TransactionAmount": 200.0,
            "Debet": "1002",
            "Credit": "1600",
            "ReferenceNumber": "REF004",
            "administration": "ExampleTenant",
        }

        # Should NOT raise — the lowercase key is accepted
        result = db.insert_transaction(transaction_lowercase)
        assert result is True
        db.execute_query.assert_called_once()

    def test_insert_transaction_accepts_uppercase_administration(self):
        """insert_transaction accepts the uppercase 'Administration' key."""
        db = self._create_db_instance()
        db.execute_query = MagicMock(return_value=True)

        transaction_uppercase = {
            "TransactionNumber": "TEST005",
            "TransactionDate": "2025-01-15",
            "TransactionDescription": "Test transaction",
            "TransactionAmount": 150.0,
            "Debet": "1002",
            "Credit": "1600",
            "ReferenceNumber": "REF005",
            "Administration": "ExampleTenant",
        }

        # Should NOT raise — the uppercase key is accepted
        result = db.insert_transaction(transaction_uppercase)
        assert result is True
        db.execute_query.assert_called_once()
