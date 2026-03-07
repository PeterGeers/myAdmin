"""
Test script to debug why "Hoogvliet" verb extraction fails
"""

import sys
import os
import re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pattern_analyzer import PatternAnalyzer

def test_extraction_step_by_step(description):
    """Step-by-step debugging of verb extraction"""
    print(f"\n{'='*80}")
    print(f"Testing: '{description}'")
    print(f"{'='*80}")
    
    description_upper = description.upper().strip()
    print(f"1. Uppercase: '{description_upper}'")
    
    # Check known patterns
    company_patterns = [
        (r'\bBOL\.COM\b', 'BOL'),
        (r'\bAIRBNB\b', 'AIRBNB'),
        (r'\bPICNIC\b', 'PICNIC'),
        (r'\bBOOKING\.COM\b', 'BOOKING'),
        (r'\bBOOKING\b', 'BOOKING'),
    ]
    
    for pattern, company in company_patterns:
        if re.search(pattern, description_upper):
            print(f"2. Matched known pattern: {company}")
            return company
    
    print("2. No known pattern matched")
    
    # Cleaning patterns
    cleaning_patterns = [
        r'\bBETAALVERZOEK\b',
        r'\bINCASSOOPDRACHT\b',
        r'\bOVERBOEKING\b',
        r'\bIDEAL\b',
        r'\bPINBETALING\b',
        r'\bGEA\b',
        r'\bNR:\w+\b',
        r'\bREF:\w+\b',
        r'\bTRN:\w+\b',
        r'\d{2}-\d{2}-\d{4}',
        r'\d{2}:\d{2}',
        r'[,\.]?\s*NEDERLAND\b',
        r'[,\.]?\s*BV\b',
        r'[,\.]?\s*NV\b',
        r'[,\.]?\s*VOF\b',
        r'[,\.]?\s*B\.V\.\b',
        r'[,\.]?\s*N\.V\.\b',
        r'\bXUI-\d+\b',
        r'\bNL\d{2}[A-Z]{4}\d+\b'
    ]
    
    cleaned_desc = description_upper
    for pattern in cleaning_patterns:
        before = cleaned_desc
        cleaned_desc = re.sub(pattern, '', cleaned_desc)
        if before != cleaned_desc:
            print(f"3. Cleaned with pattern {pattern}: '{cleaned_desc}'")
    
    print(f"3. After cleaning: '{cleaned_desc}'")
    
    # Extract words
    words = re.findall(r'\b[A-Z0-9][A-Z0-9]{2,}\b', cleaned_desc)
    print(f"4. Extracted words: {words}")
    
    # Filter noise words
    noise_words = {
        'THE', 'AND', 'VAN', 'DER', 'DEN', 'HET', 'EEN', 'VOOR', 'NAAR', 'BIJ',
        'BETALING', 'PAYMENT', 'TRANSACTION', 'TRANSFER', 'ONLINE', 'WEBSHOP',
        'BETREFT', 'INFO', 'KIJK', 'MEER', 'FACTUUR', 'XUI', 'NL04', 'NL27', 'NL15',
        'RABONL2U', 'INGBNL2AXXX', 'CITINL2X', 'BOFAIE3X', 'ADYBNL2AXXX', 'DEUTNL2A',
        'EUR', 'RABO', 'ING', 'CITI', 'BOFA', 'ADYB', 'DEUT'
    }
    
    meaningful_words = []
    for word in words:
        print(f"\n  Checking word: '{word}'")
        
        if word in noise_words:
            print(f"    ❌ Skipped: noise word")
            continue
        
        if len(word) < 3 or len(word) > 25:
            print(f"    ❌ Skipped: length {len(word)} (must be 3-25)")
            continue
        
        # Transaction ID patterns
        if (re.match(r'^[A-Z0-9]{8,}$', word) or
            re.match(r'^[A-Z]{2}\d+[A-Z]+\d+$', word) or
            re.match(r'^\d+[A-Z]+\d+$', word) or
            re.match(r'^[A-Z]+\d+[A-Z]+$', word) or
            word.startswith('P16') or
            word.startswith('NO') or
            word.startswith('ID') or
            'FACTUURNR' in word or
            'KLANTNR' in word):
            print(f"    ❌ Skipped: looks like transaction ID")
            continue
        
        # Vowel check
        vowels = set('AEIOU')
        has_vowels = len(set(word) & vowels) > 0
        print(f"    Has vowels: {has_vowels} (vowels: {set(word) & vowels})")
        
        # Acronym check
        if len(word) >= 3 and len(word) <= 5 and word.isupper() and not word.isdigit():
            print(f"    ✅ Accepted: acronym (3-5 chars, uppercase)")
            meaningful_words.append(word)
            continue
        
        # Regular word check
        if has_vowels and not word.isdigit() and len(word) >= 3:
            print(f"    ✅ Accepted: regular word with vowels")
            meaningful_words.append(word)
        else:
            print(f"    ❌ Skipped: failed vowel/digit/length check")
    
    print(f"\n5. Meaningful words: {meaningful_words}")
    
    if meaningful_words:
        result = meaningful_words[0]
        print(f"6. RESULT: '{result}'")
        return result
    else:
        print(f"6. RESULT: None")
        return None

# Test cases
test_cases = [
    "Hoogvliet",
    "TMC",
    "Albert Heijn",
    "APCOA Parking",
    "Lidl",
    "Cupido Gebakskramen"
]

print("\n" + "="*80)
print("VERB EXTRACTION DEBUG TEST")
print("="*80)

for test in test_cases:
    result = test_extraction_step_by_step(test)

# Also test with actual PatternAnalyzer
print("\n\n" + "="*80)
print("ACTUAL PATTERN ANALYZER RESULTS")
print("="*80)

analyzer = PatternAnalyzer(test_mode=False)
for test in test_cases:
    result = analyzer._extract_company_name(test)
    print(f"'{test}' → '{result}'")
