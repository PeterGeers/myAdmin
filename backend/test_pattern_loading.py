#!/usr/bin/env python3
"""Test if patterns are being loaded correctly"""

import sys
sys.path.insert(0, 'src')

from pattern_analyzer import PatternAnalyzer

analyzer = PatternAnalyzer(test_mode=False)

# Get patterns for GoodwinSolutions
patterns = analyzer.get_filtered_patterns('GoodwinSolutions')

print(f"Total patterns discovered: {patterns['patterns_discovered']}")
print(f"Reference patterns loaded: {len(patterns['reference_patterns'])}")
print(f"Debet patterns loaded: {len(patterns['debet_patterns'])}")
print(f"Credit patterns loaded: {len(patterns['credit_patterns'])}")

# Check if NETFLIX pattern exists
netflix_key = "GoodwinSolutions_1002_NETFLIX"
if netflix_key in patterns['reference_patterns']:
    print(f"\n✅ NETFLIX pattern found!")
    print(f"   Pattern: {patterns['reference_patterns'][netflix_key]}")
else:
    print(f"\n❌ NETFLIX pattern NOT found!")
    print(f"   Looking for key: {netflix_key}")
    print(f"   Available keys (first 5): {list(patterns['reference_patterns'].keys())[:5]}")
