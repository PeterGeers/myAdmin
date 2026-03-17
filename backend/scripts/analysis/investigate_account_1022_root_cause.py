#!/usr/bin/env python3
"""
Root Cause Investigation Script for Account 1022 Pattern Discovery Failure

This script investigates why is_bank_account('1022', 'PeterPrive') returns False
by checking:
1. vw_rekeningnummers view contents
2. Bank account cache contents
3. Cache key format
4. rekeningschema table registration
5. Administration name and account number format mismatches
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer


def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def investigate_view_contents(db, administration='PeterPrive'):
    """Check if account 1022 appears in vw_rekeningnummers view"""
    print_section("1. Checking vw_rekeningnummers View Contents")
    
    # Query the view directly
    query = """
        SELECT rekeningNummer, Account, administration
        FROM vw_rekeningnummers
        WHERE administration = %s
        ORDER BY Account
    """
    
    results = db.execute_query(query, (administration,))
    
    print(f"\nTotal accounts in view for '{administration}': {len(results)}")
    
    # Check if account 1022 is in the results
    account_1022 = [r for r in results if r['Account'] == '1022']
    
    if account_1022:
        print(f"\n✓ Account 1022 FOUND in view:")
        for acc in account_1022:
            print(f"  - Account: {acc['Account']}, IBAN: {acc['rekeningNummer']}, Admin: {acc['administration']}")
    else:
        print(f"\n✗ Account 1022 NOT FOUND in view")
        
        # Show sample accounts for comparison
        print(f"\nSample accounts from view (first 10):")
        for acc in results[:10]:
            print(f"  - Account: {acc['Account']}, IBAN: {acc['rekeningNummer']}, Admin: {acc['administration']}")
    
    return account_1022


def investigate_rekeningschema_table(db, administration='PeterPrive'):
    """Check if account 1022 is registered in rekeningschema table"""
    print_section("2. Checking rekeningschema Table Registration")
    
    # Query rekeningschema directly
    query = """
        SELECT Account, AccountLookup, administration, Pattern
        FROM rekeningschema
        WHERE administration = %s AND Account = '1022'
    """
    
    results = db.execute_query(query, (administration,))
    
    if results:
        print(f"\n✓ Account 1022 FOUND in rekeningschema:")
        for acc in results:
            print(f"  - Account: {acc['Account']}")
            print(f"  - AccountLookup: {acc.get('AccountLookup', 'NULL')}")
            print(f"  - Administration: {acc['administration']}")
            print(f"  - Pattern: {acc.get('Pattern', 'NULL')}")
    else:
        print(f"\n✗ Account 1022 NOT FOUND in rekeningschema")
        
        # Check if it exists with different administration
        query_all = """
            SELECT Account, AccountLookup, administration, Pattern
            FROM rekeningschema
            WHERE Account = '1022'
        """
        results_all = db.execute_query(query_all, ())
        
        if results_all:
            print(f"\n  Account 1022 found with different administration:")
            for acc in results_all:
                print(f"    - Administration: '{acc['administration']}' (expected: '{administration}')")
                print(f"    - Pattern: {acc.get('Pattern', 'NULL')}")
        else:
            print(f"\n  Account 1022 not found in rekeningschema at all")
    
    return results


def investigate_bank_account_cache(analyzer, administration='PeterPrive'):
    """Check bank account cache contents"""
    print_section("3. Checking Bank Account Cache")
    
    # Get bank accounts cache
    bank_accounts = analyzer.get_bank_accounts()
    
    print(f"\nTotal accounts in cache: {len(bank_accounts)}")
    
    # Check for account 1022 with various key formats
    possible_keys = [
        f"{administration}_1022",
        f"PeterPrive_1022",
        f"{administration}_01022",
        f"PeterPrive_01022",
    ]
    
    found_keys = []
    for key in possible_keys:
        if key in bank_accounts:
            found_keys.append(key)
            print(f"\n✓ Found account 1022 with key: '{key}'")
            print(f"  - IBAN: {bank_accounts[key]['iban']}")
            print(f"  - Account: {bank_accounts[key]['account']}")
            print(f"  - Administration: {bank_accounts[key]['administration']}")
    
    if not found_keys:
        print(f"\n✗ Account 1022 NOT FOUND in cache with any expected key format")
        
        # Show sample cache keys for comparison
        print(f"\nSample cache keys (first 10):")
        for i, key in enumerate(list(bank_accounts.keys())[:10]):
            acc = bank_accounts[key]
            print(f"  {i+1}. Key: '{key}'")
            print(f"     Account: {acc['account']}, Admin: '{acc['administration']}'")
        
        # Check if any keys contain '1022'
        matching_keys = [k for k in bank_accounts.keys() if '1022' in k]
        if matching_keys:
            print(f"\nKeys containing '1022':")
            for key in matching_keys:
                acc = bank_accounts[key]
                print(f"  - Key: '{key}'")
                print(f"    Account: {acc['account']}, Admin: '{acc['administration']}'")
    
    return found_keys


def investigate_is_bank_account_method(analyzer, administration='PeterPrive'):
    """Test is_bank_account() method directly"""
    print_section("4. Testing is_bank_account() Method")
    
    # Test with account 1022
    result_1022 = analyzer.is_bank_account('1022', administration)
    print(f"\nis_bank_account('1022', '{administration}') = {result_1022}")
    
    if not result_1022:
        print(f"  ✗ Account 1022 is NOT recognized as a bank account")
        
        # Test with account 1003 for comparison
        result_1003 = analyzer.is_bank_account('1003', administration)
        print(f"\nComparison:")
        print(f"  is_bank_account('1003', '{administration}') = {result_1003}")
        
        if result_1003:
            print(f"  ✓ Account 1003 IS recognized (working account)")
            
            # Check cache keys for both accounts
            bank_accounts = analyzer.get_bank_accounts()
            key_1003 = f"{administration}_1003"
            key_1022 = f"{administration}_1022"
            
            print(f"\nCache key comparison:")
            print(f"  Key for 1003: '{key_1003}' - Exists: {key_1003 in bank_accounts}")
            print(f"  Key for 1022: '{key_1022}' - Exists: {key_1022 in bank_accounts}")
    else:
        print(f"  ✓ Account 1022 IS recognized as a bank account")
    
    return result_1022


def investigate_view_definition(db):
    """Check the view definition for any filters"""
    print_section("5. Checking View Definition")
    
    # Get view definition
    query = "SHOW CREATE VIEW vw_rekeningnummers"
    
    try:
        results = db.execute_query(query, ())
        
        if results:
            view_def = results[0].get('Create View', '')
            print(f"\nView Definition:")
            print(view_def)
            
            # Check for filters
            if 'WHERE' in view_def.upper():
                print(f"\n✓ View has WHERE clause - checking filters...")
                
                # Check for specific filters that might exclude account 1022
                filters_to_check = [
                    ('AccountType', 'Account type filter'),
                    ('Account <', 'Account number range filter'),
                    ('Account >', 'Account number range filter'),
                    ('Account !=', 'Account exclusion filter'),
                    ('Account NOT IN', 'Account exclusion list'),
                ]
                
                for filter_text, description in filters_to_check:
                    if filter_text in view_def:
                        print(f"  ⚠ Found {description}: {filter_text}")
            else:
                print(f"\n✓ View has no WHERE clause (only Pattern IS NOT NULL)")
        else:
            print(f"\n✗ Could not retrieve view definition")
    
    except Exception as e:
        print(f"\n✗ Error retrieving view definition: {e}")


def investigate_administration_mismatch(db, analyzer):
    """Check for administration name mismatches"""
    print_section("6. Checking Administration Name Mismatches")
    
    # Get all unique administrations from rekeningschema
    query = """
        SELECT DISTINCT administration
        FROM rekeningschema
        WHERE Account = '1022'
    """
    
    results = db.execute_query(query, ())
    
    if results:
        print(f"\nAdministrations with account 1022 in rekeningschema:")
        for row in results:
            admin = row['administration']
            print(f"  - '{admin}' (length: {len(admin)})")
            
            # Check if this matches 'PeterPrive'
            if admin == 'PeterPrive':
                print(f"    ✓ Exact match with 'PeterPrive'")
            elif admin.replace(' ', '') == 'PeterPrive'.replace(' ', ''):
                print(f"    ⚠ Match after removing spaces")
            elif admin.lower() == 'PeterPrive'.lower():
                print(f"    ⚠ Case-insensitive match")
            else:
                print(f"    ✗ No match with 'PeterPrive'")
            
            # Test is_bank_account with this administration
            result = analyzer.is_bank_account('1022', admin)
            print(f"    is_bank_account('1022', '{admin}') = {result}")
    else:
        print(f"\n✗ No administrations found with account 1022")


def main():
    """Run all investigations"""
    print("\n" + "=" * 80)
    print("  ROOT CAUSE INVESTIGATION: Account 1022 Pattern Discovery Failure")
    print("=" * 80)
    print("\nThis script investigates why is_bank_account('1022', 'PeterPrive') returns False")
    
    # Initialize database and analyzer
    db = DatabaseManager(test_mode=False)
    analyzer = PatternAnalyzer(test_mode=False)
    
    administration = 'PeterPrive'
    
    # Run investigations
    view_results = investigate_view_contents(db, administration)
    schema_results = investigate_rekeningschema_table(db, administration)
    cache_keys = investigate_bank_account_cache(analyzer, administration)
    is_recognized = investigate_is_bank_account_method(analyzer, administration)
    investigate_view_definition(db)
    investigate_administration_mismatch(db, analyzer)
    
    # Summary
    print_section("INVESTIGATION SUMMARY")
    
    print(f"\nFindings:")
    print(f"  1. Account 1022 in vw_rekeningnummers view: {'YES' if view_results else 'NO'}")
    print(f"  2. Account 1022 in rekeningschema table: {'YES' if schema_results else 'NO'}")
    print(f"  3. Account 1022 in bank account cache: {'YES' if cache_keys else 'NO'}")
    print(f"  4. is_bank_account('1022', 'PeterPrive'): {is_recognized}")
    
    print(f"\nRoot Cause Analysis:")
    
    if not schema_results:
        print(f"  ✗ CRITICAL: Account 1022 is NOT registered in rekeningschema table")
        print(f"    → This is the root cause - account must be registered with Pattern=1")
    elif not view_results:
        print(f"  ✗ CRITICAL: Account 1022 is NOT in vw_rekeningnummers view")
        print(f"    → View filter is excluding account 1022 despite Pattern IS NOT NULL")
        print(f"    → Check view definition for additional filters")
    elif not cache_keys:
        print(f"  ✗ CRITICAL: Account 1022 is NOT in bank account cache")
        print(f"    → Cache population issue or key format mismatch")
        print(f"    → Check get_bank_accounts() method in pattern_analyzer.py")
    elif not is_recognized:
        print(f"  ✗ CRITICAL: is_bank_account() returns False despite cache entry")
        print(f"    → Cache key lookup logic issue")
        print(f"    → Check is_bank_account() method in pattern_analyzer.py")
    else:
        print(f"  ✓ Account 1022 is properly recognized!")
        print(f"    → Bug may be in _analyze_reference_patterns() method")
        print(f"    → Check transaction processing logic")
    
    print("\n" + "=" * 80)
    print("  Investigation Complete")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()
