"""
Unit tests for str_airbnb_parser.py and str_booking_parser.py

Tests Airbnb and Booking.com CSV parsing:
- process_airbnb_multi() - Multi-file Airbnb import
- calculate_airbnb_row() - Single Airbnb row calculation
- process_booking() - Single Booking.com file
- process_booking_multi() - Multi-file Booking.com import
- calculate_booking_row() - Single Booking.com row calculation

Task 54 of Phase 7: Missing Test Coverage
"""

import sys
import os
import tempfile
import shutil
import pytest
import pandas as pd
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from str_airbnb_parser import process_airbnb_multi, calculate_airbnb_row
from str_booking_parser import (
    process_booking, process_booking_multi, calculate_booking_row
)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir():
    """Create a temp directory for test CSV files."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def airbnb_csv(temp_dir):
    """Create a sample Airbnb CSV file."""
    df = pd.DataFrame([{
        'Begindatum': '15-06-2025',
        'Einddatum': '18-06-2025',
        'Naam van de gast': 'Jan Janssen',
        'Advertentie': 'Green Studio',
        '# nachten': 3,
        'Inkomsten': '€ 450,00',
        'Bevestigingscode': 'HM12345678',
        'Status': 'Bevestigd',
        'Contact': '+31612345678',
        '# volwassenen': 2,
        '# kinderen': 1,
        "# baby's": 0,
        'Gereserveerd': '2025-05-01',
    }])
    path = os.path.join(temp_dir, 'airbnb_test.csv')
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def booking_csv(temp_dir):
    """Create a sample Booking.com CSV file."""
    df = pd.DataFrame([{
        'Book number': '3456789',
        'Check-in': '2025-07-01',
        'Check-out': '2025-07-04',
        'Guest name(s)': 'Peter Smith',
        'Unit type': 'One-Bedroom Apartment',
        'Duration (nights)': 3,
        'Price': '300.0000 EUR',
        'Status': 'ok',
        'Commission amount': '45.000000 EUR',
        'Persons': 2,
        'Adults': 2,
        'Children': 0,
        'Booked on': '2025-06-01 10:00:00',
    }])
    path = os.path.join(temp_dir, 'booking_test.csv')
    df.to_csv(path, index=False)
    return path


# ── Airbnb Parser Tests ────────────────────────────────────────────────────


class TestCalculateAirbnbRow:

    def test_basic_calculation(self):
        """calculate_airbnb_row processes a valid row."""
        row = pd.Series({
            'Begindatum': '15-06-2025',
            'Einddatum': '18-06-2025',
            'Naam van de gast': 'Test Guest',
            'Advertentie': 'Green Studio',
            '# nachten': 3,
            'Inkomsten': '€ 450,00',
            'Bevestigingscode': 'HM12345678',
            'Status': 'Bevestigd',
            'Contact': '+31612345678',
            '# volwassenen': 2,
            '# kinderen': 0,
            "# baby's": 0,
            'Gereserveerd': '2025-05-01',
        })
        columns = row.index

        result = calculate_airbnb_row(row, columns, '2025-06-28 test.csv')

        assert result is not None
        assert result['channel'] == 'airbnb'
        assert result['listing'] == 'Green Studio'
        assert result['nights'] == 3
        assert result['guests'] == 2
        assert result['reservationCode'] == 'HM12345678'
        assert result['amountGross'] > 0
        assert result['amountChannelFee'] > 0
        assert result['amountVat'] > 0
        assert result['amountNett'] > 0
        assert result['status'] == 'realised'

    def test_cancelled_with_zero_earnings_skipped(self):
        """Cancelled bookings with zero earnings are skipped."""
        row = pd.Series({
            'Begindatum': '15-06-2025',
            'Einddatum': '18-06-2025',
            'Naam van de gast': 'Cancelled Guest',
            'Advertentie': 'Red Studio',
            '# nachten': 3,
            'Inkomsten': '€ 0,00',
            'Bevestigingscode': 'HM99999999',
            'Status': 'Geannuleerd door gast',
            'Contact': '',
            '# volwassenen': 1,
            '# kinderen': 0,
            "# baby's": 0,
            'Gereserveerd': '2025-05-01',
        })
        result = calculate_airbnb_row(row, row.index, 'test.csv')
        assert result is None

    def test_future_booking_is_planned(self):
        """Future check-in date sets status to 'planned'."""
        future_date = (date.today() + timedelta(days=30)).strftime('%d-%m-%Y')
        future_checkout = (date.today() + timedelta(days=33)).strftime('%d-%m-%Y')
        row = pd.Series({
            'Begindatum': future_date,
            'Einddatum': future_checkout,
            'Naam van de gast': 'Future Guest',
            'Advertentie': 'Green Studio',
            '# nachten': 3,
            'Inkomsten': '€ 300,00',
            'Bevestigingscode': 'HM11111111',
            'Status': 'Bevestigd',
            'Contact': '+49123456789',
            '# volwassenen': 2,
            '# kinderen': 0,
            "# baby's": 0,
            'Gereserveerd': '2025-06-01',
        })
        result = calculate_airbnb_row(row, row.index, 'test.csv')
        assert result is not None
        assert result['status'] == 'planned'

    def test_european_currency_parsing(self):
        """Parses European currency format '€ 1.841,18'."""
        row = pd.Series({
            'Begindatum': '01-01-2025',
            'Einddatum': '10-01-2025',
            'Naam van de gast': 'Big Spender',
            'Advertentie': 'Child Friendly',
            '# nachten': 9,
            'Inkomsten': '€ 1.841,18',
            'Bevestigingscode': 'HM22222222',
            'Status': 'Bevestigd',
            'Contact': '+31600000000',
            '# volwassenen': 4,
            '# kinderen': 2,
            "# baby's": 1,
            'Gereserveerd': '2024-12-01',
        })
        result = calculate_airbnb_row(row, row.index, 'test.csv')
        assert result is not None
        # €1841.18 + 15% channel fee = ~2117.36 gross
        assert result['amountGross'] > 2000

    def test_listing_normalization(self):
        """Listing names are normalized to standard values."""
        row = pd.Series({
            'Begindatum': '01-03-2025',
            'Einddatum': '03-03-2025',
            'Naam van de gast': 'Test',
            'Advertentie': 'Rode Studio met tuin',
            '# nachten': 2,
            'Inkomsten': '€ 200,00',
            'Bevestigingscode': 'HM33333333',
            'Status': 'Bevestigd',
            'Contact': '',
            '# volwassenen': 1,
            '# kinderen': 0,
            "# baby's": 0,
            'Gereserveerd': '2025-02-01',
        })
        result = calculate_airbnb_row(row, row.index, 'test.csv')
        assert result is not None
        assert result['listing'] == 'Red Studio'


class TestProcessAirbnbMulti:

    def test_single_file_success(self, airbnb_csv):
        """process_airbnb_multi processes a single valid file."""
        result = process_airbnb_multi([airbnb_csv])
        assert len(result) == 1
        assert result[0]['channel'] == 'airbnb'
        assert result[0]['reservationCode'] == 'HM12345678'

    def test_deduplication(self, temp_dir):
        """process_airbnb_multi deduplicates by Bevestigingscode."""
        row = {
            'Begindatum': '15-06-2025', 'Einddatum': '18-06-2025',
            'Naam van de gast': 'Jan', 'Advertentie': 'Green Studio',
            '# nachten': 3, 'Inkomsten': '€ 400,00',
            'Bevestigingscode': 'HMDUPLICATE', 'Status': 'Bevestigd',
            'Contact': '', '# volwassenen': 1, '# kinderen': 0,
            "# baby's": 0, 'Gereserveerd': '2025-05-01',
        }
        df1 = pd.DataFrame([row])
        df2 = pd.DataFrame([row])
        path1 = os.path.join(temp_dir, 'file1.csv')
        path2 = os.path.join(temp_dir, 'file2.csv')
        df1.to_csv(path1, index=False)
        df2.to_csv(path2, index=False)

        result = process_airbnb_multi([path1, path2])
        assert len(result) == 1  # Deduplicated

    def test_all_files_fail_raises(self, temp_dir):
        """process_airbnb_multi raises ValueError if all files fail."""
        bad_path = os.path.join(temp_dir, 'nonexistent.csv')
        with pytest.raises(ValueError, match='All files failed'):
            process_airbnb_multi([bad_path])


# ── Booking.com Parser Tests ───────────────────────────────────────────────


class TestCalculateBookingRow:

    def test_basic_calculation(self):
        """calculate_booking_row processes a valid Booking.com row."""
        row = pd.Series({
            'Check-in': '2025-07-01',
            'Check-out': '2025-07-04',
            'Guest name(s)': 'Peter Smith',
            'Unit type': 'One-Bedroom Apartment',
            'Duration (nights)': 3,
            'Price': '300.0000 EUR',
            'Book number': '3456789',
            'Status': 'ok',
            'Commission amount': '45.000000 EUR',
            'Persons': 2,
            'Adults': 2,
            'Children': 0,
            'Booked on': '2025-06-01 10:00:00',
        })
        columns = row.index

        result = calculate_booking_row(row, columns, '2025-06-28 test.csv')

        assert result is not None
        assert result['channel'] == 'booking.com'
        assert result['listing'] == 'Green Studio'  # One-Bedroom → Green Studio
        assert result['nights'] == 3
        assert result['guests'] == 2
        assert result['reservationCode'] == '3456789'
        assert result['amountGross'] > 0
        assert result['amountChannelFee'] > 0
        assert result['amountVat'] > 0
        assert result['amountNett'] > 0

    def test_cancelled_no_commission_skipped(self):
        """Cancelled bookings with no commission are skipped."""
        row = pd.Series({
            'Check-in': '2025-07-01', 'Check-out': '2025-07-04',
            'Guest name(s)': 'Cancelled',
            'Unit type': 'Apartment', 'Duration (nights)': 3,
            'Price': '0 EUR', 'Book number': '9999999',
            'Status': 'cancelled_by_guest', 'Commission amount': '',
            'Persons': 1, 'Adults': 1, 'Children': 0,
            'Booked on': '2025-06-01 10:00:00',
        })
        result = calculate_booking_row(row, row.index, 'test.csv')
        assert result is None

    def test_eur_price_parsing(self):
        """Parses '126.6314 EUR' price format."""
        row = pd.Series({
            'Check-in': '2025-08-01', 'Check-out': '2025-08-03',
            'Guest name(s)': 'EUR Guest',
            'Unit type': 'Rode Studio', 'Duration (nights)': 2,
            'Price': '126.6314 EUR', 'Book number': '1111111',
            'Status': 'ok', 'Commission amount': '15.195768 EUR',
            'Persons': 2, 'Adults': 2, 'Children': 0,
            'Booked on': '2025-07-15 08:00:00',
        })
        result = calculate_booking_row(row, row.index, 'test.csv')
        assert result is not None
        assert result['amountGross'] > 126  # Should include uplift

    def test_future_booking_is_planned(self):
        """Future check-in date sets status to 'planned'."""
        future = (date.today() + timedelta(days=60)).strftime('%Y-%m-%d')
        future_out = (date.today() + timedelta(days=63)).strftime('%Y-%m-%d')
        row = pd.Series({
            'Check-in': future, 'Check-out': future_out,
            'Guest name(s)': 'Future', 'Unit type': 'Green Studio',
            'Duration (nights)': 3, 'Price': '200.0000 EUR',
            'Book number': '7777777', 'Status': 'ok',
            'Commission amount': '30.000000 EUR',
            'Persons': 1, 'Adults': 1, 'Children': 0,
            'Booked on': '2025-06-01 10:00:00',
        })
        result = calculate_booking_row(row, row.index, 'test.csv')
        assert result is not None
        assert result['status'] == 'planned'

    def test_listing_normalization_red(self):
        """'Rode Studio' normalizes to 'Red Studio'."""
        row = pd.Series({
            'Check-in': '2025-01-01', 'Check-out': '2025-01-03',
            'Guest name(s)': 'Test', 'Unit type': 'Rode Studio',
            'Duration (nights)': 2, 'Price': '150.0000 EUR',
            'Book number': '5555555', 'Status': 'ok',
            'Commission amount': '22.500000 EUR',
            'Persons': 1, 'Adults': 1, 'Children': 0,
            'Booked on': '2024-12-15 10:00:00',
        })
        result = calculate_booking_row(row, row.index, 'test.csv')
        assert result is not None
        assert result['listing'] == 'Red Studio'


class TestProcessBooking:

    def test_single_file_success(self, booking_csv):
        """process_booking processes a single Booking.com CSV."""
        result = process_booking(booking_csv)
        assert len(result) == 1
        assert result[0]['channel'] == 'booking.com'
        assert result[0]['reservationCode'] == '3456789'

    def test_empty_file_returns_empty(self, temp_dir):
        """process_booking returns empty list for empty file."""
        df = pd.DataFrame(columns=['Book number', 'Check-in', 'Price'])
        path = os.path.join(temp_dir, 'empty.csv')
        df.to_csv(path, index=False)
        result = process_booking(path)
        assert result == []

    def test_invalid_file_returns_empty(self, temp_dir):
        """process_booking returns empty list for unreadable file."""
        path = os.path.join(temp_dir, 'bad.csv')
        with open(path, 'w') as f:
            f.write('not,a,valid\ncsv,for,booking')
        result = process_booking(path)
        assert result == []


class TestProcessBookingMulti:

    def test_single_file_success(self, booking_csv):
        """process_booking_multi processes a single file."""
        result = process_booking_multi([booking_csv])
        assert len(result) == 1

    def test_deduplication(self, temp_dir):
        """process_booking_multi deduplicates by Book number."""
        row = {
            'Book number': 'DUPBOOK', 'Check-in': '2025-07-01',
            'Check-out': '2025-07-03', 'Guest name(s)': 'Dup',
            'Unit type': 'Green Studio', 'Duration (nights)': 2,
            'Price': '200.0000 EUR', 'Status': 'ok',
            'Commission amount': '30.000000 EUR',
            'Persons': 1, 'Adults': 1, 'Children': 0,
            'Booked on': '2025-06-01 10:00:00',
        }
        df1 = pd.DataFrame([row])
        df2 = pd.DataFrame([row])
        path1 = os.path.join(temp_dir, 'bdc1.csv')
        path2 = os.path.join(temp_dir, 'bdc2.csv')
        df1.to_csv(path1, index=False)
        df2.to_csv(path2, index=False)

        result = process_booking_multi([path1, path2])
        assert len(result) == 1

    def test_all_files_fail_raises(self, temp_dir):
        """process_booking_multi raises ValueError if all files fail."""
        bad_path = os.path.join(temp_dir, 'nonexistent.csv')
        with pytest.raises(ValueError, match='All files failed'):
            process_booking_multi([bad_path])

    def test_excel_file_support(self, temp_dir):
        """process_booking_multi supports .xlsx files."""
        row = {
            'Book number': '8888888', 'Check-in': '2025-08-01',
            'Check-out': '2025-08-04', 'Guest name(s)': 'Excel Guest',
            'Unit type': 'Red Studio', 'Duration (nights)': 3,
            'Price': '350.0000 EUR', 'Status': 'ok',
            'Commission amount': '52.500000 EUR',
            'Persons': 2, 'Adults': 2, 'Children': 0,
            'Booked on': '2025-07-01 12:00:00',
        }
        df = pd.DataFrame([row])
        path = os.path.join(temp_dir, 'booking.xlsx')
        df.to_excel(path, index=False)

        result = process_booking_multi([path])
        assert len(result) == 1
        assert result[0]['reservationCode'] == '8888888'
