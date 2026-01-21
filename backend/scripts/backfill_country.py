"""
Backfill country data for existing records in bnb and bnbplanned tables

This script:
1. Reads existing records from bnb and bnbplanned tables
2. Detects country from phone (AirBNB) or addInfo (Booking.com)
3. Updates records with detected country codes
"""

import mysql.connector
import os
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from dotenv import load_dotenv
from country_detector import detect_country

# Load environment variables
load_dotenv()


def backfill_table(cursor, table_name: str, dry_run: bool = True):
    """
    Backfill country data for a specific table
    
    Args:
        cursor: Database cursor
        table_name: Name of table (bnb or bnbplanned)
        dry_run: If True, only show what would be updated without making changes
    """
    print(f"\n{'='*60}")
    print(f"Processing table: {table_name}")
    print(f"{'='*60}\n")
    
    # Get records that need country detection
    query = f"""
        SELECT id, channel, phone, addInfo, country
        FROM {table_name}
        WHERE country IS NULL
        ORDER BY id
    """
    
    cursor.execute(query)
    records = cursor.fetchall()
    
    print(f"Found {len(records)} records without country data\n")
    
    if len(records) == 0:
        print("✓ No records to update")
        return
    
    # Statistics
    stats = {
        'total': len(records),
        'detected': 0,
        'not_detected': 0,
        'by_channel': {}
    }
    
    updates = []
    
    for record_id, channel, phone, addinfo, current_country in records:
        # Detect country
        detected_country = detect_country(channel, phone, addinfo)
        
        if detected_country:
            stats['detected'] += 1
            stats['by_channel'][channel] = stats['by_channel'].get(channel, 0) + 1
            updates.append((detected_country, record_id))
            
            if dry_run:
                print(f"  ID {record_id:6d} | {channel:15s} | Would set country: {detected_country}")
        else:
            stats['not_detected'] += 1
    
    # Print statistics
    print(f"\n{'='*60}")
    print("Statistics:")
    print(f"{'='*60}")
    print(f"Total records:        {stats['total']}")
    print(f"Country detected:     {stats['detected']} ({stats['detected']/stats['total']*100:.1f}%)")
    print(f"Country not detected: {stats['not_detected']} ({stats['not_detected']/stats['total']*100:.1f}%)")
    
    if stats['by_channel']:
        print(f"\nDetections by channel:")
        for ch, count in sorted(stats['by_channel'].items()):
            print(f"  {ch:15s}: {count}")
    
    # Perform updates if not dry run
    if not dry_run and updates:
        print(f"\n{'='*60}")
        print(f"Updating {len(updates)} records...")
        print(f"{'='*60}\n")
        
        update_query = f"""
            UPDATE {table_name}
            SET country = %s
            WHERE id = %s
        """
        
        cursor.executemany(update_query, updates)
        print(f"✓ Successfully updated {len(updates)} records")
    elif dry_run and updates:
        print(f"\nDRY RUN MODE: No changes were made")
        print(f"  Run with --execute flag to apply changes")


def run_backfill(dry_run: bool = True):
    """Run the backfill process"""
    
    # Database connection
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME'),
        'port': int(os.getenv('DB_PORT', 3306))
    }
    
    mode = "DRY RUN" if dry_run else "EXECUTE"
    print(f"\n{'='*60}")
    print(f"Country Backfill Script - {mode} MODE")
    print(f"{'='*60}")
    print(f"Database: {db_config['database']} at {db_config['host']}")
    print(f"{'='*60}\n")
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Backfill bnb table (actual bookings)
        backfill_table(cursor, 'bnb', dry_run)
        
        # Backfill bnbplanned table (planned bookings)
        backfill_table(cursor, 'bnbplanned', dry_run)
        
        # Commit changes if not dry run
        if not dry_run:
            conn.commit()
            print(f"\n{'='*60}")
            print("✓ All changes committed successfully")
            print(f"{'='*60}\n")
        
        cursor.close()
        conn.close()
        
    except mysql.connector.Error as e:
        print(f"\n✗ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    # Check for --execute flag
    execute = '--execute' in sys.argv or '-e' in sys.argv
    
    if not execute:
        print("\n" + "="*60)
        print("WARNING: RUNNING IN DRY RUN MODE")
        print("="*60)
        print("This will show what would be updated without making changes.")
        print("To actually update the database, run with --execute flag:")
        print("  python scripts/backfill_country.py --execute")
        print("="*60 + "\n")
    
    run_backfill(dry_run=not execute)
