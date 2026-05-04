# Bank Account Lookup Fix — Bugfix Design

## Overview

The Banking Processor resolves bank accounts from multiple inconsistent data sources: `vw_rekeningnummers` (uses `Pattern IS NOT NULL`), `vw_lookup_accounts` (uses `AccountLookup IS NOT NULL`), and hardcoded IBANs/account codes in the frontend. The canonical source should be `rekeningschema` with `JSON_EXTRACT(parameters, '$.bank_account') = true`, which `DatabaseManager.get_bank_account_lookups()` already implements correctly. This fix unifies all bank account resolution paths to use that single source, removes all hardcoded fallback values, and enforces the `DatabaseManager` abstraction layer for all database access.

## Glossary

- **Bug_Condition (C)**: Any code path that resolves bank accounts from a source other than `rekeningschema.parameters.$.bank_account`, or uses hardcoded IBAN/account/tenant fallbacks
- **Property (P)**: All bank account resolution uses `get_bank_account_lookups()` (or equivalent `$.bank_account` query), and missing lookups produce descriptive errors instead of silent fallbacks
- **Preservation**: Existing file processing, IBAN validation, balance calculation, and pattern matching behavior must remain unchanged for inputs where the bank account lookup succeeds
- **`get_bank_account_lookups(administration)`**: The `DatabaseManager` method in `database.py` that queries `rekeningschema WHERE JSON_EXTRACT(parameters, '$.bank_account') = true`, filtered by tenant
- **`vw_rekeningnummers`**: Legacy view using `Pattern IS NOT NULL` — being replaced as a bank account source
- **`vw_lookup_accounts`**: Legacy view using `AccountLookup IS NOT NULL` — being replaced as a bank account source
- **`lookupData.bank_accounts`**: Frontend state populated from `/api/banking/lookups` endpoint, containing the tenant's bank accounts

## Bug Details

### Bug Condition

The bug manifests when any code path resolves bank accounts from a source other than `rekeningschema` with the `$.bank_account` parameter flag, or when hardcoded IBAN/account/tenant values are used instead of dynamic lookup. This creates inconsistent bank account lists across features, incorrect tenant assignment, and silent data corruption.

**Formal Specification:**

```
FUNCTION isBugCondition(codeExecution)
  INPUT: codeExecution of type { function: string, dataSource: string, usesHardcodedFallback: boolean }
  OUTPUT: boolean

  RETURN (codeExecution.function IN [
            'check_banking_accounts',
            'validate_iban_tenant',
            'processRevolutTransaction',
            'processRabobankTransaction',
            'processFiles_ibanValidation'
          ]
          AND (codeExecution.dataSource IN ['vw_rekeningnummers', 'vw_lookup_accounts']
               OR codeExecution.usesHardcodedFallback = true))
END FUNCTION
```

### Examples

- **check_banking_accounts('GoodwinSolutions')**: Queries `vw_rekeningnummers WHERE Administration = 'GoodwinSolutions'` — misses accounts that only have `$.bank_account = true` in `parameters` JSON. Expected: queries `rekeningschema WHERE JSON_EXTRACT(parameters, '$.bank_account') = true AND administration = 'GoodwinSolutions'`
- **validate_iban_tenant('NL08REVO7549383472', 'PeterPrive')**: Queries `vw_lookup_accounts WHERE rekeningNummer = %s` — may not find the IBAN if it lacks `AccountLookup`. Expected: queries `rekeningschema` with `$.bank_account` flag
- **processRevolutTransaction(columns, index, undefined, fileName)**: When `bankLookup` is undefined, uses hardcoded `Account = '1023'`, `administration = 'PeterPrive'`, `Ref1 = 'NL08REVO7549383472'`. Expected: throws error "Bank account not configured for this tenant"
- **processRabobankTransaction(columns, index, lookupData, fileName)**: When IBAN not found in `lookupData.bank_accounts`, uses `Account = '1002'`, `administration = 'GoodwinSolutions'`. Expected: throws error
- **processFiles IBAN validation**: Hardcodes `iban = 'NL08REVO7549383472'` for Revolut file detection instead of looking up Revolut accounts (IBAN containing "REVO") from `lookupData.bank_accounts`

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- File processing for valid IBANs belonging to the current tenant must continue to produce correct transactions with correct account codes and administration values
- Cross-tenant IBAN rejection must continue to block files belonging to other tenants
- Balance calculations from `vw_mutaties` must continue to return correct calculated balances, last transaction dates, and last transaction details
- `get_patterns()` bank account resolution (already using `$.bank_account`) must not regress
- Credit card file processing (`CSV_CC_*`) is explicitly out of scope and must remain unchanged
- Sequence number checking must continue to work for both numeric (Rabobank) and non-numeric (Revolut) Ref2 formats

**Scope:**
All inputs where the bank account lookup succeeds (IBAN exists in `rekeningschema` with `$.bank_account = true` for the current tenant) should produce identical results before and after the fix. Only the error path (lookup failure) changes behavior: from silent hardcoded fallback to explicit error.

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Inconsistent Data Sources**: Three different code paths use three different views/tables to resolve bank accounts:
   - `check_banking_accounts()` → `vw_rekeningnummers` (uses `Pattern IS NOT NULL`)
   - `validate_iban_tenant()` → `vw_lookup_accounts` (uses `AccountLookup IS NOT NULL`)
   - `get_bank_account_lookups()` → `rekeningschema` with `$.bank_account` flag (correct)

   The views were created before the `$.bank_account` parameter flag existed. Accounts flagged only via `$.bank_account = true` are invisible to the legacy views.

2. **Raw Cursor Usage**: `check_banking_accounts()` and `validate_iban_tenant()` use `conn.cursor()` directly instead of `DatabaseManager` methods, bypassing the abstraction layer and making it harder to maintain consistent query patterns.

3. **Hardcoded Frontend Fallbacks**: `processRevolutTransaction()`, `processRabobankTransaction()`, and `processFiles()` contain hardcoded IBANs (`NL08REVO7549383472`), account codes (`'1002'`, `'1023'`), and tenant names (`'PeterPrive'`, `'GoodwinSolutions'`) that were development-time defaults never replaced with dynamic lookup.

4. **Dead Code with Stale Patterns**: The standalone Flask app in `banking_processor.py` (lines 928–1086) duplicates route handlers with additional hardcoded values, creating confusion about which code path is active.

## Correctness Properties

Property 1: Bug Condition — Bank Account Resolution Uses $.bank_account Flag

_For any_ tenant and bank account query executed by `check_banking_accounts()` or `validate_iban_tenant()`, the query SHALL resolve bank accounts from `rekeningschema` using `JSON_EXTRACT(parameters, '$.bank_account') = true` filtered by the tenant's administration, producing the same account list as `DatabaseManager.get_bank_account_lookups(administration=tenant)`.

**Validates: Requirements 2.1, 2.2, 2.4, 2.5**

Property 2: Bug Condition — No Hardcoded Fallback Values

_For any_ input where the bank account lookup returns no result (IBAN not found in `lookupData.bank_accounts` or `get_bank_account_lookups()` returns empty for the IBAN), the system SHALL produce a descriptive error message and SHALL NOT use any hardcoded IBAN, account code, or tenant name as a fallback.

**Validates: Requirements 2.7, 2.8**

Property 3: Bug Condition — Revolut IBAN From Tenant Lookup

_For any_ Revolut file processed for a tenant that has a Revolut bank account (IBAN containing "REVO" in `lookupData.bank_accounts`), the system SHALL use that tenant's Revolut IBAN from the lookup data for `Ref1`, account code resolution, and tenant validation — not a hardcoded IBAN.

**Validates: Requirements 2.6, 3.6**

Property 4: Preservation — Valid File Processing Unchanged

_For any_ bank file (Rabobank or Revolut) where the IBAN exists in the tenant's `bank_accounts` lookup, the fixed functions SHALL produce transactions with identical `Account`, `administration`, and `Ref1` values as the original functions would produce when the lookup succeeds.

**Validates: Requirements 3.1, 3.3**

Property 5: Preservation — Cross-Tenant Rejection Unchanged

_For any_ IBAN that belongs to a different tenant than the current one, the fixed `validate_iban_tenant()` and frontend IBAN validation SHALL continue to reject the file with an access denied message, producing the same rejection behavior as the original code.

**Validates: Requirements 3.2**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/src/banking_processor.py`

**Function**: `check_banking_accounts()`

**Specific Changes**:

1. **Replace vw_rekeningnummers query with DatabaseManager call**: Replace the raw `cursor.execute("SELECT ... FROM vw_rekeningnummers ...")` with `self.db.get_bank_account_lookups(administration=administration)`. The returned rows have keys `rekeningNummer`, `Account`, `administration` — matching the current usage.
2. **Replace raw cursor with DatabaseManager for balance queries**: Use `self.db.execute_query()` for the `vw_mutaties` balance calculation and `mutaties` last-transaction queries instead of `conn.cursor()`.
3. **Remove hardcoded defaults from methods**:
   - `analyze_patterns_for_administration(administration='GoodwinSolutions')` → make `administration` required (no default)
   - `apply_enhanced_patterns(transactions, administration='GoodwinSolutions')` → make `administration` required
   - `get_pattern_summary(administration='GoodwinSolutions')` → make `administration` required
   - `check_revolut_balance_gaps(iban='NL08REVO7549383472', account_code='1022')` → make `iban` and `account_code` required
4. **Delete dead Flask app**: Remove lines 928–1086 (from `app = Flask(__name__)` through `if __name__ == '__main__': app.run(...)`)

---

**File**: `backend/src/services/banking_service.py`

**Function**: `validate_iban_tenant()`

**Specific Changes**:

1. **Replace vw_lookup_accounts query**: Replace raw cursor query against `vw_lookup_accounts` with `self.db.get_bank_account_lookups(administration=None)` (or a new targeted method) to look up the IBAN's administration from `rekeningschema` using the `$.bank_account` flag
2. **Use DatabaseManager abstraction**: Replace `conn = self.db.get_connection(); cursor = conn.cursor(dictionary=True)` with `self.db.execute_query()` or equivalent

---

**File**: `frontend/src/components/BankingProcessor.tsx`

**Function**: `processRevolutTransaction()`

**Specific Changes**:

1. **Remove hardcoded `revolutIban`**: Delete `const revolutIban = 'NL08REVO7549383472'`
2. **Require bankLookup parameter**: If `bankLookup` is null/undefined, throw an error instead of falling back to `'1023'` / `'PeterPrive'`
3. **Use bankLookup.rekeningNummer for Ref1**: Replace `revolutIban` with `bankLookup.rekeningNummer`

**Function**: `processRabobankTransaction()`

**Specific Changes**:

1. **Remove hardcoded fallbacks**: Replace `bankLookup?.Account || '1002'` with error if `bankLookup` is null
2. **Remove hardcoded administration**: Replace `bankLookup?.administration || 'GoodwinSolutions'` with error if `bankLookup` is null

**Function**: `processFiles()` (IBAN validation section)

**Specific Changes**:

1. **Remove hardcoded Revolut IBAN**: Replace `iban = 'NL08REVO7549383472'` with dynamic lookup — find Revolut accounts from `lookupData.bank_accounts` by matching IBANs containing "REVO"
2. **Use tenant's Revolut IBAN for file detection**: When processing a Revolut file, look up the tenant's Revolut IBAN from `lookupData.bank_accounts` instead of hardcoding

---

**File**: `backend/tests/test_database.py`

**Specific Changes**:

1. **Update `test_get_bank_account_lookups`**: Change mock to expect `rekeningschema` query with `JSON_EXTRACT(parameters, '$.bank_account') = true` instead of `vw_rekeningnummers`
2. **Fix BU001 violations**: Replace `mysql.connector` imports and `DatabaseManager(test_mode=...)` with `mock_db` fixture
3. **Fix BU003 violation**: Remove `sys.path.append`, rely on `conftest.py` for path setup

---

**File**: `backend/tests/test_banking_processor.py`

**Specific Changes**:

1. **Update mocks for check_banking_accounts**: Mock `get_bank_account_lookups()` return value instead of `vw_rekeningnummers` cursor results
2. **Add missing mock data keys**: Add `Administration`, `ReferenceNumber`, `Ref1`–`Ref4`, `start_date`, `account_code` to test fixtures

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call `check_banking_accounts()`, `validate_iban_tenant()`, and the frontend processing functions with accounts that have `$.bank_account = true` but no `Pattern` value. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:

1. **check_banking_accounts with $.bank_account-only account**: Create a `rekeningschema` row with `$.bank_account = true` but no `Pattern`. Call `check_banking_accounts()` — the account will be missing from results (will fail on unfixed code)
2. **validate_iban_tenant with $.bank_account-only IBAN**: Look up an IBAN that exists in `rekeningschema` with `$.bank_account = true` but not in `vw_lookup_accounts`. The validation will return "not found" (will fail on unfixed code)
3. **processRevolutTransaction with no bankLookup**: Call with `bankLookup = undefined` — will silently use `'1023'` / `'PeterPrive'` instead of erroring (will fail on unfixed code)
4. **processRabobankTransaction with unknown IBAN**: Call with an IBAN not in `lookupData.bank_accounts` — will silently use `'1002'` / `'GoodwinSolutions'` (will fail on unfixed code)

**Expected Counterexamples**:

- `check_banking_accounts()` returns empty list for tenants whose accounts only have `$.bank_account` flag
- `validate_iban_tenant()` returns "IBAN not found" for accounts only flagged via `$.bank_account`
- Frontend functions produce transactions with wrong account codes and tenant names

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedFunction(input)
  ASSERT expectedBehavior(result)
END FOR
```

Specifically:

- For `check_banking_accounts`: verify it returns accounts from `$.bank_account` flag query
- For `validate_iban_tenant`: verify it finds IBANs via `$.bank_account` flag
- For frontend functions with missing lookup: verify they throw descriptive errors
- For Revolut processing: verify tenant's IBAN is used, not hardcoded one

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for valid bank account lookups (where IBAN exists in both legacy views AND `$.bank_account` flag), then write property-based tests capturing that behavior.

**Test Cases**:

1. **Valid IBAN Processing Preservation**: For any IBAN that exists in `lookupData.bank_accounts`, verify `processRabobankTransaction` and `processRevolutTransaction` produce identical `Account`, `administration`, and `Ref1` values before and after the fix
2. **Balance Calculation Preservation**: For any tenant with bank accounts, verify `check_banking_accounts` returns identical balance calculations (the `vw_mutaties` query is unchanged — only the account list source changes)
3. **Cross-Tenant Rejection Preservation**: For any IBAN belonging to tenant A, verify `validate_iban_tenant(iban, tenantB)` still returns `valid: false` with access denied message
4. **Pattern Matching Preservation**: Verify `get_patterns()` continues to use `$.bank_account` flag (no regression)

### Unit Tests

- `test_check_banking_accounts_uses_bank_account_flag`: Verify the method calls `get_bank_account_lookups()` instead of querying `vw_rekeningnummers`
- `test_validate_iban_tenant_uses_bank_account_flag`: Verify the method queries `rekeningschema` with `$.bank_account` instead of `vw_lookup_accounts`
- `test_validate_iban_tenant_uses_database_manager`: Verify no raw `conn.cursor()` calls
- `test_processRevolutTransaction_errors_without_bankLookup`: Verify error thrown when `bankLookup` is null/undefined
- `test_processRabobankTransaction_errors_without_bankLookup`: Verify error thrown when IBAN not found
- `test_processFiles_revolut_iban_from_lookup`: Verify Revolut IBAN comes from `lookupData.bank_accounts` not hardcoded
- `test_dead_flask_app_removed`: Verify `banking_processor.py` no longer contains `app = Flask(__name__)`
- `test_no_hardcoded_defaults`: Verify `analyze_patterns_for_administration`, `apply_enhanced_patterns`, `get_pattern_summary`, `check_revolut_balance_gaps` have no default parameter values for tenant-specific arguments

### Property-Based Tests

- Generate random tenant names and bank account configurations, verify `check_banking_accounts` always uses `get_bank_account_lookups()` and returns consistent results
- Generate random IBANs and tenant combinations, verify `validate_iban_tenant` correctly identifies tenant ownership via `$.bank_account` flag
- Generate random Rabobank CSV rows with valid/invalid IBANs, verify `processRabobankTransaction` either produces correct output (valid IBAN) or throws error (invalid IBAN) — never uses hardcoded fallbacks
- Generate random Revolut transaction columns, verify `processRevolutTransaction` uses `bankLookup.rekeningNummer` for Ref1 when lookup exists, and errors when it doesn't

### Integration Tests

- End-to-end test: upload a Rabobank CSV for a tenant, verify the full flow from file upload → IBAN validation → transaction processing → account assignment uses `$.bank_account` flag throughout
- End-to-end test: upload a Revolut file for a tenant with a Revolut account, verify the tenant's Revolut IBAN is used for Ref1 and validation
- End-to-end test: attempt to upload a file with an IBAN belonging to a different tenant, verify rejection still works
- End-to-end test: Check Accounts tab loads and displays correct bank accounts for the current tenant
