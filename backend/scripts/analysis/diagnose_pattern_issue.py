"""
Diagnostic script to investigate why patterns for Hoogvliet and TMC
are not showing up for account 1022 (Revolut) but are visible for 1003.

Bug Report: .kiro/bug reports/20260307 1425 PatternsProcessor missing patterns.md
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer
from datetime import datetime, timedelta

def main():
    print("=" * 80)
    print("PATTERN PROCESSOR DIAGNOSTIC")
    print("=" * 80)
    print()
    
    # Initialize database and pattern analyzer
    db = DatabaseManager(test_mode=False)
    analyzer = PatternAnalyzer(test_mode=False)
    
    # 1. Check what bank accounts exist
    print("1. BANK ACCOUNTS")
    print("-" * 80)
    bank_accounts = analyzer.get_bank_accounts()
    for admin, accounts in bank_accounts.items():
        print(f"\nAdministration: {admin}")
        for acc_num, acc_info in accounts.items():
            if isinstance(acc_info, dict):
                print(f"  {acc_num}: {acc_info.get('AccountName', 'N/A')}")
            else:
                print(f"  {acc_num}: {acc_info}")
    
    # 2. Check historical transactions for account 1022
    print("\n\n2. HISTORICAL TRANSACTIONS FOR ACCOUNT 1022 (Revolut)")
    print("-" * 80)
    
    # Query last 2 years of transactions involving account 1022
    two_years_ago = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    
    query = """
        SELECT TransactionDate, TransactionDescription, ReferenceNumber, 
               Debet, Credit, TransactionAmount
        FROM mutaties
        WHERE (Debet = '1022' OR Credit = '1022')
          AND TransactionDate >= %s
        ORDER BY TransactionDate DESC
        LIMIT 50
    """
    
    transactions_1022 = db.execute_query(query, (two_years_ago,))
    
    print(f"Found {len(transactions_1022)} transactions for account 1022")
    print("\nSample transactions:")
    for tx in transactions_1022[:10]:
        print(f"  {tx['TransactionDate']} | {tx['TransactionDescription'][:50]:50} | "
              f"Ref: {tx['ReferenceNumber'][:20]:20} | D:{tx['Debet']} C:{tx['Credit']}")
    
    # 3. Check what patterns exist in database for account 1022
    print("\n\n3. PATTERNS IN DATABASE FOR ACCOUNT 1022")
    print("-" * 80)
    
    query = """
        SELECT administration, bank_account, verb, verb_company, 
               reference_number, debet_account, credit_account, 
               occurrences, last_seen, sample_description
        FROM pattern_verb_patterns
        WHERE bank_account = '1022'
        ORDER BY verb
    """
    
    patterns_1022 = db.execute_query(query)
    
    print(f"Found {len(patterns_1022)} patterns for account 1022")
    if patterns_1022:
        print("\nPatterns:")
        for p in patterns_1022:
            print(f"  {p['verb']:20} | Ref: {p['reference_number']:15} | "
                  f"D:{p['debet_account']} C:{p['credit_account']} | "
                  f"Occ: {p['occurrences']}")
    else:
        print("  ⚠️  NO PATTERNS FOUND FOR ACCOUNT 1022!")
    
    # 4. Check patterns for account 1003 (for comparison)
    print("\n\n4. PATTERNS IN DATABASE FOR ACCOUNT 1003 (for comparison)")
    print("-" * 80)
    
    query = """
        SELECT administration, bank_account, verb, verb_company, 
               reference_number, debet_account, credit_account, 
               occurrences, last_seen
        FROM pattern_verb_patterns
        WHERE bank_account = '1003'
          AND (verb LIKE '%Hoogvliet%' OR verb LIKE '%TMC%')
        ORDER BY verb
    """
    
    patterns_1003 = db.execute_query(query)
    
    print(f"Found {len(patterns_1003)} patterns for Hoogvliet/TMC on account 1003")
    if patterns_1003:
        print("\nPatterns:")
        for p in patterns_1003:
            print(f"  {p['verb']:20} | Ref: {p['reference_number']:15} | "
                  f"D:{p['debet_account']} C:{p['credit_account']} | "
                  f"Occ: {p['occurrences']}")
    
    # 5. Test verb extraction on sample descriptions
    print("\n\n5. VERB EXTRACTION TEST")
    print("-" * 80)
    
    test_descriptions = [
        "TMC",
        "Hoogvliet",
        "Albert Heijn",
        "APCOA Parking"
    ]
    
    for desc in test_descriptions:
        verb = analyzer._extract_company_name(desc)
        print(f"  '{desc}' → verb: '{verb}'")
    
    # 6. Check if transactions with Hoogvliet/TMC exist for 1022
    print("\n\n6. SPECIFIC CHECK: Hoogvliet and TMC transactions for 1022")
    print("-" * 80)
    
    query = """
        SELECT TransactionDate, TransactionDescription, ReferenceNumber, 
               Debet, Credit, TransactionAmount
        FROM mutaties
        WHERE (Debet = '1022' OR Credit = '1022')
          AND (TransactionDescription LIKE '%Hoogvliet%' OR TransactionDescription LIKE '%TMC%')
          AND TransactionDate >= %s
        ORDER BY TransactionDate DESC
    """
    
    specific_txs = db.execute_query(query, (two_years_ago,))
    
    print(f"Found {len(specific_txs)} Hoogvliet/TMC transactions for account 1022")
    if specific_txs:
        print("\nTransactions:")
        for tx in specific_txs:
            print(f"  {tx['TransactionDate']} | {tx['TransactionDescription']:30} | "
                  f"Ref: {tx['ReferenceNumber']:20} | D:{tx['Debet']} C:{tx['Credit']}")
            
            # Test verb extraction
            verb = analyzer._extract_company_name(tx['TransactionDescription'])
            print(f"    → Extracted verb: '{verb}'")
    else:
        print("  ⚠️  NO Hoogvliet/TMC transactions found for account 1022!")
    
    # 7. Check pattern analysis logic
    print("\n\n7. PATTERN ANALYSIS LOGIC CHECK")
    print("-" * 80)
    
    if specific_txs:
        print("Analyzing why patterns weren't created...")
        for tx in specific_txs[:3]:
            debet = tx['Debet']
            credit = tx['Credit']
            desc = tx['TransactionDescription']
            ref = tx['ReferenceNumber']
            
            print(f"\nTransaction: {desc}")
            print(f"  Debet: {debet}, Credit: {credit}")
            print(f"  Is Debet bank account? {analyzer.is_bank_account(debet, 'PeterPrive')}")
            print(f"  Is Credit bank account? {analyzer.is_bank_account(credit, 'PeterPrive')}")
            
            verb = analyzer._extract_verb_from_description(desc, ref)
            print(f"  Extracted verb: '{verb}'")
            
            # Check if pattern would be created
            if analyzer.is_bank_account(debet, 'PeterPrive'):
                pattern_key = f"PeterPrive_{debet}_{verb.split('|')[0] if verb else 'NONE'}"
                print(f"  Would create pattern key: {pattern_key}")
            elif analyzer.is_bank_account(credit, 'PeterPrive'):
                pattern_key = f"PeterPrive_{credit}_{verb.split('|')[0] if verb else 'NONE'}"
                print(f"  Would create pattern key: {pattern_key}")
            else:
                print(f"  ⚠️  NO PATTERN WOULD BE CREATED (no bank account)")
    
    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    main()
