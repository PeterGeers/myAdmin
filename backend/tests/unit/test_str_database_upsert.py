"""
Unit tests for STRDatabase.upsert_direct_bookings() duplicate handling.

Tests insert/update logic, status updates for non-confirmed re-imports,
and correct count reporting.

Requirements: 8.1–8.5
"""
import sys
import os
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from str_database import STRDatabase


def _make_booking(**overrides):
    """Create a sample booking dict with sensible defaults."""
    booking = {
        "sourceFile": "2026-07-01 test.csv",
        "channel": "dfDirect",
        "listing": "Green Studio",
        "checkinDate": "2026-07-15",
        "checkoutDate": "2026-07-19",
        "nights": 4,
        "guests": 1,
        "amountGross": 464.0,
        "amountNett": 400.0,
        "amountChannelFee": 18.56,
        "amountTouristTax": 5.0,
        "amountVat": 10.0,
        "guestName": "Test Guest",
        "phone": "",
        "reservationCode": "GY-ABC123",
        "reservationDate": "2026-06-01",
        "status": "realised",
        "pricePerNight": 100.0,
        "daysBeforeReservation": 44,
        "addInfo": "GY-ABC123 | Test Guest | Green Studio",
        "year": 2026,
        "q": 3,
        "m": 7,
        "country": "",
        "administration": "TestTenant",
    }
    booking.update(overrides)
    return booking


@pytest.fixture
def mock_str_db():
    """Create a mock STRDatabase instance with transaction context manager."""
    with patch('str_database.DatabaseManager.__init__', return_value=None):
        db = STRDatabase.__new__(STRDatabase)
        db.connection = MagicMock()

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # No existing codes by default
        mock_conn = MagicMock()

        db.transaction = MagicMock()
        db.transaction.return_value.__enter__ = MagicMock(return_value=(mock_cursor, mock_conn))
        db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        yield db, mock_cursor


class TestInsertNewBooking:
    """Req 8.3: New reservationCode → INSERT."""

    def test_insert_new_booking(self, mock_str_db):
        db, mock_cursor = mock_str_db
        mock_cursor.fetchall.return_value = []  # No existing codes

        booking = _make_booking()
        result = db.upsert_direct_bookings([booking], tenant="TestTenant")

        assert result["inserted"] == 1
        assert result["updated"] == 0

    def test_insert_uses_administration(self, mock_str_db):
        """Verify INSERT includes the administration/tenant value."""
        db, mock_cursor = mock_str_db
        mock_cursor.fetchall.return_value = []

        booking = _make_booking()
        result = db.upsert_direct_bookings([booking], tenant="TestTenant")

        assert result["inserted"] == 1
        # Verify execute was called with INSERT query containing tenant value
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if call[0][0].strip().startswith("INSERT")
        ]
        assert len(insert_calls) == 1
        # The last value in the INSERT tuple should be the tenant
        insert_values = insert_calls[0][0][1]
        assert insert_values[-1] == "TestTenant"


class TestUpdateExistingBooking:
    """Req 8.2: Existing reservationCode + dfDirect → UPDATE."""

    def test_update_existing_booking(self, mock_str_db):
        db, mock_cursor = mock_str_db
        # Simulate existing code in DB
        mock_cursor.fetchall.return_value = [{"reservationCode": "GY-ABC123"}]

        booking = _make_booking(reservationCode="GY-ABC123")
        result = db.upsert_direct_bookings([booking], tenant="TestTenant")

        assert result["inserted"] == 0
        assert result["updated"] == 1

    def test_update_query_includes_tenant_in_where(self, mock_str_db):
        """Verify UPDATE WHERE clause includes tenant for isolation."""
        db, mock_cursor = mock_str_db
        mock_cursor.fetchall.return_value = [{"reservationCode": "GY-ABC123"}]

        booking = _make_booking(reservationCode="GY-ABC123")
        db.upsert_direct_bookings([booking], tenant="TestTenant")

        # Find UPDATE call
        update_calls = [
            call for call in mock_cursor.execute.call_args_list
            if call[0][0].strip().startswith("UPDATE")
        ]
        assert len(update_calls) == 1
        # Last param in UPDATE should be tenant (in WHERE clause)
        update_values = update_calls[0][0][1]
        assert update_values[-1] == "TestTenant"


class TestMixInsertAndUpdate:
    """Req 8.1–8.3: Mix of new and existing codes."""

    def test_mix_insert_and_update(self, mock_str_db):
        db, mock_cursor = mock_str_db
        # Only GY-EXIST is already in DB
        mock_cursor.fetchall.return_value = [{"reservationCode": "GY-EXIST"}]

        bookings = [
            _make_booking(reservationCode="GY-NEW01"),
            _make_booking(reservationCode="GY-EXIST"),
        ]
        result = db.upsert_direct_bookings(bookings, tenant="TestTenant")

        assert result["inserted"] == 1
        assert result["updated"] == 1


class TestStatusUpdateNonConfirmed:
    """Req 8.5: Non-confirmed re-import updates status."""

    def test_status_update_applied(self, mock_str_db):
        db, mock_cursor = mock_str_db
        # The code must exist in DB for status update to apply
        mock_cursor.fetchall.return_value = [{"reservationCode": "GY-CAN1"}]

        status_updates = [{"reservationCode": "GY-CAN1", "status": "canceled"}]
        result = db.upsert_direct_bookings([], status_updates=status_updates, tenant="TestTenant")

        # Status update queries are separate UPDATE calls
        status_update_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "SET status" in call[0][0]
        ]
        assert len(status_update_calls) == 1
        # Verify correct parameters: (status, code, tenant)
        params = status_update_calls[0][0][1]
        assert params[0] == "canceled"
        assert params[1] == "GY-CAN1"
        assert params[2] == "TestTenant"

    def test_status_update_only_for_existing_codes(self, mock_str_db):
        """Status updates are skipped if the code doesn't exist in DB."""
        db, mock_cursor = mock_str_db
        mock_cursor.fetchall.return_value = []  # No existing codes

        status_updates = [{"reservationCode": "GY-UNKNOWN", "status": "canceled"}]
        result = db.upsert_direct_bookings([], status_updates=status_updates, tenant="TestTenant")

        # No status update query should have been executed
        status_update_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "SET status" in call[0][0]
        ]
        assert len(status_update_calls) == 0


class TestCountsReturned:
    """Req 8.4: Return summary with inserted/updated counts."""

    def test_counts_returned_correctly(self, mock_str_db):
        db, mock_cursor = mock_str_db
        mock_cursor.fetchall.return_value = [
            {"reservationCode": "GY-OLD1"},
            {"reservationCode": "GY-OLD2"},
        ]

        bookings = [
            _make_booking(reservationCode="GY-NEW1"),
            _make_booking(reservationCode="GY-NEW2"),
            _make_booking(reservationCode="GY-NEW3"),
            _make_booking(reservationCode="GY-OLD1"),
            _make_booking(reservationCode="GY-OLD2"),
        ]
        result = db.upsert_direct_bookings(bookings, tenant="TestTenant")

        assert result["inserted"] == 3
        assert result["updated"] == 2

    def test_empty_bookings_returns_zeros(self, mock_str_db):
        db, mock_cursor = mock_str_db

        result = db.upsert_direct_bookings([], tenant="TestTenant")

        assert result["inserted"] == 0
        assert result["updated"] == 0


class TestTenantFilterInQueries:
    """Verify tenant isolation in SELECT and WHERE clauses."""

    def test_tenant_filter_in_select_existing_codes(self, mock_str_db):
        """The initial SELECT for existing codes includes tenant filter."""
        db, mock_cursor = mock_str_db
        mock_cursor.fetchall.return_value = []

        booking = _make_booking()
        db.upsert_direct_bookings([booking], tenant="TestTenant")

        # First execute call should be the SELECT for existing codes
        select_call = mock_cursor.execute.call_args_list[0]
        query = select_call[0][0]
        params = select_call[0][1]

        assert "administration" in query
        assert params == ("TestTenant",)

    def test_no_tenant_filter_when_tenant_is_none(self, mock_str_db):
        """When tenant is None, no administration filter in SELECT."""
        db, mock_cursor = mock_str_db
        mock_cursor.fetchall.return_value = []

        booking = _make_booking()
        db.upsert_direct_bookings([booking], tenant=None)

        # First call should be SELECT without administration param
        select_call = mock_cursor.execute.call_args_list[0]
        query = select_call[0][0]

        assert "administration" not in query
