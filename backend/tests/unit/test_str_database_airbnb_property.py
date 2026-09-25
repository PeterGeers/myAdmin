"""Property-based tests for the Airbnb keyed-refresh upsert.

Feature: airbnb-export-format-update
Property 11: Re-import is idempotent (keyed refresh)

These tests target the pure keyed-refresh split logic of
``STRDatabase.upsert_airbnb_bookings`` (new vs. existing by ``reservationCode``
within ``channel='airbnb'`` + administration) WITHOUT touching a real database.
The live-DB behaviour is covered by the integration test (task 5.2); here we
drive the real ``upsert_airbnb_bookings`` / ``_upsert_airbnb_half`` code against
an in-memory fake cursor that models the ``bnb`` / ``bnbplanned`` tables, so the
SELECT-existing / INSERT-new / UPDATE-existing partition is exercised for real.

Per the unit-test isolation layer (autouse conftest guards real DB connections),
no ``mysql.connector`` connection is ever opened: we construct the STRDatabase
without running its connecting ``__init__`` and stub ``transaction()`` to yield
the fake cursor.
"""

from contextlib import contextmanager
from typing import ClassVar

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# str_database lives under backend/src (added to sys.path by tests/conftest.py)
from str_database import STRDatabase


# ---------------------------------------------------------------------------
# In-memory fake cursor modelling the bnb / bnbplanned tables
# ---------------------------------------------------------------------------
class _FakeCursor:
    """Minimal cursor that understands the exact queries _upsert_airbnb_half
    issues: a SELECT DISTINCT reservationCode, parameterized INSERTs, and
    parameterized UPDATEs. Rows are stored per-table as dicts so the helper's
    ``row["reservationCode"]`` access works like a real dict cursor."""

    # column order of the INSERT statement in _upsert_airbnb_half
    _INSERT_COLS: ClassVar[list[str]] = [
        "sourceFile", "channel", "listing", "checkinDate", "checkoutDate",
        "nights", "guests", "amountGross", "amountNett", "amountChannelFee",
        "amountTouristTax", "amountVat", "guestName", "phone", "reservationCode",
        "reservationDate", "status", "pricePerNight", "daysBeforeReservation",
        "addInfo", "year", "q", "m", "country", "administration",
    ]

    def __init__(self, tables):
        # tables: {table_name: list[row_dict]}
        self._tables = tables
        self._result = []

    def execute(self, query, params=None):
        q = " ".join(query.split())  # normalise whitespace
        params = params or ()

        if q.startswith("SELECT DISTINCT reservationCode FROM"):
            table = q.split()[4]
            has_admin = "administration = %s" in q
            admin = params[0] if has_admin else None
            seen = set()
            self._result = []
            for row in self._tables.setdefault(table, []):
                if row.get("channel") != "airbnb":
                    continue
                if row.get("reservationCode") is None:
                    continue
                if has_admin and row.get("administration") != admin:
                    continue
                code = row["reservationCode"]
                if code not in seen:
                    seen.add(code)
                    self._result.append({"reservationCode": code})
            return

        if q.startswith("INSERT INTO"):
            table = q.split()[2]
            row = dict(zip(self._INSERT_COLS, params))
            self._tables.setdefault(table, []).append(row)
            return

        if q.startswith("UPDATE"):
            table = q.split()[1]
            has_admin = q.rstrip().endswith("administration = %s")
            # UPDATE ... WHERE reservationCode = %s AND channel = 'airbnb' [AND administration = %s]
            code = params[-2] if has_admin else params[-1]
            admin = params[-1] if has_admin else None
            # values, in SET order
            set_cols = [
                "checkinDate", "checkoutDate", "listing", "guestName", "nights",
                "guests", "amountGross", "amountNett", "amountChannelFee",
                "amountVat", "amountTouristTax", "status", "pricePerNight",
                "sourceFile",
            ]
            new_vals = dict(zip(set_cols, params[: len(set_cols)]))
            for row in self._tables.setdefault(table, []):
                if row.get("reservationCode") != code:
                    continue
                if row.get("channel") != "airbnb":
                    continue
                if has_admin and row.get("administration") != admin:
                    continue
                row.update(new_vals)
            return

        raise AssertionError(f"Unexpected query: {q}")

    def fetchall(self):
        return self._result


def _make_str_db(tables):
    """Build an STRDatabase whose transaction() yields a fake cursor backed by
    ``tables``, without running the connecting __init__."""
    db = object.__new__(STRDatabase)

    @contextmanager
    def _fake_transaction(pool_type="primary"):
        yield _FakeCursor(tables), None

    db.transaction = _fake_transaction  # type: ignore[method-assign]
    return db


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------
_codes = st.text(alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", min_size=4, max_size=10)


@st.composite
def _booking(draw, code):
    gross = draw(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False))
    fee = draw(st.floats(min_value=0, max_value=2000, allow_nan=False, allow_infinity=False))
    return {
        "sourceFile": "airbnb_pending.csv",
        "channel": "airbnb",
        "listing": draw(st.sampled_from(["Loft", "Studio", "Suite"])),
        "checkinDate": "2026-09-23",
        "checkoutDate": "2026-09-25",
        "nights": draw(st.integers(min_value=1, max_value=14)),
        "guests": 2,
        "amountGross": gross,
        "amountNett": gross - fee,
        "amountChannelFee": fee,
        "amountTouristTax": 0,
        "amountVat": 0,
        "guestName": draw(st.sampled_from(["Alice", "Bob", "Carol"])),
        "phone": "",
        "reservationCode": code,
        "reservationDate": "2026-08-01",
        "status": "planned",
        "pricePerNight": 0,
        "daysBeforeReservation": 0,
        "addInfo": "",
        "year": 2026,
        "q": 3,
        "m": 9,
        "country": None,
    }


@st.composite
def _booking_set(draw):
    """A set of bookings with distinct reservationCodes (Payout/blank-code rows
    are already excluded upstream; the upsert key requires distinct codes)."""
    codes = draw(st.lists(_codes, min_size=0, max_size=8, unique=True))
    return [draw(_booking(c)) for c in codes]


# ---------------------------------------------------------------------------
# Property 11: Re-import is idempotent (keyed refresh)
# ---------------------------------------------------------------------------
@settings(max_examples=200)
@given(realised=_booking_set(), planned=_booking_set())
def test_reimport_is_idempotent_keyed_refresh(realised, planned):
    """Feature: airbnb-export-format-update, Property 11: Re-import is
    idempotent (keyed refresh).

    For any set of Booking_Dicts within a channel + administration, importing
    the set twice yields the same number of persisted rows as importing once:
    absent reservationCodes are inserted, existing ones updated in place.

    Validates: Requirements 10.1, 10.2, 10.3
    """
    tenant = "ExampleTenant"
    # route realised -> bnb, planned -> bnbplanned; stamp administration as the
    # route layer would (INSERT uses booking.get('administration', tenant)).
    for b in realised:
        b["status"] = "realised"
        b["sourceFile"] = "airbnb_realised.csv"
    for b in planned:
        b["status"] = "planned"

    tables = {"bnb": [], "bnbplanned": []}
    db = _make_str_db(tables)

    first = db.upsert_airbnb_bookings(realised, planned, tenant=tenant)
    rows_bnb_after_first = len(tables["bnb"])
    rows_planned_after_first = len(tables["bnbplanned"])

    second = db.upsert_airbnb_bookings(realised, planned, tenant=tenant)
    rows_bnb_after_second = len(tables["bnb"])
    rows_planned_after_second = len(tables["bnbplanned"])

    # First import: every distinct code inserted, nothing updated.
    assert first["realised_inserted"] == len(realised)
    assert first["realised_updated"] == 0
    assert first["planned_inserted"] == len(planned)
    assert first["planned_updated"] == 0

    # Persisted-row count equals the number of distinct codes per table.
    assert rows_bnb_after_first == len(realised)
    assert rows_planned_after_first == len(planned)

    # Second import: everything already exists -> updated in place, none added.
    assert second["realised_inserted"] == 0
    assert second["realised_updated"] == len(realised)
    assert second["planned_inserted"] == 0
    assert second["planned_updated"] == len(planned)

    # Idempotence: importing twice persists the same number of rows as once.
    assert rows_bnb_after_second == rows_bnb_after_first
    assert rows_planned_after_second == rows_planned_after_first


@settings(max_examples=200)
@given(
    initial=_booking_set(),
    extra=_booking_set(),
)
def test_partial_reimport_inserts_only_absent_codes(initial, extra):
    """Feature: airbnb-export-format-update, Property 11: Re-import is
    idempotent (keyed refresh).

    A second import containing both already-present codes and brand-new codes
    inserts only the absent ones and updates the present ones in place, so the
    final row count equals the number of distinct reservationCodes seen.

    Validates: Requirements 10.1, 10.2, 10.3
    """
    tenant = "ExampleTenant"
    for b in initial:
        b["status"] = "planned"
    for b in extra:
        b["status"] = "planned"

    tables = {"bnb": [], "bnbplanned": []}
    db = _make_str_db(tables)

    # First import: only the initial set.
    db.upsert_airbnb_bookings([], initial, tenant=tenant)
    assert len(tables["bnbplanned"]) == len(initial)

    # Second import: initial (existing) + extra (some may reuse initial codes).
    initial_codes = {b["reservationCode"] for b in initial}
    genuinely_new = [b for b in extra if b["reservationCode"] not in initial_codes]

    result = db.upsert_airbnb_bookings([], initial + extra, tenant=tenant)

    # Distinct codes across both imports.
    all_codes = initial_codes | {b["reservationCode"] for b in extra}
    assert len(tables["bnbplanned"]) == len(all_codes)
    # Only codes absent before this import were inserted.
    assert result["planned_inserted"] == len(
        {b["reservationCode"] for b in genuinely_new}
    )


@settings(max_examples=200)
@given(bookings=_booking_set(), other_tenant=st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=8))
def test_reimport_scoped_by_administration(bookings, other_tenant):
    """Feature: airbnb-export-format-update, Property 11: Re-import is
    idempotent (keyed refresh).

    Idempotence is scoped to the administration: a booking with the same
    reservationCode under a different administration is treated as absent and
    inserted, never updated over another tenant's row.

    Validates: Requirements 10.1, 10.2, 10.3
    """
    tenant_a = "TenantA"
    for b in bookings:
        b["status"] = "planned"

    tables = {"bnb": [], "bnbplanned": []}
    db = _make_str_db(tables)

    db.upsert_airbnb_bookings([], bookings, tenant=tenant_a)
    rows_after_a = len(tables["bnbplanned"])
    assert rows_after_a == len(bookings)

    # Same codes, different administration -> all inserted as new rows.
    other = [dict(b) for b in bookings]
    result = db.upsert_airbnb_bookings([], other, tenant=other_tenant)

    if other_tenant == tenant_a:
        # Same administration: updated in place, no new rows.
        assert result["planned_inserted"] == 0
        assert len(tables["bnbplanned"]) == rows_after_a
    else:
        # Different administration: all inserted, tenant_a rows untouched.
        assert result["planned_inserted"] == len(bookings)
        assert len(tables["bnbplanned"]) == rows_after_a + len(bookings)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
