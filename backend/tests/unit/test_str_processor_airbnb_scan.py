"""Classification unit tests for Airbnb file detection in ``str_processor``.

Exercises the scanner detection/classification helpers
(``_airbnb_header_columns``, ``_is_airbnb_file``, ``_airbnb_is_realised``) over the
two real sample export headers plus filename-token edge cases.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

import os

from str_processor import (
    _airbnb_header_columns,
    _airbnb_is_realised,
    _is_airbnb_file,
)

# Sample exports captured from the real Airbnb downloads.
_SAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", ".agent-output"
)
PENDING_SAMPLE = os.path.join(_SAMPLES_DIR, "airbnb_pending.csv")
REALISED_SAMPLE = os.path.join(_SAMPLES_DIR, "airbnb_08_2026-09_2026.csv")


class TestAirbnbHeaderColumns:
    """``_airbnb_header_columns`` reads and normalizes a CSV header."""

    def test_header_columns_pending_sample_strips_bom_and_whitespace(self):
        columns = _airbnb_header_columns(PENDING_SAMPLE)

        assert columns is not None
        # BOM removed from the first column; surrounding padding stripped.
        assert columns[0] == "Datum"
        assert "Type" in columns
        assert "Bruto-inkomsten" in columns
        assert not any(c.startswith("\ufeff") for c in columns)
        assert all(c == c.strip() for c in columns)

    def test_header_columns_realised_sample_includes_realised_markers(self):
        columns = _airbnb_header_columns(REALISED_SAMPLE)

        assert columns is not None
        assert "Uitbetaald" in columns
        assert "Verwacht op" in columns

    def test_header_columns_unreadable_file_returns_none(self):
        columns = _airbnb_header_columns(
            os.path.join(_SAMPLES_DIR, "does_not_exist_zzz.csv")
        )

        assert columns is None


class TestIsAirbnbFile:
    """``_is_airbnb_file`` classifies a file as Airbnb by header or filename."""

    def test_pending_sample_header_classifies_as_airbnb(self):
        columns = _airbnb_header_columns(PENDING_SAMPLE)

        # Req 1.1: header has both Type and Bruto-inkomsten.
        assert _is_airbnb_file("airbnb_pending.csv", columns) is True

    def test_realised_sample_header_classifies_as_airbnb(self):
        columns = _airbnb_header_columns(REALISED_SAMPLE)

        assert _is_airbnb_file("airbnb_08_2026-09_2026.csv", columns) is True

    def test_airbnb_filename_token_with_unreadable_header_classifies_as_airbnb(self):
        # Req 1.2: filename token wins even when the header cannot be read.
        assert _is_airbnb_file("something-airbnb.csv", None) is True

    def test_header_content_classifies_even_without_airbnb_in_name(self):
        # Req 1.1: header content alone is sufficient, name token not required.
        columns = _airbnb_header_columns(REALISED_SAMPLE)

        assert _is_airbnb_file("export-2026.csv", columns) is True

    def test_reservation_name_alone_not_airbnb(self):
        # Req 1.5: the legacy `reservation` token no longer classifies a file.
        assert _is_airbnb_file("reservation_2026.csv", None) is False
        assert _is_airbnb_file("reservations.csv", []) is False


class TestAirbnbIsRealised:
    """``_airbnb_is_realised`` splits Airbnb files into realised vs pending."""

    def test_realised_sample_header_classifies_as_realised(self):
        columns = _airbnb_header_columns(REALISED_SAMPLE)

        # Req 1.3: both Uitbetaald and Verwacht op present → Realised_File.
        assert _airbnb_is_realised(columns) is True

    def test_pending_sample_header_classifies_as_pending(self):
        columns = _airbnb_header_columns(PENDING_SAMPLE)

        # Req 1.4: header lacks the realised markers → Pending_File.
        assert _airbnb_is_realised(columns) is False

    def test_partial_realised_markers_not_realised(self):
        # Only one of the two markers present → still pending.
        assert _airbnb_is_realised(["Type", "Bruto-inkomsten", "Uitbetaald"]) is False
        assert (
            _airbnb_is_realised(["Type", "Bruto-inkomsten", "Verwacht op"]) is False
        )


class TestSampleFileEndToEndClassification:
    """The two real samples classify to the expected buckets end-to-end."""

    def test_pending_sample_is_airbnb_and_pending(self):
        columns = _airbnb_header_columns(PENDING_SAMPLE)

        assert _is_airbnb_file("airbnb_pending.csv", columns) is True
        assert _airbnb_is_realised(columns) is False

    def test_realised_sample_is_airbnb_and_realised(self):
        columns = _airbnb_header_columns(REALISED_SAMPLE)

        assert _is_airbnb_file("airbnb_08_2026-09_2026.csv", columns) is True
        assert _airbnb_is_realised(columns) is True

    def test_unreadable_header_airbnb_token_defaults_to_pending(self):
        # Token-only Airbnb file with an unreadable header → pending (safer).
        columns = _airbnb_header_columns(
            os.path.join(_SAMPLES_DIR, "does_not_exist_zzz.csv")
        )

        assert _is_airbnb_file("something-airbnb.csv", columns) is True
        # scanner treats "columns falsy → not realised" as pending.
        assert not (columns and _airbnb_is_realised(columns))
