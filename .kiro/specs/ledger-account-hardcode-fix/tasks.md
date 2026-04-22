# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — Hardcoded Account Resolution
  - **IMPORTANT**: Write this property-based test BEFORE implementing any fix
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate hardcoded account resolution exists across all affected files
  - **Scoped PBT Approach**: Use Hypothesis to generate tenant configurations with non-standard account numbers and verify the system uses authoritative sources
  - Test STR routes: call `calculate_str_channel_revenue()` with a mock tenant and assert it queries `rekeningschema` for `$.str_revenue_account` flag instead of hardcoding `'8003'`
  - Test STR VAT: call with various transaction dates and assert `TaxRateService.get_tax_rate()` is called instead of date-branching on `date(2026, 1, 1)`
  - Test transaction logic: call `get_last_transactions()` with a vendor that has 0 history and assert it returns an error dict (not Gamma fallback)
  - Test transaction logic single-result: call with a vendor that has exactly 1 transaction and assert VAT account comes from `TaxRateService` (not hardcoded `'2010'`)
  - Test transaction logic vendor overrides: assert no Coursera/Netflix-specific account overrides exist
  - Test pattern validation: call `get_patterns()` and assert the query uses `$.bank_account` flag (not `< '1300'` threshold)
  - Test aangifte IB: call `generate_table_rows()` with report data where `VW` and `Parent` prefix disagree, and assert it uses `VW = 'Y'`
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists in each code path)
  - Document counterexamples found (e.g., "STR route produces transactions with hardcoded '8003' regardless of tenant config")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Identical Results When Config Matches Old Hardcoded Values
  - **IMPORTANT**: Follow observation-first methodology
  - **Step 1 — Observe**: Run UNFIXED code with standard Dutch chart of accounts (where flags resolve to same accounts as hardcoded values) and record actual outputs
  - Observe: STR revenue calculation with account `8003` and 9%/21% rates produces specific journal entries
  - Observe: Pattern validation with bank accounts `1001`-`1004` (all below `1300`) identifies specific transactions
  - Observe: Aangifte IB with report data where `VW = 'Y'` matches Parent prefix 4-9 produces specific resultaat
  - Observe: `TaxRateService` with current seed data returns specific rates and ledger accounts
  - **Step 2 — Write property-based tests**: Use Hypothesis to generate tenant configurations where `$.str_revenue_account` resolves to `8003`, `$.bank_account` flags match accounts below 1300, and `VW = 'Y'` matches Parent prefix 4-9 — assert identical results
  - Property: for all STR inputs where tenant config resolves to `8003` and TaxRateService returns 9%/21% with matching accounts, journal entries are identical
  - Property: for all pattern validation inputs where `$.bank_account` flags identify accounts below 1300, same bank transactions are found
  - Property: for all report data where `VW = 'Y'` matches accounts with Parent starting 4-9, resultaat is identical
  - Property: seed data produces same TaxRateService results as current hardcoded values
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

- [x] 3. Dead code removal (reporting_routes.py + reporting_routes_tenant_example.py)
  - [x] 3.1 Remove `get_financial_summary()` method and route from `reporting_routes.py`
    - Remove the `get_financial_summary()` method from `ReportingService` class
    - Remove the `/financial-summary` route handler
    - Remove associated tests in `test_reporting_routes.py` that test this method/route
    - Leave all other routes and methods untouched (`/account-summary`, `/mutaties-table`, `/balance-data`, `/trends-data`, `/filter-options`, `/check-reference`, `/reference-analysis`, `/available-*`)
    - _Bug_Condition: dead code with hardcoded account ranges (4000-4999 labelled as Revenue)_
    - _Requirements: 2.1, 3.1_

  - [x] 3.2 Delete `reporting_routes_tenant_example.py`
    - Delete the entire file `backend/src/reporting_routes_tenant_example.py`
    - Verify no imports reference it (blueprint `reporting_tenant_example_bp` is never registered in `app.py`)
    - _Bug_Condition: dead code file with hardcoded account ranges_
    - _Requirements: 2.2, 3.2_

  - [x] 3.3 Write tests verifying dead code removal
    - Test that `ReportingService` no longer has `get_financial_summary()` method
    - Test that `/api/reports/financial-summary` endpoint returns 404
    - Test that `reporting_routes_tenant_example.py` file does not exist
    - Test that all other reporting routes still function (`/account-summary`, `/mutaties-table`, etc.)
    - _Requirements: 2.1, 2.2, 3.1, 3.2_

- [x] 4. Template update — add flags to `nl.json`
  - [x] 4.1 Add `parameters` flags to `nl.json` chart of accounts template
    - Set `{"bank_account": true}` on accounts 1002, 1003, 1004
    - Set `{"expense_account": true}` on all 4xxx expense accounts
    - Set `{"revenue_account": true, "btw_rate": "zero"}` on 8000 (Opbrengsten), 8081 (Ontvangen Rente), 8082 (Ontvangen Dividend)
    - Set `{"revenue_account": true, "btw_rate": "high"}` on 8001 (Omzet dienstverlening), 8002 (Omzet ICT)
    - Set `{"revenue_account": true, "str_revenue_account": true, "btw_rate": "low"}` on 8003 (Omzet verhuur)
    - Preserve existing `parameters` on 8098/8099 (merge `revenue_account` and `btw_rate` into existing JSON)
    - Preserve all existing `parameters` values (`vat_netting`, `vat_primary`, `asset_account`, `roles`, etc.)
    - _Bug_Condition: template has `"parameters": null` on most accounts_
    - _Expected_Behavior: new tenants get all required flags pre-configured_
    - _Requirements: 2.10_

  - [x] 4.2 Write tests for `nl.json` template completeness
    - Test all bank accounts (1002-1004) have `$.bank_account = true`
    - Test all expense accounts (4xxx) have `$.expense_account = true`
    - Test all revenue accounts (8xxx) have `$.revenue_account = true`
    - Test STR revenue account (8003) has `$.str_revenue_account = true`
    - Test revenue accounts have correct `$.btw_rate` values (high/low/zero)
    - Test existing `parameters` values are preserved (vat_netting, vat_primary, etc.)
    - Test no account has `"parameters": null` when it should have flags
    - _Requirements: 2.10_

- [x] 5. Migration script — backfill flags on existing tenants in dev/prod
  - [x] 5.1 Create migration script `backend/src/migrations/backfill_rekeningschema_flags.py`
    - For each existing tenant in the `tenants` table, update their `rekeningschema` accounts using MySQL `JSON_SET` to merge new flags without overwriting existing `parameters` values
    - Use the same flag-to-account mapping as `nl.json` template (task 4.1), but match by `AccountName` or account role rather than hardcoded account numbers (since existing tenants may have different numbering)
    - Matching strategy: use `VW`, `Parent`, `Belastingaangifte`, and existing `parameters` to identify account roles:
      - Bank accounts: accounts already flagged with `$.bank_account = true` (no change needed) OR accounts with `Pattern = true` and `VW = 'N'` in the 1xxx range (for tenants that don't have the flag yet)
      - Revenue accounts: accounts with `VW = 'Y'` and `Belastingaangifte = 'Opbrengsten'` or similar revenue grouping
      - Expense accounts: accounts with `VW = 'Y'` and `Parent` in expense ranges for the tenant
      - STR revenue account: account with `AccountName` matching 'Omzet verhuur' or similar
    - Use `JSON_SET(COALESCE(parameters, '{}'), '$.flag_name', value)` to safely merge into existing or null parameters
    - Script must be idempotent (safe to rerun)
    - Script must log what it changes per tenant
    - _Requirements: 2.10 (extended to existing tenants)_

  - [x] 5.2 Add `$.btw_rate` flag to revenue accounts for existing tenants
    - For revenue accounts, determine the BTW rate from `TaxRateService` or from the account's relationship to VAT accounts
    - Default mapping: accounts under 'Opbrengsten' with names containing 'verhuur' → `"low"`, other revenue → `"high"`, interest/dividend → `"zero"`
    - _Requirements: 2.8, 2.10_

  - [x] 5.3 Write tests for migration script
    - Test migration is idempotent (running twice produces same result)
    - Test existing `parameters` values are preserved (vat_netting, vat_primary, etc.)
    - Test new flags are correctly set based on account roles
    - Test migration handles tenants with different account numbering
    - _Requirements: 2.10_

  - [x] 5.4 Run migration on dev and prod databases
    - Run on dev first, verify results
    - Run on prod after dev verification
    - Verify flag-based queries return expected results for all existing tenants
    - _Requirements: 2.10_

- [x] 6. STR channel routes fix — resolve revenue account and VAT from authoritative sources
  - [x] 6.1 Replace hardcoded `'8003'` with `$.str_revenue_account` flag query
    - Import and use `rekeningschema` query with `JSON_EXTRACT(parameters, '$.str_revenue_account') = true`
    - Return 400 error with clear message when no STR revenue account is configured
    - Replace all `'8003'` references in transaction generation with resolved `str_revenue_account`
    - _Bug_Condition: hardcoded revenue account '8003'_
    - _Expected_Behavior: resolve from rekeningschema.parameters $.str_revenue_account flag_
    - _Requirements: 2.3_

  - [x] 6.2 Replace date-branching VAT logic with `TaxRateService`
    - Import `TaxRateService` from `services.tax_rate_service`
    - Replace `date(2026, 1, 1)` / 21% / 9% branching with `tax_svc.get_tax_rate(administration, 'btw', 'accommodation', transaction_date)`
    - Use `rate_info['rate']` for VAT rate and `rate_info['ledger_account']` for VAT account
    - Return 400 error with clear message when no BTW accommodation rate is configured
    - _Bug_Condition: hardcoded date-branching for VAT rate_
    - _Expected_Behavior: resolve from TaxRateService_
    - _Requirements: 2.4_

  - [x] 6.3 Write unit tests for STR channel routes fix
    - Test revenue account resolved from `$.str_revenue_account` flag (not hardcoded)
    - Test `TaxRateService.get_tax_rate()` called with correct parameters (administration, 'btw', 'accommodation', date)
    - Test 400 error returned when `$.str_revenue_account` flag not configured
    - Test 400 error returned when no BTW accommodation rate configured
    - Test journal entries use resolved accounts (not hardcoded `'8003'`, `'2020'`, `'2021'`)
    - _Requirements: 2.3, 2.4, 3.3_

- [x] 7. Transaction logic fix — remove Gamma fallback, resolve VAT from TaxRateService, remove vendor overrides
  - [x] 7.1 Remove Gamma fallback and return error for 0 results
    - Delete the `if not results:` block that queries for "Gamma%" transactions
    - Return error dict `{'error': True, 'message': 'No booking history found for vendor "...". Manual account selection required.', 'results': []}`
    - _Bug_Condition: silent fallback to Gamma transactions_
    - _Expected_Behavior: explicit error when no booking history exists_
    - _Requirements: 2.5_

  - [x] 7.2 Resolve VAT account from TaxRateService for single-result case
    - In the `if len(results) == 1:` block, replace hardcoded `'2010'` with `TaxRateService` lookup
    - Call `tax_svc.get_tax_rate(admin, 'btw', 'high', datetime.now().date())`
    - Use `rate_info['ledger_account']` for VAT account (graceful fallback to `'2010'` if TaxRateService returns None)
    - Keep the single-result VAT line creation logic (it's valid for vendors with only 1 DB record)
    - _Bug_Condition: hardcoded VAT account '2010'_
    - _Expected_Behavior: resolve from TaxRateService_
    - _Requirements: 2.5_

  - [x] 7.3 Remove Coursera/Netflix vendor-specific overrides
    - Delete the `if/elif` blocks for Coursera (`6200`/`1600`) and Netflix (`6400`/`1600`)
    - The first record's accounts from the DB are the correct template
    - Keep the >2 results Ref3 grouping logic (correct behavior)
    - _Bug_Condition: vendor-specific hardcoded account overrides_
    - _Expected_Behavior: use DB accounts as template_
    - _Requirements: 2.5_

  - [x] 7.4 Handle error result in callers (`invoice_service.py`, `pdf_processor.py`)
    - In `invoice_service.py` `process_file()`: check if `last_transactions` has `'error': True` and surface message to user
    - In `pdf_processor.py` `_format_vendor_transactions()`: check if `last_transactions` has `'error': True` and raise/return error instead of using hardcoded fallback `'4000'`/`'1300'`/`'2010'`
    - _Bug_Condition: callers silently proceed with invalid/empty templates_
    - _Expected_Behavior: callers surface error to user_
    - _Requirements: 2.5, 2.7_

  - [x] 7.5 Write unit tests for transaction logic fix
    - Test 0 results returns error dict (no Gamma fallback)
    - Test 1 result resolves VAT account from `TaxRateService` (not hardcoded `'2010'`)
    - Test no Coursera/Netflix vendor-specific overrides exist
    - Test single-transaction vendors list still works (1 result returned as-is)
    - Test >= 2 results returns normal results with Ref3 grouping
    - Test `invoice_service.py` handles error result from `get_last_transactions()`
    - Test `pdf_processor.py` handles error result from `get_last_transactions()`
    - _Requirements: 2.5, 2.7_

- [x] 8. Pattern validation fix — `$.bank_account` flag + consolidate duplicate `get_last_transactions`
  - [x] 8.1 Replace `< '1300'` threshold with `$.bank_account` flag query
    - In `get_patterns()`, replace `AND (debet < '1300' OR credit < '1300')` with subquery using `JSON_EXTRACT(parameters, '$.bank_account') = true`
    - Pass `administration` parameter to the subquery
    - _Bug_Condition: hardcoded bank account threshold < 1300_
    - _Expected_Behavior: resolve bank accounts from rekeningschema.parameters $.bank_account flag_
    - _Requirements: 2.6_

  - [x] 8.2 Remove duplicate `get_last_transactions()` from `validate_pattern/database.py`
    - Delete `get_last_transactions()` method from `validate_pattern/database.py`
    - Update callers (e.g., `pdf_processor.py`) to use `transaction_logic.py`'s version
    - This consolidation ensures the error handling from task 7.1 applies everywhere
    - _Bug_Condition: duplicate method with silent hardcoded fallback_
    - _Expected_Behavior: single source of truth in transaction_logic.py_
    - _Requirements: 2.7_

  - [x] 8.3 Write unit tests for pattern validation fix
    - Test `get_patterns()` uses `$.bank_account` flag query (not `< '1300'`)
    - Test `validate_pattern/database.py` no longer has `get_last_transactions()` method
    - Test callers use `transaction_logic.py` version
    - _Requirements: 2.6, 2.7, 3.4_

- [x] 9. Aangifte IB generator fix — use `VW` field + `$.btw_rate` flag
  - [x] 9.1 Replace `Parent.startswith()` with `VW = 'Y'` for P&L classification
    - In `generate_table_rows()`, change P&L account identification from `item.get('Parent', '').startswith(('4','5','6','7','8','9'))` to `item.get('VW', '') == 'Y'`
    - Verify `VW` is available in report data (upstream `vw_mutaties` query already includes it)
    - _Bug_Condition: Parent grouping/display field used as business logic_
    - _Expected_Behavior: use VW field (legitimate business field for P&L classification)_
    - _Requirements: 2.8_

  - [x] 9.2 Write unit tests for aangifte IB generator fix
    - Test `generate_table_rows()` uses `VW = 'Y'` (not `Parent.startswith()`)
    - Test with report data where `VW` and `Parent` prefix disagree — verify `VW` wins
    - Test resultaat calculation matches expected for standard chart of accounts
    - _Requirements: 2.8, 3.5_

- [x] 10. Seed script fix — resolve accounts from template/rekeningschema
  - [x] 10.1 Replace hardcoded accounts in `seed_system_btw_rates.py`
    - Load canonical account numbers from `nl.json` template by matching `$.vat_netting` and `$.vat_primary` flags
    - Map VAT codes (zero/low/high) to resolved accounts
    - Add fallback: if template cannot be loaded, log warning and use current hardcoded values with deprecation notice
    - _Bug_Condition: hardcoded ledger accounts '2010', '2021', '2020' in seed data_
    - _Expected_Behavior: resolve from nl.json template or rekeningschema.parameters flags_
    - _Requirements: 2.9_

  - [x] 10.2 Write unit tests for seed script fix
    - Test seed script resolves accounts from `nl.json` template
    - Test `TaxRateService` returns same rates and ledger accounts after seed
    - Test fallback behavior when template cannot be loaded
    - _Requirements: 2.9, 3.7_

- [x] 11. Verify bug condition exploration test now passes
  - [x] 11.1 Re-run bug condition exploration test
    - **Property 1: Expected Behavior** — Hardcoded Account Resolution Fixed
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (authoritative source resolution)
    - When this test passes, it confirms all hardcoded account resolution has been replaced
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed across all code paths)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 11.2 Re-run preservation property tests
    - **Property 2: Preservation** — Identical Results When Config Matches Old Hardcoded Values
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions for standard configurations)
    - Confirm all preservation tests still pass after fix
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

- [x] 12. Checkpoint — Ensure all tests pass
  - Run full test suite: `pytest backend/tests/ -v`
  - Ensure all bug condition exploration tests pass (Property 1)
  - Ensure all preservation property tests pass (Property 2)
  - Ensure all unit tests from tasks 3-10 pass
  - Ensure no regressions in existing test suite
  - Ask the user if questions arise
