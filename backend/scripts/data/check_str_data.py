"""Check if data exists in vw_bnb_total view"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def check_data():
    try:
        db = DatabaseManager(test_mode=False)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check total count
        cursor.execute('SELECT COUNT(*) as count FROM vw_bnb_total')
        result = cursor.fetchone()
        total_count = result['count']
        print(f'\n✓ Total records in vw_bnb_total: {total_count}')
        
        if total_count == 0:
            print('\n⚠️  WARNING: No data found in vw_bnb_total view!')
            print('   The view exists but contains no records.')
            
            # Check source tables
            cursor.execute('SELECT COUNT(*) as count FROM bnb')
            bnb_count = cursor.fetchone()['count']
            print(f'\n   Records in bnb table: {bnb_count}')
            
            cursor.execute('SELECT COUNT(*) as count FROM bnbplanned')
            planned_count = cursor.fetchone()['count']
            print(f'   Records in bnbplanned table: {planned_count}')
            
            if bnb_count == 0 and planned_count == 0:
                print('\n   ❌ Both source tables are empty. No bookings exist in the database.')
            else:
                print('\n   ⚠️  Source tables have data but view is empty. View definition may be incorrect.')
        else:
            # Show sample records
            cursor.execute('SELECT reservationCode, guestName, checkinDate, channel FROM vw_bnb_total LIMIT 5')
            results = cursor.fetchall()
            print('\n✓ Sample records:')
            for r in results:
                print(f'   - {r["reservationCode"]}: {r["guestName"]} ({r["checkinDate"]}) via {r["channel"]}')
        
        cursor.close()
        conn.close()
        
        return total_count > 0
        
    except Exception as e:
        print(f'\n❌ Error checking data: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print('\n=== Checking STR Invoice Data ===')
    has_data = check_data()
    
    if not has_data:
        print('\n⚠️  No data available for STR Invoice Generator')
        print('   The search will return empty results until bookings are added to the database.')
    else:
        print('\n✅ Data is available in the database')
