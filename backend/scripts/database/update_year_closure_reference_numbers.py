"""
Update ReferenceNumber for existing year-end closure transactions

This script updates the ReferenceNumber field for:
- OpeningBalance records -> 'Opening Balance'
- YearClose records -> 'Year Closure'
"""

import sys
import os

# Add src directory to path to import database module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from database import DatabaseManager


def update_reference_numbers(test_mode=False):
    """Update ReferenceNumber for year-end closure transactions"""
    
    db = DatabaseManager(test_mode=test_mode)
    
    print("=" * 80)
    print("UPDATE YEAR-END CLOSURE REFERENCE NUMBERS")
    print("=" * 80)
    print()
    
    # Get connection for transaction
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Update OpeningBalance records
        print("Updating OpeningBalance records...")
        update_opening = """
            UPDATE mutaties
            SET ReferenceNumber = 'Opening Balance'
            WHERE TransactionNumber LIKE 'OpeningBalance%'
            AND (ReferenceNumber IS NULL OR ReferenceNumber = '')
        """
        cursor.execute(update_opening)
        opening_updated = cursor.rowcount
        print(f"  ✅ Updated {opening_updated} OpeningBalance records")
        
        # Update YearClose records
        print("\nUpdating YearClose records...")
        update_yearclose = """
            UPDATE mutaties
            SET ReferenceNumber = 'Year Closure'
            WHERE TransactionNumber LIKE 'YearClose%'
            AND (ReferenceNumber IS NULL OR ReferenceNumber = '')
        """
        cursor.execute(update_yearclose)
        yearclose_updated = cursor.rowcount
        print(f"  ✅ Updated {yearclose_updated} YearClose records")
        
        # Commit changes
        conn.commit()
        print("\n✅ All changes committed successfully")
        
        # Verify the updates
        print("\n" + "=" * 80)
        print("VERIFICATION")
        print("=" * 80)
        
        verify_query = """
            SELECT 
                'OpeningBalance' as RecordType,
                COUNT(*) as TotalRecords,
                SUM(CASE WHEN ReferenceNumber = 'Opening Balance' THEN 1 ELSE 0 END) as WithReferenceNumber,
                SUM(CASE WHEN ReferenceNumber IS NULL OR ReferenceNumber = '' THEN 1 ELSE 0 END) as WithoutReferenceNumber
            FROM mutaties
            WHERE TransactionNumber LIKE 'OpeningBalance%'
            
            UNION ALL
            
            SELECT 
                'YearClose' as RecordType,
                COUNT(*) as TotalRecords,
                SUM(CASE WHEN ReferenceNumber = 'Year Closure' THEN 1 ELSE 0 END) as WithReferenceNumber,
                SUM(CASE WHEN ReferenceNumber IS NULL OR ReferenceNumber = '' THEN 1 ELSE 0 END) as WithoutReferenceNumber
            FROM mutaties
            WHERE TransactionNumber LIKE 'YearClose%'
        """
        
        cursor.execute(verify_query)
        results = cursor.fetchall()
        
        print("\nRecord Type          | Total | With Ref# | Without Ref#")
        print("-" * 60)
        for row in results:
            record_type = row[0] if isinstance(row, tuple) else row['RecordType']
            total = row[1] if isinstance(row, tuple) else row['TotalRecords']
            with_ref = row[2] if isinstance(row, tuple) else row['WithReferenceNumber']
            without_ref = row[3] if isinstance(row, tuple) else row['WithoutReferenceNumber']
            print(f"{record_type:20} | {total:5} | {with_ref:9} | {without_ref:12}")
        
        # Show sample records
        print("\n" + "=" * 80)
        print("SAMPLE RECORDS (first 10)")
        print("=" * 80)
        
        sample_query = """
            SELECT 
                TransactionNumber,
                TransactionDate,
                ReferenceNumber,
                administration
            FROM mutaties
            WHERE TransactionNumber LIKE 'OpeningBalance%'
               OR TransactionNumber LIKE 'YearClose%'
            ORDER BY administration, TransactionDate
            LIMIT 10
        """
        
        cursor.execute(sample_query)
        samples = cursor.fetchall()
        
        print("\nTransaction Number      | Date       | Reference Number  | Administration")
        print("-" * 90)
        for row in samples:
            txn_num = row[0] if isinstance(row, tuple) else row['TransactionNumber']
            txn_date = row[1] if isinstance(row, tuple) else row['TransactionDate']
            ref_num = row[2] if isinstance(row, tuple) else row['ReferenceNumber']
            admin = row[3] if isinstance(row, tuple) else row['administration']
            print(f"{txn_num:23} | {str(txn_date):10} | {ref_num:17} | {admin}")
        
        print("\n✅ Update completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {str(e)}")
        raise
    
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Update ReferenceNumber for year-end closure transactions'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Use test database instead of production'
    )
    
    args = parser.parse_args()
    
    if args.test:
        print("⚠️  Using TEST database")
    else:
        print("⚠️  Using PRODUCTION database")
        response = input("\nAre you sure you want to update production data? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
    
    print()
    update_reference_numbers(test_mode=args.test)
