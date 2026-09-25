"""
Property-based test for the Airbnb parser output contract.

Feature: airbnb-export-format-update, Property 10: Output contract completeness

For any Booking_Group, ``build_booking_from_group`` emits a Booking_Dict that
contains exactly the 24 contract fields (Requirement 8.1) and no ignored source
column (Requirement 9) leaks in as a field, with the fixed values:
``channel == "airbnb"`` (8.2), ``reservationCode == Bevestigingscode`` (8.4),
``listing == normalize_listing_name(Advertentie)`` (8.3), ``guests == 2`` (7.1),
and ``phone == ""`` (7.2). Attributes are read from the group's rows (2.4) and
``Valuta`` is never read into a field (9.2).

Validates: Requirements 2.4, 7.1, 7.2, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from str_airbnb_parser import build_booking_from_group
from str_utils import normalize_listing_name

# The exact 24-field output contract (design "Output Booking_Dict" / Requirement 8.1).
CONTRACT_FIELDS = {
    "sourceFile",
    "channel",
    "listing",
    "checkinDate",
    "checkoutDate",
    "nights",
    "guests",
    "amountGross",
    "amountChannelFee",
    "guestName",
    "phone",
    "reservationCode",
    "reservationDate",
    "status",
    "addInfo",
    "amountVat",
    "amountTouristTax",
    "amountNett",
    "pricePerNight",
    "year",
    "q",
    "m",
    "daysBeforeReservation",
    "country",
}

# Source columns Requirement 9 says must never become output fields.
IGNORED_SOURCE_COLUMNS = {
    "Schoonmaakkosten",
    "Door Airbnb doorbelaste en afgedragen heffingen",
    "Kosten voor snelle uitbetaling",
    "Verwacht op",
    "Uitbetaald",
    "Datum",
    "Referentienummer",
    "Inkomstenjaar",
    "Valuta",  # Req 9.2: currency treated as EUR, never read into a field
    # raw source column names that also must not leak through as-is
    "Bevestigingscode",
    "Advertentie",
    "Begindatum",
    "Einddatum",
    "Boekingsdatum",
    "Nachten",
    "Gast",
    "Informatie",
    "Bruto-inkomsten",
    "Servicekosten",
    "Bedrag",
    "Type",
}


# --- Generators ---------------------------------------------------------------

# Confirmation codes: non-blank alphanumeric tokens.
codes = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=4, max_size=12
)

# Amount cells in the mixed notations Airbnb emits (US, European, blank, padded).
amount_cells = st.sampled_from(
    ["274.80", "76.67", "0.00", "", " 85.50 ", '"42,59"', '"1.234,56"', "13,25", "—"]
)

# MM/DD/YYYY date cells plus some blanks/garbage that trigger the today fallback.
date_cells = st.sampled_from(
    ["09/23/2026", "09/04/2026", "01/15/2025", " 12/31/2024 ", "", "not-a-date"]
)

listings = st.sampled_from(
    ["Cozy Loft", "Beach House #2", "  Studio A  ", "Villa Zon", "apartment-42"]
)

guests = st.sampled_from(["Jan de Vries", "A. Smith", "", "María López"])

info = st.sampled_from(
    ["Guest from Germany", "", "Netherlands stay", "Booking from France"]
)

statuses = st.sampled_from(["planned", "realised"])

nights_cells = st.sampled_from(["1", "2", "7", "0", "", "3.0"])


@st.composite
def booking_groups(draw):
    """Build a varied 1-to-3-row Booking_Group DataFrame plus its scalar fields.

    All rows in a real group repeat the same shared attributes (dates, guest,
    listing, nights) and only the per-row amounts differ, so shared values are
    drawn once and repeated across the rows. Some ignored source columns are
    included to prove they never leak into the output dict.
    """
    code = draw(codes)
    listing = draw(listings)
    guest = draw(guests)
    add_info = draw(info)
    begindatum = draw(date_cells)
    einddatum = draw(date_cells)
    boekingsdatum = draw(date_cells)
    nachten = draw(nights_cells)
    status = draw(statuses)

    n_rows = draw(st.integers(min_value=1, max_value=3))
    row_records = []
    for _ in range(n_rows):
        row_records.append(
            {
                # consumed columns (shared across the group)
                "Bevestigingscode": code,
                "Advertentie": listing,
                "Gast": guest,
                "Informatie": add_info,
                "Begindatum": begindatum,
                "Einddatum": einddatum,
                "Boekingsdatum": boekingsdatum,
                "Nachten": nachten,
                "Type": "Boeking",
                # per-row amounts
                "Bruto-inkomsten": draw(amount_cells),
                "Servicekosten": draw(amount_cells),
                # ignored source columns that must NOT become output fields (Req 9)
                "Schoonmaakkosten": draw(amount_cells),
                "Valuta": "EUR",
                "Datum": draw(date_cells),
                "Referentienummer": "REF-123",
                "Inkomstenjaar": "2026",
                "Verwacht op": draw(date_cells),
                "Uitbetaald": draw(amount_cells),
            }
        )

    df = pd.DataFrame(row_records)
    return {
        "code": code,
        "rows": df,
        "listing": listing,
        "status": status,
    }


# --- Property -----------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(group=booking_groups())
def test_output_contract_completeness(group):
    """Property 10: Output contract completeness.

    For any Booking_Group the emitted dict has exactly the 24 contract fields,
    no ignored source column becomes a field, and the fixed contract values hold.

    Validates: Requirements 2.4, 7.1, 7.2, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2
    """
    code = group["code"]
    rows = group["rows"]
    status = group["status"]

    booking = build_booking_from_group(
        code, rows, source_file="test-source.csv", status=status
    )

    # Req 8.1 / 9.1: exactly the 24 contract fields, nothing more, nothing less.
    assert set(booking.keys()) == CONTRACT_FIELDS

    # Req 9: no ignored / raw source column name leaked in as an output key.
    assert IGNORED_SOURCE_COLUMNS.isdisjoint(booking.keys())

    # Fixed contract values.
    assert booking["channel"] == "airbnb"  # Req 8.2
    assert booking["reservationCode"] == str(code)  # Req 8.4
    assert booking["listing"] == normalize_listing_name(
        str(group["listing"])
    )  # Req 8.3 / 2.4
    assert booking["guests"] == 2  # Req 7.1
    assert booking["phone"] == ""  # Req 7.2

    # status is passed through unchanged (from the file classification).
    assert booking["status"] == status
