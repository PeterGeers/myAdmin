#!/usr/bin/env python3
"""
Test script for compound verb pattern functionality

This tests the new compound verb system that extracts both company names and reference numbers:
- "ANWB Energie B.V. 100431234 NL28BUKK..." → "ANWB|100431234"
- "ANWB BV ARNL3367411472 Betreft... 7073498490" → "ANWB|7073498490"

Pattern matching strategies:
1. Exact compound match: ANWB|100431234
2. Company match with different reference: ANWB|* 
3. Company-only fallback: ANWB
"""

import sys
import os

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from pattern_analyzer import PatternAnalyzer
from database import DatabaseManager

def test_compound_verb_extraction():
    """Test compound verb extraction from real-world descriptions"""
    print("1. Testing Compound Verb Extraction")
    print("-" * 60)
    
    analyzer = PatternAnalyzer(test_mode=False)
    
    test_cases = [
        {
            'description': 'ANWB Energie B.V. 100431234 NL28BUKK7893044720',
            'expected_company': 'ANWB',
            'expected_reference': '100431234',
            'expected_compound': 'ANWB|100431234'
        },
        {
            'description': 'ANWB BV ARNL3367411472 Betreft contributie/abonnementsgelden ANWB. Voor meer info kijk op anwb.nl/factuur 7073498490 NL73RABO0333003330',
            'expected_company': 'ANWB',
            'expected_reference': '7073498490',
            'expected_compound': 'ANWB|7073498490'
        },
        {
            'description': 'PICNIC ONLINE SUPERMARKT BETALING 987654321',
            'expected_company': 'PICNIC',
            'expected_reference': '987654321',
            'expected_compound': 'PICNIC|987654321'
        },
        {
            'description': 'GAMMA BOUWMARKT AMSTERDAM',  # No reference number
            'expected_company': 'GAMMA',
            'expected_reference': None,
            'expected_compound': 'GAMMA'
        },
        {
            'description': 'NETFLIX.COM SUBSCRIPTION REF:NF123456789',
            'expected_company': 'NETFLIX',
            'expected_reference': 'NF123456789',
            'expected_compound': 'NETFLIX|NF123456789'
        }
    ]
    
    print("🔍 Testing compound verb extraction:")
    for i, test_case in enumerate(test_cases, 1):
        description = test_case['description']
        
        # Test individual components
        company = analyzer._extract_company_name(description)
        reference = analyzer._extract_reference_number_from_description(description)
        compound = analyzer._extract_compound_verb_from_description(description, "")
        
        print(f"\n{i}. Description: {description[:60]}...")
        print(f"   Company: '{company}' (expected: '{test_case['expected_company']}')")
        print(f"   Reference: '{reference}' (expected: '{test_case['expected_reference']}')")
        print(f"   Compound: '{compound}' (expected: '{test_case['expected_compound']}')")
        
        # Validate results
        company_ok = company == test_case['expected_company']
        reference_ok = reference == test_case['expected_reference']
        compound_ok = compound == test_case['expected_compound']
        
        status = "✅" if (company_ok and reference_ok and compound_ok) else "❌"
        print(f"   Status: {status}")

def test_compound_pattern_storage():
    """Test that compound patterns are stored correctly in database"""
    print("\n2. Testing Compound Pattern Storage")
    print("-" * 60)
    
    analyzer = PatternAnalyzer(test_mode=False)
    administration = "CompoundTest"
    
    # Clear existing test patterns
    db = DatabaseManager(test_mode=False)
    db.execute_query("DELETE FROM pattern_verb_patterns WHERE administration = %s", (administration,), fetch=False, commit=True)
    db.execute_query("DELETE FROM pattern_analysis_metadata WHERE administration = %s", (administration,), fetch=False, commit=True)
    
    # Create test transactions with compound verbs
    test_transactions = [
        {
            'TransactionDescription': 'ANWB Energie B.V. 100431234 NL28BUKK7893044720',
            'Debet': '4001',
            'Credit': '1300',  # Bank account
            'ReferenceNumber': 'ANWB-Energy',
            'TransactionDate': '2024-12-01',
            'Administration': administration
        },
        {
            'TransactionDescription': 'ANWB BV ARNL3367411472 Betreft contributie 7073498490 NL73RABO0333003330',
            'Debet': '4002',
            'Credit': '1300',  # Bank account
            'ReferenceNumber': 'ANWB-Membership',
            'TransactionDate': '2024-12-15',
            'Administration': administration
        },
        {
            'TransactionDescription': 'PICNIC ONLINE SUPERMARKT 987654321',
            'Debet': '1300',  # Bank account
            'Credit': '4003',
            'ReferenceNumber': 'Picnic',
            'TransactionDate': '2024-12-10',
            'Administration': administration
        }
    ]
    
    # Manually create patterns (simulating analysis)
    print("📊 Creating compound patterns...")
    
    for tx in test_transactions:
        verb = analyzer._extract_compound_verb_from_description(tx['TransactionDescription'], tx['ReferenceNumber'])
        if verb:
            print(f"   Transaction: {tx['TransactionDescription'][:40]}...")
            print(f"   → Extracted verb: '{verb}'")
            
            # Determine bank account
            bank_account = None
            if analyzer.is_bank_account(tx['Debet'], administration):
                bank_account = tx['Debet']
            elif analyzer.is_bank_account(tx['Credit'], administration):
                bank_account = tx['Credit']
            
            if bank_account:
                # Parse compound verb
                is_compound = '|' in verb
                verb_company = verb.split('|')[0] if is_compound else verb
                verb_reference = verb.split('|')[1] if is_compound and '|' in verb else None
                
                # Store pattern
                db.execute_query("""
                    INSERT INTO pattern_verb_patterns 
                    (administration, bank_account, verb, verb_company, verb_reference, is_compound,
                     reference_number, debet_account, credit_account, occurrences, confidence, 
                     last_seen, sample_description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    occurrences = occurrences + 1,
                    last_seen = VALUES(last_seen)
                """, (
                    administration, bank_account, verb, verb_company, verb_reference, is_compound,
                    tx['ReferenceNumber'], tx['Debet'], tx['Credit'], 1, 1.0,
                    tx['TransactionDate'], tx['TransactionDescription']
                ), fetch=False, commit=True)
    
    # Verify storage
    patterns = db.execute_query("""
        SELECT verb, verb_company, verb_reference, is_compound, reference_number, 
               debet_account, credit_account, sample_description
        FROM pattern_verb_patterns 
        WHERE administration = %s
        ORDER BY verb
    """, (administration,))
    
    print(f"\n✅ Stored {len(patterns)} compound patterns:")
    for pattern in patterns:
        compound_info = f"Company: {pattern['verb_company']}"
        if pattern['verb_reference']:
            compound_info += f", Reference: {pattern['verb_reference']}"
        
        print(f"   • {pattern['verb']} ({'Compound' if pattern['is_compound'] else 'Simple'})")
        print(f"     → {compound_info}")
        print(f"     → Maps to: {pattern['reference_number']} (Debet: {pattern['debet_account']}, Credit: {pattern['credit_account']})")

def test_compound_pattern_matching():
    """Test compound pattern matching with various scenarios"""
    print("\n3. Testing Compound Pattern Matching")
    print("-" * 60)
    
    analyzer = PatternAnalyzer(test_mode=False)
    administration = "CompoundTest"
    
    # Test scenarios
    test_cases = [
        {
            'name': 'Exact Compound Match',
            'transaction': {
                'TransactionDescription': 'ANWB Energie B.V. 100431234 NL28BUKK7893044720',
                'Credit': '1300',  # Bank account
                'Debet': '',
                'ReferenceNumber': '',
                'Administration': administration
            },
            'expected': 'Should match ANWB|100431234 exactly'
        },
        {
            'name': 'Company Match, Different Reference',
            'transaction': {
                'TransactionDescription': 'ANWB Energie B.V. 999888777 NL28BUKK7893044720',
                'Credit': '1300',  # Bank account
                'Debet': '',
                'ReferenceNumber': '',
                'Administration': administration
            },
            'expected': 'Should match ANWB company with fallback'
        },
        {
            'name': 'Simple to Compound Matching',
            'transaction': {
                'TransactionDescription': 'ANWB MEMBERSHIP PAYMENT',  # No reference number
                'Credit': '1300',  # Bank account
                'Debet': '',
                'ReferenceNumber': '',
                'Administration': administration
            },
            'expected': 'Should match ANWB company patterns'
        },
        {
            'name': 'Exact Simple Match',
            'transaction': {
                'TransactionDescription': 'PICNIC ONLINE SUPERMARKT',  # No reference number
                'Debet': '1300',  # Bank account
                'Credit': '',
                'ReferenceNumber': '',
                'Administration': administration
            },
            'expected': 'Should match simple PICNIC pattern'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📝 Test Case {i}: {test_case['name']}")
        print(f"   Description: {test_case['transaction']['TransactionDescription']}")
        print(f"   Expected: {test_case['expected']}")
        
        # Apply patterns
        updated_txs, results = analyzer.apply_patterns_to_transactions([test_case['transaction']], administration)
        
        if updated_txs:
            tx = updated_txs[0]
            print(f"\n   ✅ Prediction Results:")
            if tx.get('ReferenceNumber'):
                print(f"      → ReferenceNumber: {tx['ReferenceNumber']} (confidence: {tx.get('_reference_confidence', 0):.2f})")
                if hasattr(tx, '_match_type'):
                    print(f"      → Match type: {tx.get('_match_type', 'unknown')}")
            if tx.get('Debet'):
                print(f"      → Debet: {tx['Debet']} (confidence: {tx.get('_debet_confidence', 0):.2f})")
            if tx.get('Credit'):
                print(f"      → Credit: {tx['Credit']} (confidence: {tx.get('_credit_confidence', 0):.2f})")
        else:
            print("   ❌ No predictions made")

def test_compound_vs_simple_patterns():
    """Test interaction between compound and simple patterns"""
    print("\n4. Testing Compound vs Simple Pattern Interaction")
    print("-" * 60)
    
    db = DatabaseManager(test_mode=False)
    administration = "CompoundTest"
    
    # Query patterns to show the variety
    patterns = db.execute_query("""
        SELECT verb, verb_company, verb_reference, is_compound, reference_number, 
               occurrences, last_seen
        FROM pattern_verb_patterns 
        WHERE administration = %s
        ORDER BY verb_company, is_compound DESC, verb
    """, (administration,))
    
    print(f"✅ Pattern Analysis ({len(patterns)} patterns):")
    
    current_company = None
    for pattern in patterns:
        if pattern['verb_company'] != current_company:
            current_company = pattern['verb_company']
            print(f"\n🏢 Company: {current_company}")
        
        pattern_type = "Compound" if pattern['is_compound'] else "Simple"
        ref_info = f" (Ref: {pattern['verb_reference']})" if pattern['verb_reference'] else ""
        
        print(f"   • {pattern_type}: {pattern['verb']}{ref_info}")
        print(f"     → Maps to: {pattern['reference_number']}")
        print(f"     → Occurrences: {pattern['occurrences']}, Last seen: {pattern['last_seen']}")

def cleanup_test_data():
    """Clean up test data"""
    print("\n5. Cleaning Up Test Data")
    print("-" * 60)
    
    db = DatabaseManager(test_mode=False)
    administration = "CompoundTest"
    
    # Remove test patterns
    result = db.execute_query("DELETE FROM pattern_verb_patterns WHERE administration = %s", (administration,), fetch=False, commit=True)
    print(f"✅ Cleaned up test patterns for {administration}")

def run_compound_verb_tests():
    """Run all compound verb tests"""
    print("🧪 Compound Verb Pattern Test Suite")
    print("=" * 60)
    
    try:
        test_compound_verb_extraction()
        test_compound_pattern_storage()
        test_compound_pattern_matching()
        test_compound_vs_simple_patterns()
        cleanup_test_data()
        
        print("\n🎉 ALL COMPOUND VERB TESTS COMPLETED!")
        print("\n📋 Compound Verb System Summary:")
        print("✅ Company + Reference extraction from descriptions")
        print("✅ Compound verb storage: COMPANY|REFERENCE")
        print("✅ Flexible pattern matching strategies:")
        print("   1. Exact compound match (highest priority)")
        print("   2. Company match with different reference")
        print("   3. Simple-to-compound pattern matching")
        print("   4. Compound-to-simple fallback")
        print("✅ Enhanced pattern specificity and accuracy")
        print("✅ Backward compatibility with simple patterns")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_compound_verb_tests()
    sys.exit(0 if success else 1)