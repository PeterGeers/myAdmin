#!/usr/bin/env python3
"""
Pattern Scoring and Ranking Module for Banking Transactions

Extracted from pattern_analyzer.py — contains pattern prediction and scoring logic:
- Predict debet account from verb patterns
- Predict credit account from verb patterns
- Predict reference number from verb patterns
- Resolve conflicts between multiple matching patterns
- Generate pattern statistics

These functions score/rank patterns to make predictions.
They do NOT detect patterns or manage caching.
"""

import re
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any, Callable


def generate_pattern_statistics(
    transactions: List[Dict],
    debet_patterns: Dict,
    credit_patterns: Dict,
    reference_patterns: Dict,
    is_bank_account_fn: Callable[[str, str], bool]
) -> Dict[str, Any]:
    """Generate comprehensive statistics about discovered patterns"""
    total_transactions = len(transactions)

    # Count transactions with missing fields
    missing_debet = sum(1 for tx in transactions if not tx.get('Debet'))
    missing_credit = sum(1 for tx in transactions if not tx.get('Credit'))
    missing_reference = sum(1 for tx in transactions if not tx.get('ReferenceNumber'))

    # Count bank account transactions
    bank_debet_count = 0
    bank_credit_count = 0

    for tx in transactions:
        admin = tx.get('Administration', '')
        if tx.get('Debet') and is_bank_account_fn(tx['Debet'], admin):
            bank_debet_count += 1
        if tx.get('Credit') and is_bank_account_fn(tx['Credit'], admin):
            bank_credit_count += 1

    return {
        'total_transactions': total_transactions,
        'missing_fields': {
            'debet': missing_debet,
            'credit': missing_credit,
            'reference': missing_reference
        },
        'bank_account_transactions': {
            'debet_is_bank': bank_debet_count,
            'credit_is_bank': bank_credit_count
        },
        'patterns_by_type': {
            'debet_patterns': len(debet_patterns),
            'credit_patterns': len(credit_patterns),
            'reference_patterns': len(reference_patterns)
        },
        'pattern_confidence': {
            'debet_avg_confidence': sum(p['confidence'] for p in debet_patterns.values()) / max(len(debet_patterns), 1),
            'credit_avg_confidence': sum(p['confidence'] for p in credit_patterns.values()) / max(len(credit_patterns), 1),
            'reference_avg_confidence': sum(p['confidence'] for p in reference_patterns.values()) / max(len(reference_patterns), 1)
        }
    }


def calculate_statistics_from_db_patterns(
    debet_patterns: Dict,
    credit_patterns: Dict,
    reference_patterns: Dict
) -> Dict:
    """Calculate statistics from database-loaded patterns"""
    return {
        'patterns_by_type': {
            'debet_patterns': len(debet_patterns),
            'credit_patterns': len(credit_patterns),
            'reference_patterns': len(reference_patterns)
        },
        'pattern_confidence': {
            'debet_avg_confidence': sum(p['confidence'] for p in debet_patterns.values()) / max(len(debet_patterns), 1),
            'credit_avg_confidence': sum(p['confidence'] for p in credit_patterns.values()) / max(len(credit_patterns), 1),
            'reference_avg_confidence': sum(p['confidence'] for p in reference_patterns.values()) / max(len(reference_patterns), 1)
        }
    }


def resolve_pattern_conflicts(
    matching_patterns: List[Tuple[str, Dict]],
    transaction: Dict,
    administration: str,
    is_bank_account_fn: Callable[[str, str], bool]
) -> Optional[Tuple[str, Dict]]:
    """
    Resolve conflicts when multiple patterns match the same verb

    Resolution strategy (in order of priority):
    1. Most recent pattern (last_seen date)
    2. Highest frequency (occurrences)
    3. Amount similarity (if available)
    4. Account number descending (fallback)
    """
    if not matching_patterns:
        return None

    if len(matching_patterns) == 1:
        return matching_patterns[0]

    transaction_amount = transaction.get('TransactionAmount', 0)

    # Score each pattern
    scored_patterns = []
    for key, pattern in matching_patterns:
        score = 0

        # 1. Recency score (most important - 40% weight)
        last_seen = pattern.get('last_seen')
        if last_seen:
            if isinstance(last_seen, str):
                try:
                    last_seen = datetime.strptime(last_seen, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    last_seen = None

            if last_seen:
                if isinstance(last_seen, datetime):
                    last_seen = last_seen.date()
                days_ago = (date.today() - last_seen).days
                # More recent = higher score (max 40 points)
                recency_score = max(0, 40 - (days_ago / 30))  # Decay over months
                score += recency_score

        # 2. Frequency score (30% weight)
        occurrences = pattern.get('occurrences', 1)
        frequency_score = min(30, occurrences * 2)  # Max 30 points
        score += frequency_score

        # 3. Amount similarity score (20% weight) - if transaction amount available
        if transaction_amount and transaction_amount > 0:
            pattern_amounts = pattern.get('amounts', [])
            if pattern_amounts:
                avg_amount = sum(pattern_amounts) / len(pattern_amounts)
                amount_diff = abs(transaction_amount - avg_amount)
                # Closer amounts = higher score
                if amount_diff < avg_amount * 0.1:  # Within 10%
                    score += 20
                elif amount_diff < avg_amount * 0.5:  # Within 50%
                    score += 10

        # 4. Bank account preference (10% weight)
        # Prefer patterns with the same bank account as transaction
        transaction_bank = None
        if is_bank_account_fn(transaction.get('Debet', ''), administration):
            transaction_bank = transaction.get('Debet')
        elif is_bank_account_fn(transaction.get('Credit', ''), administration):
            transaction_bank = transaction.get('Credit')

        if transaction_bank and pattern.get('bank_account') == transaction_bank:
            score += 10

        scored_patterns.append((score, key, pattern))

    # Sort by score (highest first)
    scored_patterns.sort(key=lambda x: x[0], reverse=True)

    # Return the best match
    best_score, best_key, best_pattern = scored_patterns[0]

    return (best_key, best_pattern)


def predict_debet(
    transaction: Dict,
    debet_patterns: Dict,
    administration: str,
    is_bank_account_fn: Callable[[str, str], bool],
    extract_verb_fn: Callable[[str, str], Optional[str]],
    get_filtered_patterns_fn: Callable[[str], Dict[str, Any]]
) -> Optional[Dict]:
    """
    Predict Debet account number using verb patterns

    REQ-PAT-004: If Credit is bank account → retrieve Debet number from pattern view
    Uses unified verb pattern: Administration + BankAccount + Verb → Debet account

    Only makes predictions when there's reliable historical data
    """
    description = transaction.get('TransactionDescription', '').strip()
    credit = transaction.get('Credit', '')

    if not description:
        return None

    # REQ-PAT-004: Only predict debet when credit is a bank account
    if not is_bank_account_fn(credit, administration):
        return None

    # Extract verb from description
    verb = extract_verb_fn(description, transaction.get('ReferenceNumber', ''))
    if not verb:
        # No valid verb - leave empty for manual fixing
        return None

    # Parse compound verb
    is_compound = '|' in verb
    if is_compound:
        verb_company = verb.split('|', 1)[0]
    else:
        verb_company = verb

    # Get reference patterns (which contain verb patterns)
    patterns = get_filtered_patterns_fn(administration)
    reference_patterns = patterns.get('reference_patterns', {})

    # Strategy 1: Try COMPOUND key first (most specific — handles multi-product vendors like ASR)
    if is_compound:
        compound_key = f"{administration}_{credit}_{verb}"
        if compound_key in reference_patterns:
            pattern = reference_patterns[compound_key]
            if pattern.get('confidence', 0) > 0 and pattern.get('credit_account') == credit:
                return {
                    'value': pattern.get('debet_account'),
                    'confidence': pattern.get('confidence', 1.0),
                    'pattern_key': compound_key,
                    'reason': f'Compound match: Verb "{verb}" with bank credit {credit}',
                    'verb': verb
                }

    # Strategy 2: Try COMPANY-ONLY key (fallback for single-product vendors)
    company_key = f"{administration}_{credit}_{verb_company}"
    if company_key in reference_patterns:
        pattern = reference_patterns[company_key]
        # Skip ambiguous patterns (multi-product vendors where company-level is unreliable)
        if (pattern.get('confidence', 0) > 0 and
                not pattern.get('_ambiguous') and
                pattern.get('credit_account') == credit):
            return {
                'value': pattern.get('debet_account'),
                'confidence': pattern.get('confidence', 1.0),
                'pattern_key': company_key,
                'reason': f'Company match: Verb "{verb_company}" with bank credit {credit}',
                'verb': verb
            }

    # Strategy 3: Handle multiple matches with conflict resolution
    matching_patterns = []
    for key, pattern in reference_patterns.items():
        if pattern.get('_ambiguous'):
            continue
        if (pattern.get('credit_account') == credit and
            pattern.get('administration') == administration and
            pattern.get('confidence', 0) > 0 and
            pattern.get('occurrences', 0) >= 1):
            # Match on full verb or company
            if pattern.get('verb') == verb:
                matching_patterns.append((key, pattern))
            elif pattern.get('verb_company') == verb_company and not is_compound:
                matching_patterns.append((key, pattern))

    if matching_patterns:
        best_pattern = resolve_pattern_conflicts(matching_patterns, transaction, administration, is_bank_account_fn)
        if best_pattern and best_pattern[1].get('confidence', 0) >= 0.8:
            key, pattern = best_pattern
            return {
                'value': pattern.get('debet_account'),
                'confidence': pattern.get('confidence', 1.0) * 0.9,
                'pattern_key': key,
                'reason': f'High confidence match: Verb "{verb}" with bank credit {credit}',
                'verb': verb,
                'alternatives': len(matching_patterns)
            }

    # No reliable historical pattern - leave empty for manual fixing
    return None


def predict_credit(
    transaction: Dict,
    credit_patterns: Dict,
    administration: str,
    is_bank_account_fn: Callable[[str, str], bool],
    extract_verb_fn: Callable[[str, str], Optional[str]],
    get_filtered_patterns_fn: Callable[[str], Dict[str, Any]]
) -> Optional[Dict]:
    """
    Predict Credit account number using verb patterns

    REQ-PAT-004: If Debet is bank account → retrieve Credit number from pattern view
    Uses unified verb pattern: Administration + BankAccount + Verb → Credit account

    Only makes predictions when there's reliable historical data
    """
    description = transaction.get('TransactionDescription', '').strip()
    debet = transaction.get('Debet', '')

    if not description:
        return None

    # REQ-PAT-004: Only predict credit when debet is a bank account
    if not is_bank_account_fn(debet, administration):
        return None

    # Extract verb from description
    verb = extract_verb_fn(description, transaction.get('ReferenceNumber', ''))
    if not verb:
        # No valid verb - leave empty for manual fixing
        return None

    # Parse compound verb
    is_compound = '|' in verb
    if is_compound:
        verb_company = verb.split('|', 1)[0]
    else:
        verb_company = verb

    # Get reference patterns (which contain verb patterns)
    patterns = get_filtered_patterns_fn(administration)
    reference_patterns = patterns.get('reference_patterns', {})

    # Strategy 1: Try COMPOUND key first (most specific — handles multi-product vendors like ASR)
    if is_compound:
        compound_key = f"{administration}_{debet}_{verb}"
        if compound_key in reference_patterns:
            pattern = reference_patterns[compound_key]
            if pattern.get('confidence', 0) > 0 and pattern.get('debet_account') == debet:
                return {
                    'value': pattern.get('credit_account'),
                    'confidence': pattern.get('confidence', 1.0),
                    'pattern_key': compound_key,
                    'reason': f'Compound match: Verb "{verb}" with bank debet {debet}',
                    'verb': verb
                }

    # Strategy 2: Try COMPANY-ONLY key (fallback for single-product vendors)
    company_key = f"{administration}_{debet}_{verb_company}"
    if company_key in reference_patterns:
        pattern = reference_patterns[company_key]
        # Skip ambiguous patterns (multi-product vendors where company-level is unreliable)
        if (pattern.get('confidence', 0) > 0 and
                not pattern.get('_ambiguous') and
                pattern.get('debet_account') == debet):
            return {
                'value': pattern.get('credit_account'),
                'confidence': pattern.get('confidence', 1.0),
                'pattern_key': company_key,
                'reason': f'Company match: Verb "{verb_company}" with bank debet {debet}',
                'verb': verb
            }

    # Strategy 3: Handle multiple matches with conflict resolution
    matching_patterns = []
    for key, pattern in reference_patterns.items():
        if pattern.get('_ambiguous'):
            continue
        if (pattern.get('debet_account') == debet and
            pattern.get('administration') == administration and
            pattern.get('confidence', 0) > 0 and
            pattern.get('occurrences', 0) >= 1):
            # Match on full verb or company
            if pattern.get('verb') == verb:
                matching_patterns.append((key, pattern))
            elif pattern.get('verb_company') == verb_company and not is_compound:
                matching_patterns.append((key, pattern))

    if matching_patterns:
        best_pattern = resolve_pattern_conflicts(matching_patterns, transaction, administration, is_bank_account_fn)
        if best_pattern and best_pattern[1].get('confidence', 0) >= 0.8:
            key, pattern = best_pattern
            return {
                'value': pattern.get('credit_account'),
                'confidence': pattern.get('confidence', 1.0) * 0.9,
                'pattern_key': key,
                'reason': f'High confidence match: Verb "{verb}" with bank debet {debet}',
                'verb': verb,
                'alternatives': len(matching_patterns)
            }

    # No reliable historical pattern - leave empty for manual fixing
    return None


def predict_reference(
    transaction: Dict,
    reference_patterns: Dict,
    is_bank_account_fn: Callable[[str, str], bool],
    extract_verb_fn: Callable[[str, str], Optional[str]]
) -> Optional[Dict]:
    """
    Predict ReferenceNumber using verb patterns

    REQ-PAT-002: Use historical ReferenceNumbers to match transaction descriptions
    Uses unified verb pattern: Administration + BankAccount + Verb → ReferenceNumber

    Only makes predictions when there's actual historical data - leaves fields empty otherwise
    """
    description = transaction.get('TransactionDescription', '').strip()
    debet = transaction.get('Debet', '')
    credit = transaction.get('Credit', '')
    administration = transaction.get('administration', '')

    if not description:
        return None

    # Extract verb from description
    verb = extract_verb_fn(description, transaction.get('ReferenceNumber', ''))
    if not verb:
        # No valid verb extracted - leave empty for manual fixing
        return None

    # Identify bank account
    bank_account = None
    if is_bank_account_fn(debet, administration):
        bank_account = debet
    elif is_bank_account_fn(credit, administration):
        bank_account = credit

    if not bank_account:
        return None

    # Parse compound verb if applicable
    is_compound = '|' in verb
    verb_company = None

    if is_compound:
        parts = verb.split('|', 1)
        verb_company = parts[0]
    else:
        verb_company = verb

    # Strategy 1: Try COMPOUND key first (most specific — multi-product vendors)
    if is_compound:
        compound_key = f"{administration}_{bank_account}_{verb}"
        if compound_key in reference_patterns:
            pattern = reference_patterns[compound_key]
            if pattern.get('confidence', 0) > 0:
                return {
                    'value': pattern.get('reference_number'),
                    'confidence': pattern.get('confidence', 1.0),
                    'pattern_key': compound_key,
                    'reason': f'Compound match: "{verb}" with bank account {bank_account}',
                    'verb': verb,
                    'bank_account': bank_account,
                    'match_type': 'exact_compound'
                }

    # Strategy 2: Try COMPANY-ONLY key (fallback for single-product vendors)
    company_key = f"{administration}_{bank_account}_{verb_company}"
    if company_key in reference_patterns:
        pattern = reference_patterns[company_key]
        if pattern.get('confidence', 0) > 0 and not pattern.get('_ambiguous'):
            return {
                'value': pattern.get('reference_number'),
                'confidence': pattern.get('confidence', 1.0),
                'pattern_key': company_key,
                'reason': f'Company match: "{verb_company}" with bank account {bank_account}',
                'verb': verb,
                'bank_account': bank_account,
                'match_type': 'company_fallback'
            }

    # Strategy 3: Find matching patterns with flexible matching (only if high confidence)
    matching_patterns = []

    for key, pattern in reference_patterns.items():
        if pattern.get('administration') != administration:
            continue
        if pattern.get('_ambiguous'):
            continue
        if pattern.get('confidence', 0) <= 0:
            continue

        # Only exact verb matches or very close company matches
        if pattern.get('verb') == verb:
            matching_patterns.append((key, pattern, 'exact_verb', 1.0))
        elif is_compound and pattern.get('verb_company') == verb_company and pattern.get('is_compound'):
            # Both compound: same company, different reference (high confidence only)
            if pattern.get('occurrences', 0) >= 2:  # Require 2+ occurrences for compound matching
                matching_patterns.append((key, pattern, 'company_match', 0.8))

    if matching_patterns:
        # Sort by match quality and confidence
        matching_patterns.sort(key=lambda x: (x[3], x[1].get('confidence', 0)), reverse=True)

        # Only use the best match if it's high quality
        best_match = matching_patterns[0]
        key, pattern, match_type, score = best_match

        # Require minimum confidence threshold
        if score >= 0.8 and pattern.get('confidence', 0) >= 0.8:
            return {
                'value': pattern.get('reference_number'),
                'confidence': pattern.get('confidence', 1.0) * score,
                'pattern_key': key,
                'reason': f'High confidence {match_type.replace("_", " ")} for "{verb_company}"',
                'verb': verb,
                'bank_account': pattern.get('bank_account'),
                'match_type': match_type
            }

    # No reliable historical pattern found - leave empty for manual fixing
    return None
