# Implementation Plan

Bug: The `resolution.status === 'none'` branch of `processFiles` in
`frontend/src/components/BankingFileUpload.tsx` shows the `accountSelection.noAccountConfigured`
error and aborts, instead of opening the existing account-selection popup populated with the
tenant's known accounts (`currentLookupData.bank_accounts`).

Tooling: tests use **vitest** (`npm run test:run` in `frontend/`), **@testing-library/react** for
component rendering/interaction, and **@fast-check/vitest** / **fast-check** for property-based
tests. Colocate tests next to the component (e.g. `frontend/src/components/BankingFileUpload.test.tsx`).

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - No-match import fails to open the known-accounts popup
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug (`none` branch aborts with an error, popup never opens)
  - **Scoped PBT Approach**: The bug is deterministic given a fixed set of inputs, so scope the property to the concrete failing family: non-credit-card file(s) whose resolution yields `status: 'none'` for a tenant with a non-empty `currentLookupData.bank_accounts` list. Generate over reasonable non-empty known-account lists (varying `rekeningNummer` / `Account` / `administration`) to strengthen the guarantee.
  - Render `BankingFileUpload` with a tenant lookup whose `bank_accounts` is non-empty but contains no account matching the file (e.g. no `REVO` account), select non-CC file(s) whose `resolveAccountCandidates` returns `status: 'none'`, and trigger processing (from Bug Condition `isBugCondition` in design/requirements)
  - Assert the account-selection popup opens (`showAccountDialog` true / dialog rendered) populated with all of `currentLookupData.bank_accounts`, and that the `accountSelection.noAccountConfigured` error is NOT shown (these assertions match Property 1 / Expected Behavior in design)
  - Concrete cases to cover (from design Examples): (a) two Revolut CSVs, no REVO account; (b) single Revolut CSV, no REVO account; (c) a Rabobank/IBAN file whose IBAN matches no configured `rekeningNummer`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g. "two Revolut CSVs, tenant with 3 known accounts and no REVO → `noAccountConfigured` message shown and popup never opened"), confirming the root cause: the `resolution.status === 'none'` branch calls `setMessage(...)` and returns without `setAccountCandidates` / `setShowAccountDialog(true)`
  - Mark task complete when the test is written, run, and the failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-`none` outcomes and popup mechanics behave identically
  - **IMPORTANT**: Follow observation-first methodology - observe behavior on the UNFIXED code, then encode it
  - Observe and record baseline behavior on the UNFIXED code for the non-bug-condition cases (`isBugCondition` returns false):
    - `status: 'resolved'` (single match): no popup opens; files process directly with the auto-selected account
    - `status: 'ambiguous'` (multiple matches): popup opens with exactly the matching `resolution.candidates` (NOT the full known-accounts list); selection resumes processing with the chosen account
    - Popup cancel: `handleAccountSelectionCancel` clears `showAccountDialog`, `accountCandidates`, `pendingProcessing`, and the message; processing aborts
    - Credit-card files (`CSV_CC_*` / `RA_CC_*`): route through the separate credit-card lookup/validation path; never enter the account-selection loop
    - Single-IBAN Rabobank file matching one configured account: resolves and processes with that account
  - Write property-based tests (fast-check) capturing the observed behavior across generated resolution scenarios (from Preservation Requirements in design): generate mixes of resolved / ambiguous / credit-card inputs with varying candidate counts and assert the observable outcome (popup shown?, popup candidates, error shown?, processing path) matches the recorded baseline
  - Property-based testing generates many cases for a stronger preservation guarantee that non-`none` behavior is unchanged
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix the `none` branch to open the known-accounts popup

  - [x] 3.1 Implement the fix in `processFiles`
    - In `frontend/src/components/BankingFileUpload.tsx`, replace the abort in the `resolution.status === 'none'` branch (currently `setMessage(t('accountSelection.noAccountConfigured'))` + return) with a fallback that opens the existing account-selection popup, sourced from the tenant's full known-accounts list rather than resolution candidates
    - Read `const knownAccounts = currentLookupData.bank_accounts;`
    - If `knownAccounts.length === 0` (edge case): keep `setMessage(t('accountSelection.noAccountConfigured'))`, `setLoading(false)`, and return — do NOT open an empty popup (satisfies 2.4)
    - Otherwise mirror the `ambiguous` branch's four state updates: `setAccountCandidates(knownAccounts)`, `setPendingProcessing({ files: selectedFiles, lookupData: currentLookupData })`, `setShowAccountDialog(true)`, `setLoading(false)`, then return — reusing the existing select/cancel/resume mechanics unchanged
    - Do NOT touch the `resolved`, `ambiguous`, credit-card, or validation branches, nor `handleAccountSelected` / `handleAccountSelectionCancel`
    - (Optional, non-functional) popup copy: `accountSelection.description` reads "Multiple bank accounts match this file…"; a neutral/second string may be added and selected per opening branch, applied in both `en` and `nl` `banking.json` without altering the ambiguous-case copy — not required for correctness
    - _Bug_Condition: isBugCondition(X) where non-CC file and resolveAccountCandidates(...).status === 'none' (from design)_
    - _Expected_Behavior: for non-empty bank_accounts, open popup with currentLookupData.bank_accounts and suppress the error; for empty bank_accounts, inform the user and open no popup (Property 1 / expectedBehavior from design)_
    - _Preservation: Preservation Requirements from design — resolved auto-select, ambiguous popup, user-select resume, cancel/abort, credit-card path, single-IBAN Rabobank resolution unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - No-match import opens the known-accounts popup
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior; when it passes, it confirms the fix opens the popup with `currentLookupData.bank_accounts` (non-empty case) and informs the user with no popup (empty case)
    - Run the bug condition exploration test from task 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms the bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4 (Expected Behavior / Property 1 from design)_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-`none` outcomes and popup mechanics behave identically
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run the preservation property tests from task 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in resolved / ambiguous / credit-card / cancel / single-IBAN flows)
    - Confirm all tests still pass after the fix
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full frontend test suite (`npm run test:run` in `frontend/`) plus lint/build (`npm run lint`, `npm run build`) to confirm the fix compiles and no regressions were introduced
  - Ensure the exploration test (task 1) and preservation tests (task 2) both pass, and all other existing tests remain green
  - Ask the user if any questions arise
