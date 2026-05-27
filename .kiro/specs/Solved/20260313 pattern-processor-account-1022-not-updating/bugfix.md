# Bugfix Requirements Document

## Introduction

The pattern processor fails to update the `pattern_verb_patterns` table for account 1022 (Revolut) during the pattern re-analysis workflow. The correct workflow is:

1. User saves transactions → cache is invalidated
2. User loads new CSV → clicks "Apply Patterns"
3. Backend checks cache → MISS (because cache was invalidated) → runs `analyze_historical_patterns()`
4. `_analyze_reference_patterns()` discovers patterns from ALL transactions (last 2 years)
5. `_store_verb_patterns_to_database()` UPSERTs patterns to database

**Observed Behavior**: When users import transactions for account 1022, manually assign reference numbers, save them, and then click "Apply Patterns" on a new import, the system reports "no matches found" and does not create or update patterns in the `pattern_verb_patterns` table for account 1022. The same workflow works correctly for account 1003 (Rabobank) and other accounts.

**Database Evidence**: Account 1022 IS properly registered in the `rekeningschema` table with Pattern=1, so the issue is not a missing database registration.

**Affected Component**: Pattern Analyzer (`backend/src/pattern_analyzer.py`) - somewhere in the pattern re-analysis workflow (steps 3-5 above)

**Impact**: High - The system cannot learn new patterns for account 1022 transactions, requiring users to repeatedly assign the same patterns manually instead of the system learning and auto-applying them in future imports.

**Root Cause (CONFIRMED)**: The `_is_valid_verb()` method in `pattern_analyzer.py` had a regex pattern `^[A-Z0-9]{8,}$` that was rejecting any string with 8 or more uppercase letters/digits, including pure alphabetic company names like "HOOGVLIET" (10 characters). The regex was intended to filter out transaction IDs (alphanumeric codes like "QG0DBCBZELL92QM4"), but it incorrectly rejected legitimate company names that happened to be 8+ characters long and all uppercase. The fix added a condition to only reject this pattern when the string contains BOTH letters AND digits, allowing pure alphabetic company names to pass through.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN pattern analysis runs on transactions for account 1022 (Revolut) THEN the system reports "no matches found" even when verbs like "Hoogvliet", "TMC", and "Albert Heijn" exist in the transaction descriptions

1.2 WHEN pattern analysis completes for account 1022 THEN the system does not create new entries in the `pattern_verb_patterns` table for newly discovered verbs

1.3 WHEN pattern analysis completes for account 1022 THEN the system does not update existing entries in the `pattern_verb_patterns` table with new occurrence counts or last_seen dates

1.4 WHEN old patterns exist in the `pattern_verb_patterns` table for account 1022 THEN the system updates their `updated_at` timestamp even when those patterns are not used in the current analysis

1.5 WHEN the user clicks "Apply Patterns" button after saving new transactions for account 1022 (Revolut) THEN the backend runs `analyze_historical_patterns()` which queries ALL transactions from the last 2 years, but `_analyze_reference_patterns()` skips account 1022 transactions during the re-analysis, resulting in no pattern updates in the `pattern_verb_patterns` table for account 1022

### Expected Behavior (Correct)

2.1 WHEN pattern analysis runs on transactions for account 1022 (Revolut) THEN the system SHALL identify verbs like "Hoogvliet", "TMC", and "Albert Heijn" from transaction descriptions and report matches found

2.2 WHEN pattern analysis completes for account 1022 THEN the system SHALL create new entries in the `pattern_verb_patterns` table for newly discovered verbs with the correct administration, bank_account, verb, reference_number, debet_account, and credit_account values

2.3 WHEN pattern analysis completes for account 1022 THEN the system SHALL update existing entries in the `pattern_verb_patterns` table by incrementing occurrence counts and updating last_seen dates for patterns that appear in the analyzed transactions

2.4 WHEN old patterns exist in the `pattern_verb_patterns` table for account 1022 THEN the system SHALL NOT update their `updated_at` timestamp unless those patterns are actually used or updated in the current analysis

2.5 WHEN the user clicks "Apply Patterns" button after saving new transactions for account 1022 (Revolut) THEN the backend SHALL run `analyze_historical_patterns()` which queries ALL transactions from the last 2 years, AND `_analyze_reference_patterns()` SHALL process account 1022 transactions correctly, creating new pattern entries and updating existing pattern entries (incrementing occurrence counts and updating last_seen dates) in the `pattern_verb_patterns` table

### Unchanged Behavior (Regression Prevention)

3.1 WHEN pattern analysis runs on transactions for account 1003 (Rabobank) THEN the system SHALL CONTINUE TO identify verbs, create new patterns, and update existing patterns correctly

3.2 WHEN pattern analysis runs on any account other than 1022 THEN the system SHALL CONTINUE TO store patterns in the `pattern_verb_patterns` table with the correct unique key (administration, bank_account, verb)

3.3 WHEN the `_analyze_reference_patterns` method processes transactions THEN the system SHALL CONTINUE TO use the `is_bank_account` method to identify which account is the bank account (debet or credit)

3.4 WHEN the `_store_verb_patterns_to_database` method stores patterns THEN the system SHALL CONTINUE TO use the ON DUPLICATE KEY UPDATE clause to handle existing patterns correctly

3.5 WHEN verb extraction runs on transaction descriptions THEN the system SHALL CONTINUE TO correctly extract company names like "HOOGVLIET", "TMC", and "ALBERT" as per the previous fix (20260307 1425)

3.6 WHEN the user clicks SAVE button THEN the system SHALL CONTINUE TO only update the `mutaties` table and invalidate the cache (this is by design - pattern updates happen during the NEXT "Apply Patterns" click)
