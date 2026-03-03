"""
Populate Year Closure Status Table with Historical Data

This script populates the year_closure_status table for all years that have
opening balance records, marking them as historically closed.

For each year from start until 2024:
- closure_transaction_number: "Afsluiting YYYY" (if exists)
- opening_balance_transaction_number: "OpeningBalance YYYY+1"
- closed_date: December 31 of that year
- closed_by: 'system_migration'
- notes: 'Historical closure - migrated from opening balance records'
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager

def populate_closure_history():
    """Populate year_closure_status with historical data"""
    
    db = DatabaseManager(test_mode=False)
    
    print("=" * 70)
    print("POPULATE YEAR CLOSURE HISTORY")
    print("=" * 70)
    
    # Step 1: Find all tenants with opening balance records
    print("\n1. Finding tenants with opening balance records...")
    
    query_tenants = """
        SELECT DISTINCT administration
        FROM mutaties
        WHERE TransactionNumber LIKE 'OpeningBalance %'
        ORDER BY administration
    """
    
    tenants = db.execute_query(query_tenants)
    
    if not tenants:
        print("   ❌ No tenants found with opening balance records")
        return
    
    print(f"   ✅ Found {len(tenants)} tenant(s) with opening balance records:")
    for tenant in tenants:
        print(f"      - {tenant['administration']}")
    
    # Step 2: For each tenant, find years with opening balances
    total_inserted = 0
    total_skipped = 0
    
    for tenant_row in tenants:
        administration = tenant_row['administration']
        
        print(f"\n2. Processing tenant: {administration}")
        print("-" * 70)
        
        # Find all opening balance years for this tenant
        query_years = """
            SELECT DISTINCT 
                CAST(SUBSTRING(TransactionNumber, 16) AS UNSIGNED) as opening_year
            FROM mutaties
            WHERE administration = %s
            AND TransactionNumber LIKE 'OpeningBalance %%'
            AND TransactionNumber REGEXP 'OpeningBalance [0-9]+'
            ORDER BY opening_year
        """
        
        years_result = db.execute_query(query_years, [administration])
        
        if not years_result:
            print(f"   ⚠️  No opening balance years found for {administration}")
            continue
        
        opening_years = [row['opening_year'] for row in years_result if row['opening_year']]
        print(f"   ✅ Found opening balances for years: {opening_years}")
        
        # For each opening balance year, the previous year was closed
        for opening_year in opening_years:
            if opening_year > 2025:  # Only process up to 2024 closures
                continue
            
            closed_year = opening_year - 1
            
            # Check if this year is already in year_closure_status
            check_query = """
                SELECT COUNT(*) as count
                FROM year_closure_status
                WHERE administration = %s
                AND year = %s
            """
            
            existing = db.execute_query(check_query, [administration, closed_year])
            if existing and existing[0]['count'] > 0:
                print(f"   ⏭️  Year {closed_year} already in closure status - skipping")
                total_skipped += 1
                continue
            
            # Check if "Afsluiting YYYY" transaction exists
            closure_txn_number = f"Afsluiting {closed_year}"
            check_closure_query = """
                SELECT COUNT(*) as count
                FROM mutaties
                WHERE administration = %s
                AND TransactionNumber = %s
            """
            
            closure_exists = db.execute_query(check_closure_query, [administration, closure_txn_number])
            has_closure_txn = closure_exists and closure_exists[0]['count'] > 0
            
            if not has_closure_txn:
                closure_txn_number = None  # No closure transaction found
            
            # Opening balance transaction number
            opening_txn_number = f"OpeningBalance {opening_year}"
            
            # Insert into year_closure_status
            insert_query = """
                INSERT INTO year_closure_status (
                    administration,
                    year,
                    closed_date,
                    closed_by,
                    closure_transaction_number,
                    opening_balance_transaction_number,
                    notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            closed_date = f"{closed_year}-12-31 23:59:59"
            closed_by = "system_migration"
            notes = f"Historical closure - migrated from opening balance records. Opening balance: {opening_txn_number}"
            
            if not has_closure_txn:
                notes += f". No 'Afsluiting {closed_year}' transaction found."
            
            try:
                db.execute_query(
                    insert_query,
                    [
                        administration,
                        closed_year,
                        closed_date,
                        closed_by,
                        closure_txn_number,
                        opening_txn_number,
                        notes
                    ],
                    fetch=False,
                    commit=True
                )
                
                status = "✅" if has_closure_txn else "⚠️"
                closure_info = f"with closure txn" if has_closure_txn else "NO closure txn"
                print(f"   {status} Inserted year {closed_year} ({closure_info})")
                total_inserted += 1
                
            except Exception as e:
                print(f"   ❌ Error inserting year {closed_year}: {e}")
    
    # Step 3: Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total records inserted: {total_inserted}")
    print(f"Total records skipped (already exist): {total_skipped}")
    print("=" * 70)
    
    # Step 4: Verify results
    print("\n3. Verifying results...")
    
    for tenant_row in tenants:
        administration = tenant_row['administration']
        
        verify_query = """
            SELECT year, closed_date, closure_transaction_number, opening_balance_transaction_number
            FROM year_closure_status
            WHERE administration = %s
            ORDER BY year DESC
            LIMIT 5
        """
        
        results = db.execute_query(verify_query, [administration])
        
        if results:
            print(f"\n   {administration} - Most recent closed years:")
            for row in results:
                closure_status = "✅" if row['closure_transaction_number'] else "⚠️ "
                print(f"      {closure_status} {row['year']}: {row['opening_balance_transaction_number']}")
        else:
            print(f"\n   {administration} - No closed years found")
    
    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Check FIN Reports → Year-End Closure tab")
    print("2. Verify closed years appear in the table")
    print("3. Available years should now start from 2025")
    print("=" * 70)

if __name__ == '__main__':
    try:
        populate_closure_history()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
