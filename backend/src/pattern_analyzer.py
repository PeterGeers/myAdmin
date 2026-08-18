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
from typing import Any

from database import DatabaseManager
from dialect_helpers import dialect
from pattern_cache import get_pattern_cache
from pattern_detection import (
    analyze_credit_patterns,
    analyze_debet_patterns,
    analyze_reference_patterns,
    extract_company_name,
    extract_compound_verb_from_description,
    extract_keywords,
    extract_reference_number_from_description,
    extract_verb_from_description,
    is_valid_verb,
)
from pattern_scoring import (
    CONFIDENCE_THRESHOLD_CONFIDENT,
    build_reference_account_index,
    calculate_statistics_from_db_patterns,
    generate_pattern_statistics,
    predict_account_from_reference,
    predict_credit,
    predict_debet,
    predict_reference,
    resolve_pattern_conflicts,
)
from pattern_storage import (
    build_cache_key,
    get_cache_performance_stats,
    get_incremental_update_stats,
    get_pattern_storage_stats,
    load_patterns_from_database,
    should_refresh_patterns,
    store_verb_patterns_to_database,
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

    def get_bank_accounts(self) -> dict[str, dict]:
        """Get bank account lookup data with caching"""
        if self.bank_accounts_cache is None:
            bank_accounts = self.db.get_bank_account_lookups()
            self.bank_accounts_cache = {}

            for account in bank_accounts:
                key = f"{account['administration']}_{account['Account']}".lower()
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
        key = f"{administration}_{account_number}".lower()
        return key in bank_accounts

    def analyze_historical_patterns(
        self,
        administration: str,
        reference_number: str | None = None,
        debet_account: str | None = None,
        credit_account: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze last 1 year of transaction data to discover patterns

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

        # Get transactions from last 1 year with optional filtering
        one_year_ago = datetime.now() - timedelta(days=365)

        # Build dynamic query with filters
        query_conditions = [
            "administration = %s",
            "TransactionDate >= %s",
            "(Debet IS NOT NULL OR Credit IS NOT NULL)",
        ]
        query_params = [administration, one_year_ago.strftime("%Y-%m-%d")]

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

        print(f"📊 Processing {len(transactions)} transactions from last 1 year...")

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
                "from": one_year_ago.strftime("%Y-%m-%d"),
                "to": datetime.now().strftime("%Y-%m-%d"),
            },
        }

        # Store patterns in database for persistent storage (REQ-PAT-005)
        # Guard: only store if patterns were actually discovered (avoid overwriting good data with nothing)
        if (
            not reference_number
            and not debet_account
            and not credit_account
            and len(reference_patterns_result) > 0
        ):
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
        self, transactions: list[dict], administration: str
    ) -> tuple[list[dict], dict[str, Any]]:
        """
        Apply discovered patterns to predict missing values in transactions.

        Orchestration order:
          Step 1: Predict reference (or use pre-populated ReferenceNumber)
          Step 2: If reference available → try predict_account_from_reference
          Step 3: If step 2 returned None → fall back to predict_debet/predict_credit

        Args:
            transactions: List of transaction dictionaries
            administration: Administration to get patterns for

        Returns:
            Tuple of (updated_transactions, application_results)
        """
        print(f"🔧 Applying patterns to {len(transactions)} transactions...")

        # Get patterns for this administration (multi-level cache)
        patterns = self.get_filtered_patterns(administration)

        # Build reference-account index from existing verb patterns (no extra DB query)
        reference_account_index = build_reference_account_index(
            patterns["reference_patterns"]
        )

        results = {
            "total_transactions": len(transactions),
            "predictions_made": {"debet": 0, "credit": 0, "reference": 0},
            "prediction_methods": {"reference_lookup": 0, "verb_matching": 0},
            "confidence_scores": [],
            "failed_predictions": 0,
        }

        updated_transactions = []

        for tx in transactions:
            updated_tx = tx.copy()
            tx_predictions = []

            # ─── Step 1: Predict Reference (existing, unchanged) ───
            ref_confidence = 1.0  # Default: user-supplied reference
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
                    ref_confidence = ref_prediction["confidence"]
                    results["predictions_made"]["reference"] += 1
                    tx_predictions.append(ref_prediction["confidence"])
            # else: ReferenceNumber already populated → use it with confidence 1.0 (Task 3.2)

            # ─── Step 2: Reference Lookup for counter-account (NEW) ───
            account_predicted_via_ref = False

            if (
                updated_tx.get("ReferenceNumber")
                and ref_confidence >= CONFIDENCE_THRESHOLD_CONFIDENT
            ):
                # Identify bank account for this transaction
                bank_account = None
                if self.is_bank_account(updated_tx.get("Debet", ""), administration):
                    bank_account = updated_tx["Debet"]
                elif self.is_bank_account(updated_tx.get("Credit", ""), administration):
                    bank_account = updated_tx["Credit"]

                if bank_account:
                    ref_lookup_result = predict_account_from_reference(
                        reference_code=updated_tx["ReferenceNumber"],
                        reference_confidence=ref_confidence,
                        bank_account=bank_account,
                        administration=administration,
                        reference_account_index=reference_account_index,
                    )

                    if ref_lookup_result:
                        # Determine which field to set (debet or credit)
                        if bank_account == updated_tx.get("Credit", ""):
                            # Bank is credit → predict debet
                            if not updated_tx.get("Debet"):
                                updated_tx["Debet"] = ref_lookup_result["value"]
                                updated_tx["_debet_confidence"] = ref_lookup_result[
                                    "confidence"
                                ]
                                updated_tx["_prediction_method"] = "reference_lookup"
                                updated_tx["_uncertain"] = ref_lookup_result[
                                    "uncertain"
                                ]
                                results["predictions_made"]["debet"] += 1
                                results["prediction_methods"]["reference_lookup"] += 1
                                tx_predictions.append(ref_lookup_result["confidence"])
                                account_predicted_via_ref = True
                        elif bank_account == updated_tx.get(
                            "Debet", ""
                        ) and not updated_tx.get("Credit"):
                            # Bank is debet → predict credit
                            updated_tx["Credit"] = ref_lookup_result["value"]
                            updated_tx["_credit_confidence"] = ref_lookup_result[
                                "confidence"
                            ]
                            updated_tx["_prediction_method"] = "reference_lookup"
                            updated_tx["_uncertain"] = ref_lookup_result["uncertain"]
                            results["predictions_made"]["credit"] += 1
                            results["prediction_methods"]["reference_lookup"] += 1
                            tx_predictions.append(ref_lookup_result["confidence"])
                            account_predicted_via_ref = True

            # ─── Step 3: Verb-matching fallback (existing, unchanged) ───
            if not account_predicted_via_ref:
                # Apply debet patterns (existing logic)
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
                        updated_tx["_prediction_method"] = "verb_matching"
                        updated_tx["_uncertain"] = (
                            debet_prediction["confidence"]
                            < CONFIDENCE_THRESHOLD_CONFIDENT
                        )
                        results["predictions_made"]["debet"] += 1
                        results["prediction_methods"]["verb_matching"] += 1
                        tx_predictions.append(debet_prediction["confidence"])

                # Apply credit patterns (existing logic)
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
                        updated_tx["_credit_confidence"] = credit_prediction[
                            "confidence"
                        ]
                        updated_tx["_prediction_method"] = "verb_matching"
                        updated_tx["_uncertain"] = (
                            credit_prediction["confidence"]
                            < CONFIDENCE_THRESHOLD_CONFIDENT
                        )
                        results["predictions_made"]["credit"] += 1
                        results["prediction_methods"]["verb_matching"] += 1
                        tx_predictions.append(credit_prediction["confidence"])

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
            f"✅ Pattern application complete: {sum(results['predictions_made'].values())} predictions made "
            f"(ref_lookup: {results['prediction_methods']['reference_lookup']}, "
            f"verb: {results['prediction_methods']['verb_matching']})"
        )
        return updated_transactions, results

    def analyze_incremental_patterns(self, administration: str) -> dict[str, Any]:
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
            _updated_transactions, application_results = (
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
        reference_number: str | None = None,
        debet_account: str | None = None,
        credit_account: str | None = None,
    ) -> dict[str, Any]:
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

    def get_pattern_summary(self, administration: str) -> dict[str, Any]:
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

    def get_cache_performance_stats(self, administration: str) -> dict[str, Any]:
        """Get comprehensive cache performance statistics"""
        return get_cache_performance_stats(
            self.db, administration, self.persistent_cache
        )

    def get_pattern_storage_stats(self, administration: str) -> dict[str, Any]:
        """Get statistics about pattern storage performance"""
        return get_pattern_storage_stats(self.db, administration)

    def get_incremental_update_stats(self, administration: str) -> dict[str, Any]:
        """Get statistics about incremental pattern updates"""
        return get_incremental_update_stats(self.db, administration)

    # =========================================================================
    # Private helper methods (thin wrappers for backward compatibility)
    # =========================================================================

    def _extract_verb_from_description(
        self, description: str, reference_number: str
    ) -> str | None:
        """Extract verb from description - delegates to pattern_detection module"""
        return extract_verb_from_description(description, reference_number)

    def _extract_compound_verb_from_description(
        self, description: str, reference_number: str
    ) -> str | None:
        """Extract compound verb - delegates to pattern_detection module"""
        return extract_compound_verb_from_description(description, reference_number)

    def _extract_company_name(self, description: str) -> str | None:
        """Extract company name - delegates to pattern_detection module"""
        return extract_company_name(description)

    def _extract_reference_number_from_description(
        self, description: str
    ) -> str | None:
        """Extract reference number - delegates to pattern_detection module"""
        return extract_reference_number_from_description(description)

    def _is_valid_verb(self, verb: str) -> bool:
        """Validate verb - delegates to pattern_detection module"""
        return is_valid_verb(verb)

    def _extract_keywords(self, description: str) -> list[str]:
        """Extract keywords - delegates to pattern_detection module"""
        return extract_keywords(description)

    def _analyze_debet_patterns(
        self, transactions: list[dict], administration: str
    ) -> dict[str, Any]:
        """Analyze debet patterns - delegates to pattern_detection module"""
        return analyze_debet_patterns(
            transactions, administration, self.is_bank_account
        )

    def _analyze_credit_patterns(
        self, transactions: list[dict], administration: str
    ) -> dict[str, Any]:
        """Analyze credit patterns - delegates to pattern_detection module"""
        return analyze_credit_patterns(
            transactions, administration, self.is_bank_account
        )

    def _analyze_reference_patterns(
        self, transactions: list[dict], administration: str
    ) -> dict[str, Any]:
        """Analyze reference patterns - delegates to pattern_detection module"""
        return analyze_reference_patterns(
            transactions, administration, self.is_bank_account
        )

    def _generate_pattern_statistics(
        self,
        transactions: list[dict],
        debet_patterns: dict,
        credit_patterns: dict,
        reference_patterns: dict,
    ) -> dict[str, Any]:
        """Generate statistics - delegates to pattern_scoring module"""
        return generate_pattern_statistics(
            transactions,
            debet_patterns,
            credit_patterns,
            reference_patterns,
            self.is_bank_account,
        )

    def _calculate_statistics_from_db_patterns(
        self, debet_patterns: dict, credit_patterns: dict, reference_patterns: dict
    ) -> dict:
        """Calculate stats from DB patterns - delegates to pattern_scoring module"""
        return calculate_statistics_from_db_patterns(
            debet_patterns, credit_patterns, reference_patterns
        )

    def _resolve_pattern_conflicts(
        self,
        matching_patterns: list[tuple[str, dict]],
        transaction: dict,
        administration: str,
    ) -> tuple[str, dict] | None:
        """Resolve pattern conflicts - delegates to pattern_scoring module"""
        return resolve_pattern_conflicts(
            matching_patterns, transaction, administration, self.is_bank_account
        )

    def _store_verb_patterns_to_database(
        self,
        administration: str,
        verb_patterns: dict,
        analysis_metadata: dict,
        is_incremental: bool = False,
    ):
        """Store patterns to DB - delegates to pattern_storage module"""
        store_verb_patterns_to_database(
            self.db, administration, verb_patterns, analysis_metadata, is_incremental
        )

    def _load_patterns_from_database(self, administration: str) -> dict[str, Any]:
        """Load patterns from DB - delegates to pattern_storage module"""
        return load_patterns_from_database(self.db, administration)

    def _should_refresh_patterns(self, administration: str) -> bool:
        """Check refresh needed - delegates to pattern_storage module"""
        return should_refresh_patterns(self.db, administration)

    def _build_cache_key(
        self,
        administration: str,
        reference_number: str | None = None,
        debet_account: str | None = None,
        credit_account: str | None = None,
    ) -> str:
        """Build cache key - delegates to pattern_storage module"""
        return build_cache_key(
            administration, reference_number, debet_account, credit_account
        )
