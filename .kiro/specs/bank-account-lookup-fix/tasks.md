# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — Inconsistent Bank Account Resolution
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists across all affected code paths
  - **Scoped PBT Approach**: Scope the property to the concrete failing cases identified in the design
  - **Backend tests** (pytest + hypothesis):
    - Test `check_banking_accounts(administration='TestTenant')` — mock `get_bank_account_lookups()` to return accounts with `$.bank_account = true`, but mock `vw_rekeningnummers` to return empty. On unfixed code, the method queries `vw_rekeningnummers` and returns no accounts (FAIL confirms bug)
    - Test `validate_iban_tenant('NL99TEST1234567890', 'TestTenant')` — mock `get_bank_account_lookups()` to return the IBAN, but mock `vw_lookup_accounts` to not contain it. On unfixed code, the method queries `vw_lookup_accounts` and returns "not found" (FAIL confirms bug)
  - **Frontend tests** (vitest + fast-check):
    - Test `processRevolutTransaction` with `bankLookup = undefined` — on unfixed code, silently uses hardcoded `'1023'` / `'PeterPrive'` instead of throwing error (FAIL confirms bug)
    - Test `processRabobankTransaction` with IBAN not in `lookupData.bank_accounts` — on unfixed code, silently uses `'1002'` / `'GoodwinSolutions'` instead of throwing error (FAIL confirms bug)
    - Test `processFiles` IBAN validation — on unfixed code, uses hardcoded `'NL08REVO7549383472'` for Revolut instead of tenant lookup (FAIL confirms bug)
  - The test assertions should match the Expected Behavior Properties from design (Properties 1, 2, 3)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists)
  - Document counterexamples found to understand root cause
  - Mark task complete when tests are written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7, 1.8_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Valid File Processing and Cross-Tenant Rejection Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Backend preservation tests** (pytest + hypothesis):
    - Observe: `check_banking_accounts(administration='TestTenant')` with valid accounts returns correct balances on unfixed code
    - Observe: `validate_iban_tenant(iban, correctTenant)` returns `valid: True` for IBANs that exist in BOTH legacy views AND `$.bank_account` flag
    - Observe: `validate_iban_tenant(iban, wrongTenant)` returns `valid: False` with access denied message
    - Write property-based test: for all valid IBANs (present in both old and new sources), `check_banking_accounts` returns identical balance data
    - Write property-based test: for all cross-tenant IBAN/tenant pairs, rejection behavior is preserved (from Preservation Requirements in design, Property 5)
  - **Frontend preservation tests** (vitest + fast-check):
    - Observe: `processRabobankTransaction` with valid IBAN in `lookupData.bank_accounts` produces correct `Account`, `administration`, `Ref1` on unfixed code
    - Observe: `processRevolutTransaction` with valid `bankLookup` produces correct `Account`, `administration`, `Ref1` on unfixed code
    - Write property-based test: for all valid bank lookups, `processRabobankTransaction` produces identical `Account`, `administration`, `Ref1` values (from Preservation Requirements, Property 4)
    - Write property-based test: for all valid bank lookups, `processRevolutTransaction` produces identical `Account`, `administration`, `Ref1` values (from Preservation Requirements, Property 4)
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.6_

- [x] 3. Fix backend: Replace legacy views with `$.bank_account` flag queries
  - [x] 3.1 Refactor `check_banking_accounts()` in `banking_processor.py` to use `DatabaseManager`
    - Replace `vw_rekeningnummers` query with `self.db.get_bank_account_lookups(administration=administration)`
    - Replace all raw `conn.cursor()` / `conn.close()` usage with `self.db.execute_query()` or `with self.db.get_cursor() as (cursor, conn):`
    - The returned rows have keys `rekeningNummer`, `Account`, `administration` — matching current usage
    - Keep `vw_mutaties` balance calculation queries and `mutaties` last-transaction queries but route them through `DatabaseManager`
    - _Bug_Condition: isBugCondition(input) where function='check_banking_accounts' AND dataSource='vw_rekeningnummers'_
    - _Expected_Behavior: queries rekeningschema with JSON_EXTRACT(parameters, '$.bank_account') = true filtered by administration_
    - _Preservation: Balance calculations from vw_mutaties must continue to return correct results_
    - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 2.5, 3.3_

  - [x] 3.2 Refactor `validate_iban_tenant()` in `banking_service.py` to use `DatabaseManager`
    - Replace `vw_lookup_accounts` query with `self.db.get_bank_account_lookups(administration=None)` to get all bank accounts, then find the IBAN's administration
    - Replace raw `conn = self.db.get_connection(); cursor = conn.cursor(dictionary=True)` with `self.db.execute_query()`
    - Maintain same return structure: `{'valid': True/False, 'tenant': ..., 'error': ...}`
    - _Bug_Condition: isBugCondition(input) where function='validate_iban_tenant' AND dataSource='vw_lookup_accounts'_
    - _Expected_Behavior: queries rekeningschema with $.bank_account flag to find IBAN's administration_
    - _Preservation: Cross-tenant rejection must continue to work identically_
    - _Requirements: 1.4, 2.4, 3.2_

  - [x] 3.3 Remove hardcoded default parameter values in `banking_processor.py`
    - `analyze_patterns_for_administration(self, administration='GoodwinSolutions', ...)` → `analyze_patterns_for_administration(self, administration, ...)`
    - `apply_enhanced_patterns(self, transactions, administration='GoodwinSolutions')` → `apply_enhanced_patterns(self, transactions, administration)`
    - `get_pattern_summary(self, administration='GoodwinSolutions')` → `get_pattern_summary(self, administration)`
    - `check_revolut_balance_gaps(self, iban='NL08REVO7549383472', account_code='1022', ...)` → `check_revolut_balance_gaps(self, iban, account_code, ...)`
    - Verify all callers already pass these arguments explicitly (banking_routes.py, banking_service.py, pattern_storage_routes.py)
    - _Bug_Condition: usesHardcodedFallback = true for tenant-specific method defaults_
    - _Requirements: 2.8, 4.7_

  - [x] 3.4 Delete dead standalone Flask app in `banking_processor.py`
    - Remove everything from `app = Flask(__name__)` through `if __name__ == '__main__': app.run(debug=True, port=5001)` (lines ~928–1086)
    - This includes duplicate route handlers: `scan_files`, `process_files`, `save_transactions`, `check_banking_accounts`, `check_sequence_numbers`, `analyze_patterns`, `get_pattern_summary`
    - Also remove the `from flask import Flask, request, jsonify` and `from flask_cors import CORS` imports if no longer needed
    - _Requirements: 4.6_

  - [x] 3.5 Verify bug condition exploration test now passes (backend)
    - **Property 1: Expected Behavior** — Backend Bank Account Resolution
    - **IMPORTANT**: Re-run the SAME backend tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected behavior for `check_banking_accounts` and `validate_iban_tenant`
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run backend bug condition exploration tests from step 1
    - **EXPECTED OUTCOME**: Tests PASS (confirms bug is fixed in backend)
    - _Requirements: 2.1, 2.4, 2.5_

  - [x] 3.6 Verify preservation tests still pass (backend)
    - **Property 2: Preservation** — Backend Preservation
    - **IMPORTANT**: Re-run the SAME backend tests from task 2 — do NOT write new tests
    - Run backend preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in backend)
    - Confirm all backend tests still pass after fix (no regressions)

- [x] 4. Fix frontend: Remove hardcoded IBANs and fallback values in `BankingProcessor.tsx`
  - [x] 4.1 Refactor `processRevolutTransaction()` to require `bankLookup`
    - Remove `const revolutIban = 'NL08REVO7549383472'`
    - Add guard at function start: if `bankLookup` is null/undefined, throw `Error('Bank account not configured for Revolut. Please add it in Chart of Accounts with the bank_account flag.')`
    - Replace all `bankLookup?.Account || '1023'` with `bankLookup.Account`
    - Replace all `bankLookup?.administration || 'PeterPrive'` with `bankLookup.administration`
    - Replace `revolutIban` usage in `Ref1` with `bankLookup.rekeningNummer`
    - _Bug_Condition: isBugCondition(input) where function='processRevolutTransaction' AND usesHardcodedFallback=true_
    - _Expected_Behavior: throws error when bankLookup is missing; uses bankLookup values when present_
    - _Requirements: 1.6, 1.8, 2.6, 2.7, 2.8, 3.6_

  - [x] 4.2 Refactor `processRabobankTransaction()` to require `bankLookup`
    - Add guard: if `bankLookup` is null/undefined (IBAN not found in `lookupData.bank_accounts`), return `null` and let the caller handle the error — or throw an error
    - Replace `bankLookup?.Account || '1002'` with `bankLookup.Account`
    - Replace `bankLookup?.administration || 'GoodwinSolutions'` with `bankLookup.administration`
    - _Bug_Condition: isBugCondition(input) where function='processRabobankTransaction' AND usesHardcodedFallback=true_
    - _Expected_Behavior: throws error when IBAN not in bank_accounts; uses lookup values when present_
    - _Requirements: 1.7, 2.7, 2.8_

  - [x] 4.3 Refactor `processFiles()` IBAN validation to use dynamic Revolut lookup
    - Remove hardcoded `iban = 'NL08REVO7549383472'` for Revolut file detection
    - Instead, find Revolut accounts from `lookupData.bank_accounts` by matching IBANs containing `'REVO'`
    - Use the tenant's Revolut IBAN for validation: `const revolutAccount = lookupData.bank_accounts.find(ba => ba.rekeningNummer.includes('REVO'))`
    - If no Revolut account found for tenant, show error: "No Revolut bank account configured for this tenant"
    - _Bug_Condition: isBugCondition(input) where function='processFiles_ibanValidation' AND usesHardcodedFallback=true_
    - _Expected_Behavior: uses tenant's Revolut IBAN from lookupData.bank_accounts_
    - _Requirements: 1.3, 1.6, 2.3, 2.6_

  - [x] 4.4 Verify bug condition exploration test now passes (frontend)
    - **Property 1: Expected Behavior** — Frontend Hardcoded Fallback Removal
    - **IMPORTANT**: Re-run the SAME frontend tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected behavior for `processRevolutTransaction`, `processRabobankTransaction`, and `processFiles`
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run frontend bug condition exploration tests from step 1
    - **EXPECTED OUTCOME**: Tests PASS (confirms bug is fixed in frontend)
    - _Requirements: 2.6, 2.7, 2.8_

  - [x] 4.5 Verify preservation tests still pass (frontend)
    - **Property 2: Preservation** — Frontend Preservation
    - **IMPORTANT**: Re-run the SAME frontend tests from task 2 — do NOT write new tests
    - Run frontend preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in frontend)
    - Confirm all frontend tests still pass after fix (no regressions)

- [x] 5. Update existing test suites to align with fix
  - [x] 5.1 Update `test_database.py` — fix test drift and compliance violations
    - Update `test_get_bank_account_lookups` to mock and assert the `rekeningschema` query with `JSON_EXTRACT(parameters, '$.bank_account') = true` instead of `vw_rekeningnummers`
    - Fix BU001 violations: replace `mysql.connector` imports and `DatabaseManager(test_mode=...)` with `mock_db` fixture from `conftest.py`
    - Fix BU003 violation: remove `sys.path.append`, rely on `conftest.py` for path setup
    - _Requirements: 4.1, 4.4, 4.5_

  - [x] 5.2 Update `test_banking_processor.py` — fix test drift for `check_banking_accounts`
    - Update mocks: mock `get_bank_account_lookups()` return value instead of `vw_rekeningnummers` cursor results
    - Add missing mock data keys: `Administration`, `ReferenceNumber`, `Ref1`–`Ref4`, `start_date`, `account_code`
    - Update `test_check_banking_accounts`, `test_check_banking_accounts_no_accounts`, `test_check_banking_accounts_with_end_date` to reflect new `DatabaseManager`-based implementation
    - Also update `test_banking_balance_closure.py` tests that mock `get_connection` for `check_banking_accounts`
    - _Requirements: 4.2_

  - [x] 5.3 Run full backend test suite and fix any remaining failures
    - Run `pytest backend/tests/unit/` to verify all unit tests pass
    - Fix any test failures caused by the removed hardcoded defaults (task 3.3) or dead code removal (task 3.4)
    - Verify callers in test files (e.g., `test_pattern_api.py`, `test_debet_credit_prediction.py`) pass `administration` explicitly
    - _Requirements: 3.4_

- [x] 6. Checkpoint — Ensure all tests pass
  - Run full backend test suite: `pytest backend/tests/unit/ -v`
  - Run full frontend test suite: `npx vitest --run`
  - Verify all bug condition exploration tests (task 1) now PASS
  - Verify all preservation property tests (task 2) still PASS
  - Verify all updated existing tests (task 5) PASS
  - Verify no hardcoded fallback values remain in modified files (grep for `'1002'`, `'1023'`, `'PeterPrive'`, `'GoodwinSolutions'`, `'NL08REVO7549383472'` in `banking_processor.py`, `banking_service.py`, `BankingProcessor.tsx`)
  - Verify dead Flask app is removed from `banking_processor.py`
  - Ensure all tests pass, ask the user if questions arise
