"""
Direct database test for vw_bnb_total view
Tests that the view exists and can be queried
"""
import sys
sys.path.insert(0, 'src')

from database import DatabaseManager

def test_view_exists():
    """Test if vw_bnb_total view exists"""
    print("\n" + "="*60)
    print("Testing vw_bnb_total View")
    print("="*60)
    
    try:
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Test 1: Check if view exists
        print("\n1. Checking if view exists...")
        cursor.execute("SHOW FULL TABLES WHERE Table_type = 'VIEW'")
        views = cursor.fetchall()
        
        view_names = [v[f'Tables_in_{db.config["database"]}'] for v in views]
        print(f"   Found {len(views)} views in database")
        
        if 'vw_bnb_total' in view_names:
            print(f"   ✅ vw_bnb_total view EXISTS")
        else:
            print(f"   ❌ vw_bnb_total view NOT FOUND")
            print(f"   Available views: {view_names}")
            cursor.close()
            connection.close()
            return False
        
        # Test 2: Query the view structure
        print("\n2. Checking view structure...")
        cursor.execute("DESCRIBE vw_bnb_total")
        columns = cursor.fetchall()
        print(f"   View has {len(columns)} columns:")
        for col in columns[:10]:  # Show first 10 columns
            print(f"     - {col['Field']} ({col['Type']})")
        if len(columns) > 10:
            print(f"     ... and {len(columns) - 10} more columns")
        
        # Test 3: Count records
        print("\n3. Counting records...")
        cursor.execute("SELECT COUNT(*) as count FROM vw_bnb_total")
        result = cursor.fetchone()
        record_count = result['count']
        print(f"   ✅ View contains {record_count} records")
        
        # Test 4: Sample query (like the search endpoint)
        if record_count > 0:
            print("\n4. Testing sample search query...")
            search_query = """
            SELECT reservationCode, guestName, channel, listing, 
                   checkinDate, checkoutDate, nights, guests, amountGross
            FROM vw_bnb_total 
            ORDER BY checkinDate DESC
            LIMIT 5
            """
            cursor.execute(search_query)
            results = cursor.fetchall()
            
            print(f"   ✅ Retrieved {len(results)} sample records:")
            for i, booking in enumerate(results, 1):
                print(f"\n   Booking {i}:")
                print(f"     Reservation: {booking.get('reservationCode')}")
                print(f"     Guest: {booking.get('guestName')}")
                print(f"     Channel: {booking.get('channel')}")
                print(f"     Check-in: {booking.get('checkinDate')}")
                print(f"     Amount: €{booking.get('amountGross')}")
        
        # Test 5: Test search with LIKE (as used in the endpoint)
        if record_count > 0:
            print("\n5. Testing LIKE search (as used in endpoint)...")
            search_pattern = "%a%"  # Search for anything with 'a'
            search_query = """
            SELECT COUNT(*) as count FROM vw_bnb_total 
            WHERE guestName LIKE %s OR reservationCode LIKE %s
            """
            cursor.execute(search_query, [search_pattern, search_pattern])
            result = cursor.fetchone()
            match_count = result['count']
            print(f"   ✅ Found {match_count} records matching pattern '%a%'")
        
        cursor.close()
        connection.close()
        
        print("\n" + "="*60)
        print("✅ All tests PASSED - vw_bnb_total is working correctly!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_view_exists()
    sys.exit(0 if success else 1)
