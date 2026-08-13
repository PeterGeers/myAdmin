# Implementation Plan: Prediction Engine Improvement (Phase 1)

## Overview

Implementation of sequential prediction flow: predict reference code first, then use it as a lookup key for counter-account prediction. Includes a prerequisite fix for pattern data hygiene.

Total estimated effort: ~13 hours across 5 phases. Phases 4 and 5 are optional.

## Tasks

- [x] 1. Phase 1: Pattern Data Hygiene (Prerequisite)
  - [x] 1.1 Fix occurrence accumulation in `store_verb_patterns_to_database()`
    - File: `backend/src/pattern_storage.py`
    - Change: Replace `occurrences = occurrences + VALUES(occurrences)` with `occurrences = VALUES(occurrences)` when `is_incremental = False`
    - Keep accumulation behavior for incremental analysis unchanged
    - _Requirements: 0.1_
    - _Estimate: 30 min_

  - [x] 1.2 Add stale pattern cleanup after full analysis
    - File: `backend/src/pattern_storage.py`
    - Add DELETE statement after the UPSERT loop: remove patterns where `last_seen < analysis_start_date` when `is_incremental = False`
    - Log the count of deleted patterns
    - _Requirements: 0.2, 0.3, 0.4_
    - _Estimate: 30 min_

  - [x] 1.3 Unit tests for pattern hygiene fixes
    - Test that full analysis replaces (not accumulates) occurrence counts
    - Test that stale patterns are deleted after full analysis
    - Test that incremental analysis still accumulates occurrences
    - Test that deletion only happens during full analysis, not incremental
    - Test log output on stale cleanup
    - _Requirements: 0.1, 0.2, 0.3, 0.4_
    - _Estimate: 1 hour_

  - [x] 1.4 Verify fix on live data
    - Run full analysis for one administration
    - Confirm patterns with `last_seen` > 1 year old are removed
    - Confirm occurrence counts match actual transaction counts (not doubled)
    - _Requirements: 0.1, 0.2_
    - _Estimate: 30 min_

- [x] 2. Phase 2: Reference Account Index
  - [x] 2.1 Implement `build_reference_account_index()` function
    - File: `backend/src/pattern_scoring.py`
    - Re-indexes existing verb patterns by `reference_number` instead of `verb`
    - Derives counter-account from bank_account + debet_account/credit_account
    - Skips ambiguous patterns and patterns with confidence ≤ 0
    - When multiple verbs share the same reference_number, keeps the one with highest occurrences
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
    - _Estimate: 1 hour_

  - [x] 2.2 Implement `predict_account_from_reference()` function
    - File: `backend/src/pattern_scoring.py`
    - Lookup by `{admin}_{bank_account}_{reference_code}` in the index
    - Multiply reference_confidence × lookup_confidence for combined score
    - Return result with `uncertain` flag when combined confidence < 0.80
    - Return None when no match found
    - Handle compound verbs (full compound as lookup key, no company-only fallback)
    - _Requirements: 2.2, 2.3, 4.1, 4.3, 6.1, 6.2, 6.3, 6.4_
    - _Estimate: 1 hour_

  - [x] 2.3 Add shared threshold constant
    - File: `backend/src/pattern_scoring.py`
    - Define `CONFIDENCE_THRESHOLD_CONFIDENT = 0.80` at module level
    - Use in both `predict_account_from_reference()` and existing predict functions
    - _Requirements: 7.6_
    - _Estimate: 15 min_

  - [x] 2.4 Unit tests for reference account index and prediction
    - Test `build_reference_account_index()`: single ref, multiple verbs same ref, ambiguous skipped, empty ref skipped, bank account derivation
    - Test `predict_account_from_reference()`: match found, no match, combined confidence, compound verb, uncertain flag
    - _Requirements: 1.1–1.5, 2.2–2.4, 4.1–4.5, 6.1–6.4_
    - _Estimate: 2 hours_

- [x] 3. Phase 3: Sequential Prediction Flow
  - [x] 3.0 Validation script: run prediction on historical test data
    - Write a test script that loads the CSV and account-statement files from `.kiro/specs/FIN/PatternsProcessor/Testdata/`
    - Run the prediction engine on each transaction (as if importing fresh)
    - Compare predicted ReferenceNumber and counter-account with the actual values stored in `mutaties`
    - Report: hit rate, miss rate, wrong predictions, confidence distribution
    - Use this as a baseline before and after enabling the reference lookup
    - _Requirements: 3.4_
    - _Estimate: 2 hours_

  - [x] 3.1 Modify `apply_patterns_to_transactions()` orchestration
    - File: `backend/src/pattern_analyzer.py`
    - Build reference_account_iTask 3.2 is marked completedndex at start of method from loaded patterns
    - Step 1: predict_reference (existing, unchanged)
    - Step 2: if reference predicted → try predict_account_from_reference
    - Step 3: if step 2 returned None → fall back to predict_debet/predict_credit (existing)
    - Add `_prediction_method` and `_uncertain` metadata to transaction
    - Track prediction_methods counts in results
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 7.1, 7.4, 7.5_
    - _Estimate: 2 hours_

  - [x] 3.2 Handle pre-populated ReferenceNumber
    - In the modified orchestration: when ReferenceNumber is already populated, skip step 1 and use it directly as lookup key with confidence 1.0
    - _Requirements: 2.6_
    - _Estimate: 15 min_

  - [x] 3.3 Integration test: full sequential flow
    - Load test CSV → apply patterns → verify reference predicted first, then used as lookup key for counter-account
    - Verify `_prediction_method = "reference_lookup"` when ref lookup succeeds
    - Verify `_prediction_method = "verb_matching"` when ref lookup fails and verb-matching succeeds
    - Verify `_uncertain = true` when confidence < 0.80
    - _Requirements: 2.1–2.7, 3.1–3.5, 4.4_
    - _Estimate: 2 hours_

  - [x] 3.4 Integration test: fallback behavior
    - Transaction where reference_lookup has no match → verify verb-matching produces the same result as before Phase 1
    - Transaction where no prediction methods succeed → verify field left empty
    - _Requirements: 3.1, 3.2, 3.4, 3.5_
    - _Estimate: 1 hour_

  - [x] 3.5 Regression test
    - Run existing pattern matching test suite
    - All tests must pass without modification
    - Verify prediction success rate remains ≥ 92% on known transactions
    - _Requirements: 3.4_
    - _Estimate: 30 min_

- [ ] 4. Phase 4: Frontend Indicator (Optional)
  - [x] 4.1 Add orange border for uncertain predictions
    - File: `frontend/src/components/BankingProcessor.tsx`
    - When `_uncertain = true`: show orange border instead of blue
    - When `_uncertain = false` or absent: keep existing blue border
    - _Requirements: 2.3, 2.4_
    - _Estimate: 1 hour_

- [x] 5. Phase 5: Database Index (Optional)
  - [x] 5.1 Add index on reference_number column
    - Migration: `CREATE INDEX idx_ref_lookup ON pattern_verb_patterns (administration, bank_account, reference_number)`
    - Non-breaking additive change, useful for future direct-query use
    - _Requirements: 5.5_
    - _Estimate: 15 min_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["1.4"] },
    { "id": 3, "tasks": ["2.1", "2.2", "2.3"] },
    { "id": 4, "tasks": ["2.4"] },
    { "id": 5, "tasks": ["3.0"] },
    { "id": 6, "tasks": ["3.1", "3.2"] },
    { "id": 7, "tasks": ["3.3", "3.4", "3.5"] },
    { "id": 8, "tasks": ["4.1", "5.1"] }
  ]
}
```

## Notes

- Phase 1 (data hygiene) must be completed and verified before Phase 2-3, otherwise confidence scores are unreliable
- Phase 2 tasks (2.1, 2.2, 2.3) can be developed in parallel
- Phase 3 depends on Phase 2 being complete
- Phase 4 (frontend) and Phase 5 (DB index) are independent and optional — can be done at any time after Phase 3
- Existing verb-matching tests must continue to pass throughout all phases (non-regression)
