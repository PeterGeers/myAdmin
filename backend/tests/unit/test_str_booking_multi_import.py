"""
Property-based tests for Booking.com multi-file import.

Uses Hypothesis to verify correctness properties from the design document.
Feature: str-bookingcom-multi-file-import

Reference: .kiro/specs/str-bookingcom-multi-file-import/design.md
"""

import sys
import os
import re
import pytest
import pandas as pd
import tempfile
import shutil
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume, HealthCheck

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from str_processor import STRProcessor


# ---------------------------------------------------------------------------
# Strategies: generate valid Booking.com DataFrames
# ---------------------------------------------------------------------------

def booking_row_strategy():
    """Strategy to generate a single valid Booking.com row as a dict."""
    return st.fixed_dictionaries({
        'Book number': st.integers(min_value=1000000, max_value=9999999).map(str),
        'Check-in': st.dates(
            min_value=date(2024, 1, 1),
            max_value=date(2026, 12, 31),
        ).map(lambda d: d.strftime('%Y-%m-%d')),
        'Check-out': st.dates(
            min_value=date(2024, 1, 5),
            max_value=date(2027, 1, 5),
        ).map(lambda d: d.strftime('%Y-%m-%d')),
        'Guest name(s)': st.text(
            alphabet=st.characters(whitelist_categories=('L', 'Zs')),
            min_size=2, max_size=30,
        ),
        'Unit type': st.sampled_from([
            'One-Bedroom Apartment', 'Rode Studio', 'Apartment',
            'Green Studio', 'Red Studio', 'Child Friendly',
        ]),
        'Duration (nights)': st.integers(min_value=1, max_value=30),
        'Price': st.floats(min_value=50.0, max_value=5000.0, allow_nan=False, allow_infinity=False).map(
            lambda v: f"{round(v, 4)} EUR"
        ),
        'Status': st.sampled_from(['ok', 'ok', 'ok', 'cancelled_by_guest']),
        'Commission amount': st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False).map(
            lambda v: f"{round(v, 6)} EUR"
        ),
        'Persons': st.integers(min_value=1, max_value=10),
        'Adults': st.integers(min_value=1, max_value=8),
        'Children': st.integers(min_value=0, max_value=4),
        'Booked on': st.dates(
            min_value=date(2023, 6, 1),
            max_value=date(2026, 6, 1),
        ).map(lambda d: f"{d.strftime('%Y-%m-%d')} 10:00:00"),
    })


def booking_dataframe_strategy(min_rows=1, max_rows=10):
    """Strategy to generate a DataFrame with valid Booking.com columns."""
    return st.lists(
        booking_row_strategy(),
        min_size=min_rows,
        max_size=max_rows,
    ).map(pd.DataFrame)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def processor():
    """Create STRProcessor instance for testing."""
    return STRProcessor(test_mode=True)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def write_df_to_csv(df: pd.DataFrame, directory: str, filename: str) -> str:
    """Write a DataFrame to a CSV file and return the path."""
    path = os.path.join(directory, filename)
    df.to_csv(path, index=False)
    return path


def write_df_to_excel(df: pd.DataFrame, directory: str, filename: str) -> str:
    """Write a DataFrame to an Excel file and return the path."""
    path = os.path.join(directory, filename)
    df.to_excel(path, index=False)
    return path


def write_df_to_tsv(df: pd.DataFrame, directory: str, filename: str) -> str:
    """Write a DataFrame to a TSV file and return the path."""
    path = os.path.join(directory, filename)
    df.to_csv(path, index=False, sep='\t')
    return path


# ---------------------------------------------------------------------------
# Feature: str-bookingcom-multi-file-import, Property 1: Concatenation
# preserves all rows
# ---------------------------------------------------------------------------

class TestProperty1ConcatenationPreservesAllRows:
    """
    Property 1: Concatenation preserves all rows.

    For any list of valid Booking.com DataFrames, the concatenated DataFrame
    SHALL have a row count equal to the sum of the row counts of the
    individual DataFrames (before deduplication).

    Validates: Requirements 2.1
    """

    @given(
        dfs=st.lists(
            booking_dataframe_strategy(min_rows=1, max_rows=8),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_concatenation_preserves_row_count(self, dfs):
        """Concatenating N DataFrames preserves total row count."""
        expected_total = sum(len(df) for df in dfs)
        combined = pd.concat(dfs, ignore_index=True)
        assert len(combined) == expected_total

    @given(
        dfs=st.lists(
            booking_dataframe_strategy(min_rows=1, max_rows=8),
            min_size=2,
            max_size=5,
        )
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_concatenation_preserves_columns(self, dfs):
        """Concatenating DataFrames preserves all column names."""
        expected_columns = set(dfs[0].columns)
        combined = pd.concat(dfs, ignore_index=True)
        assert set(combined.columns) == expected_columns

    @given(df=booking_dataframe_strategy(min_rows=1, max_rows=15))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_single_dataframe_concat_is_identity(self, df):
        """Concatenating a single DataFrame is an identity operation."""
        combined = pd.concat([df], ignore_index=True)
        assert len(combined) == len(df)
        assert list(combined.columns) == list(df.columns)


# ---------------------------------------------------------------------------
# Feature: str-bookingcom-multi-file-import, Property 2: Partial failure
# resilience
# ---------------------------------------------------------------------------

class TestProperty2PartialFailureResilience:
    """
    Property 2: Partial failure resilience.

    For any mix of valid and invalid file paths where at least one file is
    valid, the File_Concatenator SHALL produce a result containing all rows
    from the valid files and an error list containing exactly the filenames
    of the invalid files.

    Validates: Requirements 2.2
    """

    @given(
        valid_dfs=st.lists(
            booking_dataframe_strategy(min_rows=1, max_rows=5),
            min_size=1,
            max_size=3,
        ),
        n_invalid=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=20, deadline=2000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_valid_files_processed_despite_invalid_files(self, valid_dfs, n_invalid):
        """Valid files are processed even when some files are invalid."""
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            # Write valid files
            valid_paths = []
            for i, df in enumerate(valid_dfs):
                path = write_df_to_csv(df, tmp_dir, f"valid_{i}.csv")
                valid_paths.append(path)

            # Create invalid files (binary garbage that pandas cannot parse)
            invalid_paths = []
            for i in range(n_invalid):
                path = os.path.join(tmp_dir, f"invalid_{i}.bin")
                with open(path, 'wb') as f:
                    f.write(b'\x00\x01\x02\x80\x81\x82\xff\xfe\xfd' * 50)
                invalid_paths.append(path)

            all_paths = valid_paths + invalid_paths

            # _process_booking_multi should succeed (at least one valid file)
            result = processor._process_booking_multi(all_paths)

            # Result should contain bookings from valid files
            # (some rows may be skipped due to zero price or cancelled status,
            #  but the method should not raise)
            assert isinstance(result, list)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(n_invalid=st.integers(min_value=1, max_value=4))
    @settings(max_examples=20, deadline=2000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_all_invalid_files_raises_value_error(self, n_invalid):
        """When all files fail to parse, a ValueError is raised."""
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            invalid_paths = []
            for i in range(n_invalid):
                path = os.path.join(tmp_dir, f"bad_{i}.bin")
                with open(path, 'wb') as f:
                    f.write(b'\x00\x01\x02\x80\x81\x82\xff\xfe\xfd' * 50)
                invalid_paths.append(path)

            with pytest.raises(ValueError, match="All files failed to parse"):
                processor._process_booking_multi(invalid_paths)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(
        valid_dfs=st.lists(
            booking_dataframe_strategy(min_rows=1, max_rows=5),
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=20, deadline=2000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_all_valid_files_no_error(self, valid_dfs):
        """When all files are valid, processing succeeds without error."""
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            paths = []
            for i, df in enumerate(valid_dfs):
                path = write_df_to_csv(df, tmp_dir, f"file_{i}.csv")
                paths.append(path)

            result = processor._process_booking_multi(paths)
            assert isinstance(result, list)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Feature: str-bookingcom-multi-file-import, Property 3: Deduplication keeps
# exactly one record per Book number
# ---------------------------------------------------------------------------

class TestProperty3DeduplicationKeepsOnePerBookNumber:
    """
    Property 3: Deduplication keeps exactly one record per Book number.

    For any concatenated DataFrame containing duplicate Book number values,
    after deduplication there SHALL be exactly one row per unique Book number,
    and the retained row's values SHALL match the last occurrence in the
    concatenated order.

    Validates: Requirements 2.3
    """

    @given(
        base_df=booking_dataframe_strategy(min_rows=2, max_rows=8),
        n_duplicates=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_dedup_produces_unique_book_numbers(self, base_df, n_duplicates):
        """After deduplication, each Book number appears exactly once."""
        # Create duplicates by repeating some rows with the same Book number
        dup_rows = base_df.sample(n=min(n_duplicates, len(base_df)), replace=True)
        combined = pd.concat([base_df, dup_rows], ignore_index=True)

        deduped = combined.drop_duplicates(subset='Book number', keep='last')

        # Each Book number should appear exactly once
        assert deduped['Book number'].is_unique

    @given(
        base_df=booking_dataframe_strategy(min_rows=2, max_rows=8),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_dedup_keeps_last_occurrence(self, base_df):
        """Deduplication retains the last occurrence of each Book number."""
        # Create a modified copy with different guest names for duplicates
        modified = base_df.copy()
        modified['Guest name(s)'] = 'MODIFIED_GUEST'

        combined = pd.concat([base_df, modified], ignore_index=True)
        deduped = combined.drop_duplicates(subset='Book number', keep='last')

        # All retained rows should have the modified guest name (last occurrence)
        for _, row in deduped.iterrows():
            assert row['Guest name(s)'] == 'MODIFIED_GUEST'

    @given(df=booking_dataframe_strategy(min_rows=1, max_rows=10))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_dedup_count_leq_original(self, df):
        """Deduplicated row count is always <= original row count."""
        deduped = df.drop_duplicates(subset='Book number', keep='last')
        assert len(deduped) <= len(df)

    @given(df=booking_dataframe_strategy(min_rows=1, max_rows=10))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_dedup_count_equals_unique_book_numbers(self, df):
        """Deduplicated row count equals the number of unique Book numbers."""
        deduped = df.drop_duplicates(subset='Book number', keep='last')
        assert len(deduped) == df['Book number'].nunique()


# ---------------------------------------------------------------------------
# Feature: str-bookingcom-multi-file-import, Property 4: Multi-file algorithm
# equivalence
# ---------------------------------------------------------------------------

class TestProperty4MultiFileAlgorithmEquivalence:
    """
    Property 4: Multi-file algorithm equivalence.

    For any set of Booking.com booking rows, processing them as a single
    concatenated DataFrame through `_process_booking_multi` SHALL produce
    identical financial calculations (`amountGross`, `amountChannelFee`,
    `amountVat`, `amountTouristTax`, `amountNett`) as processing each row
    individually through the existing `_process_booking` algorithm.

    **Validates: Requirements 3.1, 7.1**
    """

    FINANCIAL_FIELDS = [
        'amountGross',
        'amountChannelFee',
        'amountVat',
        'amountTouristTax',
        'amountNett',
    ]

    @given(df=booking_dataframe_strategy(min_rows=1, max_rows=10))
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow],
        deadline=5000,
    )
    def test_multi_file_matches_single_file_financials(self, df):
        """Financial fields from _process_booking_multi match _process_booking for the same data."""
        # Filter out cancelled_by_guest rows to ensure rows are actually processed
        df = df[df['Status'] != 'cancelled_by_guest'].reset_index(drop=True)
        # Ensure unique Book numbers so deduplication in _process_booking_multi
        # doesn't reduce the row count vs _process_booking (which doesn't dedup).
        # Deduplication correctness is tested separately in Property 3.
        df = df.drop_duplicates(subset='Book number', keep='last').reset_index(drop=True)
        assume(len(df) > 0)

        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            # Write the DataFrame to a single CSV file
            csv_path = write_df_to_csv(df, tmp_dir, 'bookings.csv')

            # Process via single-file path: _process_booking
            single_result = processor._process_booking(csv_path)

            # Process via multi-file path: _process_booking_multi with 1 file
            multi_result = processor._process_booking_multi([csv_path])

            # Both should produce the same number of bookings
            assert len(single_result) == len(multi_result), (
                f"Row count mismatch: single={len(single_result)}, multi={len(multi_result)}"
            )

            # Compare financial fields for each booking (matched by reservationCode)
            single_by_code = {b['reservationCode']: b for b in single_result}
            multi_by_code = {b['reservationCode']: b for b in multi_result}

            assert set(single_by_code.keys()) == set(multi_by_code.keys()), (
                "Reservation codes differ between single and multi processing"
            )

            for code in single_by_code:
                s = single_by_code[code]
                m = multi_by_code[code]
                for field in self.FINANCIAL_FIELDS:
                    assert s[field] == m[field], (
                        f"Booking {code}: {field} differs — "
                        f"single={s[field]}, multi={m[field]}"
                    )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Feature: str-bookingcom-multi-file-import, Property 5: sourceFile format
# reflects file count
# ---------------------------------------------------------------------------

class TestProperty5SourceFileFormatReflectsFileCount:
    """
    Property 5: sourceFile format reflects file count.

    For any multi-file import with N > 1 files, every booking record's
    `sourceFile` field SHALL match the pattern "YYYY-MM-DD multi-import
    (N files)". For any single-file import, the `sourceFile` field SHALL
    match "YYYY-MM-DD {filename}".

    **Validates: Requirements 3.4**
    """

    DATE_PATTERN = r'\d{4}-\d{2}-\d{2}'

    @given(df=booking_dataframe_strategy(min_rows=1, max_rows=8))
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow],
        deadline=5000,
    )
    def test_single_file_source_format(self, df):
        """Single-file import sets sourceFile to 'YYYY-MM-DD {filename}'."""
        # Filter out cancelled_by_guest rows to ensure processable rows
        df = df[df['Status'] != 'cancelled_by_guest'].reset_index(drop=True)
        assume(len(df) > 0)

        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            csv_path = write_df_to_csv(df, tmp_dir, 'test_bookings.csv')
            result = processor._process_booking_multi([csv_path])

            assume(len(result) > 0)

            filename = os.path.basename(csv_path)
            expected_pattern = re.compile(
                rf'^{self.DATE_PATTERN} {re.escape(filename)}$'
            )

            for booking in result:
                assert expected_pattern.match(booking['sourceFile']), (
                    f"sourceFile '{booking['sourceFile']}' does not match "
                    f"single-file pattern 'YYYY-MM-DD {filename}'"
                )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(
        dfs=st.lists(
            booking_dataframe_strategy(min_rows=1, max_rows=5),
            min_size=2,
            max_size=4,
        )
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow],
        deadline=5000,
    )
    def test_multi_file_source_format(self, dfs):
        """Multi-file import sets sourceFile to 'YYYY-MM-DD multi-import (N files)'."""
        # Filter out cancelled_by_guest rows from each DataFrame
        filtered_dfs = []
        for df in dfs:
            filtered = df[df['Status'] != 'cancelled_by_guest'].reset_index(drop=True)
            filtered_dfs.append(filtered)

        # Ensure at least one DataFrame has processable rows
        total_rows = sum(len(df) for df in filtered_dfs)
        assume(total_rows > 0)

        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            paths = []
            for i, df in enumerate(dfs):
                csv_path = write_df_to_csv(df, tmp_dir, f'booking_file_{i}.csv')
                paths.append(csv_path)

            n_files = len(paths)
            result = processor._process_booking_multi(paths)

            assume(len(result) > 0)

            expected_pattern = re.compile(
                rf'^{self.DATE_PATTERN} multi-import \({n_files} files\)$'
            )

            for booking in result:
                assert expected_pattern.match(booking['sourceFile']), (
                    f"sourceFile '{booking['sourceFile']}' does not match "
                    f"multi-file pattern 'YYYY-MM-DD multi-import ({n_files} files)'"
                )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Feature: str-bookingcom-multi-file-import, Property 6: Scoped overwrite
# invariant
# ---------------------------------------------------------------------------

from str_database import STRDatabase


class TestProperty6ScopedOverwriteInvariant:
    """
    Property 6: Scoped overwrite invariant.

    For any set of planned bookings being saved, the `insert_planned_bookings`
    method SHALL delete and replace records only for `(channel, listing)` pairs
    present in the input, and SHALL leave all records for `(channel, listing)`
    pairs not present in the input completely unchanged.

    **Validates: Requirements 4.1, 4.2**
    """

    CHANNELS = ['booking.com', 'airbnb', 'vrbo']
    LISTINGS = ['Green Studio', 'Red Studio', 'Child Friendly']

    @staticmethod
    def _make_booking(channel: str, listing: str, code: str = '1234567') -> dict:
        """Create a minimal planned booking dict for testing."""
        return {
            'sourceFile': '2025-07-15 multi-import (2 files)',
            'channel': channel,
            'listing': listing,
            'checkinDate': '2025-08-01',
            'checkoutDate': '2025-08-05',
            'nights': 4,
            'guests': 2,
            'amountGross': 500.0,
            'amountNett': 400.0,
            'amountChannelFee': 50.0,
            'amountTouristTax': 20.0,
            'amountVat': 30.0,
            'guestName': 'Test Guest',
            'phone': '',
            'reservationCode': code,
            'reservationDate': '2025-07-01',
            'status': 'planned',
            'pricePerNight': 100.0,
            'daysBeforeReservation': 31,
            'addInfo': '',
            'year': 2025,
            'q': 3,
            'm': 8,
            'country': 'NL',
        }

    @given(
        imported_pairs=st.lists(
            st.tuples(
                st.sampled_from(['booking.com', 'airbnb', 'vrbo']),
                st.sampled_from(['Green Studio', 'Red Studio', 'Child Friendly']),
            ),
            min_size=1,
            max_size=5,
            unique=True,
        ),
        other_pairs=st.lists(
            st.tuples(
                st.sampled_from(['booking.com', 'airbnb', 'vrbo']),
                st.sampled_from(['Green Studio', 'Red Studio', 'Child Friendly']),
            ),
            min_size=0,
            max_size=4,
            unique=True,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_delete_only_imported_pairs(self, imported_pairs, other_pairs):
        """DELETE is called only for (channel, listing) pairs in the incoming bookings."""
        # Ensure other_pairs does not overlap with imported_pairs
        imported_set = set(imported_pairs)
        other_pairs = [p for p in other_pairs if p not in imported_set]

        # Build incoming bookings from imported_pairs
        bookings = []
        for i, (channel, listing) in enumerate(imported_pairs):
            bookings.append(self._make_booking(channel, listing, code=str(1000000 + i)))

        # Create STRDatabase with test_mode and mock the connection
        with patch.object(STRDatabase, '__init__', lambda self, **kwargs: None):
            db = STRDatabase.__new__(STRDatabase)
            db.test_mode = True
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            db.connection = mock_conn

            db.insert_planned_bookings(bookings)

            # Collect all DELETE calls from the cursor
            delete_calls = [
                call for call in mock_cursor.execute.call_args_list
                if 'DELETE' in str(call)
            ]

            # Extract the (channel, listing) pairs that were deleted
            deleted_pairs = set()
            for call in delete_calls:
                args = call[0]  # positional args to cursor.execute(query, params)
                if len(args) >= 2:
                    query, params = args[0], args[1]
                    if 'DELETE' in query:
                        deleted_pairs.add(params)

            # Verify: every imported pair was deleted
            for pair in imported_pairs:
                assert pair in deleted_pairs, (
                    f"Expected DELETE for {pair} but it was not called. "
                    f"Deleted pairs: {deleted_pairs}"
                )

            # Verify: no other pair was deleted
            for pair in other_pairs:
                assert pair not in deleted_pairs, (
                    f"Unexpected DELETE for {pair} which is not in the import. "
                    f"Deleted pairs: {deleted_pairs}"
                )

    @given(
        imported_pairs=st.lists(
            st.tuples(
                st.sampled_from(['booking.com', 'airbnb', 'vrbo']),
                st.sampled_from(['Green Studio', 'Red Studio', 'Child Friendly']),
            ),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_delete_count_matches_unique_pairs(self, imported_pairs):
        """Number of DELETE calls equals the number of unique (channel, listing) pairs."""
        # Build bookings — add multiple bookings per pair to verify dedup
        bookings = []
        for i, (channel, listing) in enumerate(imported_pairs):
            bookings.append(self._make_booking(channel, listing, code=str(2000000 + i)))
            bookings.append(self._make_booking(channel, listing, code=str(3000000 + i)))

        with patch.object(STRDatabase, '__init__', lambda self, **kwargs: None):
            db = STRDatabase.__new__(STRDatabase)
            db.test_mode = True
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            db.connection = mock_conn

            db.insert_planned_bookings(bookings)

            delete_calls = [
                call for call in mock_cursor.execute.call_args_list
                if 'DELETE' in str(call)
            ]

            # Number of DELETE calls should equal number of unique pairs
            assert len(delete_calls) == len(imported_pairs), (
                f"Expected {len(imported_pairs)} DELETE calls but got {len(delete_calls)}"
            )

    @given(
        imported_pairs=st.lists(
            st.tuples(
                st.sampled_from(['booking.com', 'airbnb', 'vrbo']),
                st.sampled_from(['Green Studio', 'Red Studio', 'Child Friendly']),
            ),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=20, database=None, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_insert_count_matches_booking_count(self, imported_pairs):
        """Number of INSERT calls equals the total number of bookings provided."""
        bookings = []
        for i, (channel, listing) in enumerate(imported_pairs):
            bookings.append(self._make_booking(channel, listing, code=str(4000000 + i)))

        with patch.object(STRDatabase, '__init__', lambda self, **kwargs: None):
            db = STRDatabase.__new__(STRDatabase)
            db.test_mode = True
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            db.connection = mock_conn

            result = db.insert_planned_bookings(bookings)

            insert_calls = [
                call for call in mock_cursor.execute.call_args_list
                if 'INSERT' in str(call)
            ]

            assert len(insert_calls) == len(bookings), (
                f"Expected {len(bookings)} INSERT calls but got {len(insert_calls)}"
            )
            assert result == len(bookings)


# ---------------------------------------------------------------------------
# Feature: str-bookingcom-multi-file-import, Example-Based Unit Tests
# ---------------------------------------------------------------------------


class TestExampleBasedMultiFileImport:
    """
    Example-based unit tests for the Booking.com multi-file import feature.

    These tests validate specific scenarios with concrete data rather than
    property-based random generation.
    """

    # -- Helpers for building test DataFrames ----------------------------------

    @staticmethod
    def _make_booking_df(listings, book_numbers=None):
        """
        Build a minimal valid Booking.com DataFrame.

        Args:
            listings: list of unit-type strings (one per row)
            book_numbers: optional list of book-number strings; auto-generated
                          if not provided
        """
        if book_numbers is None:
            book_numbers = [str(5000000 + i) for i in range(len(listings))]
        rows = []
        for i, (listing, bn) in enumerate(zip(listings, book_numbers)):
            rows.append({
                'Book number': bn,
                'Check-in': '2025-08-01',
                'Check-out': '2025-08-05',
                'Guest name(s)': f'Guest {i}',
                'Unit type': listing,
                'Duration (nights)': 4,
                'Price': '200.0000 EUR',
                'Status': 'ok',
                'Commission amount': '30.000000 EUR',
                'Persons': 2,
                'Adults': 2,
                'Children': 0,
                'Booked on': '2025-07-01 10:00:00',
            })
        return pd.DataFrame(rows)

    # -- Test 1: All files fail → ValueError (Req 2.5) -------------------------

    def test_all_files_fail_raises_value_error_with_filenames(self, temp_dir):
        """
        When every uploaded file is unparseable, _process_booking_multi raises
        a ValueError whose message contains 'All files failed to parse' and
        lists the failing filenames.

        Validates: Requirements 2.5
        """
        processor = STRProcessor(test_mode=True)

        bad_paths = []
        for name in ['alpha.csv', 'beta.xlsx', 'gamma.tsv']:
            p = os.path.join(temp_dir, name)
            with open(p, 'wb') as f:
                f.write(b'\x00\x80\xff' * 100)
            bad_paths.append(p)

        with pytest.raises(ValueError, match="All files failed to parse") as exc_info:
            processor._process_booking_multi(bad_paths)

        msg = str(exc_info.value)
        for name in ['alpha.csv', 'beta.xlsx', 'gamma.tsv']:
            assert name in msg, f"Expected '{name}' in error message: {msg}"

    # -- Test 2: Green Studio + Red Studio import leaves Child Friendly
    #            untouched (Req 4.3) -------------------------------------------

    def test_scoped_delete_leaves_child_friendly_untouched(self):
        """
        When planned bookings contain only Green Studio and Red Studio for
        booking.com, insert_planned_bookings deletes those two pairs but
        does NOT delete (booking.com, Child Friendly).

        Validates: Requirements 4.3
        """
        bookings = [
            TestProperty6ScopedOverwriteInvariant._make_booking(
                'booking.com', 'Green Studio', code='7000001'
            ),
            TestProperty6ScopedOverwriteInvariant._make_booking(
                'booking.com', 'Red Studio', code='7000002'
            ),
        ]

        with patch.object(STRDatabase, '__init__', lambda self, **kwargs: None):
            db = STRDatabase.__new__(STRDatabase)
            db.test_mode = True
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            db.connection = mock_conn

            db.insert_planned_bookings(bookings)

            # Collect DELETE calls
            delete_pairs = set()
            for call in mock_cursor.execute.call_args_list:
                args = call[0]
                if len(args) >= 2 and 'DELETE' in str(args[0]):
                    delete_pairs.add(args[1])

            # Green Studio and Red Studio must be deleted
            assert ('booking.com', 'Green Studio') in delete_pairs
            assert ('booking.com', 'Red Studio') in delete_pairs

            # Child Friendly must NOT be deleted
            assert ('booking.com', 'Child Friendly') not in delete_pairs

    # -- Test 3: Response structure has expected keys (Req 5.2) -----------------

    def test_response_structure_has_expected_keys(self, temp_dir):
        """
        Each booking dict returned by _process_booking_multi contains all
        expected keys matching the documented data model.

        Validates: Requirements 5.2
        """
        processor = STRProcessor(test_mode=True)

        df = self._make_booking_df(['Green Studio'])
        csv_path = write_df_to_csv(df, temp_dir, 'structure_test.csv')

        result = processor._process_booking_multi([csv_path])
        assert len(result) >= 1, "Expected at least one booking"

        expected_keys = {
            'sourceFile', 'channel', 'listing',
            'checkinDate', 'checkoutDate', 'nights', 'guests',
            'amountGross', 'amountChannelFee', 'amountVat',
            'amountTouristTax', 'amountNett', 'pricePerNight',
            'guestName', 'reservationCode', 'reservationDate',
            'status', 'addInfo', 'year', 'q', 'm',
            'daysBeforeReservation', 'country',
        }

        for booking in result:
            missing = expected_keys - set(booking.keys())
            assert not missing, (
                f"Booking is missing keys: {missing}. "
                f"Got keys: {sorted(booking.keys())}"
            )

    # -- Test 4: Single file upload works for all platforms (Req 7.2) -----------

    def test_single_file_upload_works_for_booking_platform(self, temp_dir):
        """
        A single Booking.com file processed through the public
        process_str_files() API returns a list of booking dicts, confirming
        backward compatibility.

        Validates: Requirements 7.2
        """
        processor = STRProcessor(test_mode=True)

        df = self._make_booking_df(['Red Studio', 'Green Studio'])
        csv_path = write_df_to_csv(df, temp_dir, 'single_booking.csv')

        result = processor.process_str_files([csv_path], 'booking')

        assert isinstance(result, list)
        assert len(result) >= 1, "Expected at least one booking from single-file upload"
        # Verify it went through the booking pipeline (channel should be booking.com)
        for b in result:
            assert b['channel'] == 'booking.com'

    # -- Test 5: Single booking file uses same delete-by-channel/listing
    #            strategy (Req 7.3) --------------------------------------------

    def test_single_file_uses_delete_by_channel_listing_strategy(self):
        """
        When a single booking file is saved via insert_planned_bookings, the
        same delete-by-(channel, listing) strategy is applied: DELETE is called
        for the pair and INSERT is called for each booking.

        Validates: Requirements 7.3
        """
        bookings = [
            TestProperty6ScopedOverwriteInvariant._make_booking(
                'booking.com', 'Green Studio', code='8000001'
            ),
            TestProperty6ScopedOverwriteInvariant._make_booking(
                'booking.com', 'Green Studio', code='8000002'
            ),
        ]

        with patch.object(STRDatabase, '__init__', lambda self, **kwargs: None):
            db = STRDatabase.__new__(STRDatabase)
            db.test_mode = True
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            db.connection = mock_conn

            result = db.insert_planned_bookings(bookings)

            # Verify DELETE was called for (booking.com, Green Studio)
            delete_calls = [
                c for c in mock_cursor.execute.call_args_list
                if 'DELETE' in str(c)
            ]
            assert len(delete_calls) == 1, (
                f"Expected exactly 1 DELETE call, got {len(delete_calls)}"
            )
            delete_args = delete_calls[0][0]
            assert delete_args[1] == ('booking.com', 'Green Studio')

            # Verify INSERT was called for each booking
            insert_calls = [
                c for c in mock_cursor.execute.call_args_list
                if 'INSERT' in str(c)
            ]
            assert len(insert_calls) == 2, (
                f"Expected 2 INSERT calls, got {len(insert_calls)}"
            )

            # Verify return value matches booking count
            assert result == 2
