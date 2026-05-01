"""
Unit test connection guard.

Prevents any unit test from making real database connections.
This conftest.py is automatically loaded by pytest for all tests
under backend/tests/unit/.
"""
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def block_real_connections():
    """
    Prevent any unit test from making real database connections.
    Raises RuntimeError if mysql.connector.connect is called without a mock.
    """
    def connection_guard(*args, **kwargs):
        raise RuntimeError(
            "Unit tests must not create real database connections. "
            "Use the 'mock_db' fixture from conftest.py instead."
        )

    with patch('mysql.connector.connect', side_effect=connection_guard):
        yield
