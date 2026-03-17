#!/usr/bin/env python3
"""
Investigation Script for _analyze_reference_patterns() Method

This script traces through the _analyze_reference_patterns() method to understand
why patterns are not being created for account 1022 transactions.

Since is_bank_account('1022', 'PeterPrive') returns True, the bug must be in:
1. Transaction query logic
2. Verb extraction logic
3. Pattern key creation logic
4. Pattern storage logic
"""

import sys
import os
from datetime import datetime, timedelta

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer


def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def investigate_transaction_query(db, administration='PeterPrive'):
    """Check if account 1022 transactions are being queried"""
    print_section("1. Checking Transaction Query for Account 1022")
    
    two_years_ago = datetime.now() - timedelta(days=730)
    
    # Query transactions for account 1022
    query = """
        SELECT TransactionDescription, Debet, Credit, ReferenceNumber, 
               TransactionDate, TransactionAmount, Ref1, administration
        FROM mutaties 
        WHERE administration = %s
          AND TransactionDate >= %s
          AND (Debet IS NOT NULL OR Credit IS NOT NULL)
          AND (Debet = '1022' OR Credit = '1022')
        ORDER BY TransactionDate DESC
        LIMIT 10
    """
    
    results = db.execute_query(query, (administration, two_years_ago.strftime('%Y-%m-%d')))
    
    print(f"\nAccount 1022 transactions in last 2 years: {len(results)}")
    
    if results:
        print(f"\nSample transactions:")
        for i, tx in enumerate(results[:5], 1):
            print(f"\n  Transaction {i}:")
            print(f"    Date: {tx['TransactionDate']}")
            print(f"    Description: {tx['TransactionDescription'][:80]}...")
            print(f"    Debet: {tx['Debet']}, Credit: {tx['Credit']}")
            print(f"    ReferenceNumber: {tx.get('ReferenceNumber', 'NULL')}")
            print(f"    Ref1 (IBAN): {tx.get('Ref1', 'NULL')}")
    else:
        print(f"\n✗ No transactions found for account 1022 in last 2 years")
    
    return results


def investigate_verb_extraction(analyzer, transactions):
    """Test verb extraction on account 1022 transactions"""
    print_section("2. Testing Verb Extraction on Account 1022 Transactions")
    
    if not transactions:
        print(f"\n✗ No transactions to test")
        return []
    
    verb_results = []
    
    for i, tx in enumerate(transactions[:5], 1):
        description = tx.get('TransactionDescription', '')
        ref_num = tx.get('ReferenceNumber', '')
        
        print(f"\nTransaction {i}:")
        print(f"  Description: {description[:80]}...")
        print(f"  ReferenceNumber: {ref_num}")
        
        # Test verb extraction
        verb = analyzer._extract_verb_from_description(description, ref_num)
        
        if verb:
            print(f"  ✓ Verb extracted: '{verb}'")
            
            # Check if compound
            is_compound = '|' in verb
            if is_compound:
                parts = verb.split('|', 1)
                print(f"    - Compound verb: Company='{parts[0]}', Reference='{parts[1] if len(parts) > 1 else 'NULL'}'")
            else:
                print(f"    - Simple verb: '{verb}'")
            
            verb_results.append({
                'transaction': tx,
                'verb': verb,
                'is_compound': is_compound
            })
        else:
            print(f"  ✗ No verb extracted")
    
    return verb_results


def investigate_bank_account_identification(analyzer, transactions, administration='PeterPrive'):
    """Check if bank account is correctly identified in transactions"""
    print_section("3. Testing Bank Account Identification")
    
    if not transactions:
        print(f"\n✗ No transactions to test")
        return []
    
    bank_account_results = []
    
    for i, tx in enumerate(transactions[:5], 1):
        debet = tx.get('Debet', '')
        credit = tx.get('Credit', '')
        
        print(f"\nTransaction {i}:")
        print(f"  Debet: {debet}, Credit: {credit}")
        
        # Check which is the bank account
        debet_is_bank = analyzer.is_bank_account(debet, administration) if debet else False
        credit_is_bank = analyzer.is_bank_account(credit, administration) if credit else False
        
        print(f"  is_bank_account('{debet}', '{administration}') = {debet_is_bank}")
        print(f"  is_bank_account('{credit}', '{administration}') = {credit_is_bank}")
        
        if debet_is_bank:
            print(f"  ✓ Bank account: {debet} (Debet)")
            bank_account = debet
            other_account = credit
        elif credit_is_bank:
            print(f"  ✓ Bank account: {credit} (Credit)")
            bank_account = credit
            other_account = debet
        else:
            print(f"  ✗ No bank account identified")
            bank_account = None
            other_account = None
        
        bank_account_results.append({
            'transaction': tx,
            'bank_account': bank_account,
            'other_account': other_account,
            'debet_is_bank': debet_is_bank,
            'credit_is_bank': credit_is_bank
        })
    
    return bank_account_results


def investigate_pattern_key_creation(verb_results, bank_account_results, administration='PeterPrive'):
    """Test pattern key creation"""
    print_section("4. Testing Pattern Key Creation")
    
    if not verb_results or not bank_account_results:
        print(f"\n✗ No data to test")
        return []
    
    pattern_keys = []
    
    for i, (verb_data, bank_data) in enumerate(zip(verb_results, bank_account_results), 1):
        verb = verb_data['verb']
        is_compound = verb_data['is_compound']
        bank_account = bank_data['bank_account']
        
        print(f"\nTransaction {i}:")
        print(f"  Verb: '{verb}'")
        print(f"  Bank Account: {bank_account}")
        
        if not bank_account:
            print(f"  ✗ Cannot create pattern key - no bank account")
            continue
        
        # Parse compound verb
        if is_compound:
            parts = verb.split('|', 1)
            verb_company = parts[0]
            verb_reference = parts[1] if len(parts) > 1 else None
        else:
            verb_company = verb
            verb_reference = None
        
        # Create pattern key (should use verb_company only, not full compound verb)
        pattern_key = f"{administration}_{bank_account}_{verb_company}"
        
        print(f"  ✓ Pattern key: '{pattern_key}'")
        print(f"    - Administration: {administration}")
        print(f"    - Bank Account: {bank_account}")
        print(f"    - Verb Company: {verb_company}")
        
        if verb_reference:
            print(f"    - Verb Reference: {verb_reference} (not used in key)")
        
        pattern_keys.append({
            'pattern_key': pattern_key,
            'verb': verb,
            'verb_company': verb_company,
            'verb_reference': verb_reference,
            'bank_account': bank_account,
            'transaction': verb_data['transaction']
        })
    
    return pattern_keys


def investigate_existing_patterns(db, administration='PeterPrive'):
    """Check existing patterns in database for account 1022"""
    print_section("5. Checking Existing Patterns in Database")
    
    query = """
        SELECT administration, bank_account, verb, verb_company, verb_reference,
               reference_number, debet_account, credit_account, occurrences, last_seen
        FROM pattern_verb_patterns
        WHERE administration = %s AND bank_account = '1022'
        ORDER BY last_seen DESC
    """
    
    results = db.execute_query(query, (administration,))
    
    print(f"\nExisting patterns for account 1022: {len(results)}")
    
    if results:
        print(f"\nPatterns:")
        for i, pattern in enumerate(results, 1):
            print(f"\n  Pattern {i}:")
            print(f"    Verb: {pattern['verb']}")
            print(f"    Verb Company: {pattern.get('verb_company', 'NULL')}")
            print(f"    Verb Reference: {pattern.get('verb_reference', 'NULL')}")
            print(f"    Reference Number: {pattern['reference_number']}")
            print(f"    Debet: {pattern['debet_account']}, Credit: {pattern['credit_account']}")
            print(f"    Occurrences: {pattern['occurrences']}")
            print(f"    Last Seen: {pattern['last_seen']}")
    else:
        print(f"\n✗ No patterns found for account 1022")
        
        # Check patterns for account 1003 for comparison
        query_1003 = """
            SELECT administration, bank_account, verb, reference_number, occurrences
            FROM pattern_verb_patterns
            WHERE administration = %s AND bank_account = '1003'
            ORDER BY last_seen DESC
            LIMIT 5
        """
        
        results_1003 = db.execute_query(query_1003, (administration,))
        
        if results_1003:
            print(f"\nComparison - Patterns for account 1003 (working): {len(results_1003)}")
            for i, pattern in enumerate(results_1003[:3], 1):
                print(f"  {i}. Verb: {pattern['verb']}, Ref: {pattern['reference_number']}, Occurrences: {pattern['occurrences']}")
    
    return results


def simulate_analyze_reference_patterns(db, analyzer, administration='PeterPrive'):
    """Simulate the _analyze_reference_patterns() method with logging"""
    print_section("6. Simulating _analyze_reference_patterns() Method")
    
    two_years_ago = datetime.now() - timedelta(days=730)
    
    # Get transactions
    query = """
        SELECT TransactionDescription, Debet, Credit, ReferenceNumber, 
               TransactionDate, TransactionAmount, Ref1, administration
        FROM mutaties 
        WHERE administration = %s
          AND TransactionDate >= %s
          AND (Debet IS NOT NULL OR Credit IS NOT NULL)
        ORDER BY TransactionDate DESC
    """
    
    transactions = db.execute_query(query, (administration, two_years_ago.strftime('%Y-%m-%d')))
    
    print(f"\nTotal transactions: {len(transactions)}")
    
    # Filter for account 1022
    account_1022_txs = [tx for tx in transactions if tx.get('Debet') == '1022' or tx.get('Credit') == '1022']
    
    print(f"Account 1022 transactions: {len(account_1022_txs)}")
    
    # Count how many would create patterns
    patterns_created = 0
    patterns_skipped = 0
    skip_reasons = []
    
    for tx in account_1022_txs[:10]:  # Test first 10
        debet = tx.get('Debet')
        credit = tx.get('Credit')
        description = tx.get('TransactionDescription', '').strip()
        ref_num = tx.get('ReferenceNumber', '').strip()
        
        # Check conditions
        if not ref_num or not description:
            patterns_skipped += 1
            skip_reasons.append("Missing ReferenceNumber or Description")
            continue
        
        # Identify bank account
        bank_account = None
        if analyzer.is_bank_account(debet, administration):
            bank_account = debet
        elif analyzer.is_bank_account(credit, administration):
            bank_account = credit
        
        if not bank_account:
            patterns_skipped += 1
            skip_reasons.append("No bank account identified")
            continue
        
        # Extract verb
        verb = analyzer._extract_verb_from_description(description, ref_num)
        if not verb:
            patterns_skipped += 1
            skip_reasons.append("No verb extracted")
            continue
        
        patterns_created += 1
    
    print(f"\nSimulation Results (first 10 transactions):")
    print(f"  Patterns that would be created: {patterns_created}")
    print(f"  Patterns skipped: {patterns_skipped}")
    
    if skip_reasons:
        print(f"\nSkip reasons:")
        from collections import Counter
        reason_counts = Counter(skip_reasons)
        for reason, count in reason_counts.items():
            print(f"  - {reason}: {count}")


def main():
    """Run all investigations"""
    print("\n" + "=" * 80)
    print("  INVESTIGATION: _analyze_reference_patterns() Method")
    print("=" * 80)
    print("\nThis script investigates why patterns are not being created for account 1022")
    print("even though is_bank_account('1022', 'PeterPrive') returns True")
    
    # Initialize database and analyzer
    db = DatabaseManager(test_mode=False)
    analyzer = PatternAnalyzer(test_mode=False)
    
    administration = 'PeterPrive'
    
    # Run investigations
    transactions = investigate_transaction_query(db, administration)
    verb_results = investigate_verb_extraction(analyzer, transactions)
    bank_account_results = investigate_bank_account_identification(analyzer, transactions, administration)
    pattern_keys = investigate_pattern_key_creation(verb_results, bank_account_results, administration)
    existing_patterns = investigate_existing_patterns(db, administration)
    simulate_analyze_reference_patterns(db, analyzer, administration)
    
    # Summary
    print_section("INVESTIGATION SUMMARY")
    
    print(f"\nFindings:")
    print(f"  1. Account 1022 transactions found: {len(transactions)}")
    print(f"  2. Verbs successfully extracted: {len(verb_results)}")
    print(f"  3. Bank accounts identified: {len([b for b in bank_account_results if b['bank_account']])}")
    print(f"  4. Pattern keys created: {len(pattern_keys)}")
    print(f"  5. Existing patterns in database: {len(existing_patterns)}")
    
    print(f"\nRoot Cause Analysis:")
    
    if len(transactions) == 0:
        print(f"  ✗ CRITICAL: No transactions found for account 1022")
        print(f"    → Check transaction data in mutaties table")
    elif len(verb_results) == 0:
        print(f"  ✗ CRITICAL: Verb extraction failing for account 1022 transactions")
        print(f"    → Check _extract_verb_from_description() method")
    elif len([b for b in bank_account_results if b['bank_account']]) == 0:
        print(f"  ✗ CRITICAL: Bank account identification failing")
        print(f"    → This contradicts earlier findings - investigate further")
    elif len(pattern_keys) == 0:
        print(f"  ✗ CRITICAL: Pattern key creation failing")
        print(f"    → Check pattern key logic in _analyze_reference_patterns()")
    elif len(existing_patterns) == 0:
        print(f"  ✗ CRITICAL: Patterns not being stored to database")
        print(f"    → Check _store_verb_patterns_to_database() method")
        print(f"    → Check if analyze_historical_patterns() is being called")
    else:
        print(f"  ✓ Patterns exist in database!")
        print(f"    → Bug may be in pattern application logic")
    
    print("\n" + "=" * 80)
    print("  Investigation Complete")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()
