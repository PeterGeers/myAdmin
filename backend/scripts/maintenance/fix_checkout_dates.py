#!/usr/bin/env python3
"""
Fix Checkout Dates in BNB Table
Updates records where checkout date equals checkin date but nights > 0
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add backend/src to path
backend_src = Path(__file__).parent / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

def fix_checkout_dates(dry_run=True):
    """
    Find and fix records where checkout = checkin but nights > 0
    
    Args:
        dry_run: If True, only show what would be fixed without making changes
    """
    print("=" * 70)
    print("🔍 Checking for Records with Wrong Checkout Dates")
    print("=" * 70)
    print()
    
    try:
        db = DatabaseManager()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Find records where checkout = checkin but nights > 0
        query = """
        SELECT 
            id,
            channel,
            listing,
            guestName,
            checkinDate,
            checkoutDate,
            nights,
            reservationCode
        FROM bnb
        WHERE checkinDate = checkoutDate
        AND nights > 0
        ORDER BY id DESC
        LIMIT 100
        """
        
        cursor.execute(query)
        wrong_records = cursor.fetchall()
        
        if not wrong_records:
            print("✅ No records found with wrong checkout dates!")
            cursor.close()
            conn.close()
            return
        
        print(f"❌ Found {len(wrong_records)} records with wrong checkout dates:")
        print()
        
        # Display the records
        print(f"{'ID':<6} {'Check-in':<12} {'Check-out':<12} {'Nights':<7} {'Should be':<12} {'Guest':<25}")
        print("-" * 90)
        
        for record in wrong_records:
            checkin = record['checkinDate']
            nights = record['nights']
            correct_checkout = checkin + timedelta(days=nights)
            
            print(f"{record['id']:<6} "
                  f"{str(checkin):<12} "
                  f"{str(record['checkoutDate']):<12} "
                  f"{nights:<7} "
                  f"{str(correct_checkout):<12} "
                  f"{record['guestName'][:24]:<25}")
        
        print()
        print("=" * 70)
        
        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
            print()
            print("To fix these records, run:")
            print("  python backend/fix_checkout_dates.py --fix")
        else:
            print("🔧 FIXING MODE - Updating records...")
            print()
            
            # Update the records
            update_query = """
            UPDATE bnb
            SET checkoutDate = DATE_ADD(checkinDate, INTERVAL nights DAY)
            WHERE id = %s
            """
            
            updated = 0
            for record in wrong_records:
                cursor.execute(update_query, (record['id'],))
                updated += 1
                correct_checkout = record['checkinDate'] + timedelta(days=record['nights'])
                print(f"  ✅ Updated record ID {record['id']} - Checkout: {record['checkinDate']} → {correct_checkout}")
            
            conn.commit()
            print()
            print(f"✅ Successfully updated {updated} records!")
        
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
        description='Fix checkout dates that equal checkin dates when nights > 0'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Actually fix the records (default is dry-run mode)'
    )
    
    args = parser.parse_args()
    
    fix_checkout_dates(dry_run=not args.fix)


if __name__ == '__main__':
    main()
