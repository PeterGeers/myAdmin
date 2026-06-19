#!/usr/bin/env python3
"""
Pattern Detection Module for Banking Transactions

Extracted from pattern_analyzer.py — contains pattern detection logic:
- Description normalization and cleaning
- Company name extraction from transaction descriptions
- Reference number extraction
- Verb (company identifier) extraction
- Keyword extraction
- Pattern analysis for debet, credit, and reference number prediction

These functions detect patterns in historical transaction data.
They do NOT score/rank patterns or manage caching.
"""

import re
from collections import defaultdict
from typing import Dict, List, Optional, Any, Callable


# ============================================================================
# Description Normalization / Cleaning Utilities
# ============================================================================

def extract_keywords(description: str) -> List[str]:
    """Extract meaningful keywords from transaction description"""
    if not description:
        return []

    # Clean and normalize
    description = description.lower().strip()

    # Remove common noise words
    noise_words = {
        'de', 'het', 'een', 'van', 'voor', 'naar', 'bij', 'op', 'in', 'aan', 'met',
        'the', 'a', 'an', 'of', 'for', 'to', 'at', 'on', 'in', 'with', 'by',
        'and', 'or', 'but', 'en', 'of', 'maar'
    }

    # Extract words (alphanumeric, minimum 3 characters)
    words = re.findall(r'\b[a-zA-Z0-9]{3,}\b', description)
    keywords = [word for word in words if word not in noise_words]

    # Return most frequent/meaningful keywords
    return keywords[:5]  # Top 5 keywords


def extract_company_name(description: str) -> Optional[str]:
    """Extract the main company/vendor name from description"""
    if not description:
        return None

    description_upper = description.upper().strip()

    # Strategy 1: Look for known company patterns (highest priority)
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

    for pattern, company in company_patterns:
        if re.search(pattern, description_upper):
            return company

    # Strategy 2: Remove common banking prefixes/suffixes and extract meaningful words
    cleaning_patterns = [
        r'\bBETAALVERZOEK\b',
        r'\bINCASSOOPDRACHT\b',
        r'\bOVERBOEKING\b',
        r'\bIDEAL\b',
        r'\bPINBETALING\b',
        r'\bGEA\b',
        r'^BCK\*?\s*',          # Bankcard (betaalkaart) prefix at start of description
        r'\bNR:\w+\b',
        r'\bREF:\w+\b',
        r'\bTRN:\w+\b',
        r'\d{2}-\d{2}-\d{4}',  # Dates
        r'\d{2}:\d{2}',        # Times
        r'[,\.]?\s*NEDERLAND\b',
        r'[,\.]?\s*BV\b',
        r'[,\.]?\s*NV\b',
        r'[,\.]?\s*VOF\b',
        r'[,\.]?\s*B\.V\.\b',
        r'[,\.]?\s*N\.V\.\b',
        r'\bXUI-\d+\b',        # Transaction IDs
        r'\bNL\d{2}[A-Z]{4}\d+\b',  # IBAN patterns
        r'\b(?:BA|BC|BEA)\b',  # Payment type codes (ba=betaalautomaat, bc=betaalchip)
        r'\bPAS:\s*\S+\b',     # Card number references
        r'\bPASNR\.?\s*\d*\b', # Card number references
        r'\bTERMIN\w*\b',      # Terminal references
        r'\b\d{4}[A-Z]{2}\b', # Postal codes (e.g., 2135JV)
        r'\bNLD\b',           # Country code
    ]

    cleaned_desc = description_upper
    for pattern in cleaning_patterns:
        cleaned_desc = re.sub(pattern, '', cleaned_desc)

    # Extract meaningful words (company names)
    # Allow digits at start of company names (e.g., "2Theloo", "123Inkt")
    words = re.findall(r'\b[A-Z0-9][A-Z0-9]{2,}\b', cleaned_desc)

    # Filter out common noise words and transaction codes
    noise_words = {
        'THE', 'AND', 'VAN', 'DER', 'DEN', 'HET', 'EEN', 'VOOR', 'NAAR', 'BIJ',
        'BETALING', 'PAYMENT', 'TRANSACTION', 'TRANSFER', 'ONLINE', 'WEBSHOP',
        'BETREFT', 'INFO', 'KIJK', 'MEER', 'FACTUUR', 'XUI', 'NL04', 'NL27', 'NL15',
        'RABONL2U', 'INGBNL2AXXX', 'CITINL2X', 'BOFAIE3X', 'ADYBNL2AXXX', 'DEUTNL2A',
        'EUR', 'RABO', 'ING', 'CITI', 'BOFA', 'ADYB', 'DEUT',
        'BCK', 'BEA', 'GEA', 'PIN', 'PAS', 'RETOUR', 'NLD',
    }

    # Filter out transaction codes and meaningless strings
    meaningful_words = []
    for word in words:
        # Skip if it's a noise word
        if word in noise_words:
            continue

        # Skip if it's too short or too long for a company name
        if len(word) < 3 or len(word) > 25:
            continue

        # Skip transaction IDs and codes (patterns that are clearly not company names)
        # Only skip alphanumeric codes that contain BOTH letters AND numbers
        # Pure alphabetic words (like "HOOGVLIET") should NOT be filtered
        has_letters = bool(re.search(r'[A-Z]', word))
        has_digits = bool(re.search(r'\d', word))

        if ((has_letters and has_digits and len(word) >= 8) or  # Long mixed alphanumeric codes
            re.match(r'^[A-Z]{2}\d+[A-Z]+\d+$', word) or  # Mixed letter-number patterns
            re.match(r'^\d+[A-Z]+\d+$', word) or  # Number-letter-number patterns
            re.match(r'^[A-Z]+\d+[A-Z]+$', word) or  # Letter-number-letter patterns
            word.startswith('P16') or  # Transaction prefixes
            word.startswith('NO') or   # Reference prefixes
            word.startswith('ID') or   # ID prefixes
            'FACTUURNR' in word or     # Invoice number references
            'KLANTNR' in word):        # Customer number references
            continue

        # Additional validation: check if word looks like a real company name
        # Real company names typically have vowels and reasonable letter patterns
        vowels = set('AEIOU')

        # Allow acronyms (3-5 uppercase letters) even without vowels (e.g., "SVB", "KPN", "NS")
        if len(word) >= 3 and len(word) <= 5 and word.isupper() and not word.isdigit():
            meaningful_words.append(word)
            continue

        # Regular words must have vowels
        if (len(set(word) & vowels) > 0 and  # Has at least one vowel
            not word.isdigit() and           # Not all digits
            len(word) >= 3):                 # Minimum length
            meaningful_words.append(word)

    if meaningful_words:
        # Return the first meaningful word as the company name
        return meaningful_words[0]

    return None


def extract_reference_number_from_description(description: str) -> Optional[str]:
    """
    Extract reference/invoice numbers from description

    Patterns to look for:
    - Invoice numbers: 6+ digits
    - Reference numbers: alphanumeric codes
    - Account numbers: specific patterns
    """
    if not description:
        return None

    # Pattern 1: Pure numeric sequences (6+ digits) - likely invoice numbers
    numeric_matches = re.findall(r'\b\d{6,12}\b', description)
    if numeric_matches:
        # Return the longest numeric sequence (most likely to be invoice number)
        return max(numeric_matches, key=len)

    # Pattern 2: Alphanumeric reference codes (4+ chars with mix of letters/numbers)
    alphanumeric_matches = re.findall(r'\b[A-Z]{2,4}\d{4,10}\b', description)
    if alphanumeric_matches:
        return alphanumeric_matches[0]

    # Pattern 3: Reference codes with specific prefixes
    ref_patterns = [
        r'\bREF:?\s*([A-Z0-9]{4,12})\b',
        r'\bNR:?\s*([A-Z0-9]{4,12})\b',
        r'\bINV:?\s*([A-Z0-9]{4,12})\b',
        r'\bFACTUUR:?\s*([A-Z0-9]{4,12})\b'
    ]

    for pattern in ref_patterns:
        matches = re.findall(pattern, description)
        if matches:
            return matches[0]

    return None


def is_valid_verb(verb: str) -> bool:
    """
    Validate that a verb is a real company name, not a transaction ID

    Returns False for patterns that are clearly transaction codes
    """
    if not verb or len(verb) < 3:
        return False

    # Reject patterns that look like transaction IDs
    # Only reject long codes that have BOTH letters AND digits (transaction IDs)
    # Pure alphabetic company names like "HOOGVLIET" should NOT be rejected
    has_letters = bool(re.search(r'[A-Z]', verb))
    has_digits = bool(re.search(r'\d', verb))

    invalid_patterns = [
        # Only reject long alphanumeric codes that have BOTH letters AND digits
        (r'^[A-Z0-9]{8,}$', has_letters and has_digits),  # Long mixed codes only
        (r'^[A-Z]{2}\d+[A-Z]+\d+$', True),  # Mixed patterns like QG0DBCBZELL92QM4
        (r'^\d+[A-Z]+\d+$', True),          # Number-letter-number
        (r'^[A-Z]+\d+[A-Z]+$', True),       # Letter-number-letter
        (r'^P\d{10,}$', True),              # Transaction IDs starting with P
        (r'^[A-Z]{1,3}\d{8,}$', True)       # Short prefix + long number
    ]

    for pattern, should_check in invalid_patterns:
        if should_check and re.match(pattern, verb):
            return False

    # Reject specific known transaction prefixes
    invalid_prefixes = ['FACTUURNR', 'KLANTNR', 'TRANSACTIE', 'BETALING']
    if any(verb.startswith(prefix) for prefix in invalid_prefixes):
        return False

    # Must have at least one vowel (real words have vowels)
    # EXCEPTION: Allow short acronyms (3-5 chars) without vowels (e.g., "TMC", "KPN", "NS")
    vowels = set('AEIOU')
    has_vowels = len(set(verb) & vowels) > 0

    if not has_vowels:
        # Allow short acronyms (3-5 uppercase letters without digits)
        if 3 <= len(verb) <= 5 and verb.isupper() and not has_digits:
            return True
        return False

    return True


def extract_compound_verb_from_description(description: str, reference_number: str) -> Optional[str]:
    """
    Extract compound verb (company + reference) from transaction description

    Logic:
    1. Extract company name (primary verb)
    2. Extract reference/invoice number (secondary verb)
    3. Combine into compound verb: "COMPANY|REFERENCE"

    Examples:
    - "ANWB Energie B.V. 100431234 NL28BUKK..." → "ANWB|100431234"
    - "ANWB BV ARNL3367411472 Betreft... 7073498490" → "ANWB|7073498490"
    """
    if not description:
        return None

    # Clean description
    description = description.upper().strip()

    # Extract company name (primary verb)
    company_name = extract_company_name(description)
    if not company_name:
        return None

    # Extract reference/invoice number (secondary verb)
    ref_number = extract_reference_number_from_description(description)

    if ref_number:
        # Return compound verb
        return f"{company_name}|{ref_number}"
    else:
        # Fallback to simple company name
        return company_name


def extract_verb_from_description(description: str, reference_number: str) -> Optional[str]:
    """
    Extract verb from description - supports both simple and compound verbs

    This method maintains backward compatibility while supporting compound verbs
    """
    # Try compound verb extraction first
    compound_verb = extract_compound_verb_from_description(description, reference_number)
    if compound_verb and '|' in compound_verb:
        return compound_verb

    # Fallback to simple company name extraction
    simple_verb = extract_company_name(description) if description else None

    # Validate that the verb makes sense (not a transaction ID)
    if simple_verb and is_valid_verb(simple_verb):
        return simple_verb

    return None


# ============================================================================
# Pattern Analysis Functions
# ============================================================================

def analyze_debet_patterns(
    transactions: List[Dict],
    administration: str,
    is_bank_account_fn: Callable[[str, str], bool]
) -> Dict[str, Any]:
    """
    Analyze patterns for predicting Debet account numbers

    REQ-PAT-002: Use ReferenceNumber and bank account logic:
    - If Credit is bank account → predict Debet from historical patterns
    - Use ReferenceNumber matching in transaction descriptions

    Args:
        transactions: List of transaction dictionaries
        administration: The administration to analyze for
        is_bank_account_fn: Callable to check if an account is a bank account
    """
    debet_patterns = defaultdict(lambda: {
        'occurrences': 0,
        'descriptions': [],
        'reference_numbers': set(),
        'amounts': [],
        'confidence': 0.0,
        'last_seen': None
    })

    for tx in transactions:
        debet = tx.get('Debet')
        credit = tx.get('Credit')
        description = tx.get('TransactionDescription', '').strip()
        ref_num = tx.get('ReferenceNumber', '').strip()
        amount = tx.get('TransactionAmount', 0)
        date = tx.get('TransactionDate')

        # Skip if no debet
        if not debet:
            continue

        # REQ-PAT-004: Bank account lookup logic
        # Only create debet patterns when credit is a bank account
        # (so we can predict debet when we know credit is bank account)
        if not is_bank_account_fn(credit, administration):
            continue

        # Create pattern key using multiple criteria (REQ-PAT-002)
        desc_keywords = extract_keywords(description)
        ref_keywords = extract_keywords(ref_num) if ref_num else []

        # Combine description and reference keywords for better matching
        all_keywords = desc_keywords + ref_keywords
        pattern_key = f"bank_credit_{credit}_{'-'.join(sorted(set(all_keywords[:3])))}"

        pattern = debet_patterns[pattern_key]
        pattern['occurrences'] += 1
        pattern['descriptions'].append(description)
        pattern['reference_numbers'].add(ref_num)
        pattern['amounts'].append(float(amount) if amount else 0.0)
        pattern['predicted_debet'] = debet
        pattern['credit_account'] = credit
        pattern['last_seen'] = date
        pattern['is_bank_credit'] = True  # Mark that credit is bank account

    # Calculate confidence scores and filter patterns
    filtered_patterns = {}
    for key, pattern in debet_patterns.items():
        if pattern['occurrences'] >= 1:  # Minimum 1 occurrence (learn from first entry)
            pattern['confidence'] = min(pattern['occurrences'] / 10.0, 1.0)  # Max confidence 1.0
            pattern['reference_numbers'] = list(pattern['reference_numbers'])
            pattern['avg_amount'] = sum(pattern['amounts']) / len(pattern['amounts'])
            filtered_patterns[key] = dict(pattern)

    return filtered_patterns


def analyze_credit_patterns(
    transactions: List[Dict],
    administration: str,
    is_bank_account_fn: Callable[[str, str], bool]
) -> Dict[str, Any]:
    """
    Analyze patterns for predicting Credit account numbers

    REQ-PAT-002: Use ReferenceNumber and bank account logic:
    - If Debet is bank account → predict Credit from historical patterns
    - Use ReferenceNumber matching in transaction descriptions

    Args:
        transactions: List of transaction dictionaries
        administration: The administration to analyze for
        is_bank_account_fn: Callable to check if an account is a bank account
    """
    credit_patterns = defaultdict(lambda: {
        'occurrences': 0,
        'descriptions': [],
        'reference_numbers': set(),
        'amounts': [],
        'confidence': 0.0,
        'last_seen': None
    })

    for tx in transactions:
        debet = tx.get('Debet')
        credit = tx.get('Credit')
        description = tx.get('TransactionDescription', '').strip()
        ref_num = tx.get('ReferenceNumber', '').strip()
        amount = tx.get('TransactionAmount', 0)
        date = tx.get('TransactionDate')

        # Skip if no credit
        if not credit:
            continue

        # REQ-PAT-004: Bank account lookup logic
        # Only create credit patterns when debet is a bank account
        # (so we can predict credit when we know debet is bank account)
        if not is_bank_account_fn(debet, administration):
            continue

        # Create pattern key using multiple criteria (REQ-PAT-002)
        desc_keywords = extract_keywords(description)
        ref_keywords = extract_keywords(ref_num) if ref_num else []

        # Combine description and reference keywords for better matching
        all_keywords = desc_keywords + ref_keywords
        pattern_key = f"bank_debet_{debet}_{'-'.join(sorted(set(all_keywords[:3])))}"

        pattern = credit_patterns[pattern_key]
        pattern['occurrences'] += 1
        pattern['descriptions'].append(description)
        pattern['reference_numbers'].add(ref_num)
        pattern['amounts'].append(float(amount) if amount else 0.0)
        pattern['predicted_credit'] = credit
        pattern['debet_account'] = debet
        pattern['last_seen'] = date
        pattern['is_bank_debet'] = True  # Mark that debet is bank account

    # Calculate confidence scores and filter patterns
    filtered_patterns = {}
    for key, pattern in credit_patterns.items():
        if pattern['occurrences'] >= 1:  # Minimum 1 occurrence (learn from first entry)
            pattern['confidence'] = min(pattern['occurrences'] / 10.0, 1.0)  # Max confidence 1.0
            pattern['reference_numbers'] = list(pattern['reference_numbers'])
            pattern['avg_amount'] = sum(pattern['amounts']) / len(pattern['amounts'])
            filtered_patterns[key] = dict(pattern)

    return filtered_patterns


def analyze_reference_patterns(
    transactions: List[Dict],
    administration: str,
    is_bank_account_fn: Callable[[str, str], bool]
) -> Dict[str, Any]:
    """
    Analyze patterns for predicting ReferenceNumber values using verb-based logic

    Logic: Administration + BankAccount + Verb → ReferenceNumber + Debet/Credit accounts
    Example: "GoodwinSolutions" + "1300" + "Picnic" → "Picnic" + debet="1003", credit="1300"

    REQ-PAT-002: Use historical ReferenceNumbers to match transaction descriptions

    Args:
        transactions: List of transaction dictionaries
        administration: The administration to analyze for
        is_bank_account_fn: Callable to check if an account is a bank account
    """
    verb_patterns = {}

    for tx in transactions:
        debet = tx.get('Debet')
        credit = tx.get('Credit')
        description = tx.get('TransactionDescription', '').strip()
        ref_num = tx.get('ReferenceNumber', '').strip()
        date = tx.get('TransactionDate')

        if not ref_num or not description:
            continue

        # Identify the bank account (either debet or credit)
        bank_account = None
        other_account = None

        if is_bank_account_fn(debet, administration):
            bank_account = debet
            other_account = credit
        elif is_bank_account_fn(credit, administration):
            bank_account = credit
            other_account = debet
        else:
            continue  # Skip if no bank account involved

        # Extract verb from description (company/vendor name)
        verb = extract_verb_from_description(description, ref_num)
        if not verb:
            continue

        # Parse compound verb if applicable
        is_compound = '|' in verb
        verb_company = None
        verb_reference = None

        if is_compound:
            parts = verb.split('|', 1)
            verb_company = parts[0]
            verb_reference = parts[1] if len(parts) > 1 else None
        else:
            verb_company = verb

        # Create pattern keys at two levels:
        # 1. Compound key (company + reference) for multi-product vendors (e.g., ASR with 5 insurances)
        # 2. Company-only key as fallback for single-product vendors
        if is_compound and verb_reference:
            compound_key = f"{administration}_{bank_account}_{verb_company}|{verb_reference}"
            verb_patterns[compound_key] = {
                'administration': administration,
                'bank_account': bank_account,
                'verb': f"{verb_company}|{verb_reference}",
                'verb_company': verb_company,
                'verb_reference': verb_reference,
                'is_compound': True,
                'reference_number': ref_num,
                'debet_account': debet,
                'credit_account': credit,
                'other_account': other_account,
                'occurrences': verb_patterns.get(compound_key, {}).get('occurrences', 0) + 1,
                'confidence': 1.0,
                'last_seen': date,
                'sample_description': description
            }

        # Company-only key (fallback for simple verbs, or aggregated for single-product vendors)
        company_key = f"{administration}_{bank_account}_{verb_company}"

        # For compound verbs: only store company-level pattern if ALL occurrences
        # of this company map to the same accounts (single-product vendor)
        existing = verb_patterns.get(company_key)
        if existing:
            # Check if this transaction uses the same accounts as existing pattern
            if (existing.get('debet_account') == debet and
                    existing.get('credit_account') == credit):
                # Same accounts — safe to keep company-level pattern
                existing['occurrences'] = existing.get('occurrences', 0) + 1
                existing['last_seen'] = date
            else:
                # Different accounts for same company — mark as ambiguous
                # Don't use company-level pattern for multi-product vendors
                existing['_ambiguous'] = True
                existing['confidence'] = 0.0
        else:
            verb_patterns[company_key] = {
                'administration': administration,
                'bank_account': bank_account,
                'verb': verb_company,
                'verb_company': verb_company,
                'verb_reference': verb_reference,
                'is_compound': is_compound,
                'reference_number': ref_num,
                'debet_account': debet,
                'credit_account': credit,
                'other_account': other_account,
                'occurrences': 1,
                'confidence': 1.0,
                'last_seen': date,
                'sample_description': description
            }

    return verb_patterns
