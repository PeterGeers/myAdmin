"""
Manual test script for Payout CSV upload API endpoint
"""
import requests
import os

# Configuration
API_URL = "http://localhost:5000/api/str/import-payout"
PAYOUT_FILE = ".kiro/specs/BDC-Algoritm-import-str_processor.py/Payout_from_2025-01-01_until_2025-12-31.csv"

def test_payout_upload():
    """Test uploading the real Payout CSV file"""
    
    # Check if file exists
    if not os.path.exists(PAYOUT_FILE):
        print(f"❌ File not found: {PAYOUT_FILE}")
        return
    
    print(f"📁 Uploading file: {PAYOUT_FILE}")
    print(f"🌐 API endpoint: {API_URL}")
    print()
    
    # Prepare file for upload
    with open(PAYOUT_FILE, 'rb') as f:
        files = {
            'file': (os.path.basename(PAYOUT_FILE), f, 'text/csv')
        }
        
        try:
            # Send POST request
            print("⏳ Sending request...")
            response = requests.post(API_URL, files=files, timeout=30)
            
            print(f"📊 Status Code: {response.status_code}")
            print()
            
            # Parse response
            if response.status_code == 200:
                result = response.json()
                
                if result.get('success'):
                    print("✅ SUCCESS!")
                    print()
                    print("📈 Processing Results:")
                    print(f"  - Total rows: {result['processing']['total_rows']}")
                    print(f"  - Reservation rows: {result['processing']['reservation_rows']}")
                    print(f"  - Updates prepared: {result['processing']['updates_prepared']}")
                    print(f"  - Processing errors: {result['processing']['processing_errors']}")
                    print()
                    print("💾 Database Results:")
                    print(f"  - Bookings updated: {result['summary']['total_updated']}")
                    print(f"  - Not found: {result['summary']['total_not_found']}")
                    print(f"  - Errors: {result['summary']['total_errors']}")
                    
                    if result['database']['not_found']:
                        print()
                        print("⚠️  Reservation codes not found in database:")
                        for code in result['database']['not_found'][:10]:  # Show first 10
                            print(f"    - {code}")
                        if len(result['database']['not_found']) > 10:
                            print(f"    ... and {len(result['database']['not_found']) - 10} more")
                    
                    if result['database']['errors']:
                        print()
                        print("❌ Database errors:")
                        for error in result['database']['errors']:
                            print(f"    - {error}")
                else:
                    print("❌ FAILED!")
                    print(f"Error: {result.get('error', 'Unknown error')}")
            else:
                print("❌ HTTP ERROR!")
                print(f"Response: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print("❌ Connection Error!")
            print("Make sure the backend server is running on http://localhost:5000")
        except requests.exceptions.Timeout:
            print("❌ Request Timeout!")
            print("The request took too long to complete")
        except Exception as e:
            print(f"❌ Unexpected Error: {e}")

if __name__ == '__main__':
    print("=" * 60)
    print("  Booking.com Payout CSV Upload Test")
    print("=" * 60)
    print()
    test_payout_upload()
    print()
    print("=" * 60)
