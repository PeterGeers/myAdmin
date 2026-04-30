"""
Unit tests for the database-agnostic exception hierarchy.

Feature: database-abstraction-layer
Requirements: 7.1, 7.5
Reference: .kiro/specs/database-abstraction-layer/design.md
"""

import sys
import os
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import db_exceptions


class TestExceptionInheritance:
    """Verify class inheritance: all specific errors are DatabaseError subclasses."""

    def test_integrity_error_is_database_error(self):
        assert issubclass(db_exceptions.IntegrityError, db_exceptions.DatabaseError)

    def test_connection_error_is_database_error(self):
        assert issubclass(db_exceptions.ConnectionError, db_exceptions.DatabaseError)

    def test_operational_error_is_database_error(self):
        assert issubclass(db_exceptions.OperationalError, db_exceptions.DatabaseError)

    def test_database_error_is_exception(self):
        assert issubclass(db_exceptions.DatabaseError, Exception)

    def test_integrity_error_instance_is_database_error(self):
        exc = db_exceptions.IntegrityError("duplicate key")
        assert isinstance(exc, db_exceptions.DatabaseError)
        assert isinstance(exc, Exception)

    def test_connection_error_instance_is_database_error(self):
        exc = db_exceptions.ConnectionError("connection refused")
        assert isinstance(exc, db_exceptions.DatabaseError)
        assert isinstance(exc, Exception)

    def test_operational_error_instance_is_database_error(self):
        exc = db_exceptions.OperationalError("deadlock")
        assert isinstance(exc, db_exceptions.DatabaseError)
        assert isinstance(exc, Exception)


class TestErrorCodeAttribute:
    """Verify error_code attribute is stored and accessible."""

    def test_database_error_stores_error_code(self):
        exc = db_exceptions.DatabaseError("fail", error_code=1045)
        assert exc.error_code == 1045

    def test_database_error_default_error_code_is_none(self):
        exc = db_exceptions.DatabaseError("fail")
        assert exc.error_code is None

    def test_integrity_error_stores_error_code(self):
        exc = db_exceptions.IntegrityError("duplicate", error_code=1062)
        assert exc.error_code == 1062

    def test_connection_error_stores_error_code(self):
        exc = db_exceptions.ConnectionError("refused", error_code=2003)
        assert exc.error_code == 2003

    def test_operational_error_stores_error_code(self):
        exc = db_exceptions.OperationalError("timeout", error_code=2013)
        assert exc.error_code == 2013


class TestCauseChaining:
    """Verify __cause__ is set when original_error is provided."""

    def test_cause_set_when_original_error_provided(self):
        original = ValueError("original problem")
        exc = db_exceptions.DatabaseError("wrapped", original_error=original)
        assert exc.__cause__ is original
        assert exc.original_error is original

    def test_cause_not_set_when_no_original_error(self):
        exc = db_exceptions.DatabaseError("standalone")
        assert exc.__cause__ is None
        assert exc.original_error is None

    def test_integrity_error_cause_chaining(self):
        original = RuntimeError("constraint violation")
        exc = db_exceptions.IntegrityError("duplicate key", error_code=1062, original_error=original)
        assert exc.__cause__ is original
        assert exc.original_error is original
        assert exc.error_code == 1062

    def test_connection_error_cause_chaining(self):
        original = OSError("connection refused")
        exc = db_exceptions.ConnectionError("cannot connect", error_code=2003, original_error=original)
        assert exc.__cause__ is original
        assert exc.original_error is original

    def test_operational_error_cause_chaining(self):
        original = TimeoutError("query timed out")
        exc = db_exceptions.OperationalError("timeout", error_code=2013, original_error=original)
        assert exc.__cause__ is original
        assert exc.original_error is original


class TestMessagePreservation:
    """Verify the exception message is accessible via str()."""

    def test_database_error_message(self):
        exc = db_exceptions.DatabaseError("something went wrong")
        assert str(exc) == "something went wrong"

    def test_integrity_error_message(self):
        exc = db_exceptions.IntegrityError("duplicate entry 'foo' for key 'PRIMARY'")
        assert "duplicate entry" in str(exc)

    def test_exception_can_be_raised_and_caught(self):
        with pytest.raises(db_exceptions.DatabaseError) as exc_info:
            raise db_exceptions.IntegrityError("test", error_code=1062)
        assert exc_info.value.error_code == 1062

    def test_exception_caught_by_specific_type(self):
        with pytest.raises(db_exceptions.IntegrityError):
            raise db_exceptions.IntegrityError("test")

    def test_connection_error_not_caught_as_integrity_error(self):
        with pytest.raises(db_exceptions.ConnectionError):
            raise db_exceptions.ConnectionError("test")
        # Verify it's NOT an IntegrityError
        exc = db_exceptions.ConnectionError("test")
        assert not isinstance(exc, db_exceptions.IntegrityError)
