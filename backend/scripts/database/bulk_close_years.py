#!/usr/bin/env python3
"""
Bulk Year-End Closure Script

Closes all years from first year with transactions up to a specified year.
This is useful for initial setup after implementing year-end closure feature.

Usage:
    python bulk_close_years.py --administration GoodwinSolutions --up-to-year 2024
    python bulk_close_years.py --administration PeterPrive --up-to-year 2024
    python bulk_close_years.py --all --up-to-year 2024
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database import DatabaseManager
from services.year_end_service import YearEndClosureService
import argparse


def get_all_administrations(db):
    """Get list of all administrations"""
    query = """
        SELECT DISTINCT administration
        FROM mutaties
        WHERE administration IS NOT NULL
        ORDER BY administration
    """
    result = db.execute_query(query)
    return [row['administration'] for row in result]


def get_first_year(db, administration):
    """Get first year with transactions for administration"""
    query = """
        SELECT MIN(YEAR(TransactionDate)) as first_year
        FROM mutaties
        WHERE administration = %s
        AND TransactionDate IS NOT NULL
    """
    result = db.execute_query(query, [administration])
    return result[0]['first_year'] if result and result[0]['first_year'] else None


def bulk_close_years(administration, up_to_year, test_mode=False, user_email='system@bulk-closure'):
    """
    Close all years from first year to up_to_year for an administration.
    
    Args:
        administration: Tenant identifier
        up_to_year: Last year to close (inclusive)
        test_mode: Use test database
        user_email: Email to record in closure status
    """
    print(f"\n{'='*80}")
    print(f"Bulk Year-End Closure: {administration}")
    print(f"{'='*80}\n")
    
    # Initialize services
    db = DatabaseManager(test_mode=test_mode)
    service = YearEndClosureService(test_mode=test_mode)
    
    # Get first year
    first_year = get_first_year(db, administration)
    
    if not first_year:
        print(f"❌ No transactions found for {administration}")
        return False
    
    print(f"First year with transactions: {first_year}")
    print(f"Closing years: {first_year} to {up_to_year}")
    print(f"Total years to close: {up_to_year - first_year + 1}\n")
    
    # Close each year sequentially
    success_count = 0
    failed_years = []
    
    for year in range(first_year, up_to_year + 1):
        try:
            print(f"Closing year {year}...", end=' ', flush=True)
            
            # Check if already closed
            status = service.get_year_status(administration, year)
            if status and status.get('year'):  # Fixed: handle None return
                print(f"⚠️  Already closed (skipping)")
                success_count += 1
                continue
            
            # Close the year
            try:
                result = service.close_year(
                    administration=administration,
                    year=year,
                    user_email=user_email,
                    notes=f'Bulk closure by script'
                )
                
                print(f"✅ Success")
                success_count += 1
                
            except Exception as close_error:
                error_msg = str(close_error)
                print(f"❌ Failed: {error_msg}")
                failed_years.append((year, error_msg))
                
        except Exception as e:
            print(f"❌ Exception: {str(e)}")
            failed_years.append((year, str(e)))
    
    # Summary
    print(f"\n{'='*80}")
    print(f"Summary for {administration}")
    print(f"{'='*80}")
    print(f"Successfully closed: {success_count}/{up_to_year - first_year + 1} years")
    
    if failed_years:
        print(f"\n❌ Failed years:")
        for year, error in failed_years:
            print(f"  - {year}: {error}")
        return False
    else:
        print(f"\n✅ All years closed successfully!")
        return True


def main():
    parser = argparse.ArgumentParser(description='Bulk close years for administration(s)')
    parser.add_argument('--administration', help='Administration to close years for')
    parser.add_argument('--all', action='store_true', help='Close years for all administrations')
    parser.add_argument('--up-to-year', type=int, required=True, help='Last year to close (inclusive)')
    parser.add_argument('--test-mode', action='store_true', help='Use test database')
    parser.add_argument('--user-email', default='system@bulk-closure', help='Email to record in closure status')
    
    args = parser.parse_args()
    
    if not args.administration and not args.all:
        parser.error('Either --administration or --all must be specified')
    
    if args.administration and args.all:
        parser.error('Cannot specify both --administration and --all')
    
    # Get list of administrations to process
    if args.all:
        db = DatabaseManager(test_mode=args.test_mode)
        administrations = get_all_administrations(db)
        print(f"\nProcessing all administrations: {', '.join(administrations)}")
    else:
        administrations = [args.administration]
    
    # Process each administration
    all_success = True
    for admin in administrations:
        success = bulk_close_years(
            administration=admin,
            up_to_year=args.up_to_year,
            test_mode=args.test_mode,
            user_email=args.user_email
        )
        if not success:
            all_success = False
    
    # Final summary
    print(f"\n{'='*80}")
    print(f"FINAL SUMMARY")
    print(f"{'='*80}")
    if all_success:
        print(f"✅ All administrations processed successfully!")
        sys.exit(0)
    else:
        print(f"❌ Some administrations had failures")
        sys.exit(1)


if __name__ == '__main__':
    main()
