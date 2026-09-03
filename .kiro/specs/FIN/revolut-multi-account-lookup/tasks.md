# Implementation Plan

## Ambiguous Bank Account Resolution Bugfix

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — Multiple candidate accounts, no dialog shown
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - Test file: `frontend/src/components/__tests__/BankingFileUpload.account-resolution-bug.test.tsx`
  - Setup: Render `BankingFileUpload` with lookup data containing 2+ bank accounts matching the resolution criteria (e.g., 2 Revolut accounts with "REVO" in IBAN)
  - Simulate file upload (`account-statement_2026-01-01.csv`)
  - Property assertion: component MUST show an account selection dialog AND selected account MUST be used for Ref1 and Account fields
  - Use `@fast-check/vitest` to generate random sets of 2-5 matching accounts
  - Run on UNFIXED code → expected FAIL (proves bug exists)
  - _Requirements: 1.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Single candidate auto-select, zero candidate error, credit card unchanged
  - Test file: `frontend/src/components/__tests__/BankingFileUpload.account-resolution-preservation.test.tsx`
  - Observe on UNFIXED code:
    - Single matching account → auto-selects without dialog
    - Zero matching accounts → shows error message
    - Credit card file → uses credit_card_accounts lookup
  - Write property-based tests capturing observed behavior
  - Run on UNFIXED code → expected PASS (confirms baseline to preserve)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Implement the fix
  - [x] 3.1 Add `resolveAccountCandidates` function
    - Location: `frontend/src/components/BankingProcessor.utils.ts`
    - Input: file, fileContent, bankAccounts array
    - Output: `{ status: 'resolved', account }` | `{ status: 'ambiguous', candidates }` | `{ status: 'none' }`
    - Resolution logic per file type:
      - Revolut (`account-statement*` / `.tsv`): filter by `rekeningNummer.includes('REVO')`
      - Rabobank (`CSV_*` non-CC): filter by `rekeningNummer === iban_from_column_0`
      - Credit card: return early (handled elsewhere)
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.2 Add state and dialog to BankingFileUpload
    - State: `showAccountDialog`, `accountCandidates`, `pendingProcessing`
    - Chakra UI Modal with generic title "Select Bank Account" / "Selecteer Bankrekening"
    - Show each candidate: Account number + IBAN
    - Select → close dialog, resume processing with selected account
    - Cancel → abort, clear pending state
    - _Requirements: 2.2, 2.3, 2.5_

  - [x] 3.3 Refactor `processFiles` to use resolution layer
    - Call `resolveAccountCandidates` before processing loop
    - If 'ambiguous' → store pending files, show dialog, return early
    - If 'none' → show error, abort
    - If 'resolved' → proceed (same as current single-account behavior)
    - Use resolved account for BOTH validation AND `processRevolutTransaction` / `processRabobankTransaction`
    - Remove the `.find(ba => ba.rekeningNummer.includes('REVO'))` calls
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1_

  - [x] 3.4 Add resume-after-selection handler
    - `handleAccountSelected(account)`: closes dialog, resumes `processFiles` with the selected account
    - `handleAccountSelectionCancel()`: closes dialog, clears pending state, no processing
    - _Requirements: 2.3, 2.5_

  - [x] 3.5 Add translation keys
    - `frontend/src/locales/en/banking.json`:
      - `accountSelection.title` — "Select Bank Account"
      - `accountSelection.description` — "Multiple bank accounts match this file. Please select which account to import into."
      - `accountSelection.cancel` — "Cancel"
      - `accountSelection.noAccountConfigured` — "No matching bank account configured for this file type."
    - `frontend/src/locales/nl/banking.json`:
      - `accountSelection.title` — "Selecteer Bankrekening"
      - `accountSelection.description` — "Meerdere bankrekeningen komen overeen met dit bestand. Selecteer in welke rekening u wilt importeren."
      - `accountSelection.cancel` — "Annuleren"
      - `accountSelection.noAccountConfigured` — "Geen passende bankrekening geconfigureerd voor dit bestandstype."
    - _Requirements: 2.2_

  - [x] 3.6 Verify bug condition test now passes
    - Re-run test from task 1
    - Expected: PASS (dialog shown, correct account used)
    - _Requirements: 2.2, 2.3_

  - [x] 3.7 Verify preservation tests still pass
    - Re-run tests from task 2
    - Expected: PASS (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint — Full validation
  - TypeScript compilation succeeds
  - All account resolution tests pass
  - All preservation tests pass
  - Existing banking module tests still pass
  - Manual verification: upload a Revolut file with 2 configured accounts → dialog appears
