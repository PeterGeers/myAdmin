#!/usr/bin/env python3
"""
Bug Condition Exploration Test for Account 1022 Pattern Discovery Failure

This test is designed to FAIL on unfixed code to demonstrate the bug exists.
It encodes the expected behavior that will be validated when the fix is implemented.

Bug: Pattern processor fails to create/update patterns for account 1022 (Revolut)
     during pattern re-analysis workflow.

Expected Outcome: TEST FAILS (this confirms the bug exists)
After Fix: TEST PASSES (this confirms the bug is fixed)
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer


@pytest.mark.integration
@pytest.mark.database
class TestAccount1022BugCondition:
    """
    Bug Condition Exploration: Account 1022 Pattern Discovery Failure
    
    This test demonstrates that account 1022 patterns are NOT being created/updated
    during pattern re-analysis, even though:
    - Account 1022 IS registered in rekeningschema with Pattern=1
    - Transactions exist with assigned ReferenceNumbers
    - The same workflow works for account 1003 (Rabobank)
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment"""
        # Use production database to test against real bug condition
        # The bug exists in production data where account 1022 has NO patterns
        self.db = DatabaseManager(test_mode=False)
        self.analyzer = PatternAnalyzer(test_mode=False)
        self.administration = 'PeterPrive'
        
        # Clean up any existing test data
        self._cleanup_test_data()
        
        yield
        
        # Clean up after test
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Remove test transactions and patterns"""
        try:
            # Delete test transactions
            self.db.execute_query(
                "DELETE FROM mutaties WHERE TransactionDescription LIKE '%TEST_ACCOUNT_1022%'",
                (),
                fetch=False,
                commit=True
            )
            
            # Delete test patterns
            self.db.execute_query(
                "DELETE FROM pattern_verb_patterns WHERE administration = %s AND bank_account IN ('1022', '1003')",
                (self.administration,),
                fetch=False,
                commit=True
            )
        except Exception as e:
            print(f"Cleanup warning: {e}")
    
    def _create_test_transaction(self, account: str, reference_number: str, 
                                 description: str, opposite_account: str = '1300') -> Dict:
        """
        Create a test transaction in the mutaties table
        Simulates user SAVE action
        """
        transaction_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        transaction = {
            'TransactionDate': transaction_date,
            'TransactionDescription': f"{description} TEST_ACCOUNT_1022",
            'TransactionAmount': 50.00,
            'Debet': account,
            'Credit': opposite_account,
            'ReferenceNumber': reference_number,
            'Ref1': f'NL08REVO{account}',  # Revolut IBAN format
            'administration': self.administration
        }
        
        # Insert into mutaties table
        query = """
            INSERT INTO mutaties 
            (TransactionDate, TransactionDescription, TransactionAmount, 
             Debet, Credit, ReferenceNumber, Ref1, administration)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        self.db.execute_query(query, (
            transaction['TransactionDate'],
            transaction['TransactionDescription'],
            transaction['TransactionAmount'],
            transaction['Debet'],
            transaction['Credit'],
            transaction['ReferenceNumber'],
            transaction['Ref1'],
            transaction['administration']
        ), fetch=False, commit=True)
        
        return transaction
    
    def _get_patterns_from_database(self, bank_account: str) -> List[Dict]:
        """Query pattern_verb_patterns table for specific bank account"""
        query = """
            SELECT administration, bank_account, verb, reference_number,
                   debet_account, credit_account, occurrences, last_seen
            FROM pattern_verb_patterns
            WHERE administration = %s AND bank_account = %s
        """
        
        return self.db.execute_query(query, (self.administration, bank_account))
    
    def test_bug_condition_account_1022_pattern_discovery_failure(self):
        """
        Property 1: Bug Condition - Account 1022 Pattern Discovery Failure
        
        CRITICAL: This test MUST FAIL on unfixed code - failure confirms the bug exists
        
        Test Steps:
        1. Create test transactions for account 1022 with assigned ReferenceNumbers
        2. Save transactions to mutaties table (simulating user SAVE action)
        3. Trigger pattern re-analysis by calling analyze_historical_patterns()
        4. Assert patterns are created in pattern_verb_patterns table
        
        Expected Outcome on UNFIXED code: TEST FAILS
        - Patterns are NOT created for account 1022
        - is_bank_account('1022', 'PeterPrive') returns False
        - _analyze_reference_patterns() skips account 1022 transactions
        
        Expected Outcome on FIXED code: TEST PASSES
        - Patterns ARE created for account 1022
        - is_bank_account('1022', 'PeterPrive') returns True
        - _analyze_reference_patterns() processes account 1022 transactions
        """
        print("\n" + "=" * 80)
        print("BUG CONDITION EXPLORATION: Account 1022 Pattern Discovery Failure")
        print("=" * 80)
        
        # Step 1: Create test transactions for account 1022
        print("\n📝 Step 1: Creating test transactions for account 1022...")
        
        test_cases = [
            ('Hoogvliet', 'HOOGVLIET Betaalpas 12:34'),
            ('TMC', 'TMC Transport Services'),
            ('Albert Heijn', 'ALBERT HEIJN 1234 Amsterdam')
        ]
        
        for ref_num, description in test_cases:
            self._create_test_transaction('1022', ref_num, description)
            print(f"   ✓ Created transaction: {ref_num} - {description}")
        
        # Step 2: Verify transactions are in database
        print("\n📊 Step 2: Verifying transactions in mutaties table...")
        
        query = """
            SELECT TransactionDescription, Debet, Credit, ReferenceNumber
            FROM mutaties
            WHERE administration = %s 
              AND Debet = '1022'
              AND TransactionDescription LIKE '%TEST_ACCOUNT_1022%'
        """
        
        transactions = self.db.execute_query(query, (self.administration,))
        assert len(transactions) == 3, f"Expected 3 transactions, found {len(transactions)}"
        print(f"   ✓ Found {len(transactions)} transactions in database")
        
        # Step 3: Check if is_bank_account recognizes account 1022
        print("\n🔍 Step 3: Checking if is_bank_account() recognizes account 1022...")
        
        is_recognized = self.analyzer.is_bank_account('1022', self.administration)
        print(f"   is_bank_account('1022', '{self.administration}') = {is_recognized}")
        
        if not is_recognized:
            print("   ❌ COUNTEREXAMPLE FOUND: Account 1022 is NOT recognized as a bank account")
            print("   This is likely the root cause of the bug")
            
            # Additional diagnostics
            print("\n🔬 Additional Diagnostics:")
            
            # Check bank account cache
            bank_accounts = self.analyzer.get_bank_accounts()
            print(f"   Total bank accounts in cache: {len(bank_accounts)}")
            
            # Check if account 1022 is in cache
            cache_key_1022 = f"{self.administration}_1022"
            if cache_key_1022 in bank_accounts:
                print(f"   ✓ Account 1022 found in cache with key: {cache_key_1022}")
            else:
                print(f"   ❌ Account 1022 NOT found in cache (expected key: {cache_key_1022})")
                
                # Show sample cache keys for comparison
                sample_keys = list(bank_accounts.keys())[:5]
                print(f"   Sample cache keys: {sample_keys}")
            
            # Check vw_rekeningnummers view
            view_query = """
                SELECT Account, rekeningNummer, administration
                FROM vw_rekeningnummers
                WHERE administration = %s AND Account = '1022'
            """
            view_results = self.db.execute_query(view_query, (self.administration,))
            
            if view_results:
                print(f"   ✓ Account 1022 found in vw_rekeningnummers view")
            else:
                print(f"   ❌ Account 1022 NOT found in vw_rekeningnummers view")
                print(f"   This suggests the view may be filtering out account 1022")
            
            # Check rekeningschema table directly
            schema_query = """
                SELECT Account, rekeningNummer, administration, Pattern
                FROM rekeningschema
                WHERE administration = %s AND Account = '1022'
            """
            schema_results = self.db.execute_query(schema_query, (self.administration,))
            
            if schema_results:
                pattern_value = schema_results[0].get('Pattern')
                print(f"   ✓ Account 1022 found in rekeningschema with Pattern={pattern_value}")
            else:
                print(f"   ❌ Account 1022 NOT found in rekeningschema")
        
        # Step 4: Trigger pattern re-analysis
        print("\n🔄 Step 4: Triggering pattern re-analysis (analyze_historical_patterns)...")
        
        result = self.analyzer.analyze_historical_patterns(self.administration)
        
        print(f"   Total transactions analyzed: {result['total_transactions']}")
        print(f"   Patterns discovered: {result['patterns_discovered']}")
        print(f"   Reference patterns: {len(result['reference_patterns'])}")
        
        # Step 5: Check if patterns were created in database
        print("\n🗄️  Step 5: Checking pattern_verb_patterns table...")
        
        patterns = self._get_patterns_from_database('1022')
        
        print(f"   Patterns found for account 1022: {len(patterns)}")
        
        if patterns:
            print("   ✓ Patterns created:")
            for pattern in patterns:
                print(f"      - {pattern['verb']}: {pattern['reference_number']} "
                      f"(occurrences: {pattern['occurrences']})")
        else:
            print("   ❌ NO PATTERNS FOUND for account 1022")
            print("   This confirms the bug: patterns are not being created")
        
        # Step 6: Compare with account 1003 (working account)
        print("\n🔬 Step 6: Comparison with account 1003 (Rabobank - working)...")
        
        # Create a test transaction for account 1003
        self._create_test_transaction('1003', 'Test Vendor', 'Test Vendor Payment')
        
        # Check if account 1003 is recognized
        is_1003_recognized = self.analyzer.is_bank_account('1003', self.administration)
        print(f"   is_bank_account('1003', '{self.administration}') = {is_1003_recognized}")
        
        # Trigger analysis again
        result_1003 = self.analyzer.analyze_historical_patterns(self.administration)
        
        # Check patterns for 1003
        patterns_1003 = self._get_patterns_from_database('1003')
        print(f"   Patterns found for account 1003: {len(patterns_1003)}")
        
        # Step 7: Document counterexamples
        print("\n📋 Step 7: Documenting Counterexamples...")
        
        counterexamples = []
        
        # Check which verbs were not discovered
        expected_verbs = ['HOOGVLIET', 'TMC', 'ALBERT']
        discovered_verbs = [p['verb'] for p in patterns]
        missing_verbs = [v for v in expected_verbs if v not in discovered_verbs]
        
        if missing_verbs:
            counterexamples.append(f"Missing verbs: {', '.join(missing_verbs)}")
        
        if not is_recognized:
            counterexamples.append("is_bank_account('1022', 'PeterPrive') returns False")
        
        if len(patterns) == 0:
            counterexamples.append("No patterns exist in database after analysis")
        
        if counterexamples:
            print("   ❌ COUNTEREXAMPLES FOUND:")
            for i, example in enumerate(counterexamples, 1):
                print(f"      {i}. {example}")
        else:
            print("   ✓ No counterexamples found - bug may be fixed!")
        
        # Final assertions - these SHOULD FAIL on unfixed code
        print("\n" + "=" * 80)
        print("FINAL ASSERTIONS (Expected to FAIL on unfixed code)")
        print("=" * 80)
        
        # Assertion 1: is_bank_account should recognize account 1022
        assert is_recognized, (
            "EXPECTED FAILURE: is_bank_account('1022', 'PeterPrive') should return True. "
            "This failure confirms the bug exists."
        )
        
        # Assertion 2: Patterns should be created for account 1022
        assert len(patterns) > 0, (
            f"EXPECTED FAILURE: Expected patterns for account 1022, found {len(patterns)}. "
            "This failure confirms the bug exists."
        )
        
        # Assertion 3: All expected verbs should be discovered
        assert len(missing_verbs) == 0, (
            f"EXPECTED FAILURE: Missing verbs: {missing_verbs}. "
            "This failure confirms the bug exists."
        )
        
        # Assertion 4: Pattern entries should have correct values for our test transactions
        test_patterns = [p for p in patterns if p['reference_number'] in ['Hoogvliet', 'TMC', 'Albert Heijn']]
        
        assert len(test_patterns) >= 3, \
            f"Expected at least 3 test patterns, found {len(test_patterns)}"
        
        for pattern in test_patterns:
            assert pattern['administration'] == self.administration, \
                f"Pattern administration mismatch: {pattern['administration']}"
            assert pattern['bank_account'] == '1022', \
                f"Pattern bank_account mismatch: {pattern['bank_account']}"
            assert pattern['reference_number'] in ['Hoogvliet', 'TMC', 'Albert Heijn'], \
                f"Pattern reference_number unexpected: {pattern['reference_number']}"
            assert pattern['debet_account'] == '1022', \
                f"Pattern debet_account mismatch: {pattern['debet_account']}"
            assert pattern['credit_account'] == '1300', \
                f"Pattern credit_account mismatch: {pattern['credit_account']}"
        
        print("\n✅ ALL ASSERTIONS PASSED - Bug is FIXED!")
        print("=" * 80)


if __name__ == '__main__':
    # Run the test directly
    pytest.main([__file__, '-v', '-s'])
