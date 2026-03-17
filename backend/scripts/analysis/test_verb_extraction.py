#!/usr/bin/env python3
"""
Test script to investigate verb extraction for HOOGVLIET vs TMC

This script tests the _extract_company_name and _extract_verb_from_description methods
to understand why HOOGVLIET patterns aren't created while TMC patterns work.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pattern_analyzer import PatternAnalyzer

def test_verb_extraction():
    """Test verb extraction for different transaction descriptions"""
    
    analyzer = PatternAnalyzer(test_mode=True)
    
    test_cases = [
        ("Hoogvliet", "Hoogvliet"),
        ("TMC", "TMC"),
        ("Funmania Aalsmeer", "Funmania"),
        ("Albert Heijn", "Albert Heijn"),
        ("Tmc Wc Hoofddorp Ba6", "Wc Hoofddorp"),
    ]
    
    print("=" * 80)
    print("VERB EXTRACTION TEST")
    print("=" * 80)
    print()
    
    for description, reference_number in test_cases:
        print(f"Description: '{description}'")
        print(f"ReferenceNumber: '{reference_number}'")
        
        # Test company name extraction
        company = analyzer._extract_company_name(description)
        print(f"  → Company extracted: {company}")
        
        # Test verb extraction
        verb = analyzer._extract_verb_from_description(description, reference_number)
        print(f"  → Verb extracted: {verb}")
        
        # Test if verb is valid
        if verb:
            is_valid = analyzer._is_valid_verb(verb)
            print(f"  → Is valid verb: {is_valid}")
        
        print()
    
    print("=" * 80)
    print("TESTING _is_valid_verb FOR EACH CASE")
    print("=" * 80)
    print()
    
    test_verbs = ["HOOGVLIET", "TMC", "FUNMANIA", "ALBERT"]
    
    for verb in test_verbs:
        print(f"Testing verb: '{verb}'")
        is_valid = analyzer._is_valid_verb(verb)
        print(f"  → Is valid: {is_valid}")
        
        # Check against invalid patterns
        import re
        invalid_patterns = [
            (r'^[A-Z0-9]{8,}$', 'Long alphanumeric codes (8+ chars)'),
            (r'^[A-Z]{2}\d+[A-Z]+\d+$', 'Mixed patterns'),
            (r'^\d+[A-Z]+\d+$', 'Number-letter-number'),
            (r'^[A-Z]+\d+[A-Z]+$', 'Letter-number-letter'),
            (r'^P\d{10,}$', 'Transaction IDs starting with P'),
            (r'^[A-Z]{1,3}\d{8,}$', 'Short prefix + long number')
        ]
        
        for pattern, description in invalid_patterns:
            if re.match(pattern, verb):
                print(f"  ✗ REJECTED by pattern: {description}")
                print(f"     Pattern: {pattern}")
        
        # Check vowels
        vowels = set('AEIOU')
        has_vowels = len(set(verb) & vowels) > 0
        print(f"  - Has vowels: {has_vowels}")
        print()
    
    print("=" * 80)
    print("DETAILED ANALYSIS FOR HOOGVLIET")
    print("=" * 80)
    print()
    
    description = "Hoogvliet"
    description_upper = description.upper().strip()
    
    print(f"Original: '{description}'")
    print(f"Upper: '{description_upper}'")
    print()
    
    # Check if it matches any known company patterns
    import re
    company_patterns = [
        (r'\bBOL\.COM\b', 'BOL'),
        (r'\bAIRBNB\b', 'AIRBNB'),
        (r'\bPICNIC\b', 'PICNIC'),
        (r'\bBOOKING\.COM\b', 'BOOKING'),
        (r'\bBOOKING\b', 'BOOKING'),
        (r'\bGREENWHEELS\b', 'GREENWHEELS'),
        (r'\bMOLLIE\b', 'MOLLIE'),
        (r'\bANWB\b', 'ANWB'),
        (r'\bAEGON\b', 'AEGON'),
        (r'\bKLEI\s+AAN\s+HET\s+IJ\b', 'KLEI'),
        (r'\bKALENDERWINKEL\b', 'KALENDERWINKEL'),
        (r'\bKAMERAMARKT\b', 'KAMERAMARKT'),
        (r'\bZORG\s+EN\s+WELZIJN\b', 'ZORG'),
        (r'\bPENSIOENFONDS\b', 'PENSIOENFONDS'),
        (r'\bSTRIPE\b', 'STRIPE'),
        (r'\bVIA\b', 'VIA')
    ]
    
    matched = False
    for pattern, company in company_patterns:
        if re.search(pattern, description_upper):
            print(f"✓ Matched pattern: {pattern} → {company}")
            matched = True
            break
    
    if not matched:
        print("✗ No known company pattern matched")
    
    print()
    
    # Extract meaningful words
    words = re.findall(r'\b[A-Z0-9][A-Z0-9]{2,}\b', description_upper)
    print(f"Words extracted: {words}")
    print()
    
    # Check noise words
    noise_words = {
        'THE', 'AND', 'VAN', 'DER', 'DEN', 'HET', 'EEN', 'VOOR', 'NAAR', 'BIJ',
        'BETALING', 'PAYMENT', 'TRANSACTION', 'TRANSFER', 'ONLINE', 'WEBSHOP',
        'BETREFT', 'INFO', 'KIJK', 'MEER', 'FACTUUR', 'XUI', 'NL04', 'NL27', 'NL15',
        'RABONL2U', 'INGBNL2AXXX', 'CITINL2X', 'BOFAIE3X', 'ADYBNL2AXXX', 'DEUTNL2A',
        'EUR', 'RABO', 'ING', 'CITI', 'BOFA', 'ADYB', 'DEUT'
    }
    
    for word in words:
        print(f"Checking word: '{word}'")
        
        if word in noise_words:
            print(f"  ✗ Rejected: noise word")
            continue
        
        if len(word) < 3 or len(word) > 25:
            print(f"  ✗ Rejected: length {len(word)} (must be 3-25)")
            continue
        
        # Check alphanumeric patterns
        has_letters = bool(re.search(r'[A-Z]', word))
        has_digits = bool(re.search(r'\d', word))
        
        print(f"  - Has letters: {has_letters}, Has digits: {has_digits}")
        
        if ((has_letters and has_digits and len(word) >= 8) or
            re.match(r'^[A-Z]{2}\d+[A-Z]+\d+$', word) or
            re.match(r'^\d+[A-Z]+\d+$', word) or
            re.match(r'^[A-Z]+\d+[A-Z]+$', word) or
            word.startswith('P16') or
            word.startswith('NO') or
            word.startswith('ID') or
            'FACTUURNR' in word or
            'KLANTNR' in word):
            print(f"  ✗ Rejected: transaction code pattern")
            continue
        
        # Check vowels
        vowels = set('AEIOU')
        has_vowels = len(set(word) & vowels) > 0
        print(f"  - Has vowels: {has_vowels}")
        
        # Check acronym exception
        if len(word) >= 3 and len(word) <= 5 and word.isupper() and not word.isdigit():
            print(f"  ✓ Accepted: acronym exception (3-5 uppercase letters)")
            continue
        
        if has_vowels and not word.isdigit() and len(word) >= 3:
            print(f"  ✓ Accepted: valid word")
        else:
            print(f"  ✗ Rejected: no vowels or invalid")

if __name__ == '__main__':
    test_verb_extraction()
