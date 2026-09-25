"""
Integration test: Airbnb DB upsert idempotence against the local Docker MySQL
test schema (testfinance).

Verifies str_database.upsert_airbnb_bookings applies a keyed refresh by
reservationCode within channel 'airbnb' + administration:

- Re-importing the same planned booking updates the existing bnbplanned row in
  place instead of duplicating it (one row, updated values).
- The same holds for a realised booking into the bnb table.
- A second administration carrying the same reservationCode is untouched by an
  import scoped to the first administration (tenant scoping).

Requirements: 10.1, 10.2, 10.3, 10.4
Feature: airbnb-export-format-update

This test hits a real MySQL instance. It targets the testfinance schema via
STRDatabase(test_mode=True). When the local Docker MySQL is not reachable the
whole module is skipped with a clear reason rather than failing.
"""

import os
import sys
import uuid

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from str_database import STRDatabase  # noqa: E402
from db_exceptions import DatabaseError  # noqa: E402


# Unique administrations per run so parallel/repeat runs never collide and no
# pre-existing tenant data is touched.
_RUN = uuid.uuid4().hex[:8]
ADMIN_A = f"TestAdminA_{_RUN}"
ADMIN_B = f"TestAdminB_{_RUN}"


def _booking(code, *, status, gross, listing="Green Studio", nights=3):
    """Build a minimal Airbnb Booking_Dict for the upsert."""
    return {
        "sourceFile": "airbnb_test.csv",
        "channel": "airbnb",
        "listing": listing,
        "checkinDate": "2026-09-23",
        "checkoutDate": "2026-09-26",
        "nights": nights,
        "guests": 2,
        "amountGross": gross,
        "amountNett": gross,
        "amountChannelFee": 0.0,
        "amountTouristTax": 0.0,
        "amountVat": 0.0,
        "guestName": "Alice Test",
        "phone": "",
        "reservationCode": code,
        "reservationDate": "2026-08-01",
        "status": status,
        "pricePerNight": round(gross / nights, 2) if nights else 0,
        "daysBeforeReservation": 53,
        "addInfo": "",
        "year": 2026,
        "q": 3,
        "m": 9,
        "country": "NL",
    }


def _db_available():
    """Return a connected STRDatabase(test_mode=True), or None if unreachable."""
    try:
        db = STRDatabase(test_mode=True)
        db.execute_query("SELECT 1", None, fetch=True)
        return db
    except Exception:
        return None


# Skip the whole module (rather than error) when the local DB is not reachable.
_DB = _db_available()
pytestmark = pytest.mark.skipif(
    _DB is None,
    reason="local Docker MySQL (testfinance) not reachable",
)


def _count(db, table, code, administration):
    rows = db.execute_query(
        f"SELECT COUNT(*) AS c FROM {table} "
        "WHERE channel = 'airbnb' AND reservationCode = %s AND administration = %s",
        (code, administration),
        fetch=True,
    )
    return rows[0]["c"]


def _fetch_one(db, table, code, administration):
    rows = db.execute_query(
        f"SELECT * FROM {table} "
        "WHERE channel = 'airbnb' AND reservationCode = %s AND administration = %s",
        (code, administration),
        fetch=True,
    )
    return rows[0] if rows else None


@pytest.mark.integration
class TestAirbnbUpsertIdempotence:
    """Keyed-refresh idempotence and tenant scoping for upsert_airbnb_bookings."""

    @pytest.fixture
    def db(self):
        return STRDatabase(test_mode=True)

    @pytest.fixture(autouse=True)
    def _cleanup(self, db):
        """Remove any rows for the test administrations before and after."""
        def _wipe():
            for table in ("bnb", "bnbplanned"):
                for admin in (ADMIN_A, ADMIN_B):
                    db.execute_query(
                        f"DELETE FROM {table} WHERE administration = %s",
                        (admin,),
                        fetch=False,
                        commit=True,
                    )

        _wipe()
        yield
        _wipe()

    def test_planned_reimport_updates_single_row_not_duplicated(self, db):
        """Re-importing the same planned booking → one updated bnbplanned row."""
        code = f"HMPLAN{_RUN}"

        first = db.upsert_airbnb_bookings(
            realised=[], planned=[_booking(code, status="planned", gross=100.0)],
            tenant=ADMIN_A,
        )
        assert "error" not in first, first
        assert first["planned_inserted"] == 1
        assert first["planned_updated"] == 0
        assert _count(db, "bnbplanned", code, ADMIN_A) == 1

        # Re-run the same import with a changed gross → update in place (Req 10.1/10.3).
        second = db.upsert_airbnb_bookings(
            realised=[], planned=[_booking(code, status="planned", gross=250.0)],
            tenant=ADMIN_A,
        )
        assert "error" not in second, second
        assert second["planned_inserted"] == 0
        assert second["planned_updated"] == 1

        # Still exactly one row, and it carries the updated value.
        assert _count(db, "bnbplanned", code, ADMIN_A) == 1
        row = _fetch_one(db, "bnbplanned", code, ADMIN_A)
        assert float(row["amountGross"]) == 250.0

    def test_realised_reimport_updates_single_row_not_duplicated(self, db):
        """Re-importing the same realised booking → one updated bnb row."""
        code = f"HMREAL{_RUN}"

        first = db.upsert_airbnb_bookings(
            realised=[_booking(code, status="realised", gross=100.0)], planned=[],
            tenant=ADMIN_A,
        )
        assert "error" not in first, first
        assert first["realised_inserted"] == 1
        assert first["realised_updated"] == 0
        assert _count(db, "bnb", code, ADMIN_A) == 1

        second = db.upsert_airbnb_bookings(
            realised=[_booking(code, status="realised", gross=333.0)], planned=[],
            tenant=ADMIN_A,
        )
        assert "error" not in second, second
        assert second["realised_inserted"] == 0
        assert second["realised_updated"] == 1

        assert _count(db, "bnb", code, ADMIN_A) == 1
        row = _fetch_one(db, "bnb", code, ADMIN_A)
        assert float(row["amountGross"]) == 333.0

    def test_upsert_is_tenant_scoped_other_admin_untouched(self, db):
        """A second administration with the same reservationCode is untouched."""
        code = f"HMSHARED{_RUN}"

        # Seed the same code for two administrations (planned + realised each).
        db.upsert_airbnb_bookings(
            realised=[_booking(code, status="realised", gross=100.0)],
            planned=[_booking(code, status="planned", gross=100.0)],
            tenant=ADMIN_B,
        )
        db.upsert_airbnb_bookings(
            realised=[_booking(code, status="realised", gross=100.0)],
            planned=[_booking(code, status="planned", gross=100.0)],
            tenant=ADMIN_A,
        )

        # Re-import for ADMIN_A only, with new values.
        result = db.upsert_airbnb_bookings(
            realised=[_booking(code, status="realised", gross=999.0)],
            planned=[_booking(code, status="planned", gross=888.0)],
            tenant=ADMIN_A,
        )
        assert "error" not in result, result
        # Everything for ADMIN_A is an update, nothing new inserted.
        assert result["realised_inserted"] == 0
        assert result["realised_updated"] == 1
        assert result["planned_inserted"] == 0
        assert result["planned_updated"] == 1

        # ADMIN_A rows reflect the new values, still one row each.
        assert _count(db, "bnb", code, ADMIN_A) == 1
        assert _count(db, "bnbplanned", code, ADMIN_A) == 1
        assert float(_fetch_one(db, "bnb", code, ADMIN_A)["amountGross"]) == 999.0
        assert float(_fetch_one(db, "bnbplanned", code, ADMIN_A)["amountGross"]) == 888.0

        # ADMIN_B rows are completely untouched (still one row each, old values).
        assert _count(db, "bnb", code, ADMIN_B) == 1
        assert _count(db, "bnbplanned", code, ADMIN_B) == 1
        assert float(_fetch_one(db, "bnb", code, ADMIN_B)["amountGross"]) == 100.0
        assert float(_fetch_one(db, "bnbplanned", code, ADMIN_B)["amountGross"]) == 100.0
