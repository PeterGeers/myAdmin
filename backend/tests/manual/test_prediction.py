#!/usr/bin/env python3
"""Test pattern prediction with actual transaction structure"""

import sys
sys.path.insert(0, 'src')

from pattern_analyzer import PatternAnalyzer

analyzer = PatternAnalyzer(test_mode=False)

# Get patterns
patterns = analyzer.get_filtered_patterns('GoodwinSolutions')

# Simulate Netflix transaction
netflix_tx = {
    'TransactionDescription': 'NETFLIX INTERNATIONAL B.V. Netflix Monthly Subscription',
    'Debet': '',  # Empty - needs prediction
    'Credit': '1002',  # Bank account
    'ReferenceNumber': '',  # Empty - needs prediction
    'administration': 'GoodwinSolutions'
}

print("Testing NETFLIX transaction:")
print(f"  Description: {netflix_tx['TransactionDescription'][:50]}...")
print(f"  Credit (bank): {netflix_tx['Credit']}")
print(f"  Debet (empty): '{netflix_tx['Debet']}'")
print(f"  ReferenceNumber (empty): '{netflix_tx['ReferenceNumber']}'")
print()

# Test reference prediction
ref_prediction = analyzer._predict_reference(netflix_tx, patterns['reference_patterns'])
print(f"Reference prediction: {ref_prediction}")
print()

# Test debet prediction  
debet_prediction = analyzer._predict_debet(netflix_tx, patterns['debet_patterns'], 'GoodwinSolutions')
print(f"Debet prediction: {debet_prediction}")
