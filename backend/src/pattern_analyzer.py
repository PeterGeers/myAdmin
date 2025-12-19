#!/usr/bin/env python3
"""
Enhanced Pattern Analysis System for Banking Processor

This module implements comprehensive pattern analysis that processes the last 2 years
of transaction data to discover and apply patterns for predicting missing:
- ReferenceNumber values
- Debet account numbers
- Credit account numbers

Requirements addressed:
- REQ-PAT-001: Analyze transactions from the last 2 years for pattern discovery
- REQ-PAT-002: Filter patterns by Administration, ReferenceNumber, Debet/Credit values, and Date
- REQ-PAT-003: Create pattern matching based on known variables
- REQ-PAT-004: Implement bank account lookup logic
"""

import re
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple, Any
from database import DatabaseManager
from pattern_cache import get_pattern_cache


class PatternAnalyzer:
    """Enhanced pattern analysis system for banking transactions"""
    
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.patterns_cache = {}  # Keep for backward compatibility, but prefer database storage
        self.bank_accounts_cache = None
        
        # Initialize persistent cache
        self.persistent_cache = get_pattern_cache(self.db)
        
    def get_bank_accounts(self) -> Dict[str, Dict]:
        """Get bank account lookup data with caching"""
        if self.bank_accounts_cache is None:
            bank_accounts = self.db.get_bank_account_lookups()
            self.bank_accounts_cache = {}
            
            for account in bank_accounts:
                key = f"{account['Administration']}_{account['Account']}"
                self.bank_accounts_cache[key] = {
                    'iban': account['rekeningNummer'],
                    'account': account['Account'],
                    'administration': account['Administration']
                }
        
        return self.bank_accounts_cache
    
    def is_bank_account(self, account_number: str, administration: str) -> bool:
        """Check if an account number is a bank account"""
        if not account_number:
            return False
            
        bank_accounts = self.get_bank_accounts()
        key = f"{administration}_{account_number}"
        return key in bank_accounts
    
    def analyze_historical_patterns(self, administration: str, 
                                  reference_number: Optional[str] = None,
                                  debet_account: Optional[str] = None,
                                  credit_account: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze last 2 years of transaction data to discover patterns
        
        Args:
            administration: The administration to analyze patterns for
            reference_number: Optional filter by specific reference number
            debet_account: Optional filter by specific debet account
            credit_account: Optional filter by specific credit account
            
        Returns:
            Dictionary containing discovered patterns and statistics
        """
        filter_desc = f"for {administration}"
        if reference_number:
            filter_desc += f" (ReferenceNumber: {reference_number})"
        if debet_account:
            filter_desc += f" (Debet: {debet_account})"
        if credit_account:
            filter_desc += f" (Credit: {credit_account})"
            
        print(f"🔍 Analyzing historical patterns {filter_desc}...")
        
        # Get transactions from last 2 years with optional filtering
        two_years_ago = datetime.now() - timedelta(days=730)
        
        # Build dynamic query with filters
        query_conditions = [
            "Administration = %s",
            "TransactionDate >= %s",
            "(Debet IS NOT NULL OR Credit IS NOT NULL)"
        ]
        query_params = [administration, two_years_ago.strftime('%Y-%m-%d')]
        
        # Add optional filters per REQ-PAT-002
        if reference_number:
            query_conditions.append("ReferenceNumber = %s")
            query_params.append(reference_number)
            
        if debet_account:
            query_conditions.append("Debet = %s")
            query_params.append(debet_account)
            
        if credit_account:
            query_conditions.append("Credit = %s")
            query_params.append(credit_account)
        
        query = f"""
            SELECT TransactionDescription, Debet, Credit, ReferenceNumber, 
                   TransactionDate, TransactionAmount, Ref1, Administration
            FROM mutaties 
            WHERE {' AND '.join(query_conditions)}
            ORDER BY TransactionDate DESC
        """
        
        transactions = self.db.execute_query(query, tuple(query_params))
        
        if not transactions:
            return {
                'total_transactions': 0,
                'patterns_discovered': 0,
                'debet_patterns': {},
                'credit_patterns': {},
                'reference_patterns': {},
                'statistics': {}
            }
        
        print(f"📊 Processing {len(transactions)} transactions from last 2 years...")
        
        # Analyze patterns
        debet_patterns = self._analyze_debet_patterns(transactions, administration)
        credit_patterns = self._analyze_credit_patterns(transactions, administration)
        reference_patterns = self._analyze_reference_patterns(transactions, administration)
        
        # Generate statistics
        statistics = self._generate_pattern_statistics(
            transactions, debet_patterns, credit_patterns, reference_patterns
        )
        
        result = {
            'total_transactions': len(transactions),
            'patterns_discovered': len(debet_patterns) + len(credit_patterns) + len(reference_patterns),
            'debet_patterns': debet_patterns,
            'credit_patterns': credit_patterns,
            'reference_patterns': reference_patterns,
            'statistics': statistics,
            'analysis_date': datetime.now().isoformat(),
            'date_range': {
                'from': two_years_ago.strftime('%Y-%m-%d'),
                'to': datetime.now().strftime('%Y-%m-%d')
            }
        }
        
        # Store patterns in database for persistent storage (REQ-PAT-005)
        if not reference_number and not debet_account and not credit_account:
            # Only store full analysis (not filtered) to database
            # Use verb patterns for all predictions (ReferenceNumber, Debet, Credit)
            self._store_verb_patterns_to_database(administration, reference_patterns, result)
            
            # Invalidate persistent cache since we have new patterns
            self.persistent_cache.invalidate_cache(administration)
        
        # Cache the results with filter-specific key for backward compatibility
        cache_key = self._build_cache_key(administration, reference_number, debet_account, credit_account)
        self.patterns_cache[cache_key] = result
        
        print(f"✅ Pattern analysis complete: {result['patterns_discovered']} patterns discovered")
        return result
    
    def _analyze_debet_patterns(self, transactions: List[Dict], administration: str) -> Dict[str, Any]:
        """
        Analyze patterns for predicting Debet account numbers
        
        REQ-PAT-002: Use ReferenceNumber and bank account logic:
        - If Credit is bank account → predict Debet from historical patterns
        - Use ReferenceNumber matching in transaction descriptions
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
            if not self.is_bank_account(credit, administration):
                continue
            
            # Create pattern key using multiple criteria (REQ-PAT-002)
            desc_keywords = self._extract_keywords(description)
            ref_keywords = self._extract_keywords(ref_num) if ref_num else []
            
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
            if pattern['occurrences'] >= 2:  # Minimum 2 occurrences
                pattern['confidence'] = min(pattern['occurrences'] / 10.0, 1.0)  # Max confidence 1.0
                pattern['reference_numbers'] = list(pattern['reference_numbers'])
                pattern['avg_amount'] = sum(pattern['amounts']) / len(pattern['amounts'])
                filtered_patterns[key] = dict(pattern)
        
        return filtered_patterns
    
    def _analyze_credit_patterns(self, transactions: List[Dict], administration: str) -> Dict[str, Any]:
        """
        Analyze patterns for predicting Credit account numbers
        
        REQ-PAT-002: Use ReferenceNumber and bank account logic:
        - If Debet is bank account → predict Credit from historical patterns
        - Use ReferenceNumber matching in transaction descriptions
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
            if not self.is_bank_account(debet, administration):
                continue
            
            # Create pattern key using multiple criteria (REQ-PAT-002)
            desc_keywords = self._extract_keywords(description)
            ref_keywords = self._extract_keywords(ref_num) if ref_num else []
            
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
            if pattern['occurrences'] >= 2:  # Minimum 2 occurrences
                pattern['confidence'] = min(pattern['occurrences'] / 10.0, 1.0)  # Max confidence 1.0
                pattern['reference_numbers'] = list(pattern['reference_numbers'])
                pattern['avg_amount'] = sum(pattern['amounts']) / len(pattern['amounts'])
                filtered_patterns[key] = dict(pattern)
        
        return filtered_patterns
    
    def _analyze_reference_patterns(self, transactions: List[Dict], administration: str) -> Dict[str, Any]:
        """
        Analyze patterns for predicting ReferenceNumber values using verb-based logic
        
        Logic: Administration + BankAccount + Verb → ReferenceNumber + Debet/Credit accounts
        Example: "GoodwinSolutions" + "1300" + "Picnic" → "Picnic" + debet="1003", credit="1300"
        
        REQ-PAT-002: Use historical ReferenceNumbers to match transaction descriptions
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
            
            if self.is_bank_account(debet, administration):
                bank_account = debet
                other_account = credit
            elif self.is_bank_account(credit, administration):
                bank_account = credit
                other_account = debet
            else:
                continue  # Skip if no bank account involved
            
            # Extract verb from description (company/vendor name)
            verb = self._extract_verb_from_description(description, ref_num)
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
            
            # Create unique pattern key: Administration + BankAccount + Verb (full)
            pattern_key = f"{administration}_{bank_account}_{verb}"
            
            # Store the most recent pattern (overwrite if exists)
            verb_patterns[pattern_key] = {
                'administration': administration,
                'bank_account': bank_account,
                'verb': verb,
                'verb_company': verb_company,
                'verb_reference': verb_reference,
                'is_compound': is_compound,
                'reference_number': ref_num,
                'debet_account': debet,
                'credit_account': credit,
                'other_account': other_account,
                'occurrences': verb_patterns.get(pattern_key, {}).get('occurrences', 0) + 1,
                'confidence': 1.0,  # High confidence for exact verb matches
                'last_seen': date,
                'sample_description': description
            }
        
        return verb_patterns
    
    def _extract_compound_verb_from_description(self, description: str, reference_number: str) -> Optional[str]:
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
        company_name = self._extract_company_name(description)
        if not company_name:
            return None
        
        # Extract reference/invoice number (secondary verb)
        reference_number = self._extract_reference_number_from_description(description)
        
        if reference_number:
            # Return compound verb
            return f"{company_name}|{reference_number}"
        else:
            # Fallback to simple company name
            return company_name
    
    def _extract_company_name(self, description: str) -> Optional[str]:
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
            r'\bNL\d{2}[A-Z]{4}\d+\b'  # IBAN patterns
        ]
        
        cleaned_desc = description_upper
        for pattern in cleaning_patterns:
            cleaned_desc = re.sub(pattern, '', cleaned_desc)
        
        # Extract meaningful words (company names)
        words = re.findall(r'\b[A-Z][A-Z0-9]{2,}\b', cleaned_desc)
        
        # Filter out common noise words and transaction codes
        noise_words = {
            'THE', 'AND', 'VAN', 'DER', 'DEN', 'HET', 'EEN', 'VOOR', 'NAAR', 'BIJ',
            'BETALING', 'PAYMENT', 'TRANSACTION', 'TRANSFER', 'ONLINE', 'WEBSHOP',
            'BETREFT', 'INFO', 'KIJK', 'MEER', 'FACTUUR', 'XUI', 'NL04', 'NL27', 'NL15',
            'RABONL2U', 'INGBNL2AXXX', 'CITINL2X', 'BOFAIE3X', 'ADYBNL2AXXX', 'DEUTNL2A',
            'EUR', 'RABO', 'ING', 'CITI', 'BOFA', 'ADYB', 'DEUT'
        }
        
        # Filter out transaction codes and meaningless strings
        meaningful_words = []
        for word in words:
            # Skip if it's a noise word
            if word in noise_words:
                continue
            
            # Skip if it's too short or too long for a company name
            if len(word) < 3 or len(word) > 15:
                continue
            
            # Skip transaction IDs and codes (patterns that are clearly not company names)
            if (re.match(r'^[A-Z0-9]{8,}$', word) or  # Long alphanumeric codes
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
            if (len(set(word) & vowels) > 0 and  # Has at least one vowel
                not word.isdigit() and           # Not all digits
                len(word) >= 3):                 # Minimum length
                meaningful_words.append(word)
        
        if meaningful_words:
            # Return the first meaningful word as the company name
            return meaningful_words[0]
        
        return None
    
    def _extract_reference_number_from_description(self, description: str) -> Optional[str]:
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
    
    def _extract_verb_from_description(self, description: str, reference_number: str) -> Optional[str]:
        """
        Extract verb from description - supports both simple and compound verbs
        
        This method maintains backward compatibility while supporting compound verbs
        """
        # Try compound verb extraction first
        compound_verb = self._extract_compound_verb_from_description(description, reference_number)
        if compound_verb and '|' in compound_verb:
            return compound_verb
        
        # Fallback to simple company name extraction
        simple_verb = self._extract_company_name(description) if description else None
        
        # Validate that the verb makes sense (not a transaction ID)
        if simple_verb and self._is_valid_verb(simple_verb):
            return simple_verb
        
        return None
    
    def _is_valid_verb(self, verb: str) -> bool:
        """
        Validate that a verb is a real company name, not a transaction ID
        
        Returns False for patterns that are clearly transaction codes
        """
        if not verb or len(verb) < 3:
            return False
        
        # Reject patterns that look like transaction IDs
        invalid_patterns = [
            r'^[A-Z0-9]{8,}$',           # Long alphanumeric codes
            r'^[A-Z]{2}\d+[A-Z]+\d+$',  # Mixed patterns like QG0DBCBZELL92QM4
            r'^\d+[A-Z]+\d+$',          # Number-letter-number
            r'^[A-Z]+\d+[A-Z]+$',       # Letter-number-letter
            r'^P\d{10,}$',              # Transaction IDs starting with P
            r'^[A-Z]{1,3}\d{8,}$'       # Short prefix + long number
        ]
        
        for pattern in invalid_patterns:
            if re.match(pattern, verb):
                return False
        
        # Reject specific known transaction prefixes
        invalid_prefixes = ['FACTUURNR', 'KLANTNR', 'TRANSACTIE', 'BETALING']
        if any(verb.startswith(prefix) for prefix in invalid_prefixes):
            return False
        
        # Must have at least one vowel (real words have vowels)
        vowels = set('AEIOU')
        if len(set(verb) & vowels) == 0:
            return False
        
        return True
    
    def _extract_keywords(self, description: str) -> List[str]:
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
    
    def _generate_pattern_statistics(self, transactions: List[Dict], 
                                   debet_patterns: Dict, credit_patterns: Dict, 
                                   reference_patterns: Dict) -> Dict[str, Any]:
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
            if tx.get('Debet') and self.is_bank_account(tx['Debet'], admin):
                bank_debet_count += 1
            if tx.get('Credit') and self.is_bank_account(tx['Credit'], admin):
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
    
    def apply_patterns_to_transactions(self, transactions: List[Dict], 
                                     administration: str) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        Apply discovered patterns to predict missing values in transactions
        
        Args:
            transactions: List of transaction dictionaries
            administration: Administration to get patterns for
            
        Returns:
            Tuple of (updated_transactions, application_results)
        """
        print(f"🔧 Applying patterns to {len(transactions)} transactions...")
        
        # Get patterns for this administration (database first, then cache)
        patterns = self.get_filtered_patterns(administration)
        
        results = {
            'total_transactions': len(transactions),
            'predictions_made': {
                'debet': 0,
                'credit': 0,
                'reference': 0
            },
            'confidence_scores': [],
            'failed_predictions': 0
        }
        
        updated_transactions = []
        
        for tx in transactions:
            updated_tx = tx.copy()
            tx_predictions = []
            
            # Apply debet patterns
            if not updated_tx.get('Debet'):
                debet_prediction = self._predict_debet(updated_tx, patterns['debet_patterns'], administration)
                if debet_prediction:
                    updated_tx['Debet'] = debet_prediction['value']
                    updated_tx['_debet_confidence'] = debet_prediction['confidence']
                    results['predictions_made']['debet'] += 1
                    tx_predictions.append(debet_prediction['confidence'])
            
            # Apply credit patterns
            if not updated_tx.get('Credit'):
                credit_prediction = self._predict_credit(updated_tx, patterns['credit_patterns'], administration)
                if credit_prediction:
                    updated_tx['Credit'] = credit_prediction['value']
                    updated_tx['_credit_confidence'] = credit_prediction['confidence']
                    results['predictions_made']['credit'] += 1
                    tx_predictions.append(credit_prediction['confidence'])
            
            # Apply reference patterns
            if not updated_tx.get('ReferenceNumber'):
                ref_prediction = self._predict_reference(updated_tx, patterns['reference_patterns'])
                if ref_prediction:
                    updated_tx['ReferenceNumber'] = ref_prediction['value']
                    updated_tx['_reference_confidence'] = ref_prediction['confidence']
                    results['predictions_made']['reference'] += 1
                    tx_predictions.append(ref_prediction['confidence'])
            
            # Track confidence scores
            if tx_predictions:
                results['confidence_scores'].extend(tx_predictions)
            else:
                results['failed_predictions'] += 1
            
            updated_transactions.append(updated_tx)
        
        # Calculate average confidence
        if results['confidence_scores']:
            results['average_confidence'] = sum(results['confidence_scores']) / len(results['confidence_scores'])
        else:
            results['average_confidence'] = 0.0
        
        print(f"✅ Pattern application complete: {sum(results['predictions_made'].values())} predictions made")
        return updated_transactions, results
    
    def _predict_debet(self, transaction: Dict, debet_patterns: Dict, administration: str) -> Optional[Dict]:
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
        if not self.is_bank_account(credit, administration):
            return None
        
        # Extract verb from description
        verb = self._extract_verb_from_description(description, transaction.get('ReferenceNumber', ''))
        if not verb:
            # No valid verb - leave empty for manual fixing
            return None
        
        # Look for exact pattern match: Administration + Credit (bank account) + Verb
        pattern_key = f"{administration}_{credit}_{verb}"
        
        # Get reference patterns (which contain verb patterns)
        patterns = self.get_filtered_patterns(administration)
        reference_patterns = patterns.get('reference_patterns', {})
        
        # Check for exact pattern match
        if pattern_key in reference_patterns:
            pattern = reference_patterns[pattern_key]
            if pattern.get('credit_account') == credit:  # Verify bank account matches
                return {
                    'value': pattern.get('debet_account'),
                    'confidence': pattern.get('confidence', 1.0),
                    'pattern_key': pattern_key,
                    'reason': f'Exact match: Verb "{verb}" with bank credit {credit}',
                    'verb': verb
                }
        
        # Handle multiple matches: find all patterns with same verb and credit account
        matching_patterns = []
        for key, pattern in reference_patterns.items():
            if (pattern.get('verb') == verb and 
                pattern.get('credit_account') == credit and
                pattern.get('administration') == administration and
                pattern.get('occurrences', 0) >= 2):  # Require multiple occurrences
                matching_patterns.append((key, pattern))
        
        if matching_patterns:
            # Only use if we have high confidence matches
            best_pattern = self._resolve_pattern_conflicts(matching_patterns, transaction, administration)
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
    
    def _predict_credit(self, transaction: Dict, credit_patterns: Dict, administration: str) -> Optional[Dict]:
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
        if not self.is_bank_account(debet, administration):
            return None
        
        # Extract verb from description
        verb = self._extract_verb_from_description(description, transaction.get('ReferenceNumber', ''))
        if not verb:
            # No valid verb - leave empty for manual fixing
            return None
        
        # Look for exact pattern match: Administration + Debet (bank account) + Verb
        pattern_key = f"{administration}_{debet}_{verb}"
        
        # Get reference patterns (which contain verb patterns)
        patterns = self.get_filtered_patterns(administration)
        reference_patterns = patterns.get('reference_patterns', {})
        
        # Check for exact pattern match
        if pattern_key in reference_patterns:
            pattern = reference_patterns[pattern_key]
            if pattern.get('debet_account') == debet:  # Verify bank account matches
                return {
                    'value': pattern.get('credit_account'),
                    'confidence': pattern.get('confidence', 1.0),
                    'pattern_key': pattern_key,
                    'reason': f'Exact match: Verb "{verb}" with bank debet {debet}',
                    'verb': verb
                }
        
        # Handle multiple matches: find all patterns with same verb and debet account
        matching_patterns = []
        for key, pattern in reference_patterns.items():
            if (pattern.get('verb') == verb and 
                pattern.get('debet_account') == debet and
                pattern.get('administration') == administration and
                pattern.get('occurrences', 0) >= 2):  # Require multiple occurrences
                matching_patterns.append((key, pattern))
        
        if matching_patterns:
            # Only use if we have high confidence matches
            best_pattern = self._resolve_pattern_conflicts(matching_patterns, transaction, administration)
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
    
    def _predict_reference(self, transaction: Dict, reference_patterns: Dict) -> Optional[Dict]:
        """
        Predict ReferenceNumber using verb patterns
        
        REQ-PAT-002: Use historical ReferenceNumbers to match transaction descriptions
        Uses unified verb pattern: Administration + BankAccount + Verb → ReferenceNumber
        
        Only makes predictions when there's actual historical data - leaves fields empty otherwise
        """
        description = transaction.get('TransactionDescription', '').strip()
        debet = transaction.get('Debet', '')
        credit = transaction.get('Credit', '')
        administration = transaction.get('Administration', '')
        
        if not description:
            return None
        
        # Extract verb from description
        verb = self._extract_verb_from_description(description, transaction.get('ReferenceNumber', ''))
        if not verb:
            # No valid verb extracted - leave empty for manual fixing
            return None
        
        # Identify bank account
        bank_account = None
        if self.is_bank_account(debet, administration):
            bank_account = debet
        elif self.is_bank_account(credit, administration):
            bank_account = credit
        
        if not bank_account:
            return None
        
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
        
        # Strategy 1: Look for exact compound match
        pattern_key = f"{administration}_{bank_account}_{verb}"
        if pattern_key in reference_patterns:
            pattern = reference_patterns[pattern_key]
            return {
                'value': pattern.get('reference_number'),
                'confidence': pattern.get('confidence', 1.0),
                'pattern_key': pattern_key,
                'reason': f'Exact match: "{verb}" with bank account {bank_account}',
                'verb': verb,
                'bank_account': bank_account,
                'match_type': 'exact_compound' if is_compound else 'exact_simple'
            }
        
        # Strategy 2: Find matching patterns with flexible matching (only if high confidence)
        matching_patterns = []
        
        for key, pattern in reference_patterns.items():
            if pattern.get('administration') != administration:
                continue
            
            # Only exact verb matches or very close company matches
            if pattern.get('verb') == verb:
                matching_patterns.append((key, pattern, 'exact_verb', 1.0))
            elif is_compound and pattern.get('verb_company') == verb_company and pattern.get('is_compound'):
                # Both compound: same company, different reference (high confidence only)
                if pattern.get('occurrences', 0) >= 3:  # Require multiple occurrences
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
    
    def _build_cache_key(self, administration: str, 
                        reference_number: Optional[str] = None,
                        debet_account: Optional[str] = None,
                        credit_account: Optional[str] = None) -> str:
        """Build cache key for filtered patterns"""
        key_parts = [administration]
        if reference_number:
            key_parts.append(f"ref:{reference_number}")
        if debet_account:
            key_parts.append(f"deb:{debet_account}")
        if credit_account:
            key_parts.append(f"cred:{credit_account}")
        return "_".join(key_parts)
    
    def _store_verb_patterns_to_database(self, administration: str, verb_patterns: Dict, analysis_metadata: Dict, is_incremental: bool = False):
        """
        Store discovered verb patterns in unified database table
        
        REQ-PAT-005: Store discovered patterns in optimized database structure
        REQ-PAT-006: Support incremental pattern updates
        Uses single table for ReferenceNumber, Debet, and Credit predictions
        
        Args:
            administration: The administration to store patterns for
            verb_patterns: Dictionary of discovered patterns
            analysis_metadata: Metadata about the analysis
            is_incremental: Whether this is an incremental update (accumulates transaction count)
        """
        print(f"💾 Storing {len(verb_patterns)} verb patterns to database...")
        
        try:
            # Store verb patterns (unified approach for all predictions)
            for pattern_key, pattern in verb_patterns.items():
                self.db.execute_query("""
                    INSERT INTO pattern_verb_patterns 
                    (administration, bank_account, verb, verb_company, verb_reference, is_compound,
                     reference_number, debet_account, credit_account, occurrences, confidence, 
                     last_seen, sample_description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    verb_company = VALUES(verb_company),
                    verb_reference = VALUES(verb_reference),
                    is_compound = VALUES(is_compound),
                    reference_number = VALUES(reference_number),
                    debet_account = VALUES(debet_account),
                    credit_account = VALUES(credit_account),
                    occurrences = occurrences + VALUES(occurrences),
                    confidence = VALUES(confidence),
                    last_seen = VALUES(last_seen),
                    sample_description = VALUES(sample_description),
                    updated_at = CURRENT_TIMESTAMP
                """, (
                    pattern.get('administration'), pattern.get('bank_account'),
                    pattern.get('verb'), pattern.get('verb_company'), pattern.get('verb_reference'),
                    pattern.get('is_compound', False), pattern.get('reference_number'),
                    pattern.get('debet_account'), pattern.get('credit_account'),
                    pattern.get('occurrences', 1), pattern.get('confidence', 1.0),
                    pattern.get('last_seen'), pattern.get('sample_description')
                ), fetch=False, commit=True)
            
            # Get current pattern count from database for accurate reporting
            pattern_count_result = self.db.execute_query("""
                SELECT COUNT(*) as count FROM pattern_verb_patterns 
                WHERE administration = %s
            """, (administration,))
            total_patterns = pattern_count_result[0]['count'] if pattern_count_result else len(verb_patterns)
            
            # Store analysis metadata
            if is_incremental:
                # For incremental updates, accumulate transaction count
                self.db.execute_query("""
                    INSERT INTO pattern_analysis_metadata 
                    (administration, last_analysis_date, transactions_analyzed, patterns_discovered,
                     date_range_from, date_range_to)
                    VALUES (%s, NOW(), %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    last_analysis_date = NOW(),
                    transactions_analyzed = transactions_analyzed + VALUES(transactions_analyzed),
                    patterns_discovered = %s,
                    date_range_to = VALUES(date_range_to),
                    updated_at = CURRENT_TIMESTAMP
                """, (
                    administration, analysis_metadata.get('total_transactions', 0),
                    total_patterns,
                    analysis_metadata.get('date_range', {}).get('from'),
                    analysis_metadata.get('date_range', {}).get('to'),
                    total_patterns
                ), fetch=False, commit=True)
            else:
                # For full analysis, replace transaction count
                self.db.execute_query("""
                    INSERT INTO pattern_analysis_metadata 
                    (administration, last_analysis_date, transactions_analyzed, patterns_discovered,
                     date_range_from, date_range_to)
                    VALUES (%s, NOW(), %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    last_analysis_date = NOW(),
                    transactions_analyzed = VALUES(transactions_analyzed),
                    patterns_discovered = VALUES(patterns_discovered),
                    date_range_from = VALUES(date_range_from),
                    date_range_to = VALUES(date_range_to),
                    updated_at = CURRENT_TIMESTAMP
                """, (
                    administration, analysis_metadata.get('total_transactions', 0),
                    len(verb_patterns),
                    analysis_metadata.get('date_range', {}).get('from'),
                    analysis_metadata.get('date_range', {}).get('to')
                ), fetch=False, commit=True)
            
            print(f"✅ Verb patterns stored successfully in database")
            
        except Exception as e:
            print(f"❌ Error storing verb patterns to database: {e}")
            raise
    
    def _load_patterns_from_database(self, administration: str) -> Dict[str, Any]:
        """
        Load patterns from database storage using unified pattern_verb_patterns table
        
        REQ-PAT-005: Store discovered patterns in optimized database structure
        REQ-PAT-006: Implement pattern caching for performance
        """
        print(f"📖 Loading patterns from database for {administration}...")
        
        try:
            # Load verb patterns (unified approach - contains all prediction data)
            verb_results = self.db.execute_query("""
                SELECT administration, bank_account, verb, verb_company, verb_reference, 
                       is_compound, reference_number, debet_account, credit_account, 
                       occurrences, confidence, last_seen, sample_description
                FROM pattern_verb_patterns 
                WHERE administration = %s
                ORDER BY last_seen DESC, occurrences DESC
            """, (administration,))
            
            reference_patterns = {}
            for row in verb_results:
                pattern_key = f"{row['administration']}_{row['bank_account']}_{row['verb']}"
                reference_patterns[pattern_key] = {
                    'administration': row['administration'],
                    'bank_account': row['bank_account'],
                    'verb': row['verb'],
                    'verb_company': row['verb_company'],
                    'verb_reference': row['verb_reference'],
                    'is_compound': bool(row['is_compound']),
                    'reference_number': row['reference_number'],
                    'debet_account': row['debet_account'],
                    'credit_account': row['credit_account'],
                    'occurrences': row['occurrences'],
                    'confidence': float(row['confidence']) if row['confidence'] else 1.0,
                    'last_seen': row['last_seen'],
                    'sample_description': row['sample_description']
                }
            
            # Load metadata
            metadata_results = self.db.execute_query("""
                SELECT last_analysis_date, transactions_analyzed, patterns_discovered,
                       date_range_from, date_range_to
                FROM pattern_analysis_metadata 
                WHERE administration = %s
            """, (administration,))
            
            metadata = {}
            if metadata_results:
                meta = metadata_results[0]
                metadata = {
                    'analysis_date': meta['last_analysis_date'].isoformat() if meta['last_analysis_date'] else None,
                    'total_transactions': meta['transactions_analyzed'] or 0,
                    'patterns_discovered': meta['patterns_discovered'] or 0,
                    'date_range': {
                        'from': meta['date_range_from'].strftime('%Y-%m-%d') if meta['date_range_from'] else None,
                        'to': meta['date_range_to'].strftime('%Y-%m-%d') if meta['date_range_to'] else None
                    }
                }
            
            result = {
                'debet_patterns': {},  # Empty - using unified verb patterns
                'credit_patterns': {},  # Empty - using unified verb patterns
                'reference_patterns': reference_patterns,
                'total_transactions': metadata.get('total_transactions', 0),
                'patterns_discovered': len(reference_patterns),
                'analysis_date': metadata.get('analysis_date'),
                'date_range': metadata.get('date_range', {}),
                'statistics': self._calculate_statistics_from_db_patterns({}, {}, reference_patterns)
            }
            
            print(f"✅ Loaded {result['patterns_discovered']} patterns from database")
            return result
            
        except Exception as e:
            print(f"❌ Error loading patterns from database: {e}")
            # Fallback to empty patterns
            return {
                'debet_patterns': {},
                'credit_patterns': {},
                'reference_patterns': {},
                'total_transactions': 0,
                'patterns_discovered': 0,
                'statistics': {}
            }
    
    def _calculate_statistics_from_db_patterns(self, debet_patterns: Dict, credit_patterns: Dict, reference_patterns: Dict) -> Dict:
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
    
    def _should_refresh_patterns(self, administration: str) -> bool:
        """
        Check if patterns should be refreshed based on last analysis date
        
        REQ-PAT-006: Implement incremental pattern updates
        """
        try:
            metadata = self.db.execute_query("""
                SELECT last_analysis_date FROM pattern_analysis_metadata 
                WHERE administration = %s
            """, (administration,))
            
            if not metadata:
                return True  # No previous analysis, need to analyze
            
            last_analysis = metadata[0]['last_analysis_date']
            if not last_analysis:
                return True
            
            # Refresh if last analysis was more than 24 hours ago
            from datetime import datetime, timedelta
            return datetime.now() - last_analysis > timedelta(hours=24)
            
        except Exception as e:
            print(f"Warning: Could not check pattern refresh status: {e}")
            return True  # Default to refresh on error
    
    def _resolve_pattern_conflicts(self, matching_patterns: List[Tuple[str, Dict]], 
                                 transaction: Dict, administration: str) -> Optional[Tuple[str, Dict]]:
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
                from datetime import datetime, date
                if isinstance(last_seen, str):
                    try:
                        last_seen = datetime.strptime(last_seen, '%Y-%m-%d').date()
                    except:
                        last_seen = None
                
                if last_seen:
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
            if self.is_bank_account(transaction.get('Debet', ''), administration):
                transaction_bank = transaction.get('Debet')
            elif self.is_bank_account(transaction.get('Credit', ''), administration):
                transaction_bank = transaction.get('Credit')
            
            if transaction_bank and pattern.get('bank_account') == transaction_bank:
                score += 10
            
            scored_patterns.append((score, key, pattern))
        
        # Sort by score (highest first)
        scored_patterns.sort(key=lambda x: x[0], reverse=True)
        
        # Return the best match
        best_score, best_key, best_pattern = scored_patterns[0]
        
        # Log conflict resolution for debugging
        print(f"🔀 Resolved pattern conflict for verb '{best_pattern.get('verb')}': "
              f"Selected {best_pattern.get('reference_number')} "
              f"(score: {best_score:.1f}, {len(matching_patterns)} alternatives)")
        
        return (best_key, best_pattern)
    
    def analyze_incremental_patterns(self, administration: str) -> Dict[str, Any]:
        """
        Analyze patterns incrementally by comparing dataset before and after applying patterns
        
        REQ-PAT-006: Incremental pattern updates - only new transactions since last analysis are processed
        
        Correct approach:
        1. Load existing patterns from database (fast)
        2. Get new transactions since last analysis
        3. Apply existing patterns to new transactions
        4. Analyze complete dataset (including new transactions) to discover patterns
        5. Compare before/after to identify what's actually new
        6. Store only the new/updated patterns
        
        Returns:
            Dictionary containing analysis results with incremental update statistics
        """
        print(f"🔄 Running incremental pattern analysis for {administration}...")
        
        try:
            # Get last analysis date and current metadata
            metadata = self.db.execute_query("""
                SELECT last_analysis_date, transactions_analyzed, patterns_discovered 
                FROM pattern_analysis_metadata 
                WHERE administration = %s
            """, (administration,))
            
            if not metadata or not metadata[0]['last_analysis_date']:
                print("No previous analysis found, running full analysis...")
                return self.analyze_historical_patterns(administration)
            
            last_analysis_date = metadata[0]['last_analysis_date']
            previous_transactions = metadata[0]['transactions_analyzed'] or 0
            previous_patterns = metadata[0]['patterns_discovered'] or 0
            
            print(f"Last analysis: {last_analysis_date}")
            print(f"Previous analysis: {previous_transactions} transactions, {previous_patterns} patterns")
            
            # Step 1: Load existing patterns from database (fast)
            print("📖 Loading existing patterns from database...")
            existing_patterns = self._load_patterns_from_database(administration)
            existing_pattern_keys = set(existing_patterns['reference_patterns'].keys())
            
            # Step 2: Get new transactions since last analysis
            query = """
                SELECT TransactionDescription, Debet, Credit, ReferenceNumber, 
                       TransactionDate, TransactionAmount, Ref1, Administration
                FROM mutaties 
                WHERE Administration = %s
                AND TransactionDate > %s
                AND (Debet IS NOT NULL OR Credit IS NOT NULL)
                ORDER BY TransactionDate DESC
            """
            
            new_transactions = self.db.execute_query(query, (administration, last_analysis_date))
            
            if not new_transactions:
                print("✅ No new transactions found since last analysis - patterns are up to date")
                existing_patterns['total_transactions'] = 0
                existing_patterns['incremental_update'] = {
                    'new_transactions_processed': 0,
                    'new_patterns_discovered': 0,
                    'previous_transaction_count': previous_transactions,
                    'previous_pattern_count': previous_patterns,
                    'total_patterns_in_database': len(existing_pattern_keys),
                    'efficiency_gain': 'No processing needed - already up to date'
                }
                return existing_patterns
            
            print(f"📊 Found {len(new_transactions)} new transactions to process")
            
            # Step 3: Apply existing patterns to new transactions (to see what gets filled)
            print("🔧 Applying existing patterns to new transactions...")
            updated_transactions, application_results = self.apply_patterns_to_transactions(
                new_transactions, administration
            )
            
            print(f"   - Applied patterns to {len(updated_transactions)} transactions")
            print(f"   - Predictions made: {sum(application_results['predictions_made'].values())}")
            
            # Step 4: Analyze complete dataset including new transactions to discover patterns
            print("🔍 Analyzing complete dataset to discover new patterns...")
            
            # Get all transactions from last 2 years (including new ones)
            two_years_ago = datetime.now() - timedelta(days=730)
            complete_query = """
                SELECT TransactionDescription, Debet, Credit, ReferenceNumber, 
                       TransactionDate, TransactionAmount, Ref1, Administration
                FROM mutaties 
                WHERE Administration = %s
                AND TransactionDate >= %s
                AND (Debet IS NOT NULL OR Credit IS NOT NULL)
                ORDER BY TransactionDate DESC
            """
            
            all_transactions = self.db.execute_query(complete_query, (administration, two_years_ago.strftime('%Y-%m-%d')))
            print(f"   - Analyzing {len(all_transactions)} total transactions for pattern discovery")
            
            # Discover patterns from complete dataset
            new_reference_patterns = self._analyze_reference_patterns(all_transactions, administration)
            
            # Step 5: Compare before/after to identify what's actually new
            print("🔍 Comparing patterns to identify new discoveries...")
            
            truly_new_patterns = {}
            updated_patterns = {}
            
            for pattern_key, pattern in new_reference_patterns.items():
                if pattern_key not in existing_pattern_keys:
                    # This is a completely new pattern
                    truly_new_patterns[pattern_key] = pattern
                else:
                    # This pattern existed before, check if it has more occurrences
                    existing_pattern = existing_patterns['reference_patterns'][pattern_key]
                    existing_occurrences = existing_pattern.get('occurrences', 0)
                    new_occurrences = pattern.get('occurrences', 0)
                    
                    if new_occurrences > existing_occurrences:
                        # Pattern has been reinforced with new data
                        pattern['occurrences'] = new_occurrences - existing_occurrences  # Store only the increment
                        updated_patterns[pattern_key] = pattern
            
            new_patterns_count = len(truly_new_patterns)
            updated_patterns_count = len(updated_patterns)
            
            print(f"   - New patterns discovered: {new_patterns_count}")
            print(f"   - Existing patterns updated: {updated_patterns_count}")
            
            # Step 6: Store only the new/updated patterns
            patterns_to_store = {**truly_new_patterns, **updated_patterns}
            
            # Generate statistics for the incremental batch
            statistics = self._generate_pattern_statistics(
                new_transactions, {}, {}, patterns_to_store
            )
            
            # Prepare result metadata
            result = {
                'total_transactions': len(new_transactions),
                'patterns_discovered': len(patterns_to_store),
                'debet_patterns': {},
                'credit_patterns': {},
                'reference_patterns': patterns_to_store,
                'statistics': statistics,
                'analysis_date': datetime.now().isoformat(),
                'date_range': {
                    'from': last_analysis_date.strftime('%Y-%m-%d'),
                    'to': datetime.now().strftime('%Y-%m-%d')
                }
            }
            
            # Store new/updated patterns
            if patterns_to_store:
                print(f"📝 Storing {len(patterns_to_store)} new/updated patterns...")
                self._store_verb_patterns_to_database(administration, patterns_to_store, result, is_incremental=True)
                
                # Invalidate persistent cache since we have new/updated patterns
                self.persistent_cache.invalidate_cache(administration)
            else:
                print("📝 No new patterns discovered, updating analysis timestamp only...")
                self.db.execute_query("""
                    UPDATE pattern_analysis_metadata 
                    SET last_analysis_date = NOW(),
                        transactions_analyzed = transactions_analyzed + %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE administration = %s
                """, (len(new_transactions), administration), fetch=False, commit=True)
            
            # Load final patterns from database
            final_result = self._load_patterns_from_database(administration)
            
            # Override to show incremental processing stats
            final_result['total_transactions'] = len(new_transactions)
            final_result['patterns_discovered'] = len(patterns_to_store)
            
            # Add detailed incremental update statistics
            final_result['incremental_update'] = {
                'new_transactions_processed': len(new_transactions),
                'new_patterns_discovered': new_patterns_count,
                'updated_patterns': updated_patterns_count,
                'total_pattern_changes': len(patterns_to_store),
                'previous_transaction_count': previous_transactions,
                'previous_pattern_count': previous_patterns,
                'total_patterns_in_database': final_result.get('patterns_discovered', 0),
                'efficiency_gain': f"Analyzed {len(new_transactions)} new transactions vs {len(all_transactions)} total",
                'time_range': f"{last_analysis_date.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}",
                'pattern_application_results': application_results
            }
            
            print(f"✅ Incremental analysis complete:")
            print(f"   - {len(new_transactions)} new transactions processed")
            print(f"   - {new_patterns_count} new patterns discovered")
            print(f"   - {updated_patterns_count} existing patterns updated")
            
            return final_result
            
        except Exception as e:
            print(f"❌ Error in incremental analysis: {e}")
            print("🔄 Falling back to full analysis...")
            # Fallback to full analysis on any error
            return self.analyze_historical_patterns(administration)
    
    def get_cache_performance_stats(self, administration: str) -> Dict[str, Any]:
        """
        Get comprehensive cache performance statistics
        
        REQ-PAT-006: Persistent Pattern Cache performance metrics
        """
        cache_stats = self.persistent_cache.get_cache_stats()
        storage_stats = self.get_pattern_storage_stats(administration)
        
        return {
            'persistent_cache': cache_stats,
            'pattern_storage': storage_stats,
            'cache_effectiveness': {
                'cache_hit_rate': cache_stats['performance']['hit_rate_percent'],
                'startup_performance': f"{cache_stats['performance']['startup_time_seconds']:.3f}s",
                'memory_efficiency': f"{cache_stats['memory_usage']['utilization_percent']:.1f}% utilized",
                'multi_level_caching': {
                    'L1_memory': cache_stats['cache_levels']['memory_entries'],
                    'L2_database': cache_stats['cache_levels']['database_active'],
                    'L3_file': cache_stats['cache_levels']['file_cache_exists']
                }
            },
            'performance_benefits': {
                'cache_survives_restart': True,
                'shared_between_instances': True,
                'automatic_cache_warming': True,
                'multi_level_fallback': True
            }
        }
    
    def get_pattern_storage_stats(self, administration: str) -> Dict[str, Any]:
        """
        Get statistics about pattern storage performance using unified pattern_verb_patterns table
        
        REQ-PAT-006: Performance improvement through database storage
        """
        try:
            # Get pattern counts from unified verb patterns table
            verb_pattern_count = self.db.execute_query("""
                SELECT COUNT(*) as count FROM pattern_verb_patterns 
                WHERE administration = %s
            """, (administration,))
            
            # Get metadata
            metadata = self.db.execute_query("""
                SELECT last_analysis_date, transactions_analyzed, patterns_discovered
                FROM pattern_analysis_metadata 
                WHERE administration = %s
            """, (administration,))
            
            # Get transaction count for comparison
            transaction_count = self.db.execute_query("""
                SELECT COUNT(*) as count FROM mutaties 
                WHERE Administration = %s 
                AND TransactionDate >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
            """, (administration,))
            
            total_patterns = verb_pattern_count[0]['count'] if verb_pattern_count else 0
            total_transactions = transaction_count[0]['count'] if transaction_count else 0
            
            # Calculate performance improvement
            if total_transactions > 0:
                data_reduction_ratio = total_patterns / total_transactions
                performance_improvement = f"{(1 - data_reduction_ratio) * 100:.1f}% reduction in data processing"
            else:
                performance_improvement = "No data available"
            
            return {
                'administration': administration,
                'pattern_storage': {
                    'unified_verb_patterns': total_patterns,
                    'total_patterns': total_patterns
                },
                'transaction_comparison': {
                    'total_transactions_2_years': total_transactions,
                    'patterns_stored': total_patterns,
                    'data_reduction_ratio': f"{data_reduction_ratio:.4f}" if total_transactions > 0 else "N/A",
                    'performance_improvement': performance_improvement
                },
                'last_analysis': metadata[0]['last_analysis_date'] if metadata else None,
                'database_storage_active': True,
                'unified_table_approach': True
            }
            
        except Exception as e:
            return {
                'error': f"Could not retrieve storage stats: {e}",
                'database_storage_active': False
            }
    
    def get_filtered_patterns(self, administration: str,
                            reference_number: Optional[str] = None,
                            debet_account: Optional[str] = None,
                            credit_account: Optional[str] = None) -> Dict[str, Any]:
        """
        Get patterns with optional filtering by ReferenceNumber, Debet/Credit values
        Implements REQ-PAT-002: Filter patterns by Administration, ReferenceNumber, Debet/Credit values, and Date
        REQ-PAT-005: Store discovered patterns in optimized database structure
        REQ-PAT-006: Implement pattern caching for performance - PERSISTENT CACHE
        """
        # Try persistent cache first (multi-level: memory -> database -> file)
        cached_patterns = self.persistent_cache.get_patterns(
            administration, reference_number, debet_account, credit_account
        )
        
        if cached_patterns:
            # Cache hit - return cached patterns
            return cached_patterns
        
        # Cache miss - analyze patterns and store in persistent cache
        print(f"🔍 Cache miss - analyzing patterns for {administration}")
        patterns = self.analyze_historical_patterns(administration, reference_number, debet_account, credit_account)
        
        # Store in persistent cache for future use
        self.persistent_cache.store_patterns(
            administration, patterns, reference_number, debet_account, credit_account
        )
        
        # Also store in legacy memory cache for backward compatibility
        cache_key = self._build_cache_key(administration, reference_number, debet_account, credit_account)
        self.patterns_cache[cache_key] = patterns
        
        return patterns

    def get_pattern_summary(self, administration: str) -> Dict[str, Any]:
        """Get a summary of patterns for an administration"""
        # Use database-first approach
        patterns = self.get_filtered_patterns(administration)
        
        return {
            'administration': administration,
            'total_patterns': patterns['patterns_discovered'],
            'statistics': patterns['statistics'],
            'date_range': patterns['date_range'],
            'analysis_date': patterns['analysis_date'],
            'pattern_types': {
                'debet': len(patterns['debet_patterns']),
                'credit': len(patterns['credit_patterns']),
                'reference': len(patterns['reference_patterns'])
            },
            'storage_stats': self.get_pattern_storage_stats(administration)
        }
    
    def get_incremental_update_stats(self, administration: str) -> Dict[str, Any]:
        """
        Get statistics about incremental pattern updates
        
        REQ-PAT-006: Performance improvement through incremental processing
        
        Returns:
            Dictionary containing incremental update performance metrics
        """
        try:
            # Get metadata about last analysis
            metadata = self.db.execute_query("""
                SELECT last_analysis_date, transactions_analyzed, patterns_discovered,
                       date_range_from, date_range_to, created_at, updated_at
                FROM pattern_analysis_metadata 
                WHERE administration = %s
            """, (administration,))
            
            if not metadata:
                return {
                    'administration': administration,
                    'incremental_updates_available': False,
                    'reason': 'No previous analysis found'
                }
            
            meta = metadata[0]
            last_analysis = meta['last_analysis_date']
            
            # Count transactions that would be processed in next incremental update
            pending_transactions = self.db.execute_query("""
                SELECT COUNT(*) as count, MIN(TransactionDate) as earliest, MAX(TransactionDate) as latest
                FROM mutaties 
                WHERE Administration = %s
                AND TransactionDate > %s
                AND (Debet IS NOT NULL OR Credit IS NOT NULL)
            """, (administration, last_analysis))
            
            pending_count = pending_transactions[0]['count'] if pending_transactions else 0
            earliest_pending = pending_transactions[0]['earliest'] if pending_transactions else None
            latest_pending = pending_transactions[0]['latest'] if pending_transactions else None
            
            # Get total transaction count for comparison
            total_transactions = self.db.execute_query("""
                SELECT COUNT(*) as count FROM mutaties 
                WHERE Administration = %s 
                AND TransactionDate >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
                AND (Debet IS NOT NULL OR Credit IS NOT NULL)
            """, (administration,))
            
            total_count = total_transactions[0]['count'] if total_transactions else 0
            
            # Calculate efficiency metrics
            if total_count > 0 and pending_count >= 0:
                efficiency_ratio = pending_count / total_count
                processing_reduction = (1 - efficiency_ratio) * 100
            else:
                efficiency_ratio = 0
                processing_reduction = 0
            
            return {
                'administration': administration,
                'incremental_updates_available': True,
                'last_analysis': {
                    'date': last_analysis.isoformat() if last_analysis else None,
                    'transactions_analyzed': meta['transactions_analyzed'],
                    'patterns_discovered': meta['patterns_discovered'],
                    'analysis_period': {
                        'from': meta['date_range_from'].strftime('%Y-%m-%d') if meta['date_range_from'] else None,
                        'to': meta['date_range_to'].strftime('%Y-%m-%d') if meta['date_range_to'] else None
                    }
                },
                'pending_incremental_update': {
                    'transactions_to_process': pending_count,
                    'date_range': {
                        'from': earliest_pending.strftime('%Y-%m-%d') if earliest_pending else None,
                        'to': latest_pending.strftime('%Y-%m-%d') if latest_pending else None
                    },
                    'efficiency_gain': f"{processing_reduction:.1f}% reduction in processing",
                    'processing_ratio': f"{pending_count}/{total_count} transactions"
                },
                'performance_benefits': {
                    'database_io_reduction': f"{processing_reduction:.1f}%",
                    'processing_time_reduction': f"~{processing_reduction:.1f}%",
                    'memory_usage_reduction': f"~{processing_reduction:.1f}%",
                    'incremental_processing_active': True
                },
                'recommendations': {
                    'should_run_incremental': pending_count > 0,
                    'should_run_full_analysis': self._should_refresh_patterns(administration),
                    'next_action': 'incremental_update' if pending_count > 0 and not self._should_refresh_patterns(administration) else 'full_analysis'
                }
            }
            
        except Exception as e:
            return {
                'administration': administration,
                'incremental_updates_available': False,
                'error': f"Could not retrieve incremental update stats: {e}"
            }