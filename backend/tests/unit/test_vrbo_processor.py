"""
Unit tests for VRBO processing in STRProcessor

Tests file detection, CSV parsing, two-file merge, amount parsing,
multi-language date parsing, and financial calculations.
"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock

from str_processor import STRProcessor


@pytest.fixture
def processor():
    return STRProcessor(test_mode=True)


@pytest.fixture
def reservations_csv(tmp_path):
    """Create a sample VRBO Reservations CSV"""
    content = (
        'Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,'
        'Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n'
        'HA-MSBK7M,10744968,JaBaKi Red Studio (617 - 10744968),2026-02-20,'
        'guest@example.com,Jacqueline Johansen,1 907-841-5191,'
        '2026-05-07,2026-05-12,5,2,0,Booked,VRBO\n'
        'HA-8YM4XP,10744968,JaBaKi Red Studio (617 - 10744968),2026-01-28,'
        'mona@example.com,Mona Reisert,49 1763 847-674-6,'
        '2026-06-06,2026-06-07,1,2,0,Booked,VRBO\n'
    )
    fp = tmp_path / 'reservations.csv'
    fp.write_text(content, encoding='utf-8')
    return str(fp)


@pytest.fixture
def payouts_csv_nl(tmp_path):
    """Create a sample VRBO Payouts CSV (Dutch)"""
    content = (
        'Naam gast,Boekingsnummer,Accommodatienummer,Uitbetalingsdatum,Status,Bedrag\n'
        'Jacqueline Johansen,HA-MSBK7M,10744968,8 mei 2026,Gepland,"€ 559,36"\n'
        'Mona Reisert,HA-8YM4XP,10744968,7 jun 2026,Gepland,"€ 115,92"\n'
        ',,,,,"Totaal: € 675,28"\n'
    )
    fp = tmp_path / 'payouts.csv'
    fp.write_text(content, encoding='utf-8')
    return str(fp)


@pytest.fixture
def payouts_csv_en(tmp_path):
    """Create a sample VRBO Payouts CSV (English)"""
    content = (
        'Guest name,Booking number,Property number,Payout date,Status,Amount\n'
        'Jacqueline Johansen,HA-MSBK7M,10744968,May 8 2026,Scheduled,"€ 559.36"\n'
    )
    fp = tmp_path / 'payouts_en.csv'
    fp.write_text(content, encoding='utf-8')
    return str(fp)


# ============================================================================
# Amount parsing
# ============================================================================

class TestParseAmount:

    def test_euro_format(self, processor):
        assert processor._parse_amount('€ 559,36') == 559.36

    def test_euro_thousands(self, processor):
        assert processor._parse_amount('€ 1.559,36') == 1559.36

    def test_usd_format(self, processor):
        assert processor._parse_amount('$559.36') == 559.36

    def test_gbp_format(self, processor):
        assert processor._parse_amount('£559.36') == 559.36

    def test_empty(self, processor):
        assert processor._parse_amount('') == 0

    def test_none(self, processor):
        assert processor._parse_amount(None) == 0

    def test_plain_number(self, processor):
        assert processor._parse_amount('100.50') == 100.50


# ============================================================================
# Multi-language date parsing
# ============================================================================

class TestParseMultilangDate:

    def test_dutch(self, processor):
        assert processor._parse_multilang_date('8 mei 2026') == '2026-05-08'

    def test_dutch_long(self, processor):
        assert processor._parse_multilang_date('15 december 2025') == '2025-12-15'

    def test_english(self, processor):
        assert processor._parse_multilang_date('May 8 2026') == '2026-05-08'

    def test_german(self, processor):
        assert processor._parse_multilang_date('8. Mai 2026') == '2026-05-08'

    def test_french(self, processor):
        assert processor._parse_multilang_date('8 juin 2026') == '2026-06-08'

    def test_fallback_iso(self, processor):
        assert processor._parse_multilang_date('2026-05-08') == '2026-05-08'

    def test_empty(self, processor):
        # Should return today's date
        result = processor._parse_multilang_date('')
        assert len(result) == 10  # YYYY-MM-DD format


# ============================================================================
# File type detection
# ============================================================================

class TestFileDetection:

    def test_detects_reservations(self, processor, reservations_csv, payouts_csv_nl):
        """_process_vrbo should detect and separate file types"""
        with patch.object(processor, '_build_vrbo_booking', return_value={'status': 'realised', 'channel': 'vrbo'}):
            bookings = processor._process_vrbo([reservations_csv, payouts_csv_nl])
        # Should process without error — file detection worked
        assert isinstance(bookings, list)

    def test_unknown_file_skipped(self, processor, tmp_path):
        """Unknown CSV files should be skipped"""
        unknown = tmp_path / 'unknown.csv'
        unknown.write_text('SomeColumn,OtherColumn\nval1,val2\n')
        bookings = processor._process_vrbo([str(unknown)])
        assert bookings == []


# ============================================================================
# Reservations parsing
# ============================================================================

class TestParseReservations:

    def test_parses_reservations(self, processor, reservations_csv):
        results = processor._parse_vrbo_reservations(reservations_csv)
        assert len(results) == 2
        assert results[0]['reservationCode'] == 'HA-MSBK7M'
        assert results[0]['guestName'] == 'Jacqueline Johansen'
        assert results[0]['nights'] == 5
        assert results[0]['adults'] == 2
        assert results[0]['children'] == 0

    def test_empty_file(self, processor, tmp_path):
        fp = tmp_path / 'empty.csv'
        fp.write_text('Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n')
        results = processor._parse_vrbo_reservations(str(fp))
        assert results == []


# ============================================================================
# Payouts parsing
# ============================================================================

class TestParsePayouts:

    def test_parses_dutch_payouts(self, processor, payouts_csv_nl):
        results = processor._parse_vrbo_payouts(payouts_csv_nl)
        assert len(results) == 2  # total row skipped
        assert results[0] == ('HA-MSBK7M', 559.36)
        assert results[1] == ('HA-8YM4XP', 115.92)

    def test_skips_total_row(self, processor, payouts_csv_nl):
        results = processor._parse_vrbo_payouts(payouts_csv_nl)
        codes = [r[0] for r in results]
        assert '' not in codes


# ============================================================================
# Two-file merge
# ============================================================================

class TestMerge:

    def test_merge_reservation_with_payout(self, processor, reservations_csv, payouts_csv_nl):
        bookings = processor._process_vrbo([reservations_csv, payouts_csv_nl])
        assert len(bookings) == 2

        # First booking should have financial data from payout
        ha_msbk = next(b for b in bookings if b['reservationCode'] == 'HA-MSBK7M')
        assert ha_msbk['amountGross'] > 0
        assert ha_msbk['amountChannelFee'] > 0
        assert ha_msbk['channel'] == 'vrbo'
        assert ha_msbk['nights'] == 5

    def test_reservation_without_payout(self, processor, reservations_csv):
        """Reservation with no payout file → amountGross = 0"""
        bookings = processor._process_vrbo([reservations_csv])
        assert len(bookings) == 2
        for b in bookings:
            assert b['amountGross'] == 0

    def test_financial_calculation(self, processor, reservations_csv, payouts_csv_nl):
        """Verify 25% fee estimate calculation"""
        bookings = processor._process_vrbo([reservations_csv, payouts_csv_nl])
        ha_msbk = next(b for b in bookings if b['reservationCode'] == 'HA-MSBK7M')

        # paidOut = 559.36, gross = 559.36 / 0.75 = 745.81, fee = 745.81 - 559.36 = 186.45
        assert abs(ha_msbk['amountGross'] - 745.81) < 0.02
        assert abs(ha_msbk['amountChannelFee'] - 186.45) < 0.02

    def test_booking_status_future(self, processor, reservations_csv, payouts_csv_nl):
        """Bookings with future check-in should be 'planned'"""
        bookings = processor._process_vrbo([reservations_csv, payouts_csv_nl])
        # All sample bookings have check-in in 2026 (future)
        for b in bookings:
            assert b['status'] == 'planned'


# ============================================================================
# Phase 3: Integration-style tests
# ============================================================================

class TestCancelledBooking:

    def test_cancelled_without_payout_skipped(self, processor, tmp_path):
        """Cancelled booking with no payout should have status 'cancelled'"""
        res_csv = tmp_path / 'res.csv'
        res_csv.write_text(
            'Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,'
            'Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n'
            'HA-CANCEL,10744968,JaBaKi Red Studio,2026-01-01,x@y.com,Test Guest,+31612345678,'
            '2025-06-01,2025-06-03,2,1,0,Cancelled,VRBO\n',
            encoding='utf-8'
        )
        bookings = processor._process_vrbo([str(res_csv)])
        assert len(bookings) == 1
        assert bookings[0]['status'] == 'cancelled'
        assert bookings[0]['amountGross'] == 0


class TestMultipleListingFiles:

    def test_merges_two_listing_files(self, processor, tmp_path, payouts_csv_nl):
        """Two reservation files (different listings) merged with one payouts file"""
        res1 = tmp_path / 'res_listing1.csv'
        res1.write_text(
            'Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,'
            'Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n'
            'HA-MSBK7M,10744968,JaBaKi Red Studio,2026-02-20,a@b.com,Guest A,+31600000001,'
            '2026-05-07,2026-05-12,5,2,0,Booked,VRBO\n',
            encoding='utf-8'
        )
        res2 = tmp_path / 'res_listing2.csv'
        res2.write_text(
            'Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,'
            'Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n'
            'HA-KN90H2,10027545,JaBaKi Garden House,2026-01-26,c@d.com,Guest B,+49170000000,'
            '2026-05-19,2026-05-20,1,3,0,Booked,VRBO\n',
            encoding='utf-8'
        )

        # Payouts CSV has both booking codes
        payouts = tmp_path / 'payouts_both.csv'
        payouts.write_text(
            'Naam gast,Boekingsnummer,Accommodatienummer,Uitbetalingsdatum,Status,Bedrag\n'
            'Guest A,HA-MSBK7M,10744968,8 mei 2026,Gepland,"€ 559,36"\n'
            'Guest B,HA-KN90H2,10027545,20 mei 2026,Gepland,"€ 148,12"\n',
            encoding='utf-8'
        )

        bookings = processor._process_vrbo([str(res1), str(res2), str(payouts)])
        assert len(bookings) == 2
        codes = {b['reservationCode'] for b in bookings}
        assert codes == {'HA-MSBK7M', 'HA-KN90H2'}
        # Both should have financial data
        for b in bookings:
            assert b['amountGross'] > 0


class TestCountryDetection:

    def test_detects_us_phone(self, processor, tmp_path):
        res_csv = tmp_path / 'res.csv'
        res_csv.write_text(
            'Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,'
            'Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n'
            'HA-US001,10744968,JaBaKi Red Studio,2026-01-01,x@y.com,US Guest,1 907-841-5191,'
            '2025-06-01,2025-06-03,2,1,0,Booked,VRBO\n',
            encoding='utf-8'
        )
        bookings = processor._process_vrbo([str(res_csv)])
        assert len(bookings) == 1
        # Country should be detected (exact value depends on detect_country implementation)
        assert 'country' in bookings[0]

    def test_detects_german_phone(self, processor, tmp_path):
        res_csv = tmp_path / 'res.csv'
        res_csv.write_text(
            'Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,'
            'Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n'
            'HA-DE001,10744968,JaBaKi Red Studio,2026-01-01,x@y.com,DE Guest,49 1763 847-674-6,'
            '2025-06-01,2025-06-03,2,1,0,Booked,VRBO\n',
            encoding='utf-8'
        )
        bookings = processor._process_vrbo([str(res_csv)])
        assert len(bookings) == 1
        assert 'country' in bookings[0]


class TestSampleData:

    def test_full_sample_from_requirements(self, processor, tmp_path):
        """Test with all 4 reservations from the requirements sample data"""
        res1 = tmp_path / 'res_red.csv'
        res1.write_text(
            'Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,'
            'Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n'
            'HA-MSBK7M,10744968,JaBaKi Red Studio (617 - 10744968),2026-02-20,'
            'jacquibarrett58@gmail.com,Jacqueline Johansen,1 907-841-5191,'
            '2026-05-07,2026-05-12,5,2,0,Booked,VRBO\n'
            'HA-8YM4XP,10744968,JaBaKi Red Studio (617 - 10744968),2026-01-28,'
            'mona.reisert@gmx.de,Mona Reisert,49 1763 847-674-6,'
            '2026-06-06,2026-06-07,1,2,0,Booked,VRBO\n'
            'HA-6316NF,10744968,JaBaKi Red Studio (617 - 10744968),2026-01-28,'
            'mona.reisert@gmx.de,Mona Reisert,49 1763 847-674-6,'
            '2026-06-04,2026-06-05,1,2,0,Booked,VRBO\n',
            encoding='utf-8'
        )
        res2 = tmp_path / 'res_garden.csv'
        res2.write_text(
            'Reservation ID,Listing Number,Property Name,Created On,Email,Inquirer,Phone,'
            'Check-in,Check-out,Nights Stay,Adults,Children,Status,Source\n'
            'HA-KN90H2,10027545,JaBaKi Child-friendly garden house (617 - 10027545),2026-01-26,'
            'kathrin.ostermann@gmx.de,Kathrin Ostermann-Schmitt,49 17376-56645,'
            '2026-05-19,2026-05-20,1,3,0,Booked,VRBO\n',
            encoding='utf-8'
        )
        payouts = tmp_path / 'payouts.csv'
        payouts.write_text(
            'Naam gast,Boekingsnummer,Accommodatienummer,Uitbetalingsdatum,Status,Bedrag\n'
            'Jacqueline Johansen,HA-MSBK7M,10744968,8 mei 2026,Gepland,"€ 559,36"\n'
            'Kathrin Ostermann-Schmitt,HA-KN90H2,10027545,20 mei 2026,Gepland,"€ 148,12"\n'
            'Mona Reisert,HA-6316NF,10744968,5 jun 2026,Gepland,"€ 87,40"\n'
            'Mona Reisert,HA-8YM4XP,10744968,7 jun 2026,Gepland,"€ 115,92"\n'
            ',,,,,"Totaal: € 910,80 - Totaal voor geselecteerd datumbereik"\n',
            encoding='utf-8'
        )

        bookings = processor._process_vrbo([str(res1), str(res2), str(payouts)])

        assert len(bookings) == 4
        codes = {b['reservationCode'] for b in bookings}
        assert codes == {'HA-MSBK7M', 'HA-KN90H2', 'HA-6316NF', 'HA-8YM4XP'}

        # All should have financial data
        for b in bookings:
            assert b['amountGross'] > 0
            assert b['channel'] == 'vrbo'
            assert b['status'] == 'planned'  # all future dates

        # Check specific amounts
        ha_msbk = next(b for b in bookings if b['reservationCode'] == 'HA-MSBK7M')
        assert ha_msbk['nights'] == 5
        assert abs(ha_msbk['amountGross'] - (559.36 / 0.75)) < 0.02
