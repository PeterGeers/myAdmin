"""
Test suite for Payout CSV import API endpoint
"""
import pytest
import os
import sys
from io import BytesIO

# Add src directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from str_processor import STRProcessor
from str_database import STRDatabase
from database import DatabaseManager


@pytest.fixture
def sample_payout_csv():
    """Create sample Payout CSV content"""
    csv_content = """Type/Transaction type,Reference number,Check-in date,Check-out date,Room nights,Gross amount,Commission,Payments Service Fee,Tax/VAT
Reservation,1234567890,2025-01-15,2025-01-18,3,450.00,-45.00,-5.00,7.50
Reservation,9876543210,2025-01-20,2025-01-25,5,750.00,-75.00,-8.00,12.50
Reservation,1111111111,2025-02-01,2025-02-05,4,600.00,-60.00,-6.50,10.00
Payout,,,,,550.00,,,
"""
    return csv_content


@pytest.fixture
def setup_test_bookings():
    """Setup test bookings in database"""
    db = DatabaseManager(test_mode=True)
    str_db = STRDatabase(test_mode=True)
    
    # Insert test bookings that will be updated by payout
    test_bookings = [
        {
            'sourceFile': 'test_booking.xlsx',
            'channel': 'booking.com',
            'listing': 'Green Studio',
            'checkinDate': '2025-01-15',
            'checkoutDate': '2025-01-18',
            'nights': 3,
            'guests': 2,
            'amountGross': 400.00,  # Will be updated to 450.00
            'amountChannelFee': 40.00,  # Will be updated
            'amountVat': 33.03,  # Will be recalculated
            'amountTouristTax': 22.00,  # Will be recalculated
            'amountNett': 304.97,  # Will be recalculated
            'guestName': 'Test Guest 1',
            'phone': '',
            'reservationCode': '1234567890',
            'reservationDate': '2025-01-01',
            'status': 'realised',
            'pricePerNight': 101.66,
            'daysBeforeReservation': 14,
            'addInfo': '',
            'year': 2025,
            'q': 1,
            'm': 1
        },
        {
            'sourceFile': 'test_booking.xlsx',
            'channel': 'booking.com',
            'listing': 'Red Studio',
            'checkinDate': '2025-01-20',
            'checkoutDate': '2025-01-25',
            'nights': 5,
            'guests': 2,
            'amountGross': 700.00,  # Will be updated to 750.00
            'amountChannelFee': 70.00,  # Will be updated
            'amountVat': 57.85,  # Will be recalculated
            'amountTouristTax': 36.50,  # Will be recalculated
            'amountNett': 535.65,  # Will be recalculated
            'guestName': 'Test Guest 2',
            'phone': '',
            'reservationCode': '9876543210',
            'reservationDate': '2025-01-05',
            'status': 'realised',
            'pricePerNight': 107.13,
            'daysBeforeReservation': 15,
            'addInfo': '',
            'year': 2025,
            'q': 1,
            'm': 1
        }
    ]
    
    # Insert bookings
    inserted = str_db.insert_realised_bookings(test_bookings)
    print(f"Setup: Inserted {inserted} test bookings")
    
    yield
    
    # Cleanup - delete test bookings
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bnb WHERE reservationCode IN ('1234567890', '9876543210', '1111111111', '2026123456')")
        conn.commit()
        cursor.close()
        print("Cleanup: Deleted test bookings")
    except Exception as e:
        print(f"Cleanup error: {e}")


def test_payout_processing_and_database_update(sample_payout_csv, setup_test_bookings, tmp_path):
    """Test complete Payout CSV processing and database update flow"""
    # Write CSV to temp file
    csv_file = tmp_path / "Payout_from_2025-01-01_until_2025-01-31.csv"
    csv_file.write_text(sample_payout_csv)
    
    # Process the Payout CSV
    str_processor = STRProcessor(test_mode=True)
    payout_result = str_processor._process_booking_payout(str(csv_file))
    
    # Verify processing results
    assert payout_result['summary']['total_rows'] == 4  # 3 reservations + 1 payout line
    assert payout_result['summary']['reservation_rows'] == 3
    assert payout_result['summary']['updated_count'] == 3
    assert len(payout_result['updates']) == 3
    
    # Update database
    str_db = STRDatabase(test_mode=True)
    update_result = str_db.update_from_payout(payout_result['updates'])
    
    # Verify database update results
    assert update_result['updated'] == 2  # Only 2 found in database
    assert len(update_result['not_found']) == 1  # 1111111111 not in database
    assert '1111111111' in update_result['not_found']
    
    # Verify database was actually updated
    db = DatabaseManager(test_mode=True)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Check first booking
    cursor.execute("SELECT * FROM bnb WHERE reservationCode = '1234567890'")
    booking1 = cursor.fetchone()
    
    assert booking1 is not None
    assert float(booking1['amountGross']) == 450.00  # Updated from 400.00
    assert float(booking1['amountChannelFee']) == 50.00  # abs(-45) + abs(-5)
    assert 'PAYOUT_' in booking1['sourceFile']  # Source file updated
    
    # Check second booking
    cursor.execute("SELECT * FROM bnb WHERE reservationCode = '9876543210'")
    booking2 = cursor.fetchone()
    
    assert booking2 is not None
    assert float(booking2['amountGross']) == 750.00  # Updated from 700.00
    assert float(booking2['amountChannelFee']) == 83.00  # abs(-75) + abs(-8)
    
    cursor.close()


def test_payout_vat_calculation_2025(sample_payout_csv, setup_test_bookings, tmp_path):
    """Test VAT calculation for 2025 bookings (9% rate)"""
    # Write CSV to temp file
    csv_file = tmp_path / "Payout_from_2025-01-01_until_2025-01-31.csv"
    csv_file.write_text(sample_payout_csv)
    
    # Process and update
    str_processor = STRProcessor(test_mode=True)
    payout_result = str_processor._process_booking_payout(str(csv_file))
    
    str_db = STRDatabase(test_mode=True)
    str_db.update_from_payout(payout_result['updates'])
    
    # Verify VAT calculation (9% for 2025)
    db = DatabaseManager(test_mode=True)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM bnb WHERE reservationCode = '1234567890'")
    booking = cursor.fetchone()
    
    # VAT should be calculated as: (450 / 109) * 9 = 37.16
    expected_vat = round((450.00 / 109) * 9, 2)
    assert float(booking['amountVat']) == expected_vat
    
    cursor.close()


def test_payout_vat_calculation_2026(setup_test_bookings, tmp_path):
    """Test VAT calculation for 2026 bookings (21% rate)"""
    # First insert a 2026 booking
    db = DatabaseManager(test_mode=True)
    str_db = STRDatabase(test_mode=True)
    
    booking_2026 = {
        'sourceFile': 'test_booking.xlsx',
        'channel': 'booking.com',
        'listing': 'Green Studio',
        'checkinDate': '2026-02-15',
        'checkoutDate': '2026-02-18',
        'nights': 3,
        'guests': 2,
        'amountGross': 400.00,
        'amountChannelFee': 40.00,
        'amountVat': 33.03,
        'amountTouristTax': 22.00,
        'amountNett': 304.97,
        'guestName': 'Test Guest 2026',
        'phone': '',
        'reservationCode': '2026123456',
        'reservationDate': '2026-01-01',
        'status': 'realised',
        'pricePerNight': 101.66,
        'daysBeforeReservation': 45,
        'addInfo': '',
        'year': 2026,
        'q': 1,
        'm': 2
    }
    
    str_db.insert_realised_bookings([booking_2026])
    
    # Create Payout CSV with 2026 booking
    csv_content = """Type/Transaction type,Reference number,Check-in date,Check-out date,Room nights,Gross amount,Commission,Payments Service Fee,Tax/VAT
Reservation,2026123456,2026-02-15,2026-02-18,3,450.00,-45.00,-5.00,7.50
"""
    
    csv_file = tmp_path / "Payout_from_2026-02-01_until_2026-02-28.csv"
    csv_file.write_text(csv_content)
    
    # Process and update
    str_processor = STRProcessor(test_mode=True)
    payout_result = str_processor._process_booking_payout(str(csv_file))
    
    str_db.update_from_payout(payout_result['updates'])
    
    # Verify VAT calculation (21% for 2026)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM bnb WHERE reservationCode = '2026123456'")
    booking = cursor.fetchone()
    
    # VAT should be calculated as: (450 / 121) * 21 = 78.10
    expected_vat = round((450.00 / 121) * 21, 2)
    assert float(booking['amountVat']) == expected_vat
    
    cursor.close()


def test_payout_tourist_tax_calculation(sample_payout_csv, setup_test_bookings, tmp_path):
    """Test tourist tax calculation from payout data"""
    # Write CSV to temp file
    csv_file = tmp_path / "Payout_from_2025-01-01_until_2025-01-31.csv"
    csv_file.write_text(sample_payout_csv)
    
    # Process and update
    str_processor = STRProcessor(test_mode=True)
    payout_result = str_processor._process_booking_payout(str(csv_file))
    
    str_db = STRDatabase(test_mode=True)
    str_db.update_from_payout(payout_result['updates'])
    
    # Verify tourist tax calculation
    db = DatabaseManager(test_mode=True)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM bnb WHERE reservationCode = '1234567890'")
    booking = cursor.fetchone()
    
    # Tourist tax calculation:
    # 1. VAT-exclusive amount = 450 - 37.16 = 412.84
    # 2. Tourist tax = (412.84 / 106.02) * 6.02 = 23.43
    vat = round((450.00 / 109) * 9, 2)
    vat_exclusive = 450.00 - vat
    expected_tourist_tax = round((vat_exclusive / 106.02) * 6.02, 2)
    
    assert float(booking['amountTouristTax']) == expected_tourist_tax
    
    cursor.close()


def test_payout_empty_csv(tmp_path):
    """Test processing empty Payout CSV"""
    csv_content = """Type/Transaction type,Reference number,Check-in date,Check-out date,Room nights,Gross amount,Commission,Payments Service Fee,Tax/VAT
"""
    
    csv_file = tmp_path / "Payout_from_2025-01-01_until_2025-01-31.csv"
    csv_file.write_text(csv_content)
    
    str_processor = STRProcessor(test_mode=True)
    payout_result = str_processor._process_booking_payout(str(csv_file))
    
    assert payout_result['summary']['reservation_rows'] == 0
    assert payout_result['summary']['updated_count'] == 0
    assert len(payout_result['updates']) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

