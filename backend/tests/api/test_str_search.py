"""
Test script for STR Invoice Generator search functionality
Tests the /api/str-invoice/search-booking endpoint
"""
import requests
import json

# Test configuration
BASE_URL = "http://127.0.0.1:5000"
SEARCH_ENDPOINT = f"{BASE_URL}/api/str-invoice/search-booking"

def test_search_booking(query):
    """Test the search booking endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing search with query: '{query}'")
    print(f"{'='*60}")
    
    try:
        # Make GET request to search endpoint with proper headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'http://localhost:3000'
        }
        response = requests.get(SEARCH_ENDPOINT, params={'query': query}, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        # Parse JSON response
        data = response.json()
        print(f"\nResponse Data:")
        print(json.dumps(data, indent=2, default=str))
        
        # Validate response structure
        if response.status_code == 200:
            if data.get('success'):
                bookings = data.get('bookings', [])
                print(f"\n✅ Search successful!")
                print(f"Found {len(bookings)} booking(s)")
                
                # Display booking details
                if bookings:
                    print(f"\nBooking Details:")
                    for i, booking in enumerate(bookings, 1):
                        print(f"\n  Booking {i}:")
                        print(f"    Reservation Code: {booking.get('reservationCode')}")
                        print(f"    Guest Name: {booking.get('guestName')}")
                        print(f"    Channel: {booking.get('channel')}")
                        print(f"    Listing: {booking.get('listing')}")
                        print(f"    Check-in: {booking.get('checkinDate')}")
                        print(f"    Check-out: {booking.get('checkoutDate')}")
                        print(f"    Nights: {booking.get('nights')}")
                        print(f"    Guests: {booking.get('guests')}")
                        print(f"    Amount Gross: €{booking.get('amountGross')}")
                else:
                    print(f"\n⚠️  No bookings found for query: '{query}'")
                
                return True
            else:
                print(f"\n❌ Search failed: {data.get('error')}")
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
        return False

def test_empty_query():
    """Test with empty query (should return error)"""
    print(f"\n{'='*60}")
    print(f"Testing with empty query (should fail)")
    print(f"{'='*60}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'http://localhost:3000'
        }
        response = requests.get(SEARCH_ENDPOINT, params={'query': ''}, headers=headers, timeout=10)
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(data, indent=2)}")
        
        if response.status_code == 400 and not data.get('success'):
            print(f"\n✅ Correctly rejected empty query")
            return True
        else:
            print(f"\n❌ Should have rejected empty query")
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("STR Invoice Generator - Search Functionality Test")
    print("="*60)
    
    # Test 1: Empty query (should fail)
    test_empty_query()
    
    # Test 2: Search by partial guest name
    test_search_booking("Smith")
    
    # Test 3: Search by reservation code
    test_search_booking("RES")
    
    # Test 4: Search with common term
    test_search_booking("booking")
    
    # Test 5: Search with single character
    test_search_booking("a")
    
    print("\n" + "="*60)
    print("Test Suite Complete")
    print("="*60)

if __name__ == "__main__":
    main()
