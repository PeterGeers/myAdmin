#!/usr/bin/env python3
"""
Enhanced Pattern Analysis System for Banking Processor

This module is the orchestrator for pattern analysis. It delegates to:
- pattern_detection.py: Pattern detection logic (verb/company extraction, keyword analysis)
- pattern_scoring.py: Pattern scoring, ranking, and prediction
- pattern_storage.py: Database persistence and cache key management
- pattern_cache.py: Multi-level persistent caching (memory/DB/file)

Requirements addressed:
- REQ-PAT-001: Analyze transactions from the last 2 years for pattern discovery
- REQ-PAT-002: Filter patterns by Administration, ReferenceNumber, Debet/Credit values, and Date
- REQ-PAT-003: Create pattern matching based on known variables
- REQ-PAT-004: Implement bank account lookup logic
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from database import DatabaseManager
from dialect_helpers import dialect
from pattern_cache import get_pattern_cache
from pattern_detection import (
    extract_keywords,
    extract_company_name,
    extract_reference_number_from_description,
    extract_compound_verb_from_description,
    extract_verb_from_description,
    is_valid_verb,
    analyze_debet_patterns,
    analyze_credit_patterns,
    analyze_reference_patterns,
)
from pattern_scoring import (
    generate_pattern_statistics,
    calculate_statistics_from_db_patterns,
    resolve_pattern_conflicts,
    predict_debet,
    predict_credit,
    predict_reference,
)
from pattern_storage import (
    build_cache_key,
    store_verb_patterns_to_database,
    load_patterns_from_database,
    should_refresh_patterns,
    get_cache_performance_stats,
    get_pattern_storage_stats,
    get_incremental_update_stats,
)


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
                key = f"{account['administration']}_{account['Account']}"
                self.bank_accounts_cache[key] = {
                    "iban": account["rekeningNummer"],
                    "account": account["Account"],
                    "administration": account["administration"],
                }

        return self.bank_accounts_cache

    def is_bank_account(self, account_number: str, administration: str) -> bool:
        """Check if an account number is a bank account"""
        if not account_number:
            return False

        bank_accounts = self.get_bank_accounts()
        key = f"{administration}_{account_number}"
        return key in bank_accounts

    def analyze_historical_patterns(
        self,
        administration: str,
        reference_number: Optional[str] = None,
        debet_account: Optional[str] = None,
        credit_account: Optional[str] = None,
    ) -> Dict[str, Any]:
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
            "administration = %s",
            "TransactionDate >= %s",
            "(Debet IS NOT NULL OR Credit IS NOT NULL)",
        ]
        query_params = [administration, two_years_ago.strftime("%Y-%m-%d")]

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
                   TransactionDate, TransactionAmount, Ref1, administration
            FROM mutaties 
            WHERE {" AND ".join(query_conditions)}
            ORDER BY TransactionDate DESC
        """

        transactions = self.db.execute_query(query, tuple(query_params))

        if not transactions:
            return {
                "total_transactions": 0,
                "patterns_discovered": 0,
                "debet_patterns": {},
                "credit_patterns": {},
                "reference_patterns": {},
                "statistics": {},
            }

        print(f"📊 Processing {len(transactions)} transactions from last 2 years...")

        # Analyze patterns (delegated to pattern_detection module)
        debet_patterns = analyze_debet_patterns(
            transactions, administration, self.is_bank_account
        )
        credit_patterns = analyze_credit_patterns(
            transactions, administration, self.is_bank_account
        )
        reference_patterns_result = analyze_reference_patterns(
            transactions, administration, self.is_bank_account
        )

        # Generate statistics (delegated to pattern_scoring module)
        statistics = generate_pattern_statistics(
            transactions,
            debet_patterns,
            credit_patterns,
            reference_patterns_result,
            self.is_bank_account,
        )

        result = {
            "total_transactions": len(transactions),
            "patterns_discovered": len(debet_patterns)
            + len(credit_patterns)
            + len(reference_patterns_result),
            "debet_patterns": debet_patterns,
            "credit_patterns": credit_patterns,
            "reference_patterns": reference_patterns_result,
            "statistics": statistics,
            "analysis_date": datetime.now().isoformat(),
            "date_range": {
                "from": two_years_ago.strftime("%Y-%m-%d"),
                "to": datetime.now().strftime("%Y-%m-%d"),
            },
        }

        # Store patterns in database for persistent storage (REQ-PAT-005)
        if not reference_number and not debet_account and not credit_account:
            store_verb_patterns_to_database(
                self.db, administration, reference_patterns_result, result
            )
            # Invalidate persistent cache since we have new patterns
            self.persistent_cache.invalidate_cache(administration)

        # Cache the results with filter-specific key for backward compatibility
        cache_key = build_cache_key(
            administration, reference_number, debet_account, credit_account
        )
        self.patterns_cache[cache_key] = result

        print(
            f"✅ Pattern analysis complete: {result['patterns_discovered']} patterns discovered"
        )
        return result

    def apply_patterns_to_transactions(
        self, transactions: List[Dict], administration: str
    ) -> Tuple[List[Dict], Dict[str, Any]]:
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
            "total_transactions": len(transactions),
            "predictions_made": {"debet": 0, "credit": 0, "reference": 0},
            "confidence_scores": [],
            "failed_predictions": 0,
        }

        updated_transactions = []

        for tx in transactions:
            updated_tx = tx.copy()
            tx_predictions = []

            # Apply debet patterns (delegated to pattern_scoring module)
            if not updated_tx.get("Debet"):
                debet_prediction = predict_debet(
                    updated_tx,
                    patterns["reference_patterns"],
                    administration,
                    self.is_bank_account,
                    self._extract_verb_from_description,
                    self.get_filtered_patterns,
                )
                if debet_prediction:
                    updated_tx["Debet"] = debet_prediction["value"]
                    updated_tx["_debet_confidence"] = debet_prediction["confidence"]
                    results["predictions_made"]["debet"] += 1
                    tx_predictions.append(debet_prediction["confidence"])

            # Apply credit patterns (delegated to pattern_scoring module)
            if not updated_tx.get("Credit"):
                credit_prediction = predict_credit(
                    updated_tx,
                    patterns["reference_patterns"],
                    administration,
                    self.is_bank_account,
                    self._extract_verb_from_description,
                    self.get_filtered_patterns,
                )
                if credit_prediction:
                    updated_tx["Credit"] = credit_prediction["value"]
                    updated_tx["_credit_confidence"] = credit_prediction["confidence"]
                    results["predictions_made"]["credit"] += 1
                    tx_predictions.append(credit_prediction["confidence"])

            # Apply reference patterns (delegated to pattern_scoring module)
            if not updated_tx.get("ReferenceNumber"):
                ref_prediction = predict_reference(
                    updated_tx,
                    patterns["reference_patterns"],
                    self.is_bank_account,
                    self._extract_verb_from_description,
                )
                if ref_prediction:
                    updated_tx["ReferenceNumber"] = ref_prediction["value"]
                    updated_tx["_reference_confidence"] = ref_prediction["confidence"]
                    results["predictions_made"]["reference"] += 1
                    tx_predictions.append(ref_prediction["confidence"])

            # Track confidence scores
            if tx_predictions:
                results["confidence_scores"].extend(tx_predictions)
            else:
                results["failed_predictions"] += 1

            updated_transactions.append(updated_tx)

        # Calculate average confidence
        if results["confidence_scores"]:
            results["average_confidence"] = sum(results["confidence_scores"]) / len(
                results["confidence_scores"]
            )
        else:
            results["average_confidence"] = 0.0

        print(
            f"✅ Pattern application complete: {sum(results['predictions_made'].values())} predictions made"
        )
        return updated_transactions, results

    def analyze_incremental_patterns(self, administration: str) -> Dict[str, Any]:
        """
        Analyze patterns incrementally — only new transactions since last analysis

        REQ-PAT-006: Incremental pattern updates
        """
        print(f"🔄 Running incremental pattern analysis for {administration}...")

        try:
            # Get last analysis date and current metadata
            metadata = self.db.execute_query(
                """
                SELECT last_analysis_date, transactions_analyzed, patterns_discovered 
                FROM pattern_analysis_metadata 
                WHERE administration = %s
            """,
                (administration,),
            )

            if not metadata or not metadata[0]["last_analysis_date"]:
                print("No previous analysis found, running full analysis...")
                return self.analyze_historical_patterns(administration)

            last_analysis_date = metadata[0]["last_analysis_date"]
            previous_transactions = metadata[0]["transactions_analyzed"] or 0
            previous_patterns = metadata[0]["patterns_discovered"] or 0

            print(f"Last analysis: {last_analysis_date}")
            print(
                f"Previous analysis: {previous_transactions} transactions, {previous_patterns} patterns"
            )

            # Step 1: Load existing patterns from database
            existing_patterns = load_patterns_from_database(self.db, administration)
            existing_pattern_keys = set(existing_patterns["reference_patterns"].keys())

            # Step 2: Get new transactions since last analysis
            new_transactions = self.db.execute_query(
                """
                SELECT TransactionDescription, Debet, Credit, ReferenceNumber, 
                       TransactionDate, TransactionAmount, Ref1, administration
                FROM mutaties 
                WHERE administration = %s
                AND TransactionDate > %s
                AND (Debet IS NOT NULL OR Credit IS NOT NULL)
                ORDER BY TransactionDate DESC
            """,
                (administration, last_analysis_date),
            )

            if not new_transactions:
                print(
                    "✅ No new transactions found since last analysis - patterns are up to date"
                )
                existing_patterns["total_transactions"] = 0
                existing_patterns["incremental_update"] = {
                    "new_transactions_processed": 0,
                    "new_patterns_discovered": 0,
                    "previous_transaction_count": previous_transactions,
                    "previous_pattern_count": previous_patterns,
                    "total_patterns_in_database": len(existing_pattern_keys),
                    "efficiency_gain": "No processing needed - already up to date",
                }
                return existing_patterns

            print(f"📊 Found {len(new_transactions)} new transactions to process")

            # Step 3: Apply existing patterns to new transactions
            updated_transactions, application_results = (
                self.apply_patterns_to_transactions(new_transactions, administration)
            )

            # Step 4: Analyze complete dataset to discover new patterns
            two_years_ago = datetime.now() - timedelta(days=730)
            all_transactions = self.db.execute_query(
                """
                SELECT TransactionDescription, Debet, Credit, ReferenceNumber, 
                       TransactionDate, TransactionAmount, Ref1, administration
                FROM mutaties 
                WHERE administration = %s
                AND TransactionDate >= %s
                AND (Debet IS NOT NULL OR Credit IS NOT NULL)
                ORDER BY TransactionDate DESC
            """,
                (administration, two_years_ago.strftime("%Y-%m-%d")),
            )

            new_reference_patterns = analyze_reference_patterns(
                all_transactions, administration, self.is_bank_account
            )

            # Step 5: Compare before/after to identify new patterns
            truly_new_patterns = {}
            updated_patterns = {}

            for pattern_key, pattern in new_reference_patterns.items():
                if pattern_key not in existing_pattern_keys:
                    truly_new_patterns[pattern_key] = pattern
                else:
                    existing_pattern = existing_patterns["reference_patterns"][
                        pattern_key
                    ]
                    if pattern.get("occurrences", 0) > existing_pattern.get(
                        "occurrences", 0
                    ):
                        pattern["occurrences"] = pattern[
                            "occurrences"
                        ] - existing_pattern.get("occurrences", 0)
                        updated_patterns[pattern_key] = pattern

            # Step 6: Store new/updated patterns
            patterns_to_store = {**truly_new_patterns, **updated_patterns}

            statistics = generate_pattern_statistics(
                new_transactions, {}, {}, patterns_to_store, self.is_bank_account
            )

            result = {
                "total_transactions": len(new_transactions),
                "patterns_discovered": len(patterns_to_store),
                "debet_patterns": {},
                "credit_patterns": {},
                "reference_patterns": patterns_to_store,
                "statistics": statistics,
                "analysis_date": datetime.now().isoformat(),
                "date_range": {
                    "from": last_analysis_date.strftime("%Y-%m-%d"),
                    "to": datetime.now().strftime("%Y-%m-%d"),
                },
            }

            if patterns_to_store:
                store_verb_patterns_to_database(
                    self.db,
                    administration,
                    patterns_to_store,
                    result,
                    is_incremental=True,
                )
                self.persistent_cache.invalidate_cache(administration)
            else:
                self.db.execute_query(
                    f"""
                    UPDATE pattern_analysis_metadata 
                    SET last_analysis_date = {dialect.current_timestamp()},
                        transactions_analyzed = transactions_analyzed + %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE administration = %s
                """,
                    (len(new_transactions), administration),
                    fetch=False,
                    commit=True,
                )

            # Load final patterns from database
            final_result = load_patterns_from_database(self.db, administration)
            final_result["total_transactions"] = len(new_transactions)
            final_result["patterns_discovered"] = len(patterns_to_store)
            final_result["incremental_update"] = {
                "new_transactions_processed": len(new_transactions),
                "new_patterns_discovered": len(truly_new_patterns),
                "updated_patterns": len(updated_patterns),
                "total_pattern_changes": len(patterns_to_store),
                "previous_transaction_count": previous_transactions,
                "previous_pattern_count": previous_patterns,
                "total_patterns_in_database": final_result.get(
                    "patterns_discovered", 0
                ),
                "efficiency_gain": f"Analyzed {len(new_transactions)} new transactions vs {len(all_transactions)} total",
                "time_range": f"{last_analysis_date.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}",
                "pattern_application_results": application_results,
            }

            print("✅ Incremental analysis complete:")
            print(f"   - {len(new_transactions)} new transactions processed")
            print(f"   - {len(truly_new_patterns)} new patterns discovered")
            print(f"   - {len(updated_patterns)} existing patterns updated")

            return final_result

        except Exception as e:
            print(f"❌ Error in incremental analysis: {e}")
            print("🔄 Falling back to full analysis...")
            return self.analyze_historical_patterns(administration)

    def get_filtered_patterns(
        self,
        administration: str,
        reference_number: Optional[str] = None,
        debet_account: Optional[str] = None,
        credit_account: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get patterns with optional filtering — uses persistent cache with fallback to analysis.

        REQ-PAT-002: Filter patterns by Administration, ReferenceNumber, Debet/Credit values, and Date
        REQ-PAT-006: Implement pattern caching for performance - PERSISTENT CACHE
        """
        # Try persistent cache first (multi-level: memory -> database -> file)
        cached_patterns = self.persistent_cache.get_patterns(
            administration, reference_number, debet_account, credit_account
        )

        if cached_patterns:
            return cached_patterns

        # Cache miss - analyze patterns and store in persistent cache
        print(f"🔍 Cache miss - analyzing patterns for {administration}")
        patterns = self.analyze_historical_patterns(
            administration, reference_number, debet_account, credit_account
        )

        # Store in persistent cache for future use
        self.persistent_cache.store_patterns(
            administration, patterns, reference_number, debet_account, credit_account
        )

        # Also store in legacy memory cache for backward compatibility
        cache_key = build_cache_key(
            administration, reference_number, debet_account, credit_account
        )
        self.patterns_cache[cache_key] = patterns

        return patterns

    def get_pattern_summary(self, administration: str) -> Dict[str, Any]:
        """Get a summary of patterns for an administration"""
        patterns = self.get_filtered_patterns(administration)

        return {
            "administration": administration,
            "total_patterns": patterns["patterns_discovered"],
            "statistics": patterns["statistics"],
            "date_range": patterns["date_range"],
            "analysis_date": patterns["analysis_date"],
            "pattern_types": {
                "debet": len(patterns["debet_patterns"]),
                "credit": len(patterns["credit_patterns"]),
                "reference": len(patterns["reference_patterns"]),
            },
            "storage_stats": get_pattern_storage_stats(self.db, administration),
        }

    def get_cache_performance_stats(self, administration: str) -> Dict[str, Any]:
        """Get comprehensive cache performance statistics"""
        return get_cache_performance_stats(
            self.db, administration, self.persistent_cache
        )

    def get_pattern_storage_stats(self, administration: str) -> Dict[str, Any]:
        """Get statistics about pattern storage performance"""
        return get_pattern_storage_stats(self.db, administration)

    def get_incremental_update_stats(self, administration: str) -> Dict[str, Any]:
        """Get statistics about incremental pattern updates"""
        return get_incremental_update_stats(self.db, administration)

    # =========================================================================
    # Private helper methods (thin wrappers for backward compatibility)
    # =========================================================================

    def _extract_verb_from_description(
        self, description: str, reference_number: str
    ) -> Optional[str]:
        """Extract verb from description - delegates to pattern_detection module"""
        return extract_verb_from_description(description, reference_number)

    def _extract_compound_verb_from_description(
        self, description: str, reference_number: str
    ) -> Optional[str]:
        """Extract compound verb - delegates to pattern_detection module"""
        return extract_compound_verb_from_description(description, reference_number)

    def _extract_company_name(self, description: str) -> Optional[str]:
        """Extract company name - delegates to pattern_detection module"""
        return extract_company_name(description)

    def _extract_reference_number_from_description(
        self, description: str
    ) -> Optional[str]:
        """Extract reference number - delegates to pattern_detection module"""
        return extract_reference_number_from_description(description)

    def _is_valid_verb(self, verb: str) -> bool:
        """Validate verb - delegates to pattern_detection module"""
        return is_valid_verb(verb)

    def _extract_keywords(self, description: str) -> List[str]:
        """Extract keywords - delegates to pattern_detection module"""
        return extract_keywords(description)

    def _analyze_debet_patterns(
        self, transactions: List[Dict], administration: str
    ) -> Dict[str, Any]:
        """Analyze debet patterns - delegates to pattern_detection module"""
        return analyze_debet_patterns(
            transactions, administration, self.is_bank_account
        )

    def _analyze_credit_patterns(
        self, transactions: List[Dict], administration: str
    ) -> Dict[str, Any]:
        """Analyze credit patterns - delegates to pattern_detection module"""
        return analyze_credit_patterns(
            transactions, administration, self.is_bank_account
        )

    def _analyze_reference_patterns(
        self, transactions: List[Dict], administration: str
    ) -> Dict[str, Any]:
        """Analyze reference patterns - delegates to pattern_detection module"""
        return analyze_reference_patterns(
            transactions, administration, self.is_bank_account
        )

    def _generate_pattern_statistics(
        self,
        transactions: List[Dict],
        debet_patterns: Dict,
        credit_patterns: Dict,
        reference_patterns: Dict,
    ) -> Dict[str, Any]:
        """Generate statistics - delegates to pattern_scoring module"""
        return generate_pattern_statistics(
            transactions,
            debet_patterns,
            credit_patterns,
            reference_patterns,
            self.is_bank_account,
        )

    def _calculate_statistics_from_db_patterns(
        self, debet_patterns: Dict, credit_patterns: Dict, reference_patterns: Dict
    ) -> Dict:
        """Calculate stats from DB patterns - delegates to pattern_scoring module"""
        return calculate_statistics_from_db_patterns(
            debet_patterns, credit_patterns, reference_patterns
        )

    def _resolve_pattern_conflicts(
        self,
        matching_patterns: List[Tuple[str, Dict]],
        transaction: Dict,
        administration: str,
    ) -> Optional[Tuple[str, Dict]]:
        """Resolve pattern conflicts - delegates to pattern_scoring module"""
        return resolve_pattern_conflicts(
            matching_patterns, transaction, administration, self.is_bank_account
        )

    def _store_verb_patterns_to_database(
        self,
        administration: str,
        verb_patterns: Dict,
        analysis_metadata: Dict,
        is_incremental: bool = False,
    ):
        """Store patterns to DB - delegates to pattern_storage module"""
        store_verb_patterns_to_database(
            self.db, administration, verb_patterns, analysis_metadata, is_incremental
        )

    def _load_patterns_from_database(self, administration: str) -> Dict[str, Any]:
        """Load patterns from DB - delegates to pattern_storage module"""
        return load_patterns_from_database(self.db, administration)

    def _should_refresh_patterns(self, administration: str) -> bool:
        """Check refresh needed - delegates to pattern_storage module"""
        return should_refresh_patterns(self.db, administration)

    def _build_cache_key(
        self,
        administration: str,
        reference_number: Optional[str] = None,
        debet_account: Optional[str] = None,
        credit_account: Optional[str] = None,
    ) -> str:
        """Build cache key - delegates to pattern_storage module"""
        return build_cache_key(
            administration, reference_number, debet_account, credit_account
        )
