# Implementation Plan

## Overview

This plan fixes the banking import bug where a tenant importing a single Rabobank CSV (`CSV_O`) covering more than one of its own bank accounts has the second (and subsequent) account's rows silently dropped as duplicates **before they are ever shown in the review grid**. The confirmed root cause is **PRIMARY** in the frontend pre-display duplicate filter and **SECONDARY** (defense-in-depth) in the backend save-path gate:

- **PRIMARY — `frontend/src/components/BankingFileUpload.tsx` → `processFiles`.** Two defects: (a) `const iban = allTransactions[0]?.Ref1` uses only the FIRST parsed row's IBAN for the whole file; (b) `allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2))` filters by `Ref2` membership alone, ignoring `Ref1`. Because Rabobank's `Volgnr` (mapped to `Ref2`) restarts per account, a second account's low `Volgnr` (1..5) collides with the first account's existing sequences and every such row is dropped BEFORE reaching `onTransactionsLoaded`, the grid, and the save step. FIX: group parsed rows by `Ref1`; for each distinct `Ref1` call `/api/banking/check-sequences` with THAT `Ref1` and only that account's `Ref2` sequences; filter each account's rows only against that account's returned duplicates; combine kept rows → `onTransactionsLoaded`; aggregate the duplicates-filtered message across accounts; keep the `{ iban, sequences, test_mode }` request shape per call.
- **SECONDARY (defense-in-depth) — `backend/src/banking_processor.py` → `save_approved_transactions`.** The authoritative gate is `SELECT ID FROM mutaties WHERE Ref2 = %s AND administration = %s LIMIT 1` (tenant-only, account-blind). It did NOT produce the reported symptom (rows were dropped pre-display and never reached it), but once the frontend fix lets multi-account rows through it could still wrongly skip them. FIX: add `Ref1` → `WHERE Ref2 = %s AND Ref1 = %s AND administration = %s LIMIT 1`, passing `transaction.get("Ref1")` as a parameterized bound value.

It follows the exploratory bugfix workflow across BOTH layers: first write bug-condition exploration tests that FAIL on the unfixed code (Task 1 frontend, Task 2 backend), then preservation tests that PASS on the unfixed code (Task 3), then apply the PRIMARY frontend fix (Task 4) and the SECONDARY backend fix (Task 5), each followed by verification sub-tasks that re-run the exploration tests (now passing) and preservation tests (still passing), and finally a checkpoint running both the frontend (vitest) and backend (pytest against `testfinance`) suites.

Frontend tests use the repo's existing vitest + React Testing Library + `@fast-check/vitest` setup (banking tests live under `frontend/src/components/banking/__tests__/*.test.tsx`), mocking `authenticatedPost('/api/banking/check-sequences', …)` so each per-account call returns only that account's existing sequences and asserting on `onTransactionsLoaded` / the status message. Backend tests run against the `testfinance` schema (`test_mode=True`) with seeded `rekeningschema` and `mutaties` fixtures reproducing the overlapping-`Volgnr` scenario (seed `NL98RABO0174003390` `Ref2 = 1..47`, import `NL60RABO1101699949` `Ref2 = 1..5` for the same tenant). No schema change is required and no production data is touched. Explicitly NOT changed: `processRabobankTransaction` (per-row account resolution and `Ref2` normalization), the account-selection popup, `banking_service.check_sequences`, `get_existing_sequences` (already `Ref1`-scoped), the zero-amount skip, the closed-period guard, and the wrong-tenant rejection.

## Tasks

- [x] 1. Write FRONTEND bug condition exploration tests
  - **Property 1: Bug Condition** - Per-Account Pre-Display Dedupe Keeps Cross-Account Rows
  - **CRITICAL**: These tests MUST FAIL on the unfixed `processFiles` - failure confirms the bug exists
  - **DO NOT attempt to fix the tests or the code when they fail** at this stage
  - **NOTE**: These tests encode the expected behavior - they will validate the PRIMARY fix (Task 4) when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug - for a two-account parse, 0 `NL60` rows reach `onTransactionsLoaded` because the single-IBAN check (`allTransactions[0]?.Ref1`) plus the `Ref2`-only filter drop the second account's cross-account `Volgnr` collisions before the review grid
  - **Scoped PBT Approach**: The reported case is deterministic, so scope the property to concrete, reproducible failing cases while still asserting the universal shape ("for all rows where `isBugCondition` holds — the row's `Ref1` differs from the first row's `Ref1`, its `Ref2` collides with that first account's existing sequences under the same tenant, but no record exists for its own `(Ref1, Ref2)` — the row survives the pre-display dedupe and reaches `onTransactionsLoaded`")
  - Create test file `frontend/src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-bug.test.tsx` using vitest + React Testing Library + `@fast-check/vitest`
  - **Mock setup**: mock `authenticatedPost('/api/banking/check-sequences', …)` so a call for `NL98RABO0174003390` returns existing sequences (e.g. `1..47` / `1..5`) and a call for `NL60RABO1101699949` returns `[]`; render `BankingFileUpload` (or drive `processFiles` directly) with a parsed two-account set and capture the `onTransactionsLoaded` argument
  - **Test case 1 - Cross-account drop**: parse `NL98` rows (treated as existing, `Ref2 = 1..5`) plus 5 new `NL60` rows (`Ref2 = 1..5`), same tenant; assert all 5 `NL60` rows reach `onTransactionsLoaded` (will FAIL on unfixed code - 0 `NL60` rows reach it because only one `check-sequences` call is made for the first row's IBAN and the `Ref2`-only filter removes them)
  - **Test case 2 - Single second-account row**: `NL98` existing `Ref2 = 1`, one new `NL60` row `Ref2 = 1`; assert it reaches `onTransactionsLoaded` (will FAIL on unfixed code - filtered out as a duplicate)
  - **Test case 3 - Out-of-order first row (edge case)**: parse where the FIRST row belongs to `NL60` and later rows to `NL98` (the account whose `Volgnr` collides is NOT first); assert both accounts' genuinely new rows reach `onTransactionsLoaded` (will FAIL on unfixed code for whichever account is not first - characterizes the `allTransactions[0]?.Ref1` single-IBAN assumption)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bug exists)
  - Document counterexamples found (`onTransactionsLoaded` receives 0 `NL60` rows; the duplicates-filtered status message reports the second account's rows as duplicates; only ONE `check-sequences` call is made, for the first row's IBAN) to confirm the root-cause hypothesis
  - Mark task complete when tests are written, run, and the failures are documented
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 2. Write BACKEND bug condition exploration test (defense-in-depth)
  - **Property 1: Bug Condition** - Account-Scoped Save-Path Gate Saves Cross-Account Rows
  - **CRITICAL**: This test MUST FAIL on the unfixed `save_approved_transactions` gate - failure confirms the secondary account-blindness exists
  - **DO NOT attempt to fix the test or the code when it fails** at this stage
  - **NOTE**: This test encodes the expected behavior - it will validate the SECONDARY fix (Task 5) when it passes after implementation
  - **GOAL**: Surface the counterexample that demonstrates the authoritative gate (`WHERE Ref2 = %s AND administration = %s`) would skip a genuinely new cross-account row once the frontend lets it through
  - **Scoped PBT Approach**: Scope to the concrete reproducible case (seed `NL98` `Ref2 = 1..5`, save `NL60` `Ref2 = 1..5`, same tenant) while asserting the universal shape ("for all rows where a matching `Ref2` exists under the same tenant for a DIFFERENT `Ref1` but NO record exists for the row's own `(administration, Ref1, Ref2)`, the row is saved as new")
  - Create test file `backend/tests/unit/test_bug_condition_account_scoped_save.py`, running against the `testfinance` schema with `test_mode=True`
  - **Fixture setup**: seed `testfinance.rekeningschema` + `testfinance.mutaties` for a tenant with an existing account `Ref1 = NL98RABO0174003390`, `Ref2 = 1..5`; seed ZERO `mutaties` rows for the second account `Ref1 = NL60RABO1101699949`
  - **Test case - Cross-account collision saved**: drive `save_approved_transactions` with 5 `NL60` rows carrying `Ref2 = 1..5`, same tenant; assert `saved_count == 5` and none skipped as "duplicate (Ref2 match)" (will FAIL on unfixed gate - 0 saved, all skipped because the account-blind gate matches `NL98`'s `Ref2`)
  - Run the test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the gate is account-blind)
  - Document the counterexample (`saved_count == 0` / "Skipping duplicate (Ref2 match)" for `NL60` rows whose only match is an `NL98` record)
  - Mark task complete when the test is written, run, and the failure is documented
  - _Requirements: 2.4_

- [x] 3. Write preservation property tests (BEFORE implementing either fix)
  - **Property 2: Preservation** - Unchanged Behavior for Non-Colliding Inputs
  - **IMPORTANT**: Follow the observation-first methodology - run the UNFIXED code on non-bug inputs (`isBugCondition` returns false), record the actual outputs, then write property-based tests asserting those observed outputs
  - **Why property-based**: preservation is a universal property ("for all non-buggy inputs, fixed == original"); generating many inputs (one vs many accounts, `Volgnr` ranges, existing-row configurations, zero amounts, closed years, wrong tenant) catches edge cases unit tests miss and gives a strong no-regression guarantee
  - **FRONTEND** - create `frontend/src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-preservation.test.tsx` (vitest + React Testing Library + `@fast-check/vitest`, mocking `authenticatedPost('/api/banking/check-sequences', …)`):
    - **Single-account import preserved**: observe that a one-account CSV makes exactly one `check-sequences` call and passes a given set of surviving rows to `onTransactionsLoaded` on unfixed code; property: for all single-account parses the fixed code produces the same surviving rows and still one call (Req 3.1)
    - **Same-account re-import still filtered**: observe that re-importing `NL98` `Ref2 = 1..47` (matching `check-sequences` duplicates for that same account) drops all rows on unfixed code; property: for all rows whose own account `Ref2` is in that account's returned duplicates, the row is still filtered after the fix (Req 3.2)
    - **`Ref2` normalization preserved**: observe `processRabobankTransaction` yields `Ref2 = parseInt(columns[3] || '0').toString()` on unfixed code; property: the fixed grouping compares on that same normalized value and the normalization is unchanged (Req 3.3)
    - **Resolution + popup preserved**: observe per-row account resolution (`Debet`/`Credit` from `lookupData.bank_accounts`) and the account-selection popup behavior on unfixed code; property: both are byte-for-byte unchanged after the fix (Req 3.4)
  - **BACKEND** - create `backend/tests/unit/test_preservation_account_scoped_save.py` (against `testfinance`, `test_mode=True`):
    - **Same-account duplicate still skipped**: observe that re-saving a row whose `(administration, Ref1, Ref2)` already exists is skipped on unfixed code; property: for all rows with a matching same-account triple the fixed gate still skips them (Req 3.2)
    - **Zero-amount lines skipped**: observe zero-amount line skipping on unfixed code; property: for all zero-amount rows the fixed pipeline continues to skip them (Req 3.5)
    - **Closed-period blocking preserved**: observe the closed-period error for closed-fiscal-year rows on unfixed code; property: for all rows targeting a closed year the fixed pipeline continues to block with the existing error (Req 3.6)
    - **Wrong-tenant rejection preserved**: observe that an IBAN owned by another tenant yields the access-denied / wrong-tenant rejection on unfixed code; property: for all cross-tenant IBANs the fixed pipeline returns the identical rejection (Req 3.7)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 4. PRIMARY FIX - Per-account grouping in frontend `processFiles`

  - [x] 4.1 Group parsed rows by `Ref1` and dedupe per account
    - In `frontend/src/components/BankingFileUpload.tsx`, in `processFiles`, replace the single-account block (`const iban = allTransactions[0]?.Ref1`; `const sequences = allTransactions.map(t => t.Ref2).filter(Boolean)`; single `check-sequences` call; `const filteredTransactions = allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2))`) with per-account grouping
    - Build groups keyed by `t.Ref1` from `allTransactions` (rows with a falsy `Ref1` pass through unchanged / as their own group)
    - For each distinct `Ref1`, collect that account's `Ref2` sequences (`.filter(Boolean)`) and call `/api/banking/check-sequences` with THAT `Ref1` and only that account's sequences
    - Filter each account's rows against ONLY that account's returned `duplicates` (`groupRows.filter(t => !groupDuplicates.includes(t.Ref2))`), so a `Ref2` that exists for a different account does not remove rows of the current account
    - Combine the kept rows across all groups and pass them to `onTransactionsLoaded`
    - Aggregate the duplicates-filtered message across accounts: sum the kept-row count and the duplicate count over all groups so `messages.duplicatesFiltered` (`new` / `duplicates`) reflects totals, falling back to `messages.transactionsLoaded` when no duplicates were found (matching today's two message paths)
    - Keep the per-call request shape `{ iban, sequences, test_mode }` and the `test_mode` flag; only the scoping (one call per account) changes
    - Leave `processRabobankTransaction` (account resolution + `Ref2` normalization), the account-selection popup, and `banking_service.check_sequences` / `get_existing_sequences` unchanged
    - _Bug_Condition: isBugCondition(input) where input.rows[i].TransactionAmount != 0 AND normalizeRef2(input.rows[i].Ref2) not empty AND input.rows[i].Ref1 != input.rows[0].Ref1 AND a mutaties record exists for (tenant, Ref1=firstRef1, Ref2=row.Ref2) AND NOT a mutaties record exists for (tenant, Ref1=row.Ref1, Ref2=row.Ref2)_
    - _Expected_Behavior: expectedBehavior(result) - processFiles groups rows by Ref1, checks each account's Ref2 against ONLY that account's existing sequences, keeps every row not a duplicate for its own account, passes it to onTransactionsLoaded (shown in the grid), and reports duplicate totals aggregated across accounts_
    - _Preservation: single-account grouping degenerates to the single-IBAN check (Req 3.1); same-account re-import still filtered (Req 3.2); Ref2 normalization, resolution + popup all unchanged (Req 3.3, 3.4)_
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 4.2 Verify FRONTEND bug condition exploration tests now pass
    - **Property 1: Expected Behavior** - Per-Account Pre-Display Dedupe Keeps Cross-Account Rows
    - **IMPORTANT**: Re-run the SAME tests from Task 1 - do NOT write new tests
    - The tests from Task 1 encode the expected behavior; when they pass they confirm the expected behavior is satisfied
    - Run `frontend/src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-bug.test.tsx`
    - **EXPECTED OUTCOME**: Tests PASS (confirms the bug is fixed - all 5 `NL60` rows reach `onTransactionsLoaded`, the single second-account row survives, the out-of-order-first-row case keeps both accounts' new rows, and one `check-sequences` call is made per distinct `Ref1`)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 4.3 Verify preservation tests still pass (frontend)
    - **Property 2: Preservation** - Unchanged Behavior for Non-Colliding Inputs
    - **IMPORTANT**: Re-run the SAME frontend tests from Task 3 - do NOT write new tests
    - Run `frontend/src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-preservation.test.tsx`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions - single-account import, same-account re-import filtering, `Ref2` normalization, and resolution/popup all unchanged)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 5. SECONDARY FIX (defense-in-depth) - Scope the backend save-path gate by `Ref1`

  - [x] 5.1 Add `Ref1` to the primary `Ref2` duplicate check in `save_approved_transactions`
    - In `backend/src/banking_processor.py`, in `save_approved_transactions`, change the authoritative gate from `SELECT ID FROM mutaties WHERE Ref2 = %s AND administration = %s LIMIT 1` to `SELECT ID FROM mutaties WHERE Ref2 = %s AND Ref1 = %s AND administration = %s LIMIT 1`
    - Pass `transaction.get("Ref1")` as the new bound parameter alongside the existing `ref2` and `administration` parameters, in the order matching the `%s` placeholders
    - Keep parameterized `%s` placeholders (no string interpolation) and keep the existing tenant (`administration`) scope intact for defense-in-depth
    - Leave the secondary text/amount/date duplicate check, the zero-amount skip, the closed-period guard, `validate_iban_tenant` (wrong-tenant rejection), `banking_service.save_transactions` / `get_existing_sequences`, and `read_rabo_csv` column mapping unchanged
    - _Bug_Condition: isBugCondition(row) where a mutaties record exists for (administration, Ref2) under a DIFFERENT Ref1 AND NOT a mutaties record exists for the row's own (administration, Ref1, Ref2)_
    - _Expected_Behavior: expectedBehavior(result) - the gate scopes to (administration, Ref1, Ref2); a row is skipped only when a matching record exists for the same tenant AND same bank account, so cross-account `Volgnr` collisions are saved as new_
    - _Preservation: same-account duplicate still skipped (Req 3.2); secondary dedupe, zero-amount skip, closed-period block, and wrong-tenant rejection all unchanged (Req 3.5, 3.6, 3.7)_
    - _Requirements: 2.4_

  - [x] 5.2 Verify BACKEND bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Account-Scoped Save-Path Gate Saves Cross-Account Rows
    - **IMPORTANT**: Re-run the SAME test from Task 2 - do NOT write a new test
    - Run `backend/tests/unit/test_bug_condition_account_scoped_save.py` against `testfinance`
    - **EXPECTED OUTCOME**: Test PASSES (confirms the gate is fixed - the 5 `NL60` rows save with `saved_count == 5` and none skipped as a `Ref2` duplicate)
    - _Requirements: 2.4_

  - [x] 5.3 Verify preservation tests still pass (backend)
    - **Property 2: Preservation** - Unchanged Behavior for Non-Colliding Inputs
    - **IMPORTANT**: Re-run the SAME backend tests from Task 3 - do NOT write new tests
    - Run `backend/tests/unit/test_preservation_account_scoped_save.py` against `testfinance`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions - same-account duplicate still skipped, zero-amount skipping, closed-period blocking, and wrong-tenant rejection all unchanged)
    - _Requirements: 3.2, 3.5, 3.6, 3.7_

- [x] 6. Checkpoint - Ensure all tests pass (both layers)
  - Run the FRONTEND suite: `cd frontend && npx vitest run src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-bug.test.tsx src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-preservation.test.tsx src/components/banking/__tests__/BankingFileUpload.preservation.test.tsx`
  - Run the BACKEND suite against `testfinance`: `cd backend && source .venv/bin/activate && pytest tests/unit/test_bug_condition_account_scoped_save.py tests/unit/test_preservation_account_scoped_save.py tests/unit/test_banking_service.py tests/unit/test_banking_processor.py -v`
  - Ensure both the bug-condition (Property 1) and preservation (Property 2) suites pass in BOTH layers, and no existing banking tests regressed
  - Ask the user if questions arise

## Task Dependency Graph

Tests are written before the fixes; the frontend (PRIMARY) and backend (SECONDARY) fixes run in order, each with its verification sub-tasks; the checkpoint runs last:

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2", "3"] },
    { "id": 1, "tasks": ["4.1"] },
    { "id": 2, "tasks": ["4.2", "4.3"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3"] },
    { "id": 5, "tasks": ["6"] }
  ]
}
```

- Wave 0: Task 1 (frontend bug exploration, must FAIL on unfixed code), Task 2 (backend bug exploration, must FAIL on unfixed code), and Task 3 (preservation tests, must PASS on unfixed code) are all written before any fix.
- Wave 1: Task 4.1 applies the PRIMARY frontend fix in `processFiles` (group by `Ref1`, per-account `check-sequences`, per-account filter, combine, aggregate message).
- Wave 2: 4.2 re-runs the Task 1 frontend tests (now expected to pass) and 4.3 re-runs the Task 3 frontend preservation tests (still expected to pass).
- Wave 3: Task 5.1 applies the SECONDARY backend fix in `save_approved_transactions` (add `Ref1` to the gate).
- Wave 4: 5.2 re-runs the Task 2 backend test (now expected to pass) and 5.3 re-runs the Task 3 backend preservation tests (still expected to pass).
- Wave 5: Task 6 (checkpoint) runs last, after both fixes and all verification sub-tasks are complete.

## Notes

- The PRIMARY fix is the frontend `processFiles` per-account grouping; the SECONDARY fix is the backend `save_approved_transactions` gate (`+ Ref1`). The backend change is defense-in-depth: it does not recover the reported symptom on its own (rows were dropped pre-display) but prevents the authoritative gate from re-dropping multi-account rows once the frontend lets them through.
- Frontend tests use vitest + React Testing Library + `@fast-check/vitest` and live under `frontend/src/components/banking/__tests__/`; mock `authenticatedPost('/api/banking/check-sequences', …)` so each per-account call returns only that account's existing sequences.
- Backend tests run against the `testfinance` schema with `test_mode=True`, using seeded `rekeningschema` + `mutaties` fixtures reproducing the overlapping-`Volgnr` scenario (seed `NL98RABO0174003390` `Ref2 = 1..47`, import `NL60RABO1101699949` `Ref2 = 1..5` same tenant); local dev config (`DB_*` in `.env`) must not be repointed and no production data is touched.
- No schema change is required - the frontend change is confined to `processFiles` and the backend change is a single query change in `save_approved_transactions`.
- Tasks 1, 2 (exploration) MUST fail on unfixed code; Task 3 (preservation) MUST pass on unfixed code. Tasks 4.2/5.2 re-run the exploration tests (now passing) and Tasks 4.3/5.3 re-run the preservation tests (still passing) - no new tests are written in the verification sub-tasks.
- Explicitly NOT changed: `processRabobankTransaction` (per-row account resolution `Ref1 = columns[0]`, `Ref2 = parseInt(columns[3] || '0').toString()`), the account-selection popup, `banking_service.check_sequences`, `get_existing_sequences` (already `Ref1`-scoped), the zero-amount skip, the closed-period guard, the wrong-tenant rejection, and `read_rabo_csv` column mapping.
