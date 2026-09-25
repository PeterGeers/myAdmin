"""
Property-based tests for Airbnb file detection in str_processor.

Uses Hypothesis to verify correctness properties from the design document.
Feature: airbnb-export-format-update, Property 1: Airbnb file detection

Validates: Requirements 1.1, 1.2, 1.5
Reference: .kiro/specs/airbnb-export-format-update/design.md
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from str_processor import _is_airbnb_file

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# The two header markers whose joint presence classifies a file as Airbnb (Req 1.1).
AIRBNB_HEADER_MARKERS = ("Type", "Bruto-inkomsten")

# Arbitrary non-marker column names — deliberately exclude the two marker names
# so a generated "noise" header never accidentally contains a marker.
_noise_columns = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=12
).filter(lambda c: c.strip() not in AIRBNB_HEADER_MARKERS)


@st.composite
def header_columns(draw):
    """A stripped header column list that may or may not contain the markers.

    Callers rely on the returned list already being stripped (as the scanner's
    _airbnb_header_columns produces), so membership tests match the predicate.
    """
    include_type = draw(st.booleans())
    include_bruto = draw(st.booleans())
    noise = draw(st.lists(_noise_columns, min_size=0, max_size=5))
    cols = list(noise)
    if include_type:
        cols.append("Type")
    if include_bruto:
        cols.append("Bruto-inkomsten")
    # Shuffle marker position among noise by inserting at a drawn index.
    order = draw(st.permutations(cols))
    return list(order)


@st.composite
def filenames(draw):
    """A CSV filename that may contain the 'airbnb' and/or 'reservation' token."""
    include_airbnb = draw(st.booleans())
    include_reservation = draw(st.booleans())
    stem = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", max_size=10))
    parts = [stem]
    if include_airbnb:
        # Mixed case to exercise the case-insensitive match (Req 1.2).
        parts.append(draw(st.sampled_from(["airbnb", "Airbnb", "AIRBNB", "AirBnB"])))
    if include_reservation:
        parts.append("reservation")
    draw(st.randoms()).shuffle(parts)
    return "-".join(p for p in parts if p) + ".csv"


def _reference_is_airbnb(filename, columns):
    """Independent restatement of the classification rule (Property 1)."""
    name_token = "airbnb" in filename.lower()
    header_match = bool(
        columns and "Type" in columns and "Bruto-inkomsten" in columns
    )
    return name_token or header_match


# ---------------------------------------------------------------------------
# Property 1: Airbnb file detection
# ---------------------------------------------------------------------------


class TestAirbnbFileDetectionProperty:
    """Feature: airbnb-export-format-update, Property 1: Airbnb file detection."""

    @given(filename=filenames(), columns=header_columns())
    @settings(max_examples=200)
    def test_detection_matches_name_token_or_header_markers(self, filename, columns):
        """A CSV is Airbnb iff name contains 'airbnb' OR header has both markers.

        Validates: Requirements 1.1, 1.2, 1.5
        """
        assert _is_airbnb_file(filename, columns) == _reference_is_airbnb(
            filename, columns
        )

    @given(columns=header_columns())
    @settings(max_examples=100)
    def test_reservation_token_alone_does_not_classify(self, columns):
        """A 'reservation' filename token alone must NOT classify as Airbnb (Req 1.5).

        Only holds when the header does not independently qualify the file, so we
        restrict to headers lacking the marker pair.
        """
        has_markers = "Type" in columns and "Bruto-inkomsten" in columns
        if has_markers:
            columns = [c for c in columns if c != "Bruto-inkomsten"]
        # A reservation-only name with a non-qualifying header is not Airbnb.
        assert _is_airbnb_file("reservation-2026.csv", columns) is False

    @given(filename=filenames())
    @settings(max_examples=100)
    def test_airbnb_name_token_always_classifies(self, filename):
        """Any filename containing 'airbnb' classifies regardless of header (Req 1.2)."""
        forced = filename if "airbnb" in filename.lower() else "airbnb-" + filename
        assert _is_airbnb_file(forced, None) is True

    @given(columns=header_columns())
    @settings(max_examples=100)
    def test_both_header_markers_classify_without_name_token(self, columns):
        """Header with both markers classifies even when the name lacks 'airbnb' (Req 1.1)."""
        forced = list(columns)
        if "Type" not in forced:
            forced.append("Type")
        if "Bruto-inkomsten" not in forced:
            forced.append("Bruto-inkomsten")
        assert _is_airbnb_file("export-2026.csv", forced) is True


# ---------------------------------------------------------------------------
# Property 2: Realised vs. pending classification
# ---------------------------------------------------------------------------
#
# Feature: airbnb-export-format-update, Property 2: Realised vs. pending classification
#
# For any Airbnb file header, the File_Scanner classifies it as a Realised_File
# if and only if the header contains both `Uitbetaald` and `Verwacht op`, and
# otherwise as a Pending_File.
#
# Validates: Requirements 1.3, 1.4
# Reference: .kiro/specs/airbnb-export-format-update/design.md (Property 2)

from str_processor import _airbnb_is_realised

# The two markers whose joint presence classifies a header as a Realised_File.
AIRBNB_REALISED_MARKERS = ("Uitbetaald", "Verwacht op")

# Arbitrary non-marker column names — exclude the realised markers so generated
# "noise" never accidentally introduces one.
_non_marker_columns = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=12
).filter(lambda c: c.strip() not in AIRBNB_REALISED_MARKERS)


@st.composite
def realised_header_columns(draw):
    """A stripped header list that independently varies each realised marker.

    The header always contains the shared Airbnb markers (Type, Bruto-inkomsten)
    plus arbitrary noise, and independently may or may not carry each of the two
    realised markers — so the generated space covers all four presence combos.
    """
    include_uitbetaald = draw(st.booleans())
    include_verwacht = draw(st.booleans())
    noise = draw(st.lists(_non_marker_columns, min_size=0, max_size=5))
    cols = ["Type", "Bruto-inkomsten"] + list(noise)
    if include_uitbetaald:
        cols.append("Uitbetaald")
    if include_verwacht:
        cols.append("Verwacht op")
    order = draw(st.permutations(cols))
    return list(order)


def _reference_is_realised(columns):
    """Independent restatement of the realised-vs-pending rule (Property 2)."""
    return "Uitbetaald" in columns and "Verwacht op" in columns


class TestRealisedVsPendingProperty:
    """Feature: airbnb-export-format-update, Property 2: Realised vs. pending classification."""

    @given(columns=realised_header_columns())
    @settings(max_examples=200)
    def test_realised_iff_both_markers_present(self, columns):
        """A header is Realised_File iff it has both `Uitbetaald` and `Verwacht op`.

        Validates: Requirements 1.3, 1.4
        """
        assert _airbnb_is_realised(columns) == _reference_is_realised(columns)

    @given(columns=realised_header_columns())
    @settings(max_examples=100)
    def test_both_markers_present_is_realised(self, columns):
        """A header carrying both realised markers classifies as realised (Req 1.3)."""
        forced = list(columns)
        if "Uitbetaald" not in forced:
            forced.append("Uitbetaald")
        if "Verwacht op" not in forced:
            forced.append("Verwacht op")
        assert _airbnb_is_realised(forced) is True

    @given(
        columns=realised_header_columns(),
        drop_which=st.sampled_from(AIRBNB_REALISED_MARKERS),
    )
    @settings(max_examples=100)
    def test_missing_either_marker_is_pending(self, columns, drop_which):
        """A header missing at least one realised marker is pending (Req 1.4)."""
        pending = [c for c in columns if c != drop_which]
        assert _airbnb_is_realised(pending) is False
