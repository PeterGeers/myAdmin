#!/usr/bin/env python3
"""Test verb extraction from transaction descriptions"""

import sys
sys.path.insert(0, 'src')

from pattern_analyzer import PatternAnalyzer

analyzer = PatternAnalyzer(test_mode=False)

# Test descriptions from the CSV
test_descriptions = [
    "NETFLIX INTERNATIONAL B.V. Netflix Monthly Subscription",
    "Booking.com B.V. NO.QJR24hgYApztg5d6/ID.5615303",
    "AIRBNB PAYMENTS LUXEMBOURG S.A. Airbnb",
]

for desc in test_descriptions:
    verb = analyzer._extract_verb_from_description(desc, "")
    print(f"Description: {desc[:50]}...")
    print(f"Extracted verb: {verb}")
    print()
