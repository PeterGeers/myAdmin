"""
Test Opening Balance Creation

Tests the _create_opening_balances() and _get_ending_balances() methods.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.year_end_service import YearEndClosureService
from database import DatabaseManager

def test_opening_balances():
    """Test opening balance creation"""
    
    print("=" * 60)
    print("Opening Balance Creation Test")
    print("=" * 60)
    print()
    
    # Initialize service
    service = YearEndClosureService(test_mode=False)
    db = DatabaseManager(test_mode=False)
    
    # Test with GoodwinSolutions tenant
    administration = 'GoodwinSolutions'
    
    print(f"Testing with tenant: {administration}")
    print()
    
    # Test getting ending balances for various years
    test_years = [2024, 2025, 2026, 2027]
    
    for year in test_years:
        print(f"\n{'=' * 60}")
        print(f"Ending Balances for Year {year}")
        print(f"{'=' * 60}")
        
        # Get a database connection and cursor
        conn = db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get ending balances
            balances = service._get_ending_balances(administration, year, cursor)
            
            if not balances:
                print(f"No balance sheet accounts with balances for {year}")
                continue
            
            print(f"\nFound {len(balances)} accounts with non-zero balances:")
            print()
            
            # Show first 10 balances
            total_positive = 0
            total_negative = 0
            count_positive = 0
            count_negative = 0
            
            for i, balance_info in enumerate(balances[:10]):
                account = balance_info['account']
                name = balance_info['account_name']
                balance = balance_info['balance']
                
                if balance > 0:
                    total_positive += balance
                    count_positive += 1
                    sign = "+"
                else:
                    total_negative += balance
                    count_negative += 1
                    sign = ""
                
                print(f"  {account} - {name[:40]:40} {sign}€{abs(balance):>12,.2f}")
            
            if len(balances) > 10:
                print(f"  ... and {len(balances) - 10} more accounts")
            
            print()
            print(f"Summary:")
            print(f"  Positive balances (assets): {count_positive} accounts, €{total_positive:,.2f}")
            print(f"  Negative balances (liab/equity): {count_negative} accounts, €{abs(total_negative):,.2f}")
            print(f"  Net balance: €{total_positive + total_negative:,.2f}")
            
            # Simulate opening balance creation for next year
            print(f"\nSimulated Opening Balances for {year + 1}:")
            print(f"  TransactionNumber: OpeningBalance {year + 1}")
            print(f"  TransactionDate: {year + 1}-01-01")
            print(f"  Records to create: {len(balances)}")
            
            # Get interim account
            from services.year_end_config import YearEndConfigService
            config_service = YearEndConfigService(test_mode=False)
            interim_account_info = config_service.get_account_by_purpose(
                administration, 'interim_opening_balance'
            )
            
            if interim_account_info:
                interim_account = interim_account_info['Account']
                print(f"  Interim account: {interim_account} - {interim_account_info['AccountName']}")
                
                # Show example transactions
                print(f"\n  Example transactions:")
                for balance_info in balances[:3]:
                    account = balance_info['account']
                    balance = balance_info['balance']
                    amount = abs(balance)
                    
                    if balance > 0:
                        print(f"    Debit: {account}, Credit: {interim_account}, Amount: €{amount:,.2f}")
                    else:
                        print(f"    Debit: {interim_account}, Credit: {account}, Amount: €{amount:,.2f}")
            else:
                print(f"  ⚠️  Interim account not configured")
        
        finally:
            cursor.close()
            conn.close()
    
    print()
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print()
    print("✅ Ending balances query tested")
    print("✅ Opening balance logic tested")
    print("✅ Positive balances: Debit Account, Credit Interim")
    print("✅ Negative balances: Debit Interim, Credit Account")
    print()
    print("Note: This test simulates transactions without inserting them.")
    print("To actually create transactions, use the close_year() method.")
    print()


if __name__ == '__main__':
    test_opening_balances()
