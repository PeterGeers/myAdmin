import sys
import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime, date

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from str_processor import STRProcessor

class TestSTRProcessor:
    
    @pytest.fixture
    def str_processor(self):
        """Create STRProcessor instance for testing"""
        return STRProcessor(test_mode=True)
    
    @pytest.fixture
    def sample_airbnb_data(self):
        """Sample Airbnb CSV data"""
        return {
            'Begindatum': '15-01-2025',
            'Einddatum': '17-01-2025',
            'Naam van de gast': 'John Doe',
            'Advertentie': 'Green Studio',
            '# nachten': 2,
            'Inkomsten': '€ 190,10',
            'Bevestigingscode': 'ABC123',
            'Status': 'Bevestigd',
            'Contact': '+31612345678',
            '# volwassenen': 2,
            '# kinderen': 0,
            "# baby's": 0,
            'Gereserveerd': '2025-01-01'
        }
    
    @pytest.fixture
    def sample_booking_data(self):
        """Sample Booking.com data"""
        return {
            'Check-in': '2025-01-15',
            'Check-out': '2025-01-17',
            'Guest name(s)': 'Jane Smith',
            'Unit type': 'Red Studio',
            'Duration (nights)': 2,
            'Price': '200.00 EUR',
            'Book number': 'BK456',
            'Status': 'ok',
            'Commission amount': '30.00',
            'Persons': 2,
            'Adults': 2,
            'Children': 0,
            'Booked on': '2025-01-01 10:00:00'
        }
    
    @pytest.fixture
    def sample_direct_data(self):
        """Sample direct booking data"""
        return {
            'type': 'reservation',
            'startDate': '2025-01-15',
            'guestName': 'Bob Johnson',
            'listing': 'Child Friendly',
            'nights': 3,
            'guests': 4,
            'amountGross': 300.00,
            'paidOut': 255.00,
            'reservationCode': 'DIR789',
            'typeTrade': 'goodwin',
            'details': 'Direct booking',
            'currency': 'EUR',
            'cleaningFee': 25.00
        }
    
    def test_init_test_mode(self):
        """Test initialization in test mode"""
        processor = STRProcessor(test_mode=True)
        assert processor.test_mode == True
        assert processor.platforms == ['airbnb', 'booking', 'direct']
        # Tax rates are calculated dynamically via get_tax_rates(), not stored as attributes
        tax_rates_2024 = processor.get_tax_rates('2024-01-01')
        assert tax_rates_2024['vat_rate'] == 9
        assert tax_rates_2024['tourist_tax_rate'] == 6.02  # Actual rate is 6.02%
    
    def test_init_production_mode(self):
        """Test initialization in production mode"""
        processor = STRProcessor(test_mode=False)
        assert processor.test_mode == False
        assert hasattr(processor, 'property_mappings')
    
    def test_normalize_listing_name_green(self, str_processor):
        """Test Green Studio listing normalization"""
        test_cases = ['One', 'groen', 'Groen', 'green', 'Green']
        for case in test_cases:
            result = str_processor._normalize_listing_name(case)
            assert result == 'Green Studio'
    
    def test_normalize_listing_name_child_friendly(self, str_processor):
        """Test Child Friendly listing normalization"""
        test_cases = ['Apartment', 'Tuinhuis', 'Garden', 'garden', 'Child', 'child']
        for case in test_cases:
            result = str_processor._normalize_listing_name(case)
            assert result == 'Child Friendly'
    
    def test_normalize_listing_name_red(self, str_processor):
        """Test Red Studio listing normalization"""
        test_cases = ['Rode', 'rode', 'Red', 'Rood', 'rood', 'red']
        for case in test_cases:
            result = str_processor._normalize_listing_name(case)
            assert result == 'Red Studio'
    
    def test_normalize_listing_name_unchanged(self, str_processor):
        """Test listing name remains unchanged for unknown patterns"""
        result = str_processor._normalize_listing_name('Unknown Listing')
        assert result == 'Unknown Listing'
    
    def test_normalize_listing_name_empty(self, str_processor):
        """Test empty listing name handling"""
        result = str_processor._normalize_listing_name('')
        assert result == ''
        
        result = str_processor._normalize_listing_name(None)
        assert result is None
    
    @patch('os.listdir')
    @patch('os.path.isfile')
    def test_scan_str_files_success(self, mock_isfile, mock_listdir, str_processor):
        """Test successful STR file scanning"""
        mock_listdir.return_value = [
            'reservation_export.csv',
            'check-in_report.xlsx',
            'jabakirechtstreeks_data.xlsx',
            'other_file.txt'
        ]
        mock_isfile.return_value = True
        
        files = str_processor.scan_str_files('/test/folder')
        
        assert len(files['airbnb']) == 1
        assert len(files['booking']) == 1
        assert len(files['direct']) == 1
        assert 'reservation_export.csv' in files['airbnb'][0]
        assert 'check-in_report.xlsx' in files['booking'][0]
        assert 'jabakirechtstreeks_data.xlsx' in files['direct'][0]
    
    @patch('os.listdir')
    def test_scan_str_files_error(self, mock_listdir, str_processor):
        """Test STR file scanning with error"""
        mock_listdir.side_effect = Exception("Permission denied")
        
        files = str_processor.scan_str_files('/test/folder')
        
        assert files['airbnb'] == []
        assert files['booking'] == []
        assert files['direct'] == []
    
    @patch('os.listdir')
    @patch('os.path.isfile')
    def test_scan_str_files_no_matches(self, mock_isfile, mock_listdir, str_processor):
        """Test STR file scanning with no matching files"""
        mock_listdir.return_value = ['document.pdf', 'image.jpg']
        mock_isfile.return_value = True
        
        files = str_processor.scan_str_files('/test/folder')
        
        assert files['airbnb'] == []
        assert files['booking'] == []
        assert files['direct'] == []
    
    def test_process_single_file_unsupported_platform(self, str_processor):
        """Test processing with unsupported platform"""
        with pytest.raises(ValueError, match="Unsupported platform"):
            str_processor._process_single_file('test.csv', 'unsupported')
    
    @patch('pandas.read_csv')
    def test_process_airbnb_success(self, mock_read_csv, str_processor, sample_airbnb_data):
        """Test successful Airbnb processing"""
        mock_df = pd.DataFrame([sample_airbnb_data])
        mock_read_csv.return_value = mock_df
        
        with patch('os.path.basename', return_value='test.csv'):
            result = str_processor._process_airbnb('test.csv')
        
        assert len(result) == 1
        assert result[0]['channel'] == 'airbnb'
        assert result[0]['listing'] == 'Green Studio'
        assert result[0]['nights'] == 2
        assert result[0]['guestName'] == 'John Doe'
        assert result[0]['reservationCode'] == 'ABC123'
    
    @patch('pandas.read_csv')
    def test_process_airbnb_cancelled_no_earnings(self, mock_read_csv, str_processor, sample_airbnb_data):
        """Test Airbnb processing skips cancelled bookings with no earnings"""
        sample_airbnb_data['Status'] = 'Geannuleerd'
        sample_airbnb_data['Inkomsten'] = '€ 0,00'
        mock_df = pd.DataFrame([sample_airbnb_data])
        mock_read_csv.return_value = mock_df
        
        result = str_processor._process_airbnb('test.csv')
        
        assert len(result) == 0  # Should be skipped
    
    @patch('pandas.read_csv')
    def test_process_airbnb_error(self, mock_read_csv, str_processor):
        """Test Airbnb processing with error"""
        mock_read_csv.side_effect = Exception("File not found")
        
        result = str_processor._process_airbnb('nonexistent.csv')
        
        assert result == []
    
    @patch('pandas.read_excel')
    def test_process_booking_success(self, mock_read_excel, str_processor, sample_booking_data):
        """Test successful Booking.com processing"""
        mock_df = pd.DataFrame([sample_booking_data])
        mock_read_excel.return_value = mock_df
        
        with patch('os.path.basename', return_value='test.xlsx'):
            result = str_processor._process_booking('test.xlsx')
        
        assert len(result) == 1
        assert result[0]['channel'] == 'booking.com'
        assert result[0]['listing'] == 'Red Studio'
        assert result[0]['nights'] == 2
        assert result[0]['guestName'] == 'Jane Smith'
        assert result[0]['reservationCode'] == 'BK456'
    
    @patch('pandas.read_csv')
    def test_process_booking_csv(self, mock_read_csv, str_processor, sample_booking_data):
        """Test Booking.com CSV processing"""
        mock_df = pd.DataFrame([sample_booking_data])
        mock_read_csv.return_value = mock_df
        
        with patch('os.path.basename', return_value='test.csv'):
            result = str_processor._process_booking('test.csv')
        
        assert len(result) == 1
        assert result[0]['channel'] == 'booking.com'
    
    @patch('pandas.read_excel')
    def test_process_booking_cancelled(self, mock_read_excel, str_processor, sample_booking_data):
        """Test Booking.com processing skips cancelled bookings with no commission"""
        sample_booking_data['Status'] = 'cancelled_by_guest'
        sample_booking_data['Commission amount'] = ''
        mock_df = pd.DataFrame([sample_booking_data])
        mock_read_excel.return_value = mock_df
        
        result = str_processor._process_booking('test.xlsx')
        
        assert len(result) == 0  # Should be skipped
    
    @patch('pandas.read_excel')
    def test_process_direct_success(self, mock_read_excel, str_processor, sample_direct_data):
        """Test successful direct booking processing"""
        mock_df = pd.DataFrame([sample_direct_data])
        mock_read_excel.return_value = mock_df
        
        with patch('os.path.basename', return_value='test.xlsx'):
            result = str_processor._process_direct('test.xlsx')
        
        assert len(result) == 1
        assert result[0]['channel'] == 'dfDirect'  # goodwin -> dfDirect
        assert result[0]['listing'] == 'Child Friendly'
        assert result[0]['nights'] == 3
        assert result[0]['guestName'] == 'Bob Johnson'
        assert result[0]['reservationCode'] == 'DIR789'
    
    @patch('pandas.read_excel')
    def test_process_direct_vrbo_channel(self, mock_read_excel, str_processor, sample_direct_data):
        """Test direct booking VRBO channel detection"""
        sample_direct_data['typeTrade'] = 'vrbo booking'
        mock_df = pd.DataFrame([sample_direct_data])
        mock_read_excel.return_value = mock_df
        
        with patch('os.path.basename', return_value='test.xlsx'):
            result = str_processor._process_direct('test.xlsx')
        
        assert len(result) == 1
        assert result[0]['channel'] == 'VRBO'
    
    @patch('pandas.read_excel')
    def test_process_direct_skip_non_reservation(self, mock_read_excel, str_processor, sample_direct_data):
        """Test direct booking skips non-reservation records"""
        sample_direct_data['type'] = 'payment'
        mock_df = pd.DataFrame([sample_direct_data])
        mock_read_excel.return_value = mock_df
        
        result = str_processor._process_direct('test.xlsx')
        
        assert len(result) == 0  # Should be skipped
    
    def test_parse_date_formats(self, str_processor):
        """Test various date format parsing"""
        test_cases = [
            ('2025-01-15', '2025-01-15'),
            ('15/01/2025', '2025-01-15'),
            ('01/15/2025', '2025-01-15'),
            ('15-01-2025', '2025-01-15')
        ]
        
        for input_date, expected in test_cases:
            result = str_processor._parse_date(input_date)
            assert result == expected
    
    def test_parse_date_invalid(self, str_processor):
        """Test invalid date parsing returns current date"""
        result = str_processor._parse_date('invalid-date')
        # Should return current date in YYYY-MM-DD format
        assert len(result) == 10
        assert result.count('-') == 2
    
    def test_parse_date_empty(self, str_processor):
        """Test empty date parsing returns current date"""
        result = str_processor._parse_date('')
        # Should return current date in YYYY-MM-DD format
        assert len(result) == 10
        assert result.count('-') == 2
    
    def test_generate_summary_empty(self, str_processor):
        """Test summary generation with empty bookings"""
        result = str_processor.generate_summary([])
        assert result == {}
    
    def test_generate_summary_with_data(self, str_processor):
        """Test summary generation with booking data"""
        bookings = [
            {
                'channel': 'airbnb',
                'listing': 'Green Studio',
                'nights': 2,
                'amountGross': 200.00,
                'amountNett': 150.00,
                'pricePerNight': 75.00,
                'checkinDate': '2025-01-15'
            },
            {
                'channel': 'booking.com',
                'listing': 'Red Studio',
                'nights': 3,
                'amountGross': 300.00,
                'amountNett': 225.00,
                'pricePerNight': 75.00,
                'checkinDate': '2025-01-20'
            }
        ]
        
        result = str_processor.generate_summary(bookings)
        
        assert result['total_bookings'] == 2
        assert result['total_nights'] == 5
        assert result['total_gross'] == 500.00
        assert result['total_net'] == 375.00
        assert result['avg_nightly_rate'] == 75.00
        assert result['channels']['airbnb'] == 1
        assert result['channels']['booking.com'] == 1
        assert result['date_range']['start'] == '2025-01-15'
        assert result['date_range']['end'] == '2025-01-20'
    
    def test_separate_by_status_basic_functionality(self, str_processor):
        """Test basic status separation functionality"""
        
        bookings = [
            {'channel': 'airbnb', 'reservationCode': 'ABC123', 'status': 'realised'},
            {'channel': 'airbnb', 'reservationCode': 'DEF456', 'status': 'cancelled'},
            {'channel': 'booking.com', 'reservationCode': 'GHI789', 'status': 'planned'}
        ]
        
        result = str_processor.separate_by_status(bookings)
        
        # Should have realised, planned, and already_loaded keys
        assert 'realised' in result
        assert 'planned' in result
        assert 'already_loaded' in result
        
        # Check that bookings are categorized
        assert len(result['realised']) >= 1  # At least realised bookings
        assert len(result['planned']) >= 1   # At least planned bookings
    
    def test_separate_by_status_fallback(self, str_processor):
        """Test status separation fallback without database"""
        bookings = [
            {'status': 'realised', 'reservationCode': 'ABC123'},
            {'status': 'cancelled', 'reservationCode': 'DEF456'},
            {'status': 'planned', 'reservationCode': 'GHI789'}
        ]
        
        # Mock the import to raise an exception
        with patch('builtins.__import__', side_effect=lambda name, *args: Exception("Import error") if name == 'str_database' else __import__(name, *args)):
            result = str_processor.separate_by_status(bookings)
        
        assert len(result['realised']) == 2  # realised + cancelled
        assert len(result['planned']) == 1
        assert len(result['already_loaded']) == 0
    
    def test_generate_future_summary_empty(self, str_processor):
        """Test future summary generation with empty bookings"""
        result = str_processor.generate_future_summary([])
        assert result == []
    
    def test_generate_future_summary_with_data(self, str_processor):
        """Test future summary generation with planned bookings"""
        planned_bookings = [
            {
                'channel': 'airbnb',
                'listing': 'Green Studio',
                'amountGross': 200.00,
                'reservationCode': 'ABC123'
            },
            {
                'channel': 'airbnb',
                'listing': 'Green Studio',
                'amountGross': 150.00,
                'reservationCode': 'DEF456'
            },
            {
                'channel': 'booking.com',
                'listing': 'Red Studio',
                'amountGross': 300.00,
                'reservationCode': 'GHI789'
            }
        ]
        
        result = str_processor.generate_future_summary(planned_bookings)
        
        assert len(result) == 2  # Two unique channel/listing combinations
        # Find the airbnb/Green Studio entry
        airbnb_entry = next(r for r in result if r['channel'] == 'airbnb' and r['listing'] == 'Green Studio')
        assert airbnb_entry['amount'] == 350.00  # 200 + 150
        assert airbnb_entry['items'] == 2
        
        # Find the booking.com/Red Studio entry
        booking_entry = next(r for r in result if r['channel'] == 'booking.com' and r['listing'] == 'Red Studio')
        assert booking_entry['amount'] == 300.00
        assert booking_entry['items'] == 1
    
    @patch.object(STRProcessor, '_process_single_file')
    def test_process_str_files_success(self, mock_process_single, str_processor):
        """Test processing multiple STR files"""
        mock_process_single.side_effect = [
            [{'booking': 1}],
            [{'booking': 2}]
        ]
        
        result = str_processor.process_str_files(['file1.csv', 'file2.csv'], 'airbnb')
        
        assert len(result) == 2
        assert mock_process_single.call_count == 2
    
    @patch.object(STRProcessor, '_process_single_file')
    def test_process_str_files_with_error(self, mock_process_single, str_processor):
        """Test processing STR files with one file error"""
        mock_process_single.side_effect = [
            [{'booking': 1}],
            Exception("File error")
        ]
        
        result = str_processor.process_str_files(['file1.csv', 'file2.csv'], 'airbnb')
        
        assert len(result) == 1  # Only successful file processed
        assert mock_process_single.call_count == 2

if __name__ == '__main__':
    pytest.main([__file__])