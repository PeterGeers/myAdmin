"""
Property-based test for Airbnb row grouping in str_airbnb_parser.

Uses Hypothesis to verify a correctness property from the design document.
Feature: airbnb-export-format-update, Property 3: Grouping produces one booking
per confirmation code, Payout rows excluded

Validates: Requirements 2.1, 2.2, 2.3
Reference: .kiro/specs/airbnb-export-format-update/design.md (Property 3)
"""

import csv

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from str_airbnb_parser import process_airbnb_multi

# ---------------------------------------------------------------------------
# CSV shape
# ---------------------------------------------------------------------------
#
# The Pending_File header (design "Data shapes"). The parser strips BOM and
# whitespace from column names, drops `Payout` rows and blank-`Bevestigingscode`
# rows, then groups the remainder by the stripped `Bevestigingscode`.

HEADER = [
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


def _row(row_type, code):
    """Build one CSV row dict for a given Type and Bevestigingscode.

    Booking rows carry realistic dates/amounts; Payout rows leave the code blank
    and carry no confirmation-linked attributes (matching the export).
    """
    if row_type == "Payout":
        code = ""
    return {
        "Datum": "09/23/2026",
        "Type": row_type,
        "Bevestigingscode": code,
        "Boekingsdatum": "09/04/2026",
        "Begindatum": "09/23/2026",
        "Einddatum": "09/25/2026",
        "Nachten": "2",
        "Gast": "Test Guest",
        "Advertentie": "Test Listing",
        "Informatie": "",
        "Referentienummer": "",
        "Valuta": "EUR",
        "Bedrag": "274.80",
        "Servicekosten": "42,59" if row_type == "Boeking" else "0.00",
        "Schoonmaakkosten": "0.00",
        "Bruto-inkomsten": "274.80" if row_type == "Boeking" else "76.67",
        "Door Airbnb doorbelaste en afgedragen heffingen": "0.00",
        "Inkomstenjaar": "2026",
    }


def _write_csv(path, rows):
    """Write the header + given row dicts to a CSV the parser can read."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# Distinct, non-blank confirmation codes (uppercase alnum, Airbnb-style).
# Real Airbnb confirmation codes always contain at least one letter (e.g.
# `HMXDT8WAFF`); an all-digit code is outside the actual input space and would
# only exercise pandas' numeric-column coercion, not the grouping logic. The
# generator therefore requires at least one alphabetic character.
_codes = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=6, max_size=10
).filter(lambda c: any(ch.isalpha() for ch in c))


@st.composite
def row_plans(draw):
    """Generate an interleaving of Boeking / Doorloop totaal / Payout rows.

    Returns (rows, expected_codes):
      - `rows` is a shuffled list of CSV row dicts. Each distinct booking code
        gets at least one Boeking/Doorloop row; Payout rows carry a blank code.
      - `expected_codes` is the set of distinct non-blank codes that MUST each
        produce exactly one Booking_Dict.
    """
    codes = draw(st.lists(_codes, min_size=0, max_size=6, unique=True))
    n_payouts = draw(st.integers(min_value=0, max_value=4))

    rows = []
    for code in codes:
        # Each booking appears as a Boeking + Doorloop totaal pair; occasionally
        # only one of the two rows is present to exercise single-row groups.
        which = draw(
            st.sampled_from([("Boeking", "Doorloop totaal"), ("Boeking",), ("Doorloop totaal",)])
        )
        for row_type in which:
            rows.append(_row(row_type, code))

    for _ in range(n_payouts):
        rows.append(_row("Payout", ""))

    # Interleave everything so Payout/booking order is arbitrary.
    rows = draw(st.permutations(rows))
    return list(rows), set(codes)


# ---------------------------------------------------------------------------
# Property 3: Grouping — one booking per code, Payout excluded
# ---------------------------------------------------------------------------


class TestAirbnbGroupingProperty:
    """Feature: airbnb-export-format-update, Property 3: Grouping produces one
    booking per confirmation code, Payout rows excluded."""

    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(plan=row_plans())
    def test_one_booking_per_code_payout_excluded(self, plan, tmp_path):
        """For any interleaving of Boeking/Doorloop/Payout rows, the parser emits
        exactly one Booking_Dict per distinct non-blank Bevestigingscode and none
        for Payout/blank-code rows.

        Validates: Requirements 2.1, 2.2, 2.3
        """
        rows, expected_codes = plan

        csv_path = tmp_path / "airbnb_pending.csv"
        _write_csv(str(csv_path), rows)

        if not rows:
            # No booking rows at all → every file row is dropped → parser raises
            # nothing to group; an empty CSV still parses to an empty result.
            result = process_airbnb_multi([str(csv_path)], status="planned")
            assert result == []
            return

        result = process_airbnb_multi([str(csv_path)], status="planned")

        result_codes = [b["reservationCode"] for b in result]

        # Req 2.2: exactly one Booking_Dict per distinct code (no duplicates).
        assert len(result) == len(expected_codes)
        # Req 2.1 / 2.3: the produced codes are exactly the distinct non-blank
        # codes — no Payout/blank-code row produced a dict.
        assert set(result_codes) == expected_codes
        assert len(result_codes) == len(set(result_codes))
        # No dict ever carries a blank reservation code.
        assert all(code != "" for code in result_codes)
