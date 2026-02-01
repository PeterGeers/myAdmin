"""
Tests for Booking.com Payout CSV import functionality
"""
import pytest
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from str_processor import STRProcessor


class TestBookingPayoutImport:
    """Test Booking.com Payout CSV import"""
    
    def test_process_booking_payout_basic(self, tmp_path):
        """Test basic payout CSV processing"""
        # Create test CSV file
        csv_content = """Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
(Payout)             , y55PeMz92KfbsTyD    , -               , -            , -             , -         , -                 , -    , -          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , -           , -         , -           , -                   , -                     , -      , -                 , -                   , -            ,          95.26, 95.26        , EUR            , 2025-03-10 , Daily           , *6917
Reservation          , y55PeMz92KfbsTyD    , 4649972566      , 2025-03-08   , 2025-03-09    , 2025-03-09, Okay              , 1    , 1          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , 112.50      , -12.79    , 11.37%      , -1.46               , 1.30%                 , -2.99  , 95.26             , EUR                 , 1.00         ,          95.26, -            , EUR            , 2025-03-10 , Daily           , *6917
"""
        
        csv_file = tmp_path / "Payout_from_2025-01-01_until_2025-12-31.csv"
        csv_file.write_text(csv_content)
        
        # Process the file
        processor = STRProcessor(test_mode=True)
        results = processor._process_booking_payout(str(csv_file))
        
        # Verify results
        assert results is not None
        assert 'updated' in results
        assert 'summary' in results
        assert results['summary']['reservation_rows'] == 1
        assert len(results['updates']) == 1
        
        # Verify the update record
        update = results['updates'][0]
        assert update['reservationCode'] == '4649972566'
        assert update['amountGross'] == 112.50
        assert update['amountChannelFee'] == 14.25  # abs(-12.79) + abs(-1.46)
        # VAT calculated on gross: (112.50 / 109) * 9 = 9.29
        assert update['amountVat'] == 9.29
        assert update['nights'] == 1
    
    def test_process_booking_payout_channel_fee_calculation(self, tmp_path):
        """Test that channel fee is correctly calculated from Commission + Service Fee"""
        csv_content = """Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
Reservation          , test123             , 1234567890      , 2025-03-08   , 2025-03-09    , 2025-03-09, Okay              , 1    , 1          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , 100.00      , -10.00    , 10.00%      , -2.00               , 2.00%                 , -3.00  , 85.00             , EUR                 , 1.00         ,          85.00, -            , EUR            , 2025-03-10 , Daily           , *6917
"""
        
        csv_file = tmp_path / "Payout_test.csv"
        csv_file.write_text(csv_content)
        
        processor = STRProcessor(test_mode=True)
        results = processor._process_booking_payout(str(csv_file))
        
        update = results['updates'][0]
        # Channel fee should be abs(-10.00) + abs(-2.00) = 12.00
        assert update['amountChannelFee'] == 12.00
    
    def test_process_booking_payout_tourist_tax_calculation(self, tmp_path):
        """Test that tourist tax is calculated correctly (not in CSV)"""
        csv_content = """Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
Reservation          , test123             , 1234567890      , 2025-03-08   , 2025-03-09    , 2025-03-09, Okay              , 1    , 1          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , 112.50      , -12.79    , 11.37%      , -1.46               , 1.30%                 , -2.99  , 95.26             , EUR                 , 1.00         ,          95.26, -            , EUR            , 2025-03-10 , Daily           , *6917
"""
        
        csv_file = tmp_path / "Payout_test.csv"
        csv_file.write_text(csv_content)
        
        processor = STRProcessor(test_mode=True)
        results = processor._process_booking_payout(str(csv_file))
        
        update = results['updates'][0]
        
        # Tourist tax should be calculated using the algorithm
        # For 2025-03-08 (pre-2026): vat_rate = 9%, tourist_tax_rate = 6.02%, tourist_tax_base = 106.02
        # VAT = (112.50 / 109) * 9 = 9.29
        # vat_exclusive_amount = 112.50 - 9.29 = 103.21
        # tourist_tax = (103.21 / 106.02) * 6.02 = 5.86
        assert update['amountVat'] == 9.29
        assert update['amountTouristTax'] == 5.86
    
    def test_process_booking_payout_net_amount_calculation(self, tmp_path):
        """Test that net amount is correctly calculated"""
        csv_content = """Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
Reservation          , test123             , 1234567890      , 2025-03-08   , 2025-03-09    , 2025-03-09, Okay              , 1    , 1          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , 112.50      , -12.79    , 11.37%      , -1.46               , 1.30%                 , -2.99  , 95.26             , EUR                 , 1.00         ,          95.26, -            , EUR            , 2025-03-10 , Daily           , *6917
"""
        
        csv_file = tmp_path / "Payout_test.csv"
        csv_file.write_text(csv_content)
        
        processor = STRProcessor(test_mode=True)
        results = processor._process_booking_payout(str(csv_file))
        
        update = results['updates'][0]
        
        # Net = Gross - VAT - TouristTax - ChannelFee
        # VAT = (112.50 / 109) * 9 = 9.29
        # TouristTax = ((112.50 - 9.29) / 106.02) * 6.02 = 5.86
        # Net = 112.50 - 9.29 - 5.86 - 14.25 = 83.10
        assert update['amountNett'] == 83.10
    
    def test_process_booking_payout_2026_tax_rates(self, tmp_path):
        """Test that 2026 tax rates are used for check-in dates >= 2026-01-01"""
        csv_content = """Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
Reservation          , test123             , 1234567890      , 2026-01-15   , 2026-01-16    , 2026-01-15, Okay              , 1    , 1          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , 112.50      , -12.79    , 11.37%      , -1.46               , 1.30%                 , -2.99  , 95.26             , EUR                 , 1.00         ,          95.26, -            , EUR            , 2026-01-16 , Daily           , *6917
"""
        
        csv_file = tmp_path / "Payout_test.csv"
        csv_file.write_text(csv_content)
        
        processor = STRProcessor(test_mode=True)
        results = processor._process_booking_payout(str(csv_file))
        
        update = results['updates'][0]
        
        # For 2026: vat_rate = 21%, tourist_tax_rate = 6.9%, tourist_tax_base = 106.9
        # VAT = (112.50 / 121) * 21 = 19.52
        # vat_exclusive_amount = 112.50 - 19.52 = 92.98
        # tourist_tax = (92.98 / 106.9) * 6.9 = 6.00
        assert update['amountVat'] == 19.52
        assert update['amountTouristTax'] == 6.00
    
    def test_process_booking_payout_skip_payout_rows(self, tmp_path):
        """Test that (Payout) summary rows are skipped"""
        csv_content = """Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
(Payout)             , y55PeMz92KfbsTyD    , -               , -            , -             , -         , -                 , -    , -          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , -           , -         , -           , -                   , -                     , -      , -                 , -                   , -            ,          95.26, 95.26        , EUR            , 2025-03-10 , Daily           , *6917
(Payout)             , another_payout      , -               , -            , -             , -         , -                 , -    , -          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , -           , -         , -           , -                   , -                     , -      , -                 , -                   , -            ,          50.00, 50.00        , EUR            , 2025-03-11 , Daily           , *6917
Reservation          , y55PeMz92KfbsTyD    , 4649972566      , 2025-03-08   , 2025-03-09    , 2025-03-09, Okay              , 1    , 1          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , 112.50      , -12.79    , 11.37%      , -1.46               , 1.30%                 , -2.99  , 95.26             , EUR                 , 1.00         ,          95.26, -            , EUR            , 2025-03-10 , Daily           , *6917
"""
        
        csv_file = tmp_path / "Payout_test.csv"
        csv_file.write_text(csv_content)
        
        processor = STRProcessor(test_mode=True)
        results = processor._process_booking_payout(str(csv_file))
        
        # Should only process 1 Reservation row, not the 2 (Payout) rows
        assert results['summary']['total_rows'] == 3
        assert results['summary']['reservation_rows'] == 1
        assert len(results['updates']) == 1
    
    def test_process_booking_payout_multiple_reservations(self, tmp_path):
        """Test processing multiple reservations in one file"""
        csv_content = """Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
Reservation          , test1               , 1111111111      , 2025-03-08   , 2025-03-09    , 2025-03-09, Okay              , 1    , 1          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , 112.50      , -12.79    , 11.37%      , -1.46               , 1.30%                 , -2.99  , 95.26             , EUR                 , 1.00         ,          95.26, -            , EUR            , 2025-03-10 , Daily           , *6917
Reservation          , test2               , 2222222222      , 2025-03-10   , 2025-03-11    , 2025-03-11, Okay              , 1    , 1          ,     5615303, "Jabaki Red Studio"  ,  8411095, "Goodwin Solutions BV", Netherlands, Net        , 65.00       , -7.39     , 11.37%      , -0.84               , 1.30%                 , -1.73  , 55.04             , EUR                 , 1.00         ,          55.04, -            , EUR            , 2025-03-12 , Daily           , *6917
Reservation          , test3               , 3333333333      , 2025-03-15   , 2025-03-22    , 2025-03-22, Okay              , 1    , 7          ,     5615303, "Jabaki Red Studio"  ,  8411095, "Goodwin Solutions BV", Netherlands, Net        , 729.00      , -82.88    , 11.37%      , -9.48               , 1.30%                 , -19.40 , 617.24            , EUR                 , 1.00         ,         617.24, -            , EUR            , 2025-03-24 , Daily           , *6917
"""
        
        csv_file = tmp_path / "Payout_test.csv"
        csv_file.write_text(csv_content)
        
        processor = STRProcessor(test_mode=True)
        results = processor._process_booking_payout(str(csv_file))
        
        assert results['summary']['reservation_rows'] == 3
        assert len(results['updates']) == 3
        assert results['updates'][0]['reservationCode'] == '1111111111'
        assert results['updates'][1]['reservationCode'] == '2222222222'
        assert results['updates'][2]['reservationCode'] == '3333333333'
    
    def test_scan_str_files_detects_payout_files(self, tmp_path):
        """Test that scan_str_files detects Payout CSV files"""
        # Create test files
        (tmp_path / "Payout_from_2025-01-01_until_2025-12-31.csv").write_text("test")
        (tmp_path / "Check-in_2025-01-01.xls").write_text("test")
        (tmp_path / "reservations.csv").write_text("test")
        
        processor = STRProcessor(test_mode=True)
        files = processor.scan_str_files(str(tmp_path))
        
        assert 'booking_payout' in files
        assert len(files['booking_payout']) == 1
        assert 'Payout_from' in files['booking_payout'][0]
        assert len(files['booking']) == 1
        assert len(files['airbnb']) == 1
    
    def test_process_booking_payout_price_per_night(self, tmp_path):
        """Test that price per night is correctly calculated"""
        csv_content = """Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
Reservation          , test123             , 1234567890      , 2025-03-15   , 2025-03-22    , 2025-03-22, Okay              , 1    , 7          ,     5615303, "Jabaki Red Studio"  ,  8411095, "Goodwin Solutions BV", Netherlands, Net        , 729.00      , -82.88    , 11.37%      , -9.48               , 1.30%                 , -19.40 , 617.24            , EUR                 , 1.00         ,         617.24, -            , EUR            , 2025-03-24 , Daily           , *6917
"""
        
        csv_file = tmp_path / "Payout_test.csv"
        csv_file.write_text(csv_content)
        
        processor = STRProcessor(test_mode=True)
        results = processor._process_booking_payout(str(csv_file))
        
        update = results['updates'][0]
        
        # Price per night = Net / Nights
        expected_price_per_night = round(update['amountNett'] / 7, 2)
        assert update['pricePerNight'] == expected_price_per_night
        assert update['nights'] == 7
