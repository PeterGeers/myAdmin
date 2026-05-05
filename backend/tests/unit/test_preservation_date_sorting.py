"""
Preservation Property Tests — Non-Date Fields Unchanged by normalize_dates

Property 2: Preservation — Non-Date Fields Unchanged by normalize_dates

IMPORTANT: These tests are written BEFORE implementing the fix.
They verify that normalize_dates preserves all non-date fields exactly,
ensuring no regressions are introduced when the fix is applied.

Observation-first methodology:
- Observe: non-date fields (strings, ints, floats, None, booleans) pass through unchanged
- Observe: fields not listed in date_fields parameter are never modified
- Observe: None values in date fields remain None
- Observe: already-ISO string values in date fields pass through unchanged

Validates: Requirements 3.1, 3.3, 3.4, 3.5, 3.6
"""
import os
import sys
import copy
import datetime
import pytest
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from utils.date_utils import normalize_dates


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for generating non-date scalar values (the types that should be preserved)
non_date_values = st.one_of(
    st.text(min_size=0, max_size=100),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.none(),
    st.booleans(),
)

# Strategy for generating field names (non-date field names)
field_names = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_'),
    min_size=1,
    max_size=30,
).filter(lambda x: x not in ('TransactionDate', 'checkinDate', 'checkoutDate'))

# Strategy for generating a row dict with mixed non-date fields
non_date_row = st.dictionaries(
    keys=field_names,
    values=non_date_values,
    min_size=1,
    max_size=10,
)


@st.composite
def row_with_non_date_fields_and_transaction_date(draw):
    """
    Generate a row dict that has random non-date fields plus a TransactionDate
    field that may be None, a string, or a datetime.date.
    """
    base_row = draw(non_date_row)
    # Add a TransactionDate field with various possible values
    date_value = draw(st.one_of(
        st.none(),
        st.dates(min_value=datetime.date(2000, 1, 1), max_value=datetime.date(2030, 12, 31)),
        # Already-ISO string values
        st.dates(
            min_value=datetime.date(2000, 1, 1),
            max_value=datetime.date(2030, 12, 31)
        ).map(lambda d: d.isoformat()),
    ))
    base_row['TransactionDate'] = date_value
    return base_row


@st.composite
def row_with_mixed_date_fields(draw):
    """
    Generate a row dict with checkinDate and checkoutDate fields that may be
    None, strings, or datetime.date objects, plus random non-date fields.
    """
    base_row = draw(non_date_row)
    date_value_strategy = st.one_of(
        st.none(),
        st.dates(min_value=datetime.date(2000, 1, 1), max_value=datetime.date(2030, 12, 31)),
        st.dates(
            min_value=datetime.date(2000, 1, 1),
            max_value=datetime.date(2030, 12, 31)
        ).map(lambda d: d.isoformat()),
    )
    base_row['checkinDate'] = draw(date_value_strategy)
    base_row['checkoutDate'] = draw(date_value_strategy)
    return base_row


# ---------------------------------------------------------------------------
# Test A: Non-date fields are preserved exactly
# ---------------------------------------------------------------------------

class TestNonDateFieldPreservation:
    """
    **Validates: Requirements 3.3, 3.4, 3.6**

    For any row dictionary, fields NOT listed in date_fields must pass
    through normalize_dates completely unchanged — same type, same value.
    """

    @given(rows=st.lists(non_date_row, min_size=1, max_size=5))
    @settings(max_examples=100, deadline=5000)
    def test_non_date_fields_unchanged_with_transaction_date_spec(self, rows):
        """
        Property: When normalize_dates is called with date_fields=['TransactionDate'],
        all fields that are NOT 'TransactionDate' must remain exactly unchanged.
        """
        # Deep copy to compare before/after
        original = copy.deepcopy(rows)

        result = normalize_dates(rows, ['TransactionDate'])

        for i, row in enumerate(result):
            for key, value in row.items():
                if key != 'TransactionDate':
                    assert row[key] == original[i][key], (
                        f"PRESERVATION VIOLATED: Field '{key}' changed from "
                        f"{original[i][key]!r} to {row[key]!r} after normalize_dates. "
                        f"Non-date fields must never be modified."
                    )

    @given(rows=st.lists(non_date_row, min_size=1, max_size=5))
    @settings(max_examples=100, deadline=5000)
    def test_non_date_fields_unchanged_with_bnb_date_spec(self, rows):
        """
        Property: When normalize_dates is called with
        date_fields=['checkinDate', 'checkoutDate'], all fields that are NOT
        in that list must remain exactly unchanged.
        """
        original = copy.deepcopy(rows)

        result = normalize_dates(rows, ['checkinDate', 'checkoutDate'])

        for i, row in enumerate(result):
            for key, value in row.items():
                if key not in ('checkinDate', 'checkoutDate'):
                    assert row[key] == original[i][key], (
                        f"PRESERVATION VIOLATED: Field '{key}' changed from "
                        f"{original[i][key]!r} to {row[key]!r} after normalize_dates. "
                        f"Non-date fields must never be modified."
                    )

    @given(rows=st.lists(non_date_row, min_size=1, max_size=5))
    @settings(max_examples=100, deadline=5000)
    def test_row_keys_preserved(self, rows):
        """
        Property: normalize_dates must not add or remove any keys from row dicts.
        """
        original_keys = [set(row.keys()) for row in rows]

        result = normalize_dates(rows, ['TransactionDate', 'checkinDate', 'checkoutDate'])

        for i, row in enumerate(result):
            assert set(row.keys()) == original_keys[i], (
                f"PRESERVATION VIOLATED: Row keys changed. "
                f"Before: {original_keys[i]}, After: {set(row.keys())}. "
                f"normalize_dates must not add or remove keys."
            )


# ---------------------------------------------------------------------------
# Test B: None values in date fields remain None
# ---------------------------------------------------------------------------

class TestNoneDateValuePreservation:
    """
    **Validates: Requirements 3.5, 3.6**

    None values in date fields must remain None after normalize_dates.
    This ensures null handling in sort comparisons continues to work.
    """

    @given(
        non_date_data=non_date_row,
        num_rows=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=5000)
    def test_none_transaction_date_preserved(self, non_date_data, num_rows):
        """
        Property: When TransactionDate is None, it must remain None after
        normalize_dates — null values sort to end regardless of direction.
        """
        rows = []
        for _ in range(num_rows):
            row = dict(non_date_data)
            row['TransactionDate'] = None
            rows.append(row)

        result = normalize_dates(rows, ['TransactionDate'])

        for row in result:
            assert row['TransactionDate'] is None, (
                f"PRESERVATION VIOLATED: None TransactionDate became "
                f"{row['TransactionDate']!r}. None values must remain None "
                f"to preserve null-to-end sort behavior."
            )

    @given(non_date_data=non_date_row)
    @settings(max_examples=100, deadline=5000)
    def test_none_checkin_checkout_preserved(self, non_date_data):
        """
        Property: When checkinDate or checkoutDate is None, they must remain
        None after normalize_dates.
        """
        row = dict(non_date_data)
        row['checkinDate'] = None
        row['checkoutDate'] = None

        result = normalize_dates([row], ['checkinDate', 'checkoutDate'])

        assert result[0]['checkinDate'] is None, (
            f"PRESERVATION VIOLATED: None checkinDate became "
            f"{result[0]['checkinDate']!r}."
        )
        assert result[0]['checkoutDate'] is None, (
            f"PRESERVATION VIOLATED: None checkoutDate became "
            f"{result[0]['checkoutDate']!r}."
        )


# ---------------------------------------------------------------------------
# Test C: Already-ISO string values pass through unchanged
# ---------------------------------------------------------------------------

class TestAlreadyISOStringPreservation:
    """
    **Validates: Requirements 3.1, 3.6**

    Date fields that are already ISO-8601 strings (e.g., from char columns
    or from endpoints that already call .isoformat()) must pass through
    unchanged. This ensures /api/banking/mutaties continues to work.
    """

    @given(date_value=st.dates(
        min_value=datetime.date(2000, 1, 1),
        max_value=datetime.date(2030, 12, 31)
    ))
    @settings(max_examples=100, deadline=5000)
    def test_iso_string_transaction_date_unchanged(self, date_value):
        """
        Property: If TransactionDate is already an ISO-8601 string,
        normalize_dates must not modify it.
        """
        iso_string = date_value.isoformat()
        row = {'TransactionDate': iso_string, 'Amount': 100.50}

        result = normalize_dates([row], ['TransactionDate'])

        assert result[0]['TransactionDate'] == iso_string, (
            f"PRESERVATION VIOLATED: Already-ISO string '{iso_string}' was "
            f"changed to '{result[0]['TransactionDate']}'. String date values "
            f"must pass through unchanged."
        )

    @given(
        checkin=st.dates(min_value=datetime.date(2000, 1, 1), max_value=datetime.date(2030, 12, 31)),
        checkout=st.dates(min_value=datetime.date(2000, 1, 1), max_value=datetime.date(2030, 12, 31)),
    )
    @settings(max_examples=100, deadline=5000)
    def test_iso_string_bnb_dates_unchanged(self, checkin, checkout):
        """
        Property: If checkinDate/checkoutDate are already ISO-8601 strings,
        normalize_dates must not modify them.
        """
        checkin_str = checkin.isoformat()
        checkout_str = checkout.isoformat()
        row = {
            'checkinDate': checkin_str,
            'checkoutDate': checkout_str,
            'guestName': 'Test',
        }

        result = normalize_dates([row], ['checkinDate', 'checkoutDate'])

        assert result[0]['checkinDate'] == checkin_str, (
            f"PRESERVATION VIOLATED: Already-ISO checkinDate '{checkin_str}' "
            f"was changed to '{result[0]['checkinDate']}'."
        )
        assert result[0]['checkoutDate'] == checkout_str, (
            f"PRESERVATION VIOLATED: Already-ISO checkoutDate '{checkout_str}' "
            f"was changed to '{result[0]['checkoutDate']}'."
        )


# ---------------------------------------------------------------------------
# Test D: Empty list and missing fields
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """
    **Validates: Requirements 3.5, 3.6**

    Edge cases: empty lists, rows missing date field keys, and rows with
    only non-date fields must all be handled gracefully.
    """

    def test_empty_list_returns_empty_list(self):
        """normalize_dates with empty list returns empty list."""
        result = normalize_dates([], ['TransactionDate'])
        assert result == [], (
            f"PRESERVATION VIOLATED: Empty list input should return empty list, "
            f"got {result!r}."
        )

    def test_empty_list_with_multiple_date_fields(self):
        """normalize_dates with empty list and multiple date fields returns empty list."""
        result = normalize_dates([], ['TransactionDate', 'checkinDate', 'checkoutDate'])
        assert result == [], (
            f"PRESERVATION VIOLATED: Empty list input should return empty list, "
            f"got {result!r}."
        )

    @given(rows=st.lists(non_date_row, min_size=1, max_size=5))
    @settings(max_examples=100, deadline=5000)
    def test_missing_date_field_keys_no_error(self, rows):
        """
        Property: When rows do not contain the specified date field keys,
        normalize_dates must not raise an error and must not modify the rows.
        """
        original = copy.deepcopy(rows)

        # These rows don't have TransactionDate — should not error
        result = normalize_dates(rows, ['TransactionDate'])

        for i, row in enumerate(result):
            assert row == original[i], (
                f"PRESERVATION VIOLATED: Row was modified even though it "
                f"doesn't contain the date field 'TransactionDate'. "
                f"Before: {original[i]!r}, After: {row!r}."
            )

    @given(rows=st.lists(non_date_row, min_size=1, max_size=5))
    @settings(max_examples=100, deadline=5000)
    def test_missing_bnb_date_fields_no_error(self, rows):
        """
        Property: When rows do not contain checkinDate/checkoutDate keys,
        normalize_dates must not raise an error and must not modify the rows.
        """
        original = copy.deepcopy(rows)

        result = normalize_dates(rows, ['checkinDate', 'checkoutDate'])

        for i, row in enumerate(result):
            assert row == original[i], (
                f"PRESERVATION VIOLATED: Row was modified even though it "
                f"doesn't contain 'checkinDate' or 'checkoutDate'. "
                f"Before: {original[i]!r}, After: {row!r}."
            )

    def test_empty_date_fields_list(self):
        """normalize_dates with empty date_fields list preserves all rows."""
        rows = [
            {'TransactionDate': datetime.date(2024, 1, 15), 'Amount': 100},
            {'checkinDate': datetime.date(2024, 3, 5), 'guestName': 'Test'},
        ]
        original = copy.deepcopy(rows)

        result = normalize_dates(rows, [])

        for i, row in enumerate(result):
            assert row == original[i], (
                f"PRESERVATION VIOLATED: Row was modified with empty date_fields. "
                f"Before: {original[i]!r}, After: {row!r}."
            )


# ---------------------------------------------------------------------------
# Test E: Return value is the same list reference (mutate in place)
# ---------------------------------------------------------------------------

class TestReturnBehavior:
    """
    **Validates: Design requirement — mutate in place and return the list**

    normalize_dates must return the same list object (mutate in place),
    matching the pattern used in banking_service.py.
    """

    @given(rows=st.lists(non_date_row, min_size=0, max_size=5))
    @settings(max_examples=50, deadline=5000)
    def test_returns_same_list_reference(self, rows):
        """
        Property: normalize_dates returns the same list object it received.
        """
        result = normalize_dates(rows, ['TransactionDate'])

        assert result is rows, (
            "DESIGN VIOLATED: normalize_dates must return the same list "
            "reference (mutate in place), matching banking_service.py pattern."
        )


# ---------------------------------------------------------------------------
# Test F: Composite rows with mixed date and non-date fields
# ---------------------------------------------------------------------------

class TestCompositeRowPreservation:
    """
    **Validates: Requirements 3.3, 3.4, 3.5, 3.6**

    Full integration-style property test with composite rows containing
    both date fields and non-date fields of various types.
    """

    @given(row=row_with_non_date_fields_and_transaction_date())
    @settings(max_examples=100, deadline=5000)
    def test_composite_row_non_date_fields_preserved(self, row):
        """
        Property: In a row with both TransactionDate and other fields,
        all non-TransactionDate fields must be preserved exactly.
        """
        original = copy.deepcopy(row)

        result = normalize_dates([row], ['TransactionDate'])

        for key in original:
            if key != 'TransactionDate':
                assert result[0][key] == original[key], (
                    f"PRESERVATION VIOLATED: Field '{key}' changed from "
                    f"{original[key]!r} to {result[0][key]!r} in composite row."
                )

    @given(row=row_with_non_date_fields_and_transaction_date())
    @settings(max_examples=100, deadline=5000)
    def test_composite_row_none_date_preserved(self, row):
        """
        Property: In a composite row, if TransactionDate is None,
        it must remain None after normalize_dates.
        """
        row['TransactionDate'] = None
        result = normalize_dates([row], ['TransactionDate'])

        assert result[0]['TransactionDate'] is None, (
            f"PRESERVATION VIOLATED: None TransactionDate became "
            f"{result[0]['TransactionDate']!r} in composite row."
        )

    @given(row=row_with_mixed_date_fields())
    @settings(max_examples=100, deadline=5000)
    def test_composite_row_bnb_non_date_fields_preserved(self, row):
        """
        Property: In a row with checkinDate, checkoutDate, and other fields,
        all non-date fields must be preserved exactly.
        """
        original = copy.deepcopy(row)

        result = normalize_dates([row], ['checkinDate', 'checkoutDate'])

        for key in original:
            if key not in ('checkinDate', 'checkoutDate'):
                assert result[0][key] == original[key], (
                    f"PRESERVATION VIOLATED: Field '{key}' changed from "
                    f"{original[key]!r} to {result[0][key]!r} in BNB composite row."
                )
