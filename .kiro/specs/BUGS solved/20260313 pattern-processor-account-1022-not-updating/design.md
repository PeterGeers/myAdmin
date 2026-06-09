# Pattern Processor Account 1022 Bugfix Design

## Overview

The pattern processor fails to update the `pattern_verb_patterns` table with new patterns for ledger account 1022 (Revolut) during the pattern re-analysis workflow. The correct workflow is:

1. User saves transactions → cache is invalidated
2. User loads new CSV → clicks "Apply Patterns"
3. Backend checks cache → MISS (because cache was invalidated in step 1)
4. Backend runs `analyze_historical_patterns()` which queries ALL transactions from last 2 years
5. `_analyze_reference_patterns()` discovers patterns from those transactions
6. `_store_verb_patterns_to_database()` UPSERTs patterns to database
7. Patterns are cached and applied to the new transactions

The bug occurs in step 5: `_analyze_reference_patterns()` skips account 1022 transactions during the re-analysis of historical data, even though account 1022 IS properly registered in the `rekeningschema` table with Pattern=1. This causes no patterns to be created or updated for account 1022, while the same workflow works correctly for account 1003 (Rabobank) and other accounts.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when `_analyze_reference_patterns()` processes historical transactions during pattern re-analysis after the user clicks "Apply Patterns"
- **Property (P)**: The desired behavior - `_analyze_reference_patterns()` should process account 1022 transactions and create/update patterns in the `pattern_verb_patterns` table
- **Preservation**: Existing pattern re-analysis workflow for account 1003 (Rabobank) and other accounts must remain unchanged
- **Pattern Re-Analysis Workflow**: User saves transactions → cache invalidated → User loads new CSV → clicks "Apply Patterns" → Backend checks cache (MISS) → Runs `analyze_historical_patterns()` → Queries ALL transactions from last 2 years → `_analyze_reference_patterns()` discovers patterns → `_store_verb_patterns_to_database()` UPSERTs to database
- **analyze_historical_patterns()**: Method in `pattern_analyzer.py` that queries last 2 years of transactions and calls `_analyze_reference_patterns()` to discover patterns
- **\_analyze_reference_patterns()**: Method that iterates through transactions, extracts verbs, identifies bank accounts, and creates pattern entries (THIS IS WHERE THE BUG OCCURS FOR ACCOUNT 1022)
- **\_store_verb_patterns_to_database()**: Method that UPSERTs discovered patterns to the `pattern_verb_patterns` table using ON DUPLICATE KEY UPDATE
- **is_bank_account()**: Method in `pattern_analyzer.py` that checks if an account number is a registered bank account by looking it up in the cached bank account dictionary
- **vw_rekeningnummers**: Database view that returns bank accounts from `rekeningschema` table where `Pattern IS NOT NULL`
- **pattern_verb_patterns**: Database table that stores discovered patterns with unique key (administration, bank_account, verb)
- **rekeningschema**: Database table containing account registrations - account 1022 IS registered here with Pattern=1

## Bug Details

### Bug Condition

The bug manifests during pattern re-analysis when the user clicks "Apply Patterns" after saving new transactions. The backend runs `analyze_historical_patterns()` which queries ALL transactions from the last 2 years, then calls `_analyze_reference_patterns()` to discover patterns. However, `_analyze_reference_patterns()` skips account 1022 transactions during this analysis, resulting in no patterns being created or updated for account 1022.

This suggests that `_analyze_reference_patterns()` either:

1. Does not recognize account 1022 as a bank account (the `is_bank_account()` method returns false)
2. Has a condition that filters out account 1022 transactions before processing
3. The transaction data for account 1022 has a different format that causes verb extraction or pattern key creation to fail
4. The query that fetches historical transactions filters by IBAN/account in a way that excludes account 1022

**Formal Specification:**

```
FUNCTION isBugCondition(patternAnalysis)
  INPUT: patternAnalysis containing historical transactions from last 2 years
  OUTPUT: boolean

  RETURN EXISTS transaction IN patternAnalysis.transactions WHERE
         (transaction.Debet == '1022' OR transaction.Credit == '1022')
         AND transaction.ReferenceNumber IS NOT NULL
         AND transaction.TransactionDescription IS NOT NULL
         AND NOT pattern_created_or_updated_in_database('1022', extracted_verb(transaction))
         AND is_bank_account('1022', transaction.administration) == TRUE
END FUNCTION
```

### Examples

**Scenario 1: Pattern Re-Analysis After Save (Bug Manifestation)**

- User imports Revolut transactions with account 1022, manually assigns ReferenceNumber="Hoogvliet", OppositeAccount=1300
- User clicks SAVE → `mutaties` table updated, cache invalidated
- User loads new CSV, clicks "Apply Patterns"
- Backend runs `analyze_historical_patterns()` → queries last 2 years of transactions (includes the saved Hoogvliet transaction)
- `_analyze_reference_patterns()` processes transactions
  - Expected: Creates pattern "PeterPrive_1022_HOOGVLIET" in `pattern_verb_patterns` table
  - Actual: Skips account 1022 transactions, no pattern created

**Scenario 2: Account 1003 Comparison (Working)**

- User imports Rabobank transactions with account 1003, manually assigns ReferenceNumber="Albert Heijn", OppositeAccount=1300
- User clicks SAVE → `mutaties` table updated, cache invalidated
- User loads new CSV, clicks "Apply Patterns"
- Backend runs `analyze_historical_patterns()` → queries last 2 years of transactions
- `_analyze_reference_patterns()` processes transactions
  - Expected: Creates pattern "PeterPrive_1003_ALBERT" in `pattern_verb_patterns` table
  - Actual: Works correctly - pattern created and stored

**Scenario 3: Existing Pattern Update (Bug Manifestation)**

- Pattern "PeterPrive_1022_TMC" exists in database with occurrences=1, last_seen=2025-01-01
- User imports new Revolut transaction with "TMC" in description, clicks SAVE
- User loads new CSV, clicks "Apply Patterns"
- Backend runs `analyze_historical_patterns()` → queries last 2 years (includes new TMC transaction)
- `_analyze_reference_patterns()` processes transactions
  - Expected: Updates pattern with occurrences=2, last_seen=2025-03-07
  - Actual: Pattern not updated (occurrences stays 1, last_seen unchanged)

**Edge Case: Mixed Accounts in Same Analysis**

- Database contains transactions for both account 1003 and 1022 from last 2 years
- User clicks "Apply Patterns"
- Backend runs `analyze_historical_patterns()` → queries ALL transactions
- `_analyze_reference_patterns()` processes transactions
  - Expected: Patterns created/updated for both accounts
  - Actual: Patterns created/updated for 1003 but not for 1022

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Pattern re-analysis for account 1003 and other accounts must continue to work exactly as before
- The SAVE operation must continue to only update `mutaties` table and invalidate cache (by design)
- The "Apply Patterns" button must continue to trigger `analyze_historical_patterns()` on cache miss
- The `is_bank_account()` method must continue to use the cached lookup from `vw_rekeningnummers`
- Pattern storage logic must continue to use ON DUPLICATE KEY UPDATE for existing patterns
- Verb extraction logic (including the previous fix for company names like "HOOGVLIET") must remain unchanged
- The query that fetches last 2 years of transactions must continue to work for all accounts

**Scope:**

All inputs that do NOT involve account 1022 should be completely unaffected by this fix. This includes:

- Pattern re-analysis workflow for account 1003 and other bank accounts
- Pattern retrieval, application, and storage for non-1022 accounts
- The bank account lookup caching mechanism
- The SAVE operation's update logic for the `mutaties` table (this works for 1022, should continue working)
- Cache invalidation logic (works correctly, should continue working)

## Hypothesized Root Cause

Based on the corrected understanding of the pattern update workflow, the most likely root causes are:

**PRIMARY HYPOTHESIS: `is_bank_account()` Method Does Not Recognize Account 1022**

The `is_bank_account()` method in `pattern_analyzer.py` checks if an account is registered by looking it up in the cached bank account dictionary. This cache is populated from the `vw_rekeningnummers` view, which queries the `rekeningschema` table.

**Possible Issues:**

1. **View Filter Issue**: The `vw_rekeningnummers` view may have additional filters beyond `Pattern IS NOT NULL` that exclude account 1022
   - Example: `WHERE Pattern IS NOT NULL AND AccountType = 'Rabobank'` (would exclude Revolut)
   - Example: `WHERE Pattern IS NOT NULL AND Account < 1020` (would exclude 1022)

2. **Cache Population Issue**: The `get_bank_accounts()` method may filter out account 1022 when building the cache
   - Check the cache key format: `f"{account['administration']}_{account['Account']}"`
   - Verify administration name matches exactly (case-sensitive)

3. **Administration Mismatch**: Account 1022 may be registered under a different administration name
   - Database: `administration = 'PeterPrive'`
   - Transaction: `administration = 'Peter Prive'` (space difference)
   - Cache lookup would fail due to key mismatch

**SECONDARY HYPOTHESIS: Transaction Data Format Difference**

Revolut CSV format may differ from Rabobank format in ways that cause processing failures:

1. **IBAN Format**: Revolut uses different IBAN format (NL08REVO...) vs Rabobank (NL27RABO...)
   - The `is_bank_account()` lookup may use IBAN instead of account number
   - Cache key mismatch if IBAN is used for lookup

2. **Description Format**: Revolut transaction descriptions may have different structure
   - Verb extraction may fail for Revolut-specific description patterns
   - Pattern key creation may fail if verb extraction returns None

3. **Account Number Format**: Account 1022 may be stored with leading zeros or different format
   - Database: `Account = '01022'`
   - Transaction: `Debet = '1022'`
   - Cache lookup would fail

**TERTIARY HYPOTHESIS: Query Filter Issue**

The query in `analyze_historical_patterns()` may filter out account 1022 transactions:

```python
query = """
    SELECT TransactionDescription, Debet, Credit, ReferenceNumber,
           TransactionDate, TransactionAmount, Ref1, administration
    FROM mutaties
    WHERE administration = %s
      AND TransactionDate >= %s
      AND (Debet IS NOT NULL OR Credit IS NOT NULL)
    ORDER BY TransactionDate DESC
"""
```

**Possible Issues:**

1. **Additional Hidden Filter**: There may be a view or trigger that filters account 1022
2. **Ref1 (IBAN) Filter**: Query may have an implicit filter on Ref1 that excludes Revolut IBANs
3. **Account Range Filter**: Query may filter by account number range (e.g., `WHERE Debet < 1020 OR Credit < 1020`)

## Correctness Properties

Property 1: Bug Condition - Pattern Discovery for Account 1022

_For any_ pattern re-analysis where `analyze_historical_patterns()` queries transactions from the last 2 years and those transactions include account 1022 (in either Debet or Credit) with non-null ReferenceNumber and TransactionDescription, the fixed `_analyze_reference_patterns()` method SHALL process those account 1022 transactions, extract verbs, create pattern keys, and store/update patterns in the `pattern_verb_patterns` table via `_store_verb_patterns_to_database()`.

**Validates: Requirements 2.1, 2.2, 2.3, 2.5**

Property 2: Preservation - Non-1022 Account Pattern Discovery

_For any_ transaction where account 1022 does NOT appear (transactions involving account 1003 or other bank accounts), the fixed system SHALL produce exactly the same pattern discovery and storage behavior as the original code, preserving all existing functionality for non-1022 transactions during the pattern re-analysis workflow.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

**CONFIRMED ROOT CAUSE**: The `_is_valid_verb()` method in `pattern_analyzer.py` had a regex pattern `^[A-Z0-9]{8,}$` that was rejecting pure alphabetic company names with 8 or more characters, including "HOOGVLIET". This affected ALL accounts, not just account 1022.

**Root Cause Details**:

The original regex `^[A-Z0-9]{8,}$` was designed to filter out transaction IDs (like "QG0DBCBZELL92QM4"), but it incorrectly rejected ANY string with 8+ uppercase letters/digits, including legitimate company names like "HOOGVLIET" (10 characters, all letters).

**Fix Applied** (already implemented in `backend/src/pattern_analyzer.py` lines 602-608):

```python
def _is_valid_verb(self, verb: str) -> bool:
    """
    Validate that a verb is a real company name, not a transaction ID

    Returns False for patterns that are clearly transaction codes
    """
    if not verb or len(verb) < 3:
        return False

    # Reject patterns that look like transaction IDs
    # FIX: Only reject long codes that have BOTH letters AND digits (transaction IDs)
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

    # ... rest of validation logic
```

**Key Change**: The first pattern now includes a condition `has_letters and has_digits`, so it only rejects strings that contain BOTH letters AND digits. Pure alphabetic company names like "HOOGVLIET" now pass through correctly.

**Impact**: This fix applies to ALL accounts, not just 1022. Any account with long company names (8+ characters) will now have patterns created correctly.

    # Try multiple key formats
    possible_keys = [
        f"{administration}_{account_number}",  # Exact match
        f"{administration}_{normalized_account}",  # Without leading zeros
        f"{administration}_{account_number.zfill(4)}",  # With leading zeros (4 digits)
    ]

    for key in possible_keys:
        if key in bank_accounts:
            return True

    return False

````

### Fix Option 4: Add Explicit Account 1022 Support

If all else fails, add explicit support as a temporary workaround:

**File**: `backend/src/pattern_analyzer.py`
**Method**: `is_bank_account()` (Line ~50)

```python
def is_bank_account(self, account_number: str, administration: str) -> bool:
    """Check if an account number is a bank account"""
    if not account_number:
        return False

    # TEMPORARY FIX: Explicitly recognize account 1022 for PeterPrive
    if account_number == '1022' and administration == 'PeterPrive':
        return True

    bank_accounts = self.get_bank_accounts()
    key = f"{administration}_{account_number}"
    return key in bank_accounts
````

**Note**: This is a workaround, not a proper fix. Use only for testing while investigating the root cause.

### Testing the Fix

After applying the appropriate fix:

1. **Verify Bank Account Recognition**:
   - Call `is_bank_account('1022', 'PeterPrive')` → should return True
   - Check cache contents to verify account 1022 is present

2. **Test Pattern Re-Analysis**:
   - Import Revolut transactions with account 1022
   - Manually assign reference numbers, click SAVE
   - Load new CSV, click "Apply Patterns"
   - Verify `analyze_historical_patterns()` is called
   - Verify `_analyze_reference_patterns()` processes account 1022 transactions
   - Check `pattern_verb_patterns` table for new/updated patterns

3. **Verify Preservation**:
   - Test same workflow with account 1003 transactions
   - Verify patterns are still created/updated correctly
   - Ensure no regression in existing functionality

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code (diagnostic phase), then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis by checking if `is_bank_account()` recognizes account 1022. If we refute, we will need to re-hypothesize.

**Test Plan**: Check the `vw_rekeningnummers` view, bank account cache, and `is_bank_account()` method to understand why account 1022 is not recognized. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:

1. **View Query Test**: Query `vw_rekeningnummers` view directly to check if account 1022 appears (will fail on unfixed code if view filters it out)
2. **Cache Contents Test**: Add logging to `get_bank_accounts()` to print all cached accounts and check if account 1022 is present (will fail on unfixed code if cache doesn't include it)
3. **is_bank_account() Test**: Call `is_bank_account('1022', 'PeterPrive')` and log the result (will return False on unfixed code)
4. **Pattern Analysis Test**: Run `analyze_historical_patterns()` with logging in `_analyze_reference_patterns()` to see if account 1022 transactions are processed (will skip account 1022 on unfixed code)
5. **Account 1003 Comparison Test**: Run same tests for account 1003 to compare behavior (will succeed - shows the difference)

**Expected Counterexamples**:

- `vw_rekeningnummers` view does not return account 1022, OR
- Bank account cache does not contain account 1022, OR
- `is_bank_account('1022', 'PeterPrive')` returns False, OR
- Administration name mismatch (e.g., 'PeterPrive' vs 'Peter Prive'), OR
- Account number format mismatch (e.g., '1022' vs '01022')
- Possible causes: view filter, cache population issue, key format mismatch, administration name mismatch

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds (pattern re-analysis with account 1022 transactions), the fixed system produces the expected behavior (patterns are discovered and stored in `pattern_verb_patterns` table).

**Pseudocode:**

```
FOR ALL patternAnalysis WHERE isBugCondition(patternAnalysis) DO
  result := analyze_historical_patterns_fixed(patternAnalysis.administration)

  // Verify is_bank_account() recognizes account 1022
  ASSERT is_bank_account('1022', patternAnalysis.administration) == TRUE

  // Verify _analyze_reference_patterns() processes account 1022 transactions
  FOR EACH transaction IN patternAnalysis.transactions WHERE involves_account_1022(transaction) DO
    IF transaction.ReferenceNumber IS NOT NULL AND transaction.TransactionDescription IS NOT NULL THEN
      verb := extracted_verb(transaction)
      pattern_key := f"{administration}_{bank_account}_{verb}"

      ASSERT pattern_exists_in_database(pattern_key)
      ASSERT pattern.reference_number == transaction.ReferenceNumber
      ASSERT pattern.debet_account == transaction.Debet
      ASSERT pattern.credit_account == transaction.Credit
    END IF
  END FOR
END FOR
```

**Test Plan**: After applying the fix to the `is_bank_account()` method or `vw_rekeningnummers` view, perform the full pattern re-analysis workflow with account 1022 transactions and verify that patterns are created and updated correctly.

**Test Cases**:

1. **New Pattern Creation**: Import account 1022 transactions → Manually assign reference numbers → SAVE → Load new CSV → Click "Apply Patterns" → Verify new patterns created in `pattern_verb_patterns`
2. **Existing Pattern Update**: Import account 1022 transactions with existing verbs → SAVE → Load new CSV → Click "Apply Patterns" → Verify existing patterns updated (occurrence count, last_seen)
3. **Mixed Verbs**: Import account 1022 transactions with both new and existing verbs → SAVE → Load new CSV → Click "Apply Patterns" → Verify both new patterns created and existing patterns updated
4. **Full Workflow**: Complete the full workflow for account 1022 and verify end-to-end behavior matches account 1003

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (transactions with account 1003 or other accounts), the fixed system produces the same result as the original system.

**Pseudocode:**

```
FOR ALL transaction WHERE NOT isBugCondition(transaction) DO
  ASSERT analyze_historical_patterns_original(transaction) = analyze_historical_patterns_fixed(transaction)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-1022 transactions

**Test Plan**: Observe behavior on UNFIXED code first for account 1003 transactions during the full pattern re-analysis workflow, then write property-based tests capturing that behavior and verify it continues after the fix.

**Test Cases**:

1. **Account 1003 Full Workflow Preservation**: Import Rabobank transactions for account 1003 → SAVE → Load new CSV → Click "Apply Patterns" → Verify patterns are created and updated exactly as before
2. **Other Bank Accounts Preservation**: Verify the full pattern re-analysis workflow for other registered bank accounts continues to work
3. **Non-Bank Account Skip Preservation**: Verify transactions where neither Debet nor Credit is a bank account are still skipped during pattern processing
4. **SAVE Operation Preservation**: Verify SAVE operation continues to only update `mutaties` table and invalidate cache (does NOT update pattern table directly - this is by design)

### Unit Tests

- Test `is_bank_account()` method with account 1022 (should return True after fix)
- Test `is_bank_account()` method with account 1003 (should continue to return True)
- Test `get_bank_accounts()` cache population (should include account 1022)
- Test `_analyze_reference_patterns()` with account 1022 transactions (should create patterns)
- Test `_analyze_reference_patterns()` with account 1003 transactions (should continue to work)
- Test pattern creation for new verbs (should create new entries)
- Test pattern updates for existing verbs (should increment occurrence count, update last_seen)

### Property-Based Tests

- Generate random pattern re-analysis operations with account 1022 transactions and verify patterns are always created/updated when ReferenceNumber is assigned
- Generate random pattern re-analysis operations with account 1003 transactions and verify behavior is unchanged (preservation property)
- Generate random pattern re-analysis operations with non-bank accounts and verify they are still skipped (preservation property)
- Test that all bank accounts in `rekeningschema` with Pattern IS NOT NULL have patterns created/updated during pattern re-analysis

### Integration Tests

- Full pattern re-analysis workflow test: Import CSV with Revolut transactions → SAVE → Load new CSV → Click "Apply Patterns" → Verify patterns in database → Import more transactions → Click "Apply Patterns" → Verify automatic assignment works
- Cross-account workflow test: Import transactions for both account 1003 and 1022 → SAVE → Load new CSV → Click "Apply Patterns" → Verify both accounts have patterns created/updated correctly
- Incremental update test: Import transactions → SAVE → Load new CSV → Click "Apply Patterns" → Import more transactions with same verbs → SAVE → Load new CSV → Click "Apply Patterns" → Verify patterns are updated with incremented occurrence counts
- End-to-end comparison test: Perform identical workflow for account 1003 and 1022, verify both produce same pattern table updates (different bank_account values but same structure)
