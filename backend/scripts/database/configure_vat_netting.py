#!/usr/bin/env python3
"""
Configure VAT Account Netting for Year-End Closure

This script configures VAT accounts to be netted together during year-end closure.
The net balance (Received VAT - Paid VAT) will be carried forward as a single
opening balance entry in the primary VAT account.

Usage:
    python configure_vat_netting.py [--administration ADMIN_NAME]
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database import DatabaseManager
import argparse


def configure_vat_netting(administration, vat_accounts, primary_account, test_mode=False):
    """
    Configure VAT accounts for netting.
    
    Args:
        administration: Tenant identifier
        vat_accounts: List of VAT account codes to net together
        primary_account: Primary account that receives the net balance
        test_mode: Use test database if True
    """
    db = DatabaseManager(test_mode=test_mode)
    
    print(f"\n{'='*60}")
    print(f"Configuring VAT Netting for {administration}")
    print(f"{'='*60}\n")
    
    # Update query
    update_query = """
        UPDATE rekeningschema 
        SET parameters = JSON_SET(
            COALESCE(parameters, '{}'), 
            '$.vat_netting', true,
            '$.vat_primary', %s
        )
        WHERE Account = %s
        AND administration = %s
    """
    
    # Verify query
    verify_query = """
        SELECT 
            Account,
            AccountName,
            VW,
            JSON_EXTRACT(parameters, '$.vat_netting') as vat_netting,
            JSON_EXTRACT(parameters, '$.vat_primary') as vat_primary
        FROM rekeningschema
        WHERE Account IN ({})
        AND administration = %s
        ORDER BY Account
    """.format(','.join(['%s'] * len(vat_accounts)))
    
    try:
        # Configure each VAT account
        for account in vat_accounts:
            print(f"Configuring account {account}...")
            db.execute_query(
                update_query, 
                [primary_account, account, administration],
                fetch=False,
                commit=True
            )
            print(f"  ✓ Account {account} configured")
        
        print(f"\n{'='*60}")
        print("Configuration Complete - Verification:")
        print(f"{'='*60}\n")
        
        # Verify configuration
        params = vat_accounts + [administration]
        results = db.execute_query(verify_query, params)
        
        if results:
            print(f"{'Account':<10} {'Name':<30} {'VW':<5} {'Netting':<10} {'Primary':<10}")
            print(f"{'-'*10} {'-'*30} {'-'*5} {'-'*10} {'-'*10}")
            
            for row in results:
                account = row['Account']
                name = row['AccountName'][:28]
                vw = row['VW']
                netting = str(row['vat_netting']).strip('"')
                primary = str(row['vat_primary']).strip('"') if row['vat_primary'] else 'N/A'
                
                print(f"{account:<10} {name:<30} {vw:<5} {netting:<10} {primary:<10}")
            
            print(f"\n{'='*60}")
            print("✓ VAT netting configured successfully!")
            print(f"{'='*60}\n")
            
            print("Next steps:")
            print("1. Close a year to test VAT netting")
            print("2. Verify only one opening balance entry for VAT (account 2010)")
            print("3. Check VAT report shows correct net balance\n")
        else:
            print("⚠ Warning: No accounts found. Check administration name and account codes.\n")
    
    except Exception as e:
        print(f"\n✗ Error configuring VAT netting: {e}\n")
        raise


def main():
    parser = argparse.ArgumentParser(
        description='Configure VAT account netting for year-end closure'
    )
    parser.add_argument(
        '--administration',
        default='GoodwinSolutions',
        help='Administration/tenant name (default: GoodwinSolutions)'
    )
    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Use test database'
    )
    parser.add_argument(
        '--vat-accounts',
        nargs='+',
        default=['2010', '2020', '2021'],
        help='VAT account codes to net together (default: 2010 2020 2021)'
    )
    parser.add_argument(
        '--primary-account',
        default='2010',
        help='Primary account for net balance (default: 2010)'
    )
    
    args = parser.parse_args()
    
    print("\nVAT Account Netting Configuration")
    print(f"Administration: {args.administration}")
    print(f"VAT Accounts: {', '.join(args.vat_accounts)}")
    print(f"Primary Account: {args.primary_account}")
    print(f"Test Mode: {args.test_mode}")
    
    # Confirm before proceeding
    response = input("\nProceed with configuration? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Configuration cancelled.")
        return
    
    configure_vat_netting(
        args.administration,
        args.vat_accounts,
        args.primary_account,
        args.test_mode
    )


if __name__ == '__main__':
    main()
