#!/usr/bin/env python3
"""
Fix Future Booking Status
Updates bookings that have future check-in dates but are marked as 'realised' to 'planned'
"""

import sys
from pathlib import Path
from datetime import date, datetime

# Add backend/src to path
backend_src = Path(__file__).parent / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

def fix_future_bookings(dry_run=True):
    """
    Find and fix bookings with future check-in dates that are marked as 'realised'
    
    Args:
        dry_run: If True, only show what would be fixed without making changes
    """
    print("=" * 70)
    print("🔍 Checking for Future Bookings with Wrong Status")
    print("=" * 70)
    print()
    
    today = date.today()
    print(f"Today's date: {today}")
    print()
    
    try:
        db = DatabaseManager()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Find bookings with future check-in dates but status='realised'
        query = """
        SELECT 
            id,
            channel,
            listing,
            guestName,
            checkinDate,
            checkoutDate,
            nights,
            guests,
            amountGross,
            amountChannelFee,
            amountNett,
            reservationCode,
            status
        FROM bnb
        WHERE status = 'realised'
        AND checkinDate > %s
        ORDER BY checkinDate
        """
        
        cursor.execute(query, (today,))
        wrong_status_bookings = cursor.fetchall()
        
        if not wrong_status_bookings:
            print("✅ No bookings found with wrong status!")
            print("   All future bookings are correctly marked as 'planned'")
            cursor.close()
            conn.close()
            return
        
        print(f"❌ Found {len(wrong_status_bookings)} bookings with wrong status:")
        print()
        
        # Display the bookings
        print(f"{'ID':<6} {'Channel':<15} {'Guest':<25} {'Check-in':<12} {'Nights':<7} {'Status':<10}")
        print("-" * 90)
        
        for booking in wrong_status_bookings:
            print(f"{booking['id']:<6} "
                  f"{booking['channel']:<15} "
                  f"{booking['guestName'][:24]:<25} "
                  f"{str(booking['checkinDate']):<12} "
                  f"{booking['nights']:<7} "
                  f"{booking['status']:<10}")
        
        print()
        print("=" * 70)
        
        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
            print()
            print("To fix these bookings, run:")
            print("  python backend/fix_future_booking_status.py --fix")
        else:
            print("🔧 FIXING MODE - Updating bookings...")
            print()
            
            # Update the bookings
            update_query = """
            UPDATE bnb
            SET status = 'planned'
            WHERE id = %s
            """
            
            updated = 0
            for booking in wrong_status_bookings:
                cursor.execute(update_query, (booking['id'],))
                updated += 1
                print(f"  ✅ Updated booking ID {booking['id']} ({booking['guestName']}) to 'planned'")
            
            conn.commit()
            print()
            print(f"✅ Successfully updated {updated} bookings!")
            print()
            print("📝 Next steps:")
            print("  1. These bookings should now be moved from 'bnb' to 'bnbplanned' table")
            print("  2. Re-import the file to properly categorize them")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Fix future bookings that are incorrectly marked as realised'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Actually fix the bookings (default is dry-run mode)'
    )
    
    args = parser.parse_args()
    
    fix_future_bookings(dry_run=not args.fix)


if __name__ == '__main__':
    main()
