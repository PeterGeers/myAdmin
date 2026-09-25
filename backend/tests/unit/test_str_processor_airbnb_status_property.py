"""
Property-based test for Airbnb status routing in the STR ingest path.

Feature: airbnb-export-format-update, Property 9: Status follows file classification

For any parsed batch, every Booking_Dict's ``status`` equals ``planned`` when the batch
came from a Pending_File and ``realised`` when it came from a Realised_File, independent
of the check-in date relative to the current date.

The test writes generated booking rows to a temp CSV with either a Pending header (no
``Uitbetaald`` / ``Verwacht op``) or a Realised header (with them) and drives the file
through ``STRProcessor._process_airbnb_multi``, which is the component that classifies a
file by its header and calls the parser with the resulting status. Check-in dates are
generated BOTH in the past and in the future so the property proves status does NOT depend
on the check-in date vs. today (Req 6.5).

A per-example ``tempfile.TemporaryDirectory`` is used (rather than pytest's function-scoped
``tmp_path`` fixture) so each Hypothesis-generated input gets a fresh directory.

Validates: Requirements 6.1, 6.3, 6.5
Reference: .kiro/specs/airbnb-export-format-update/design.md (Property 9)
"""

import csv
import os
import tempfile
from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from str_airbnb_parser import process_airbnb_multi
from str_processor import STRProcessor

# ---------------------------------------------------------------------------
# Headers — the ONLY difference between a Pending_File and a Realised_File is the
# presence of the three realised-only columns; both share Type + Bruto-inkomsten.
# ---------------------------------------------------------------------------

_SHARED_COLUMNS = [
    "Datum",
    "Type",
    "Bevestigingscode",
    "Boekingsdatum",
    "Begindatum",
    "Einddatum",
    "Nachten",
    "Gast",
    "Advertentie",
    "Informatie",
    "Referentienummer",
    "Valuta",
    "Bedrag",
    "Servicekosten",
    "Schoonmaakkosten",
    "Bruto-inkomsten",
    "Door Airbnb doorbelaste en afgedragen heffingen",
    "Inkomstenjaar",
]

# Realised files add these three columns (design "Header difference").
_REALISED_EXTRA = ["Verwacht op", "Uitbetaald", "Kosten voor snelle uitbetaling"]

PENDING_COLUMNS = list(_SHARED_COLUMNS)
REALISED_COLUMNS = _SHARED_COLUMNS[:16] + [_REALISED_EXTRA[0], _REALISED_EXTRA[1]] + [
    _SHARED_COLUMNS[16],
    _SHARED_COLUMNS[17],
    _REALISED_EXTRA[2],
]


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# Confirmation codes: 10 uppercase-alphanumeric chars, like `HMXDT8WAFF`.
_codes = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=6, max_size=10)


@st.composite
def booking_rows(draw):
    """Generate distinct-code bookings whose check-in dates span far past AND far future.

    Half the batch is forced into the past and half into the future (relative to today),
    so a batch always contains both — this is what proves status is independent of the
    check-in-vs-today relationship (Req 6.5). Each booking is emitted as a Boeking +
    Doorloop totaal pair sharing one confirmation code.
    """
    today = date.today()
    n = draw(st.integers(min_value=1, max_value=4))
    codes = draw(
        st.lists(_codes, min_size=n, max_size=n, unique=True)
    )

    rows = []
    for i, code in enumerate(codes):
        # Alternate far-past and far-future check-ins so both are always present.
        if i % 2 == 0:
            offset = draw(st.integers(min_value=-4000, max_value=-1))  # past
        else:
            offset = draw(st.integers(min_value=1, max_value=4000))  # future
        checkin = today + timedelta(days=offset)
        nights = draw(st.integers(min_value=1, max_value=14))
        checkout = checkin + timedelta(days=nights)
        # Reservation date always before check-in.
        reservation = checkin - timedelta(days=draw(st.integers(min_value=1, max_value=365)))

        checkin_s = checkin.strftime("%m/%d/%Y")
        checkout_s = checkout.strftime("%m/%d/%Y")
        reservation_s = reservation.strftime("%m/%d/%Y")

        # Boeking row carries the bulk of gross + the service fee.
        rows.append(
            {
                "Type": "Boeking",
                "Bevestigingscode": code,
                "Boekingsdatum": reservation_s,
                "Begindatum": checkin_s,
                "Einddatum": checkout_s,
                "Nachten": str(nights),
                "Gast": f"Guest {i}",
                "Advertentie": f"Listing {i}",
                "Servicekosten": '"42,59"',
                "Bruto-inkomsten": "274.80",
            }
        )
        # Doorloop totaal row carries the remainder, zero service fee.
        rows.append(
            {
                "Type": "Doorloop totaal",
                "Bevestigingscode": code,
                "Boekingsdatum": reservation_s,
                "Begindatum": checkin_s,
                "Einddatum": checkout_s,
                "Nachten": str(nights),
                "Gast": f"Guest {i}",
                "Advertentie": f"Listing {i}",
                "Servicekosten": "0.00",
                "Bruto-inkomsten": "76.67",
            }
        )
    # A Payout row (blank code) that must never become a booking.
    rows.append({"Type": "Payout", "Bevestigingscode": "", "Uitbetaald": "100.00"})
    return codes, rows


def _write_csv(path, columns, rows):
    """Write rows to a CSV under ``path`` using ``columns`` as the header."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return str(path)


# ---------------------------------------------------------------------------
# Property 9: Status follows file classification
# ---------------------------------------------------------------------------


class TestAirbnbStatusFollowsClassificationProperty:
    """Feature: airbnb-export-format-update, Property 9: Status follows file classification."""

    @given(data=booking_rows())
    @settings(max_examples=150, deadline=None)
    def test_pending_file_yields_planned_regardless_of_dates(self, data):
        """A Pending_File (no realised columns) yields status=='planned' for every dict.

        Holds even though the batch contains both past and future check-in dates,
        proving status is not derived from check-in-vs-today.

        Validates: Requirements 6.1, 6.5
        """
        codes, rows = data
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = _write_csv(
                os.path.join(tmp, "airbnb_pending.csv"), PENDING_COLUMNS, rows
            )
            processor = STRProcessor(tax_rate_service=None, tenant="ExampleTenant")
            bookings = processor._process_airbnb_multi([csv_path])

        assert len(bookings) == len(codes)  # one dict per code, Payout dropped
        assert all(b["status"] == "planned" for b in bookings)

    @given(data=booking_rows())
    @settings(max_examples=150, deadline=None)
    def test_realised_file_yields_realised_regardless_of_dates(self, data):
        """A Realised_File (with Uitbetaald + Verwacht op) yields status=='realised'.

        Holds even though the batch contains both past and future check-in dates.

        Validates: Requirements 6.3, 6.5
        """
        codes, rows = data
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = _write_csv(
                os.path.join(tmp, "airbnb_realised.csv"), REALISED_COLUMNS, rows
            )
            processor = STRProcessor(tax_rate_service=None, tenant="ExampleTenant")
            bookings = processor._process_airbnb_multi([csv_path])

        assert len(bookings) == len(codes)
        assert all(b["status"] == "realised" for b in bookings)

    @given(
        data=booking_rows(),
        status=st.sampled_from(["planned", "realised"]),
    )
    @settings(max_examples=150, deadline=None)
    def test_parser_stamps_the_batch_status_on_every_dict(self, data, status):
        """The parser stamps the explicit per-bucket status on every dict it returns.

        Drives ``process_airbnb_multi`` directly with an explicit ``status`` (as the
        processor does per classification bucket) and confirms every emitted dict carries
        that status regardless of the generated past/future check-in dates.

        Validates: Requirements 6.1, 6.3, 6.5
        """
        codes, rows = data
        columns = PENDING_COLUMNS if status == "planned" else REALISED_COLUMNS
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = _write_csv(
                os.path.join(tmp, f"airbnb_{status}.csv"), columns, rows
            )
            bookings = process_airbnb_multi(
                [csv_path], tax_rate_service=None, tenant="ExampleTenant", status=status
            )

        assert len(bookings) == len(codes)
        assert all(b["status"] == status for b in bookings)
