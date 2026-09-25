"""
Unit tests for str_airbnb_parser.py and str_booking_parser.py

Tests Airbnb and Booking.com CSV parsing:
- process_airbnb_multi()      - Multi-file Airbnb import (new export format)
- build_booking_from_group()  - Single-group booking assembly (new export format)
- process_booking()           - Single Booking.com file
- process_booking_multi()     - Multi-file Booking.com import
- calculate_booking_row()     - Single Booking.com row calculation

The Airbnb path was rewritten for the new two-file export format
(airbnb-export-format-update): rows arrive as Boeking/Doorloop-totaal pairs grouped
by Bevestigingscode, amounts are summed per group, status comes from file
classification, and the old single-row `calculate_airbnb_row` was removed.
"""

import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from str_airbnb_parser import (
    build_booking_from_group,
    parse_airbnb_amount,
    process_airbnb_multi,
)
from str_booking_parser import (
    calculate_booking_row,
    process_booking,
    process_booking_multi,
)

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir():
    """Create a temp directory for test CSV files."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _airbnb_row(code, type_, gross, service, *, begin='06/15/2025', end='06/18/2025',
                booked='05/01/2025', nights=3, guest='Jan Janssen',
                listing='Green Studio', info=''):
    """Build one new-format Airbnb export row (dict) for a booking pair member."""
    return {
        'Datum': begin,
        'Type': type_,
        'Bevestigingscode': code,
        'Boekingsdatum': booked,
        'Begindatum': begin,
        'Einddatum': end,
        'Nachten': nights,
        'Gast': guest,
        'Advertentie': listing,
        'Informatie': info,
        'Referentienummer': '',
        'Valuta': 'EUR',
        'Bedrag': gross,
        'Servicekosten': service,
        'Schoonmaakkosten': '0.00',
        'Bruto-inkomsten': gross,
        'Door Airbnb doorbelaste en afgedragen heffingen': '0.00',
        'Inkomstenjaar': 2025,
    }


@pytest.fixture
def airbnb_csv(temp_dir):
    """Create a sample new-format Airbnb (pending) CSV: one Boeking/Doorloop pair."""
    df = pd.DataFrame([
        _airbnb_row('HM12345678', 'Boeking', 360.00, '"54,00"'),
        _airbnb_row('HM12345678', 'Doorloop totaal', 90.00, '0.00'),
    ])
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


class TestBuildBookingFromGroup:
    """build_booking_from_group() assembles one Booking_Dict from a row group.

    The new export presents each booking as a Boeking + Doorloop-totaal pair sharing
    one Bevestigingscode; gross and fee are summed across the group, dates read from
    the first row, and status is passed in (from file classification).
    """

    def test_basic_group_sums_gross_and_fee(self):
        """Gross and channel fee are the sums over the group (Req 3.1, 3.2)."""
        group = pd.DataFrame([
            _airbnb_row('HM12345678', 'Boeking', 360.00, '"54,00"'),
            _airbnb_row('HM12345678', 'Doorloop totaal', 90.00, '0.00'),
        ])

        result = build_booking_from_group(
            'HM12345678', group, '2025-06-28 test.csv', 'realised'
        )

        assert result['channel'] == 'airbnb'
        assert result['listing'] == 'Green Studio'
        assert result['nights'] == 3
        assert result['guests'] == 2          # no guest-count column → default 2 (Req 7.1)
        assert result['phone'] == ''          # no contact column (Req 7.2)
        assert result['reservationCode'] == 'HM12345678'
        assert result['amountGross'] == 450.00   # 360.00 + 90.00
        assert result['amountChannelFee'] == 54.00  # 54,00 + 0.00
        assert result['amountVat'] > 0
        assert result['amountNett'] > 0
        assert result['status'] == 'realised'    # passed by caller (Req 6.3)

    def test_status_is_taken_from_caller_not_dates(self):
        """A future-dated group tagged 'planned' keeps that status (Req 6.5)."""
        future_begin = (date.today() + timedelta(days=30)).strftime('%m/%d/%Y')
        future_end = (date.today() + timedelta(days=33)).strftime('%m/%d/%Y')
        group = pd.DataFrame([
            _airbnb_row('HM11111111', 'Boeking', 300.00, '"45,00"',
                        begin=future_begin, end=future_end),
        ])

        result = build_booking_from_group(
            'HM11111111', group, 'test.csv', 'planned'
        )
        assert result['status'] == 'planned'

    def test_dates_parsed_mmddyyyy_and_periods_derived(self):
        """MM/DD/YYYY dates map to checkin/checkout and derived year/q/m (Req 5)."""
        group = pd.DataFrame([
            _airbnb_row('HM55555555', 'Boeking', 200.00, '"30,00"',
                        begin='09/23/2026', end='09/25/2026', booked='09/04/2026'),
        ])
        result = build_booking_from_group('HM55555555', group, 'test.csv', 'planned')
        assert result['checkinDate'] == '2026-09-23'
        assert result['checkoutDate'] == '2026-09-25'
        assert result['reservationDate'] == '2026-09-04'
        assert result['year'] == 2026
        assert result['q'] == 3
        assert result['m'] == 9

    def test_listing_normalization(self):
        """Listing names normalize to standard values (Req 8.3)."""
        group = pd.DataFrame([
            _airbnb_row('HM33333333', 'Boeking', 200.00, '"30,00"',
                        listing='Rode Studio met tuin'),
        ])
        result = build_booking_from_group('HM33333333', group, 'test.csv', 'planned')
        assert result['listing'] == 'Red Studio'

    def test_european_amount_parsing(self):
        """Quoted European service fee like "1.841,18" parses correctly (Req 4.2)."""
        assert parse_airbnb_amount('"1.841,18"') == 1841.18


class TestProcessAirbnbMulti:

    def test_single_file_success(self, airbnb_csv):
        """A single new-format file yields one booking per confirmation code."""
        result = process_airbnb_multi([airbnb_csv], status='planned')
        assert len(result) == 1
        assert result[0]['channel'] == 'airbnb'
        assert result[0]['reservationCode'] == 'HM12345678'
        assert result[0]['status'] == 'planned'
        assert result[0]['amountGross'] == 450.00      # 360.00 + 90.00 summed
        assert result[0]['amountChannelFee'] == 54.00

    def test_payout_rows_excluded_from_grouping(self, temp_dir):
        """Payout rows (blank Bevestigingscode) never produce a booking (Req 2.3)."""
        payout = _airbnb_row('', 'Payout', '', '',
                             info='Transfer naar Example BV')
        df = pd.DataFrame([
            payout,
            _airbnb_row('HMREAL0001', 'Boeking', 360.00, '"54,00"'),
            _airbnb_row('HMREAL0001', 'Doorloop totaal', 90.00, '0.00'),
        ])
        path = os.path.join(temp_dir, 'with_payout.csv')
        df.to_csv(path, index=False)

        result = process_airbnb_multi([path], status='realised')
        assert len(result) == 1
        assert result[0]['reservationCode'] == 'HMREAL0001'

    def test_grouping_one_dict_per_code(self, temp_dir):
        """Multiple confirmation codes yield one dict each (Req 2.1, 2.2)."""
        df = pd.DataFrame([
            _airbnb_row('HMAAA', 'Boeking', 300.00, '"45,00"'),
            _airbnb_row('HMAAA', 'Doorloop totaal', 75.00, '0.00'),
            _airbnb_row('HMBBB', 'Boeking', 200.00, '"30,00"'),
            _airbnb_row('HMBBB', 'Doorloop totaal', 50.00, '0.00'),
        ])
        path = os.path.join(temp_dir, 'two_codes.csv')
        df.to_csv(path, index=False)

        result = process_airbnb_multi([path], status='realised')
        codes = sorted(b['reservationCode'] for b in result)
        assert codes == ['HMAAA', 'HMBBB']

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
