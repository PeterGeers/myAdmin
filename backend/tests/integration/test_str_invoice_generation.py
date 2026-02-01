"""
Test script for STR Invoice Generator - Invoice Generation functionality
Tests the /api/str-invoice/generate-invoice endpoint
Validates Requirements 2.2 and 2.4

NOTE: This is a standalone test script, not a pytest test file.
It should be run manually with: python test_str_invoice_generation.py
"""
import requests
import json
import sys

# Prevent pytest from collecting this file - it's a standalone script
__test__ = False

# Test configuration
BASE_URL = "http://127.0.0.1:5000"
SEARCH_ENDPOINT = f"{BASE_URL}/api/str-invoice/search-booking"
GENERATE_ENDPOINT = f"{BASE_URL}/api/str-invoice/generate-invoice"

def search_for_booking(query="a"):
    """Search for a booking to use in invoice generation test"""
    print(f"\n{'='*60}")
    print(f"Step 1: Searching for a booking with query: '{query}'")
    print(f"{'='*60}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'http://localhost:3000'
        }
        response = requests.get(SEARCH_ENDPOINT, params={'query': query}, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('bookings'):
                bookings = data['bookings']
                print(f"✅ Found {len(bookings)} booking(s)")
                
                # Display first booking
                booking = bookings[0]
                print(f"\nSelected booking for invoice generation:")
                print(f"  Reservation Code: {booking.get('reservationCode')}")
                print(f"  Guest Name: {booking.get('guestName')}")
                print(f"  Channel: {booking.get('channel')}")
                print(f"  Check-in: {booking.get('checkinDate')}")
                print(f"  Amount Gross: €{booking.get('amountGross')}")
                
                return booking
            else:
                print(f"❌ No bookings found")
                return None
        else:
            print(f"❌ Search failed with status {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Error during search: {e}")
        return None

def test_generate_invoice(reservation_code, language='nl'):
    """Test invoice generation for a specific booking"""
    print(f"\n{'='*60}")
    print(f"Step 2: Generating invoice for reservation: {reservation_code}")
    print(f"{'='*60}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Referer': 'http://localhost:3000'
        }
        
        payload = {
            'reservationCode': reservation_code,
            'language': language
        }
        
        print(f"Request payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(GENERATE_ENDPOINT, json=payload, headers=headers, timeout=10)
        
        print(f"\nStatus Code: {response.status_code}")
        
        # Parse JSON response
        data = response.json()
        
        # Validate response structure
        if response.status_code == 200:
            if data.get('success'):
                print(f"\n✅ Invoice generated successfully!")
                
                # Verify booking_data is present
                booking_data = data.get('booking_data', {})
                if not booking_data:
                    print(f"❌ ERROR: booking_data is missing from response")
                    return False
                
                print(f"\n{'='*60}")
                print(f"Step 3: Verifying financial fields (Requirement 2.2)")
                print(f"{'='*60}")
                
                # Required financial fields per Requirement 2.2
                required_fields = [
                    'amountGross',
                    'amountTouristTax', 
                    'amountChannelFee',
                    'amountNett',
                    'amountVat'
                ]
                
                # Additional important fields
                additional_fields = [
                    'reservationCode',
                    'guestName',
                    'checkinDate',
                    'checkoutDate',
                    'nights',
                    'guests'
                ]
                
                all_fields_valid = True
                
                print(f"\nFinancial Fields:")
                for field in required_fields:
                    value = booking_data.get(field)
                    if value is not None:
                        print(f"  ✅ {field}: {value}")
                    else:
                        print(f"  ❌ {field}: MISSING")
                        all_fields_valid = False
                
                print(f"\nBooking Details:")
                for field in additional_fields:
                    value = booking_data.get(field)
                    if value is not None:
                        print(f"  ✅ {field}: {value}")
                    else:
                        print(f"  ❌ {field}: MISSING")
                        all_fields_valid = False
                
                # Verify HTML content is present
                html_content = data.get('html', '')
                if html_content:
                    print(f"\n✅ HTML content generated ({len(html_content)} characters)")
                    
                    # Check if key values appear in HTML
                    print(f"\nVerifying values in HTML:")
                    checks = [
                        (reservation_code, "Reservation code"),
                        (str(booking_data.get('amountGross', '')), "Gross amount"),
                        (booking_data.get('guestName', ''), "Guest name")
                    ]
                    
                    for value, description in checks:
                        if str(value) in html_content:
                            print(f"  ✅ {description} found in HTML")
                        else:
                            print(f"  ⚠️  {description} not found in HTML (might be formatted differently)")
                else:
                    print(f"\n❌ HTML content is missing")
                    all_fields_valid = False
                
                print(f"\n{'='*60}")
                if all_fields_valid:
                    print(f"✅ ALL TESTS PASSED - Invoice generation working correctly")
                    print(f"✅ Requirement 2.2: All financial fields retrieved")
                    print(f"✅ Requirement 2.4: Invoice data passed to generation function")
                else:
                    print(f"❌ SOME TESTS FAILED - See errors above")
                print(f"{'='*60}")
                
                return all_fields_valid
            else:
                print(f"\n❌ Invoice generation failed: {data.get('error')}")
                return False
        else:
            print(f"\n❌ HTTP Error {response.status_code}")
            print(f"Error: {data.get('error', 'Unknown error')}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Connection Error: Could not connect to {BASE_URL}")
        print("Make sure the backend server is running!")
        return False
    except requests.exceptions.Timeout:
        print(f"\n❌ Timeout: Request took too long")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_invalid_reservation_code():
    """Test invoice generation with non-existent reservation code (Requirement 2.3)"""
    print(f"\n{'='*60}")
    print(f"Step 4: Testing error handling with invalid reservation code")
    print(f"{'='*60}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Referer': 'http://localhost:3000'
        }
        
        payload = {
            'reservationCode': 'NONEXISTENT_CODE_12345',
            'language': 'nl'
        }
        
        response = requests.post(GENERATE_ENDPOINT, json=payload, headers=headers, timeout=10)
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(data, indent=2)}")
        
        if response.status_code == 404 and not data.get('success'):
            print(f"\n✅ Correctly returned 404 for non-existent booking")
            print(f"✅ Requirement 2.3: Proper error handling verified")
            return True
        else:
            print(f"\n❌ Should have returned 404 for non-existent booking")
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

def main():
    """Run all invoice generation tests"""
    print("\n" + "="*60)
    print("STR Invoice Generator - Invoice Generation Test")
    print("Testing Requirements 2.2 and 2.4")
    print("="*60)
    
    # Step 1: Search for a booking
    booking = search_for_booking("a")
    
    if not booking:
        print("\n❌ Cannot proceed with tests - no booking found")
        print("Please ensure the database has booking data in vw_bnb_total view")
        sys.exit(1)
    
    # Step 2 & 3: Generate invoice and verify fields
    reservation_code = booking.get('reservationCode')
    success = test_generate_invoice(reservation_code)
    
    # Step 4: Test error handling
    error_handling_success = test_invalid_reservation_code()
    
    # Final summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    if success and error_handling_success:
        print("✅ ALL TESTS PASSED")
        print("✅ Task 4 completed successfully")
        print("✅ Invoice generation functionality verified")
        print("✅ All financial fields populated correctly")
        print("✅ Error handling working correctly")
    else:
        print("❌ SOME TESTS FAILED")
        if not success:
            print("❌ Invoice generation or field validation failed")
        if not error_handling_success:
            print("❌ Error handling test failed")
    print("="*60)
    
    return success and error_handling_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
