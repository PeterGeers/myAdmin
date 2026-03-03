"""
Migrate Historical Opening Balances

This script creates opening balance transactions for all historical years
that don't already have them. It uses the same logic as the year-end closure
feature, including VAT netting.

Usage:
    python migrate_historical_opening_balances.py [--dry-run] [--tenant TENANT_NAME]

Options:
    --dry-run: Show what would be done without making changes
    --tenant: Process only specific tenant (default: all tenants)
"""

import sys
import os
from datetime import datetime
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database import DatabaseManager
from services.year_end_service import YearEndClosureService


def get_years_needing_migration(db, administration=None):
    """
    Find years that have transactions but no opening balance records.
    
    Returns: List of (administration, year) tuples
    """
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all years with transactions
    query = """
        SELECT DISTINCT 
            administration,
            YEAR(TransactionDate) as year
        FROM mutaties
        WHERE 1=1
    """
    
    if administration:
        query += " AND administration = %s"
        cursor.execute(query, (administration,))
    else:
        cursor.execute(query)
    
    all_years = cursor.fetchall()
    
    # Filter out years that already have opening balances
    years_needing_migration = []
    
    for row in all_years:
        admin = row['administration']
        year = row['year']
        
        # Check if opening balance exists
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM mutaties
            WHERE TransactionNumber = %s
            AND administration = %s
        """, (f'OpeningBalance {year}', admin))
        
        result = cursor.fetchone()
        if result['count'] == 0:
            years_needing_migration.append((admin, year))
    
    cursor.close()
    conn.close()
    
    return sorted(years_needing_migration)


def get_first_year_with_transactions(db, administration):
    """Get the first year with transactions for an administration."""
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT MIN(YEAR(TransactionDate)) as first_year
        FROM mutaties
        WHERE administration = %s
    """, (administration,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return result['first_year'] if result else None


def migrate_opening_balances(dry_run=False, tenant=None):
    """
    Migrate opening balances for historical years.
    """
    print("=" * 80)
    print("Historical Opening Balance Migration")
    print("=" * 80)
    print()
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()
    
    # Initialize database and service
    db = DatabaseManager(test_mode=False)
    service = YearEndClosureService()
    
    # Get years needing migration
    years_to_migrate = get_years_needing_migration(db, tenant)
    
    if not years_to_migrate:
        print("✅ No years need migration - all years already have opening balances")
        return
    
    print(f"Found {len(years_to_migrate)} year(s) needing opening balance records:")
    print()
    
    # Group by administration
    by_admin = {}
    for admin, year in years_to_migrate:
        if admin not in by_admin:
            by_admin[admin] = []
        by_admin[admin].append(year)
    
    for admin, years in by_admin.items():
        print(f"  {admin}: {len(years)} years ({min(years)}-{max(years)})")
    
    print()
    
    if dry_run:
        print("Dry run complete. Run without --dry-run to apply changes.")
        return
    
    # Confirm before proceeding
    response = input("Proceed with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        return
    
    print()
    print("Starting migration...")
    print()
    
    # Process each year
    success_count = 0
    error_count = 0
    
    for admin, year in years_to_migrate:
        # Skip first year (no previous year to get opening balance from)
        first_year = get_first_year_with_transactions(db, admin)
        if year == first_year:
            print(f"⏭️  Skipping {admin} {year} (first year with transactions)")
            continue
        
        try:
            print(f"Processing {admin} {year}...")
            
            # Create opening balance using the service
            # This will use the same logic as the UI, including VAT netting
            result = service._create_opening_balances(admin, year)
            
            if result['success']:
                print(f"  ✅ Created opening balance: {result['transaction_number']}")
                print(f"     Accounts: {result['account_count']}")
                success_count += 1
            else:
                print(f"  ⚠️  No opening balance needed (all balances zero)")
                success_count += 1
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            error_count += 1
    
    print()
    print("=" * 80)
    print("Migration Summary")
    print("=" * 80)
    print(f"✅ Successful: {success_count}")
    print(f"❌ Errors: {error_count}")
    print(f"📊 Total processed: {success_count + error_count}")
    print()
    
    if error_count == 0:
        print("🎉 Migration completed successfully!")
    else:
        print("⚠️  Migration completed with errors. Review the output above.")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate historical opening balances')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--tenant', type=str, help='Process only specific tenant')
    
    args = parser.parse_args()
    
    try:
        migrate_opening_balances(dry_run=args.dry_run, tenant=args.tenant)
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
