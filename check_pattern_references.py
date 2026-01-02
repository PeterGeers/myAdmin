#!/usr/bin/env python3
"""
Check Pattern Reference Numbers

This script checks what reference numbers are stored in the pattern database
to see if they contain transaction codes instead of logical company names.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from database import DatabaseManager

def check_pattern_references():
    print("🔍 Checking Pattern Reference Numbers")
    print("=" * 60)
    
    db = DatabaseManager(test_mode=False)
    
    # Get all reference numbers from patterns
    patterns = db.execute_query("""
        SELECT DISTINCT reference_number, COUNT(*) as count
        FROM pattern_verb_patterns 
        WHERE administration = 'GoodwinSolutions'
          AND reference_number IS NOT NULL 
          AND reference_number != ''
        GROUP BY reference_number
        ORDER BY count DESC, reference_number
    """)
    
    print(f"Found {len(patterns)} unique reference numbers in patterns:")
    print()
    
    # Categorize the reference numbers
    good_references = []
    strange_references = []
    
    for pattern in patterns:
        ref = pattern['reference_number']
        count = pattern['count']
        
        # Check if it looks like a transaction code (long alphanumeric)
        if len(ref) > 15 and any(c.isdigit() for c in ref) and any(c.isalpha() for c in ref):
            strange_references.append((ref, count))
        else:
            good_references.append((ref, count))
    
    print("✅ GOOD REFERENCE NUMBERS (logical names):")
    print("-" * 40)
    for ref, count in good_references[:20]:  # Show first 20
        print(f"  {ref:<30} ({count} patterns)")
    
    if len(good_references) > 20:
        print(f"  ... and {len(good_references) - 20} more")
    
    print(f"\n❌ STRANGE REFERENCE NUMBERS (transaction codes):")
    print("-" * 40)
    for ref, count in strange_references[:10]:  # Show first 10
        print(f"  {ref:<40} ({count} patterns)")
    
    if len(strange_references) > 10:
        print(f"  ... and {len(strange_references) - 10} more")
    
    print(f"\n📊 SUMMARY:")
    print(f"  Good references: {len(good_references)}")
    print(f"  Strange references: {len(strange_references)}")
    
    if strange_references:
        print(f"\n🚨 ISSUE IDENTIFIED:")
        print(f"  The pattern database contains {len(strange_references)} reference numbers")
        print(f"  that look like transaction codes instead of logical company names.")
        print(f"  This is why 'Apply Patterns' suggests strange codes!")
        
        print(f"\n💡 SOLUTION:")
        print(f"  1. Clean up the pattern database to remove patterns with transaction codes")
        print(f"  2. Re-analyze patterns to learn proper company names")
        print(f"  3. Or manually update the reference_number field in existing patterns")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    check_pattern_references()