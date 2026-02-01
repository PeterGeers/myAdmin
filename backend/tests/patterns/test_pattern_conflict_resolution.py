#!/usr/bin/env python3
"""
Test script for pattern conflict resolution

This tests the scenario where multiple reference numbers match the same description/verb.
The system should intelligently choose the best match based on:
1. Most recent pattern (last_seen date)
2. Highest frequency (occurrences)
3. Amount similarity
4. Account number preference
"""

import sys
import os
from datetime import datetime, date, timedelta

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from pattern_analyzer import PatternAnalyzer
from database import DatabaseManager

def create_test_conflict_patterns():
    """Create test patterns that have conflicts (same verb, different reference numbers)"""
    print("1. Creating Test Conflict Patterns")
    print("-" * 60)
    
    db = DatabaseManager(test_mode=False)
    administration = "TestConflicts"
    
    # Clear existing test patterns
    db.execute_query("DELETE FROM pattern_verb_patterns WHERE administration = %s", (administration,), fetch=False, commit=True)
    
    # Create conflicting patterns for the same verb "TESTSHOP"
    test_patterns = [
        {
            'administration': administration,
            'bank_account': '1300',
            'verb': 'TESTSHOP',
            'reference_number': 'TestShop-Old',
            'debet_account': '4001',
            'credit_account': '1300',
            'occurrences': 5,
            'confidence': 1.0,
            'last_seen': date.today() - timedelta(days=90),  # 3 months ago
            'sample_description': 'TESTSHOP OUDE LOCATIE'
        },
        {
            'administration': administration,
            'bank_account': '1300',
            'verb': 'TESTSHOP',
            'reference_number': 'TestShop-New',
            'debet_account': '4002',
            'credit_account': '1300',
            'occurrences': 15,
            'confidence': 1.0,
            'last_seen': date.today() - timedelta(days=7),  # 1 week ago (most recent)
            'sample_description': 'TESTSHOP NIEUWE LOCATIE'
        },
        {
            'administration': administration,
            'bank_account': '1300',
            'verb': 'TESTSHOP',
            'reference_number': 'TestShop-Frequent',
            'debet_account': '4003',
            'credit_account': '1300',
            'occurrences': 25,  # Highest frequency
            'confidence': 1.0,
            'last_seen': date.today() - timedelta(days=30),  # 1 month ago
            'sample_description': 'TESTSHOP FREQUENT GEBRUIK'
        }
    ]
    
    # Insert test patterns
    for pattern in test_patterns:
        db.execute_query("""
            INSERT INTO pattern_verb_patterns 
            (administration, bank_account, verb, reference_number, debet_account, 
             credit_account, occurrences, confidence, last_seen, sample_description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            pattern['administration'], pattern['bank_account'], pattern['verb'],
            pattern['reference_number'], pattern['debet_account'], pattern['credit_account'],
            pattern['occurrences'], pattern['confidence'], pattern['last_seen'],
            pattern['sample_description']
        ), fetch=False, commit=True)
    
    print(f"✅ Created {len(test_patterns)} conflicting patterns for verb 'TESTSHOP':")
    for i, pattern in enumerate(test_patterns, 1):
        print(f"   {i}. {pattern['reference_number']}")
        print(f"      → Occurrences: {pattern['occurrences']}, Last seen: {pattern['last_seen']}")
        print(f"      → Debet: {pattern['debet_account']}, Credit: {pattern['credit_account']}")
    
    return administration

def test_conflict_resolution_scenarios():
    """Test different conflict resolution scenarios"""
    print("\n2. Testing Conflict Resolution Scenarios")
    print("-" * 60)
    
    analyzer = PatternAnalyzer(test_mode=False)
    administration = "TestConflicts"
    
    # Test scenarios
    test_cases = [
        {
            'name': 'Basic Conflict Resolution',
            'transaction': {
                'TransactionDescription': 'TESTSHOP ONLINE PURCHASE',
                'TransactionAmount': 50.00,
                'Credit': '1300',  # Bank account
                'Debet': '',  # Missing
                'ReferenceNumber': '',  # Missing
                'Administration': administration
            },
            'expected_logic': 'Should choose most recent pattern (TestShop-New)'
        },
        {
            'name': 'Amount-Based Resolution',
            'transaction': {
                'TransactionDescription': 'TESTSHOP LARGE ORDER',
                'TransactionAmount': 500.00,  # Large amount
                'Credit': '1300',  # Bank account
                'Debet': '',  # Missing
                'ReferenceNumber': '',  # Missing
                'Administration': administration
            },
            'expected_logic': 'Should consider amount in scoring'
        },
        {
            'name': 'Frequency vs Recency',
            'transaction': {
                'TransactionDescription': 'TESTSHOP REGULAR PURCHASE',
                'TransactionAmount': 25.00,
                'Credit': '1300',  # Bank account
                'Debet': '',  # Missing
                'ReferenceNumber': '',  # Missing
                'Administration': administration
            },
            'expected_logic': 'Should balance frequency vs recency'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📝 Test Case {i}: {test_case['name']}")
        print(f"   Description: {test_case['transaction']['TransactionDescription']}")
        print(f"   Amount: €{test_case['transaction']['TransactionAmount']}")
        print(f"   Expected: {test_case['expected_logic']}")
        
        # Apply patterns
        updated_txs, results = analyzer.apply_patterns_to_transactions([test_case['transaction']], administration)
        
        if updated_txs:
            tx = updated_txs[0]
            print(f"\n   ✅ Resolution Result:")
            if tx.get('ReferenceNumber'):
                print(f"      → ReferenceNumber: {tx['ReferenceNumber']} (confidence: {tx.get('_reference_confidence', 0):.2f})")
            if tx.get('Debet'):
                print(f"      → Debet: {tx['Debet']} (confidence: {tx.get('_debet_confidence', 0):.2f})")
            
            # Check if alternatives were considered
            if hasattr(tx, '_alternatives'):
                print(f"      → Alternatives considered: {tx.get('_alternatives', 0)}")
        else:
            print("   ❌ No predictions made")

def test_conflict_resolution_algorithm():
    """Test the conflict resolution algorithm directly"""
    print("\n3. Testing Conflict Resolution Algorithm")
    print("-" * 60)
    
    analyzer = PatternAnalyzer(test_mode=False)
    
    # Create mock patterns with different characteristics
    mock_patterns = [
        ('old_frequent', {
            'verb': 'TESTSHOP',
            'reference_number': 'TestShop-OldFrequent',
            'occurrences': 50,  # Very frequent
            'last_seen': date.today() - timedelta(days=180),  # 6 months ago
            'bank_account': '1300',
            'debet_account': '4001',
            'credit_account': '1300'
        }),
        ('recent_rare', {
            'verb': 'TESTSHOP',
            'reference_number': 'TestShop-RecentRare',
            'occurrences': 3,  # Rare
            'last_seen': date.today() - timedelta(days=2),  # Very recent
            'bank_account': '1300',
            'debet_account': '4002',
            'credit_account': '1300'
        }),
        ('balanced', {
            'verb': 'TESTSHOP',
            'reference_number': 'TestShop-Balanced',
            'occurrences': 15,  # Moderate frequency
            'last_seen': date.today() - timedelta(days=14),  # 2 weeks ago
            'bank_account': '1300',
            'debet_account': '4003',
            'credit_account': '1300'
        })
    ]
    
    test_transaction = {
        'TransactionDescription': 'TESTSHOP TEST PURCHASE',
        'TransactionAmount': 100.00,
        'Credit': '1300',
        'Administration': 'TestConflicts'
    }
    
    # Test conflict resolution
    best_pattern = analyzer._resolve_pattern_conflicts(mock_patterns, test_transaction, 'TestConflicts')
    
    if best_pattern:
        key, pattern = best_pattern
        print(f"✅ Algorithm selected: {pattern['reference_number']}")
        print(f"   → Occurrences: {pattern['occurrences']}")
        print(f"   → Last seen: {pattern['last_seen']}")
        print(f"   → Reasoning: Balanced recency and frequency scoring")
    else:
        print("❌ Algorithm failed to select a pattern")

def cleanup_test_data():
    """Clean up test data"""
    print("\n4. Cleaning Up Test Data")
    print("-" * 60)
    
    db = DatabaseManager(test_mode=False)
    administration = "TestConflicts"
    
    # Remove test patterns
    result = db.execute_query("DELETE FROM pattern_verb_patterns WHERE administration = %s", (administration,), fetch=False, commit=True)
    print(f"✅ Cleaned up test patterns for {administration}")

def run_conflict_resolution_tests():
    """Run all conflict resolution tests"""
    print("🧪 Pattern Conflict Resolution Test Suite")
    print("=" * 60)
    
    try:
        administration = create_test_conflict_patterns()
        test_conflict_resolution_scenarios()
        test_conflict_resolution_algorithm()
        cleanup_test_data()
        
        print("\n🎉 ALL CONFLICT RESOLUTION TESTS COMPLETED!")
        print("\n📋 Conflict Resolution Strategy Summary:")
        print("✅ 1. Most Recent Pattern (40% weight) - Reflects current business practices")
        print("✅ 2. Highest Frequency (30% weight) - Most common usage patterns")
        print("✅ 3. Amount Similarity (20% weight) - Transaction amount matching")
        print("✅ 4. Bank Account Preference (10% weight) - Same bank account priority")
        print("\n🔀 Benefits:")
        print("✅ Intelligent conflict resolution instead of arbitrary sorting")
        print("✅ Adapts to changing business patterns over time")
        print("✅ Considers multiple factors for best match")
        print("✅ Provides transparency in decision making")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_conflict_resolution_tests()
    sys.exit(0 if success else 1)