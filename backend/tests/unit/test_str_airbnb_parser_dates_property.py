"""
Property-based test for Airbnb date parsing and derived periods.

Uses Hypothesis to verify a correctness property from the design document.
Feature: airbnb-export-format-update, Property 8: Dates and derived periods

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 9.3
Reference: .kiro/specs/airbnb-export-format-update/design.md (Property 8)
"""

import datetime as _dt

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from str_airbnb_parser import build_booking_from_group

# ---------------------------------------------------------------------------
# CSV shape
# ---------------------------------------------------------------------------
#
# The parser reads dates from the first row of a group via parse_airbnb_date
# (MM/DD/YYYY), sets checkinDate/checkoutDate/reservationDate to those calendar
# days (emitted as YYYY-MM-DD), derives year/q/m from the check-in date, and
# computes daysBeforeReservation = (checkin - reservation).days.
#
# calculate_str_taxes is invoked with tax_rate_service=None so it needs no DB.


def _mmddyyyy(d: _dt.date) -> str:
    """Format a date as the export's MM/DD/YYYY notation."""
    return f"{d.month:02d}/{d.day:02d}/{d.year:04d}"


def _group(begindatum: str, einddatum: str, boekingsdatum: str) -> pd.DataFrame:
    """Build a one-row group DataFrame with the given date strings.

    Only the date columns matter for this property; other consumed columns carry
    neutral, parseable values so build_booking_from_group runs end to end.
    """
    return pd.DataFrame(
        [
            {
                "Type": "Boeking",
                "Bevestigingscode": "HMTESTCODE",
                "Boekingsdatum": boekingsdatum,
                "Begindatum": begindatum,
                "Einddatum": einddatum,
                "Nachten": "2",
                "Gast": "Test Guest",
                "Advertentie": "Test Listing",
                "Informatie": "",
                "Servicekosten": "0.00",
                "Bruto-inkomsten": "100.00",
            }
        ]
    )


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------
#
# Sensible range: MM/DD/YYYY only carries a 4-digit year, and datetime.strptime
# with %Y accepts years 1..9999 but the export deals in contemporary dates. A
# 2000-2099 window keeps generated dates realistic while still exercising leap
# years, month/quarter boundaries, and both orderings of reservation vs check-in.

_dates = st.dates(min_value=_dt.date(2000, 1, 1), max_value=_dt.date(2099, 12, 31))


# ---------------------------------------------------------------------------
# Property 8: Dates and derived periods
# ---------------------------------------------------------------------------


class TestAirbnbDatesProperty:
    """Feature: airbnb-export-format-update, Property 8: Dates and derived periods."""

    @settings(max_examples=200)
    @given(checkin=_dates, checkout=_dates, reservation=_dates)
    def test_dates_and_derived_periods(self, checkin, checkout, reservation):
        """For any Begindatum/Einddatum/Boekingsdatum in MM/DD/YYYY form, the parser
        sets checkinDate/checkoutDate/reservationDate to those same calendar days,
        derives year/q/m from the check-in date, and sets daysBeforeReservation to
        (checkin - reservation).days.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4, 9.3
        """
        group = _group(
            begindatum=_mmddyyyy(checkin),
            einddatum=_mmddyyyy(checkout),
            boekingsdatum=_mmddyyyy(reservation),
        )

        booking = build_booking_from_group(
            code="HMTESTCODE",
            rows=group,
            source_file="test.csv",
            status="planned",
            tax_rate_service=None,
            tenant=None,
        )

        # Req 5.1 / 5.2: dates parsed from MM/DD/YYYY and emitted as the same
        # calendar days in YYYY-MM-DD form.
        assert booking["checkinDate"] == checkin.strftime("%Y-%m-%d")
        assert booking["checkoutDate"] == checkout.strftime("%Y-%m-%d")
        assert booking["reservationDate"] == reservation.strftime("%Y-%m-%d")

        # Req 5.4 / 9.3: year / q / m derived from the check-in date.
        assert booking["year"] == checkin.year
        assert booking["q"] == (checkin.month - 1) // 3 + 1
        assert booking["m"] == checkin.month

        # Req 5.3: lead time is the day delta between reservation and check-in.
        assert booking["daysBeforeReservation"] == (checkin - reservation).days
