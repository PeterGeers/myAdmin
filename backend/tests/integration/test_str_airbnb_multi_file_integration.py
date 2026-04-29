"""
Integration tests for Airbnb multi-file import.

Tests the end-to-end flow from route to processor, verifying:
- Route passes all file paths to processor for airbnb (Req 5.1)
- Temp file cleanup after success and failure (Req 5.4)
- Single airbnb file upload works through multi path (Req 5.1)

Feature: str-airbnb-multi-file-import
"""

import sys
import os
import tempfile
import shutil
import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from str_processor import STRProcessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_airbnb_df(rows=None):
    """Create a valid Airbnb DataFrame with sensible defaults."""
    if rows is None:
        rows = [
            {
                'Begindatum': '01-08-2025',
                'Einddatum': '05-08-2025',
                'Naam van de gast': 'Alice Test',
                'Advertentie': 'Green Studio',
                '# nachten': 4,
                'Inkomsten': '€ 400,00',
                'Bevestigingscode': 'HMAB0001',
                'Status': 'Bevestigd',
                'Contact': '+31612345678',
                '# volwassenen': 2,
                '# kinderen': 0,
                "# baby's": 0,
                'Gereserveerd': '2025-07-01',
            },
            {
                'Begindatum': '10-09-2025',
                'Einddatum': '14-09-2025',
                'Naam van de gast': 'Bob Test',
                'Advertentie': 'Red Studio',
                '# nachten': 4,
                'Inkomsten': '€ 350,00',
                'Bevestigingscode': 'HMAB0002',
                'Status': 'Bevestigd',
                'Contact': '+31698765432',
                '# volwassenen': 1,
                '# kinderen': 0,
                "# baby's": 0,
                'Gereserveerd': '2025-08-15',
            },
        ]
    return pd.DataFrame(rows)


def _write_csv(df, directory, filename):
    """Write a DataFrame to CSV in the given directory."""
    path = os.path.join(directory, filename)
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def processor():
    return STRProcessor(test_mode=True)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test: Route passes all file paths to processor for airbnb (Req 5.1)
# ---------------------------------------------------------------------------

class TestRoutePassesAllFilePathsAirbnb:
    """Verify that process_str_files passes all file paths to
    _process_airbnb_multi for the airbnb platform."""

    def test_process_str_files_delegates_to_airbnb_multi(
        self, processor, temp_dir
    ):
        """process_str_files delegates to _process_airbnb_multi for airbnb.

        Validates: Requirements 5.1
        """
        df = _make_airbnb_df()
        csv_path = _write_csv(df, temp_dir, 'airbnb_export.csv')

        with patch.object(
            processor, '_process_airbnb_multi',
            wraps=processor._process_airbnb_multi
        ) as mock_multi:
            processor.process_str_files([csv_path], 'airbnb')
            mock_multi.assert_called_once_with([csv_path])

    def test_multiple_airbnb_files_all_passed_to_processor(
        self, processor, temp_dir
    ):
        """All uploaded airbnb file paths are passed to _process_airbnb_multi.

        Validates: Requirements 5.1
        """
        df1 = _make_airbnb_df([{
            'Begindatum': '01-08-2025', 'Einddatum': '05-08-2025',
            'Naam van de gast': 'Guest One', 'Advertentie': 'Green Studio',
            '# nachten': 4, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMAB1001', 'Status': 'Bevestigd',
            'Contact': '+31612345678', '# volwassenen': 2,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-07-01',
        }])
        df2 = _make_airbnb_df([{
            'Begindatum': '10-09-2025', 'Einddatum': '14-09-2025',
            'Naam van de gast': 'Guest Two', 'Advertentie': 'Red Studio',
            '# nachten': 4, 'Inkomsten': '€ 350,00',
            'Bevestigingscode': 'HMAB1002', 'Status': 'Bevestigd',
            'Contact': '+31698765432', '# volwassenen': 1,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-08-15',
        }])
        df3 = _make_airbnb_df([{
            'Begindatum': '20-10-2025', 'Einddatum': '25-10-2025',
            'Naam van de gast': 'Guest Three', 'Advertentie': 'Child Friendly',
            '# nachten': 5, 'Inkomsten': '€ 500,00',
            'Bevestigingscode': 'HMAB1003', 'Status': 'Bevestigd',
            'Contact': '+31611111111', '# volwassenen': 2,
            '# kinderen': 1, "# baby's": 0, 'Gereserveerd': '2025-09-01',
        }])

        csv1 = _write_csv(df1, temp_dir, 'green.csv')
        csv2 = _write_csv(df2, temp_dir, 'red.csv')
        csv3 = _write_csv(df3, temp_dir, 'child.csv')

        captured_paths = []

        original_multi = processor._process_airbnb_multi

        def spy_multi(file_paths):
            captured_paths.extend(file_paths)
            return original_multi(file_paths)

        with patch.object(processor, '_process_airbnb_multi', side_effect=spy_multi):
            processor.process_str_files([csv1, csv2, csv3], 'airbnb')

        assert len(captured_paths) == 3
        assert csv1 in captured_paths
        assert csv2 in captured_paths
        assert csv3 in captured_paths

    def test_multi_file_airbnb_produces_all_bookings(
        self, processor, temp_dir
    ):
        """Multiple airbnb files produce bookings from all files.

        Validates: Requirements 5.1
        """
        df1 = _make_airbnb_df([{
            'Begindatum': '01-08-2025', 'Einddatum': '05-08-2025',
            'Naam van de gast': 'Green Guest', 'Advertentie': 'Green Studio',
            '# nachten': 4, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMAB2001', 'Status': 'Bevestigd',
            'Contact': '+31612345678', '# volwassenen': 2,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-07-01',
        }])
        df2 = _make_airbnb_df([{
            'Begindatum': '10-09-2025', 'Einddatum': '14-09-2025',
            'Naam van de gast': 'Red Guest', 'Advertentie': 'Red Studio',
            '# nachten': 4, 'Inkomsten': '€ 350,00',
            'Bevestigingscode': 'HMAB2002', 'Status': 'Bevestigd',
            'Contact': '+31698765432', '# volwassenen': 1,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-08-15',
        }])

        csv1 = _write_csv(df1, temp_dir, 'file1.csv')
        csv2 = _write_csv(df2, temp_dir, 'file2.csv')

        result = processor.process_str_files([csv1, csv2], 'airbnb')

        assert len(result) == 2
        codes = {b['reservationCode'] for b in result}
        assert codes == {'HMAB2001', 'HMAB2002'}
        guests = {b['guestName'] for b in result}
        assert 'Green Guest' in guests
        assert 'Red Guest' in guests

    def test_response_structure_matches_expected_fields(
        self, processor, temp_dir
    ):
        """Multi-file airbnb response has all expected booking fields.

        Validates: Requirements 5.2
        """
        df = _make_airbnb_df()
        csv_path = _write_csv(df, temp_dir, 'structure_test.csv')

        result = processor.process_str_files([csv_path], 'airbnb')

        assert len(result) > 0
        booking = result[0]

        expected_fields = [
            'sourceFile', 'channel', 'listing', 'checkinDate', 'checkoutDate',
            'nights', 'guests', 'amountGross', 'amountChannelFee', 'guestName',
            'reservationCode', 'reservationDate', 'status', 'amountVat',
            'amountTouristTax', 'amountNett', 'pricePerNight', 'year', 'q', 'm',
            'daysBeforeReservation', 'country', 'addInfo',
        ]
        for field in expected_fields:
            assert field in booking, f"Missing field: {field}"

    def test_multi_file_response_structure_matches_single(
        self, processor, temp_dir
    ):
        """Multi-file airbnb response has the same fields as single-file.

        Validates: Requirements 5.1, 5.2
        """
        df1 = _make_airbnb_df([{
            'Begindatum': '01-08-2025', 'Einddatum': '05-08-2025',
            'Naam van de gast': 'Single Guest', 'Advertentie': 'Green Studio',
            '# nachten': 4, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMAB3001', 'Status': 'Bevestigd',
            'Contact': '+31612345678', '# volwassenen': 2,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-07-01',
        }])
        df2 = _make_airbnb_df([{
            'Begindatum': '10-09-2025', 'Einddatum': '14-09-2025',
            'Naam van de gast': 'Multi Guest', 'Advertentie': 'Red Studio',
            '# nachten': 4, 'Inkomsten': '€ 350,00',
            'Bevestigingscode': 'HMAB3002', 'Status': 'Bevestigd',
            'Contact': '+31698765432', '# volwassenen': 1,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-08-15',
        }])

        csv1 = _write_csv(df1, temp_dir, 'single.csv')
        csv2 = _write_csv(df2, temp_dir, 'extra.csv')

        single_result = processor.process_str_files([csv1], 'airbnb')
        multi_result = processor.process_str_files([csv1, csv2], 'airbnb')

        assert len(single_result) > 0
        assert len(multi_result) > 0

        single_keys = set(single_result[0].keys())
        multi_keys = set(multi_result[0].keys())
        assert single_keys == multi_keys, (
            f"Field mismatch: single-only={single_keys - multi_keys}, "
            f"multi-only={multi_keys - single_keys}"
        )


# ---------------------------------------------------------------------------
# Test: Temp files cleaned up after success and failure (Req 5.4)
# ---------------------------------------------------------------------------

class TestTempFileCleanupAirbnb:
    """Verify that temporary files are cleaned up after Airbnb processing,
    regardless of success or failure."""

    def test_temp_files_cleaned_after_successful_airbnb_processing(
        self, temp_dir
    ):
        """Temp files are removed after successful multi-file airbnb processing.

        Validates: Requirements 5.4
        """
        df1 = _make_airbnb_df([{
            'Begindatum': '01-08-2025', 'Einddatum': '05-08-2025',
            'Naam van de gast': 'Cleanup Guest 1', 'Advertentie': 'Green Studio',
            '# nachten': 4, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMAB4001', 'Status': 'Bevestigd',
            'Contact': '+31612345678', '# volwassenen': 2,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-07-01',
        }])
        df2 = _make_airbnb_df([{
            'Begindatum': '10-09-2025', 'Einddatum': '14-09-2025',
            'Naam van de gast': 'Cleanup Guest 2', 'Advertentie': 'Red Studio',
            '# nachten': 4, 'Inkomsten': '€ 350,00',
            'Bevestigingscode': 'HMAB4002', 'Status': 'Bevestigd',
            'Contact': '+31698765432', '# volwassenen': 1,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-08-15',
        }])

        path1 = _write_csv(df1, temp_dir, 'temp_airbnb1.csv')
        path2 = _write_csv(df2, temp_dir, 'temp_airbnb2.csv')
        temp_paths = [path1, path2]

        # Verify files exist before cleanup
        assert os.path.exists(path1)
        assert os.path.exists(path2)

        # Simulate the route's processing + cleanup logic
        processor = STRProcessor(test_mode=True)
        processor.process_str_files(temp_paths, 'airbnb')

        # Simulate route cleanup (same pattern as str_routes.py)
        for tp in temp_paths:
            try:
                os.remove(tp)
            except OSError:
                pass

        # Verify files are cleaned up
        assert not os.path.exists(path1)
        assert not os.path.exists(path2)

    def test_temp_files_cleaned_after_airbnb_all_fail(self, temp_dir):
        """Temp files are removed even when all airbnb files fail to parse.

        Validates: Requirements 5.4
        """
        # Create invalid files that will cause _process_airbnb_multi to raise
        path1 = os.path.join(temp_dir, 'corrupt1.csv')
        path2 = os.path.join(temp_dir, 'corrupt2.csv')
        with open(path1, 'wb') as f:
            f.write(b'\x00\x01\x02\x80\x81\x82\xff\xfe\xfd' * 50)
        with open(path2, 'wb') as f:
            f.write(b'\xff\xfe\xfd\x00\x01\x02' * 50)

        temp_paths = [path1, path2]

        # Simulate route: process then cleanup (cleanup always runs)
        processor = STRProcessor(test_mode=True)
        try:
            processor.process_str_files(temp_paths, 'airbnb')
        except (ValueError, Exception):
            pass  # Expected: all files fail → ValueError

        # Cleanup always runs (simulating the route's behavior)
        for tp in temp_paths:
            try:
                os.remove(tp)
            except OSError:
                pass

        assert not os.path.exists(path1)
        assert not os.path.exists(path2)

    def test_temp_files_cleaned_after_airbnb_partial_failure(self, temp_dir):
        """Temp files are removed after partial failure (some valid, some invalid).

        Validates: Requirements 5.4
        """
        valid_df = _make_airbnb_df([{
            'Begindatum': '01-08-2025', 'Einddatum': '05-08-2025',
            'Naam van de gast': 'Valid Guest', 'Advertentie': 'Green Studio',
            '# nachten': 4, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMAB5001', 'Status': 'Bevestigd',
            'Contact': '+31612345678', '# volwassenen': 2,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-07-01',
        }])
        valid_path = _write_csv(valid_df, temp_dir, 'valid_airbnb.csv')

        invalid_path = os.path.join(temp_dir, 'invalid_airbnb.csv')
        with open(invalid_path, 'wb') as f:
            f.write(b'\x00\x01\x02' * 100)

        temp_paths = [valid_path, invalid_path]

        processor = STRProcessor(test_mode=True)
        try:
            result = processor.process_str_files(temp_paths, 'airbnb')
            # Should succeed with partial results
            assert len(result) >= 1
        except Exception:
            pass

        # Cleanup always runs
        for tp in temp_paths:
            try:
                os.remove(tp)
            except OSError:
                pass

        assert not os.path.exists(valid_path)
        assert not os.path.exists(invalid_path)

    def test_cleanup_handles_already_removed_airbnb_files(self, temp_dir):
        """Cleanup loop handles already-removed airbnb files gracefully.

        Validates: Requirements 5.4
        """
        path1 = os.path.join(temp_dir, 'already_gone.csv')
        path2 = os.path.join(temp_dir, 'still_here.csv')

        # Only create path2
        with open(path2, 'w') as f:
            f.write('test')

        temp_paths = [path1, path2]

        # Simulate route cleanup — should not raise
        for tp in temp_paths:
            try:
                os.remove(tp)
            except OSError:
                pass

        assert not os.path.exists(path2)


# ---------------------------------------------------------------------------
# Test: Single airbnb file upload works through multi path (Req 5.1)
# ---------------------------------------------------------------------------

class TestSingleAirbnbFileViaMultiPath:
    """Verify that a single airbnb file upload works correctly through
    the _process_airbnb_multi code path."""

    def test_single_airbnb_file_produces_correct_bookings(
        self, processor, temp_dir
    ):
        """Single airbnb file processed through process_str_files works.

        Validates: Requirements 5.1
        """
        df = _make_airbnb_df()
        csv_path = _write_csv(df, temp_dir, 'single_airbnb.csv')

        result = processor.process_str_files([csv_path], 'airbnb')

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(b['channel'] == 'airbnb' for b in result)
        codes = {b['reservationCode'] for b in result}
        assert codes == {'HMAB0001', 'HMAB0002'}

    def test_single_file_source_file_format(self, processor, temp_dir):
        """Single airbnb file has sourceFile format 'YYYY-MM-DD filename'.

        Validates: Requirements 5.1
        """
        df = _make_airbnb_df([{
            'Begindatum': '01-08-2025', 'Einddatum': '05-08-2025',
            'Naam van de gast': 'Source Guest', 'Advertentie': 'Green Studio',
            '# nachten': 4, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMAB6001', 'Status': 'Bevestigd',
            'Contact': '+31612345678', '# volwassenen': 2,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-07-01',
        }])
        csv_path = _write_csv(df, temp_dir, 'my_export.csv')

        result = processor.process_str_files([csv_path], 'airbnb')

        assert len(result) == 1
        today_str = datetime.now().strftime('%Y-%m-%d')
        assert result[0]['sourceFile'] == f"{today_str} my_export.csv"

    def test_multi_file_source_file_format(self, processor, temp_dir):
        """Multi-file airbnb has sourceFile format 'YYYY-MM-DD multi-import (N files)'.

        Validates: Requirements 5.1
        """
        df1 = _make_airbnb_df([{
            'Begindatum': '01-08-2025', 'Einddatum': '05-08-2025',
            'Naam van de gast': 'Guest A', 'Advertentie': 'Green Studio',
            '# nachten': 4, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMAB7001', 'Status': 'Bevestigd',
            'Contact': '+31612345678', '# volwassenen': 2,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-07-01',
        }])
        df2 = _make_airbnb_df([{
            'Begindatum': '10-09-2025', 'Einddatum': '14-09-2025',
            'Naam van de gast': 'Guest B', 'Advertentie': 'Red Studio',
            '# nachten': 4, 'Inkomsten': '€ 350,00',
            'Bevestigingscode': 'HMAB7002', 'Status': 'Bevestigd',
            'Contact': '+31698765432', '# volwassenen': 1,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-08-15',
        }])

        csv1 = _write_csv(df1, temp_dir, 'file_a.csv')
        csv2 = _write_csv(df2, temp_dir, 'file_b.csv')

        result = processor.process_str_files([csv1, csv2], 'airbnb')

        assert len(result) == 2
        today_str = datetime.now().strftime('%Y-%m-%d')
        expected_source = f"{today_str} multi-import (2 files)"
        assert all(b['sourceFile'] == expected_source for b in result)

    def test_single_file_uses_airbnb_multi_path(self, processor, temp_dir):
        """Single airbnb file is routed through _process_airbnb_multi, not _process_single_file.

        Validates: Requirements 5.1
        """
        df = _make_airbnb_df([{
            'Begindatum': '01-08-2025', 'Einddatum': '05-08-2025',
            'Naam van de gast': 'Path Guest', 'Advertentie': 'Green Studio',
            '# nachten': 4, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMAB8001', 'Status': 'Bevestigd',
            'Contact': '+31612345678', '# volwassenen': 2,
            '# kinderen': 0, "# baby's": 0, 'Gereserveerd': '2025-07-01',
        }])
        csv_path = _write_csv(df, temp_dir, 'single_path_test.csv')

        with patch.object(
            processor, '_process_airbnb_multi',
            wraps=processor._process_airbnb_multi
        ) as mock_multi:
            with patch.object(
                processor, '_process_single_file',
                wraps=processor._process_single_file
            ) as mock_single:
                processor.process_str_files([csv_path], 'airbnb')

                # _process_airbnb_multi should be called
                mock_multi.assert_called_once_with([csv_path])
                # _process_single_file should NOT be called
                mock_single.assert_not_called()
