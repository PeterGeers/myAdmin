"""Test if STR Invoice API is responding correctly"""
import requests
import json

def test_api_endpoint():
    """Test the actual API endpoint"""
    base_url = "http://localhost:5000"
    
    print("\n=== Testing STR Invoice API ===\n")
    
    # Test 1: Search with a known guest name
    print("1. Testing search endpoint with 'Davies'...")
    try:
        response = requests.get(f"{base_url}/api/str-invoice/search-booking?query=Davies", timeout=5)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success')}")
            print(f"   Results: {len(data.get('bookings', []))} bookings found")
            
            if data.get('bookings'):
                booking = data['bookings'][0]
                print(f"   Sample: {booking.get('reservationCode')} - {booking.get('guestName')}")
        else:
            print(f"   Error: {response.text}")
    except requests.exceptions.ConnectionError:
        print("   ❌ ERROR: Cannot connect to backend server at http://localhost:5000")
        print("   Is the backend server running?")
        print("   Try running: cd backend && python src/app.py")
        return False
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False
    
    # Test 2: Search with reservation code
    print("\n2. Testing search endpoint with reservation code '1089888747'...")
    try:
        response = requests.get(f"{base_url}/api/str-invoice/search-booking?query=1089888747", timeout=5)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success')}")
            print(f"   Results: {len(data.get('bookings', []))} bookings found")
            
            if data.get('bookings'):
                booking = data['bookings'][0]
                print(f"   Found: {booking.get('reservationCode')} - {booking.get('guestName')}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False
    
    # Test 3: Empty search (should return 400)
    print("\n3. Testing empty search (should return error)...")
    try:
        response = requests.get(f"{base_url}/api/str-invoice/search-booking?query=", timeout=5)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 400:
            data = response.json()
            print(f"   ✓ Correctly returns 400 error")
            print(f"   Error message: {data.get('error')}")
        else:
            print(f"   Unexpected status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False
    
    print("\n✅ API tests completed successfully!")
    print("\nIf the frontend still shows no data, check:")
    print("  1. Browser console for errors (F12)")
    print("  2. Network tab to see if requests are being made")
    print("  3. CORS configuration if frontend is on different port")
    
    return True

if __name__ == '__main__':
    test_api_endpoint()
