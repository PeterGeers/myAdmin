#!/usr/bin/env python3
"""
Analyze year closure data inconsistency in Railway database
- Check for OpeningBalance transactions in mutaties
- Check year_closure_status table
- Identify the gap
"""
import os
import sys
from datetime import datetime

# Override to connect to Railway
os.environ['DB_HOST'] = 'shinkansen.proxy.rlwy.net'
os.environ['DB_PORT'] = '42375'
os.environ['DB_USER'] = 'root'
os.environ['DB_PASSWORD'] = 'Kx9mP2vL8nQ5wR7jT4MyAdmin2026'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

from database import DatabaseManager

def analyze_year_closure():
    """Analyze the year closure data inconsistency"""
    try:
        db = DatabaseManager(test_mode=False)
        print("✅ Connected to Railway MySQL database")
        print(f"Host: {os.getenv('DB_HOST')}")
        print(f"Database: {os.getenv('DB_NAME')}\n")
        
        # 1. Check for OpeningBalance transactions
        print("="*80)
        print("1. OPENING BALANCE TRANSACTIONS IN MUTATIES TABLE")
        print("="*80)
        
        opening_balance_query = """
            SELECT 
                administration,
                TransactionNumber,
                TransactionDate,
                COUNT(*) as transaction_count,
                SUM(TransactionAmount) as total_amount
            FROM mutaties
            WHERE TransactionNumber LIKE 'OpeningBalance%'
            GROUP BY administration, TransactionNumber, TransactionDate
            ORDER BY administration, TransactionDate
        """
        
        opening_balances = db.execute_query(opening_balance_query)
        
        if opening_balances:
            print(f"Found {len(opening_balances)} OpeningBalance transaction groups:\n")
            for ob in opening_balances:
                print(f"  Administration: {ob['administration']}")
                print(f"  Transaction: {ob['TransactionNumber']}")
                print(f"  Date: {ob['TransactionDate']}")
                print(f"  Count: {ob['transaction_count']} records")
                print(f"  Total: €{ob['total_amount']:,.2f}")
                print("-"*80)
        else:
            print("  ⚠️  No OpeningBalance transactions found")
        
        # 2. Check year_closure_status table
        print("\n" + "="*80)
        print("2. YEAR_CLOSURE_STATUS TABLE")
        print("="*80)
        
        closure_status_query = """
            SELECT 
                administration,
                year,
                closed_date,
                closed_by,
                closure_transaction_number,
                opening_balance_transaction_number,
                status
            FROM year_closure_status
            ORDER BY administration, year DESC
        """
        
        closure_statuses = db.execute_query(closure_status_query)
        
        if closure_statuses:
            print(f"Found {len(closure_statuses)} year closure records:\n")
            for cs in closure_statuses:
                print(f"  Administration: {cs['administration']}")
                print(f"  Year: {cs['year']}")
                print(f"  Status: {cs['status']}")
                print(f"  Closed: {cs['closed_date']} by {cs['closed_by']}")
                print(f"  Closure Transaction: {cs['closure_transaction_number']}")
                print(f"  Opening Balance Transaction: {cs['opening_balance_transaction_number']}")
                print("-"*80)
        else:
            print("  ⚠️  Table is EMPTY - This is the problem!")
        
        # 3. Extract years from OpeningBalance transactions
        print("\n" + "="*80)
        print("3. ANALYSIS: YEARS WITH OPENING BALANCES")
        print("="*80)
        
        if opening_balances:
            years_with_ob = {}
            for ob in opening_balances:
                admin = ob['administration']
                trans_num = ob['TransactionNumber']
                # Extract year from "OpeningBalance YYYY"
                year = trans_num.replace('OpeningBalance ', '').strip()
                
                if admin not in years_with_ob:
                    years_with_ob[admin] = []
                years_with_ob[admin].append(year)
            
            print("Years that should have closure records:\n")
            for admin, years in years_with_ob.items():
                print(f"  {admin}: {', '.join(sorted(years))}")
        
        # 4. Check for YearClose transactions
        print("\n" + "="*80)
        print("4. YEAR CLOSE TRANSACTIONS IN MUTATIES TABLE")
        print("="*80)
        
        year_close_query = """
            SELECT 
                administration,
                TransactionNumber,
                TransactionDate,
                COUNT(*) as transaction_count
            FROM mutaties
            WHERE TransactionNumber LIKE 'YearClose%'
            GROUP BY administration, TransactionNumber, TransactionDate
            ORDER BY administration, TransactionDate
        """
        
        year_closes = db.execute_query(year_close_query)
        
        if year_closes:
            print(f"Found {len(year_closes)} YearClose transaction groups:\n")
            for yc in year_closes:
                print(f"  Administration: {yc['administration']}")
                print(f"  Transaction: {yc['TransactionNumber']}")
                print(f"  Date: {yc['TransactionDate']}")
                print(f"  Count: {yc['transaction_count']} records")
                print("-"*80)
        else:
            print("  ⚠️  No YearClose transactions found")
        
        # 5. Summary and diagnosis
        print("\n" + "="*80)
        print("5. DIAGNOSIS")
        print("="*80)
        
        print("\n📊 FINDINGS:")
        print(f"  • OpeningBalance transactions: {len(opening_balances) if opening_balances else 0}")
        print(f"  • YearClose transactions: {len(year_closes) if year_closes else 0}")
        print(f"  • year_closure_status records: {len(closure_statuses) if closure_statuses else 0}")
        
        print("\n🔍 ROOT CAUSE:")
        if opening_balances and not closure_statuses:
            print("  ❌ CRITICAL: Opening balance transactions exist but year_closure_status is empty!")
            print("  This means:")
            print("    1. Year-end closures were performed (OpeningBalance created)")
            print("    2. But the year_closure_status table was NOT populated")
            print("    3. This could be due to:")
            print("       - Migration from old system without status tracking")
            print("       - Manual SQL inserts bypassing the service layer")
            print("       - Database restore from partial backup")
            print("       - Bug in year-end closure process")
        
        print("\n⚠️  IMPACT:")
        print("  • Year-end closure UI will show years as 'available' even though they're closed")
        print("  • Risk of duplicate closures")
        print("  • Audit trail is incomplete")
        print("  • Cannot track who closed which years")
        
        print("\n💡 RECOMMENDED ACTIONS:")
        print("  1. Verify data integrity: Check if OpeningBalance + YearClose pairs match")
        print("  2. Backfill year_closure_status from existing transactions")
        print("  3. Add validation to prevent future inconsistencies")
        print("  4. Consider adding database constraints")
        
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_year_closure()
