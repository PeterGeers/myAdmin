# Revolut IBAN Select Popup Fix — Bugfix Design

## Overview

When a non-credit-card bank statement file is imported and the account-resolution step finds
no configured account that matches it, the banking upload flow currently shows the error
message "No matching bank account configured for this file type." and aborts the import. This
is a regression: the "no match" case used to fall back to an account-selection popup so the
user could manually pick which of the tenant's known bank accounts the import should map to.

The concrete trigger is importing two Revolut CSV files (`account-statement_*.csv`) for a
tenant that has no configured account whose account number contains `REVO`. Revolut files
carry no IBAN, so `resolveAccountCandidates` matches them by looking for `REVO` in
`rekeningNummer`; with no such account, it returns `status: 'none'`, and the component
dead-ends at the error.

The fix is narrow and localized to `BankingFileUpload.tsx`: the `none` branch in `processFiles`
should stop aborting and instead open the *existing* account-selection popup — the same popup
the `ambiguous` branch already opens — populated with **all** of the tenant's known bank
accounts (`currentLookupData.bank_accounts`) rather than a subset of resolution candidates.
When the tenant has no configured accounts at all, the popup would be empty, so in that single
edge case we keep informing the user with the existing message rather than showing an empty
dialog.

All other resolution outcomes (`resolved` auto-select, `ambiguous` popup), the popup's
select/cancel mechanics, the credit-card lookup path, and single-IBAN Rabobank resolution are
left untouched.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a non-credit-card file whose
  account resolution returns `status: 'none'` (no configured account matches). Today this
  shows an error and aborts instead of offering account selection.
- **Property (P)**: The desired behavior for the bug condition — open the account-selection
  popup populated with the tenant's known bank accounts (or, if there are none, inform the
  user), rather than aborting with an error.
- **Preservation**: Every non-`none` outcome and all existing popup mechanics
  (`resolved` auto-select, `ambiguous` popup, user-select resume, cancel/abort, credit-card
  path, single-IBAN Rabobank resolution) must behave exactly as they do today.
- **`resolveAccountCandidates`**: The pure function in
  `frontend/src/components/BankingProcessor.utils.ts` that, given a file, its content, and the
  tenant's `bankAccounts`, returns a `ResolutionResult` of `{ status: 'resolved', account }`,
  `{ status: 'ambiguous', candidates }`, or `{ status: 'none' }`.
- **`processFiles`**: The `useCallback` in `frontend/src/components/BankingFileUpload.tsx` that
  drives the import: resolution → validation → transaction processing → duplicate check. This
  is the function being changed (F → F').
- **`bank_accounts` / known accounts**: `currentLookupData.bank_accounts` — the tenant's full
  list of configured bank accounts (`{ rekeningNummer, Account, administration }`). This is the
  source of the popup list for the `none` case.
- **Account-selection popup**: The Chakra `Modal` gated on `showAccountDialog`, rendering one
  button per entry in `accountCandidates`, wired to `handleAccountSelected` (resume) and
  `handleAccountSelectionCancel` (abort).

## Bug Details

### Bug Condition

The bug manifests when a non-credit-card bank file is imported and
`resolveAccountCandidates` returns `status: 'none'` — meaning zero configured accounts match
the file. In `processFiles`, the `none` branch calls
`setMessage(t('accountSelection.noAccountConfigured'))` and returns, so the
account-selection popup is never opened and the user has no way to map the import to any of
the tenant's known accounts. Credit-card files are excluded because they take a separate
lookup path.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type BankFileImportContext
    // input.file        - the selected non-credit-card file
    // input.fileContent  - the file text
    // input.bankAccounts - the tenant's configured bank accounts (currentLookupData.bank_accounts)
  OUTPUT: boolean

  // Credit card files use a separate path and are out of scope
  IF isCreditCardFile(input.file) THEN RETURN false

  resolution := resolveAccountCandidates(input.file, input.fileContent, input.bankAccounts)

  // Bug is triggered when resolution finds no matching account,
  // because the flow shows an error and aborts instead of opening the popup.
  RETURN resolution.status = 'none'
END FUNCTION
```

### Examples

- **Two Revolut CSVs, no REVO account (primary counterexample)**: importing
  `account-statement_2026-08-01_2026-09-25_en-us_468cd1.csv` and
  `..._4428f6.csv` for a tenant with no `REVO` account.
  - *Expected*: account-selection popup opens listing the tenant's known bank accounts; user
    picks one and the import continues.
  - *Actual*: "No matching bank account configured for this file type." is shown and the import
    aborts; no popup.
- **Single Revolut CSV, no REVO account**: importing one `account-statement_*.csv` for the same
  tenant.
  - *Expected*: popup with known accounts.
  - *Actual*: error shown, no popup.
- **Rabobank/IBAN file whose IBAN matches no configured account**: `rekeningNummer` never equals
  the file's IBAN, so `candidates` is empty → `status: 'none'`.
  - *Expected*: popup with known accounts.
  - *Actual*: error shown, no popup.
- **Edge case — tenant with zero configured bank accounts**: resolution is still `none`, but
  there are no accounts to list.
  - *Expected*: inform the user that no account is available (no empty popup).
  - *Actual (today)*: same "no account configured" message — this specific case is already
    acceptable and must be preserved by the fix.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- **Resolved auto-select** — a non-CC file that matches exactly one configured account
  (`status: 'resolved'`) continues to auto-select that account and process without any popup.
- **Ambiguous popup** — a non-CC file that matches multiple configured accounts
  (`status: 'ambiguous'`) continues to open the popup with exactly those matching candidates
  and process using the user's selection.
- **User-select resume** — selecting an account in the popup continues to resume processing
  with the chosen account (`handleAccountSelected` → `processFiles(account)`).
- **Cancel/abort** — cancelling or closing the popup continues to abort processing and clear
  pending state (`handleAccountSelectionCancel` clears `showAccountDialog`, `accountCandidates`,
  `pendingProcessing`, and the message).
- **Credit-card path** — `CSV_CC_*` / `RA_CC_*` files continue to use the separate credit-card
  lookup and validation path unchanged (they never enter the resolution loop for account
  selection).
- **Single-IBAN Rabobank resolution** — a Rabobank / IBAN-bearing file that matches a single
  configured account continues to resolve and process using that account.

**Scope:**
All inputs whose resolution status is NOT `'none'` (or that are credit-card files) must be
completely unaffected by this fix. This includes:
- `status: 'resolved'` files (auto-select).
- `status: 'ambiguous'` files (matching-candidates popup).
- Credit-card files (`CSV_CC_*` / `RA_CC_*`).
- Popup interactions (select and cancel) regardless of which branch opened the popup.

**Note:** The desired correct behavior for the bug condition itself is defined in the
Correctness Properties section (Property 1). This section captures only what must NOT change.

## Hypothesized Root Cause

The root cause is already well isolated by the requirements and confirmed against the source.

1. **`none` branch aborts instead of falling back to selection**: In `processFiles`
   (`BankingFileUpload.tsx`), the resolution loop handles `ambiguous` by opening the popup but
   handles `none` by showing `t('accountSelection.noAccountConfigured')` and returning. The
   `none` branch simply lacks the fallback-to-popup behavior that the "no match" case used to
   have.

2. **Popup was designed to be fed only matching candidates**: The `ambiguous` branch sets
   `accountCandidates` from `resolution.candidates`. For the `none` case there are no
   candidates, so the fix must feed the popup from a different source — the full known-accounts
   list (`currentLookupData.bank_accounts`) — rather than resolution output.

3. **Empty known-accounts list would produce an empty popup**: If the fallback naively opened
   the popup for every `none` case, a tenant with zero configured accounts would see an empty
   dialog. The fix must guard this edge case and keep informing the user instead.

4. **Popup copy is worded for the ambiguous case only**: `accountSelection.description` reads
   "Multiple bank accounts match this file…", which is inaccurate for the "no match" fallback.
   This is a wording nuance, not the functional defect; addressing it is optional (see Fix
   Implementation) and out of scope for correctness.

## Correctness Properties

Property 1: Bug Condition — No-match import opens the known-accounts popup

_For any_ non-credit-card import where the bug condition holds (`isBugCondition` returns true,
i.e. `resolveAccountCandidates` returns `status: 'none'`), the fixed `processFiles` SHALL, when
the tenant has at least one configured bank account, open the account-selection popup populated
with all of the tenant's known bank accounts (`currentLookupData.bank_accounts`) and SHALL NOT
show the "no account configured" error; and when the tenant has no configured bank accounts,
SHALL inform the user that no account is available rather than opening an empty popup.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation — Non-`none` outcomes behave identically

_For any_ input where the bug condition does NOT hold (`isBugCondition` returns false —
`resolved`, `ambiguous`, or credit-card files), the fixed `processFiles` SHALL produce the same
result as the original function, preserving auto-select for `resolved`, the matching-candidates
popup for `ambiguous`, the credit-card lookup/validation path, single-IBAN Rabobank resolution,
and the popup select/cancel mechanics.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming the root cause analysis is correct, the change is confined to the `none` branch of the
resolution loop in `processFiles`.

**File**: `frontend/src/components/BankingFileUpload.tsx`

**Function**: `processFiles` (the `none`-status branch within the account-resolution loop)

**Specific Changes**:

1. **Replace the abort with a fallback to the existing popup**: In the `resolution.status === 'none'`
   branch, instead of `setMessage(t('accountSelection.noAccountConfigured'))` + return, populate
   and open the account-selection popup exactly as the `ambiguous` branch does — but source the
   list from the tenant's full known-accounts list rather than resolution candidates:
   ```
   if (resolution.status === 'none') {
     const knownAccounts = currentLookupData.bank_accounts;
     if (knownAccounts.length === 0) {
       // Edge case: nothing to choose from — keep informing the user (2.4)
       setMessage(t('accountSelection.noAccountConfigured'));
       setLoading(false);
       return;
     }
     setAccountCandidates(knownAccounts);
     setPendingProcessing({ files: selectedFiles, lookupData: currentLookupData });
     setShowAccountDialog(true);
     setLoading(false);
     return;
   }
   ```
   This mirrors the `ambiguous` branch's four state updates (`setAccountCandidates`,
   `setPendingProcessing`, `setShowAccountDialog(true)`, `setLoading(false)`) so the downstream
   select/cancel/resume mechanics are reused with no further changes.

2. **Feed the popup from `currentLookupData.bank_accounts`**: The known-accounts list is the same
   `BankAccount[]` shape (`{ rekeningNummer, Account, administration }`) the popup already renders
   for the ambiguous case, so no rendering changes are needed. The `Account` field remains the
   React `key`.

3. **Guard the empty-accounts edge case**: When `currentLookupData.bank_accounts` is empty, do
   NOT open the popup; retain the existing `noAccountConfigured` message and abort. This satisfies
   requirement 2.4 and preserves today's behavior for tenants with no configured accounts.

4. **Do not touch the `resolved`, `ambiguous`, credit-card, or validation branches**: All other
   branches of the resolution loop, the credit-card validation loop, `handleAccountSelected`, and
   `handleAccountSelectionCancel` remain byte-for-byte unchanged, ensuring preservation.

5. **(Optional, non-functional) popup copy**: `accountSelection.description` currently reads
   "Multiple bank accounts match this file…", which is inaccurate for the no-match fallback.
   Optionally introduce a neutral/second description string (e.g.
   `accountSelection.descriptionNoMatch`) selected based on which branch opened the popup. This is
   a wording improvement only and is not required for correctness; if done, it must be applied in
   both `en` and `nl` `banking.json` locale files and must not alter the ambiguous-case copy.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that
demonstrate the bug on the unfixed code (the `none` case aborting with an error and no popup),
then verify the fix opens the known-accounts popup for the `none` case while leaving every other
outcome unchanged.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm
or refute the root cause (the `none` branch aborts instead of opening the popup). If refuted,
re-hypothesize.

**Test Plan**: Render `BankingFileUpload` (or drive `processFiles`) with a tenant lookup that has
known bank accounts but none matching the file, select non-CC file(s) whose resolution yields
`status: 'none'`, trigger processing, and assert whether the popup opens. Run against the UNFIXED
code to observe the failure (error shown, popup absent).

**Test Cases**:
1. **Two Revolut CSVs, no REVO account** — select two `account-statement_*.csv` files for a tenant
   with known accounts but no `REVO` account; assert the popup opens with the known accounts (will
   fail on unfixed code — error shown, no popup).
2. **Single Revolut CSV, no REVO account** — same as above with one file (will fail on unfixed
   code).
3. **Rabobank/IBAN file matching no account** — a `.csv` whose column-0 IBAN matches no configured
   `rekeningNummer`; assert popup opens with known accounts (will fail on unfixed code).
4. **Edge case — no configured accounts** — tenant with empty `bank_accounts`; assert the user is
   informed (message shown) and no popup opens (may pass on unfixed code, since the message is
   already shown — this pins the preserved edge-case behavior).

**Expected Counterexamples**:
- For cases 1–3 on unfixed code: `accountSelection.noAccountConfigured` message is shown and the
  account-selection popup is never opened.
- Confirmed cause: the `resolution.status === 'none'` branch calls `setMessage(...)` and returns
  without setting `accountCandidates` / opening the dialog.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces
the expected behavior (popup with known accounts, or informed-no-account when the list is empty).

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  behavior := processFiles_fixed(input)
  IF input.bankAccounts is non-empty THEN
    ASSERT popupShown(behavior) = true
    ASSERT popupCandidates(behavior) = input.bankAccounts   // all known accounts
    ASSERT errorMessageShown(behavior) = false
  ELSE
    ASSERT userInformedNoAccount(behavior) = true           // no empty popup
    ASSERT popupShown(behavior) = false
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function
produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT processFiles_original(input) = processFiles_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many resolution scenarios automatically across the input domain.
- It catches edge cases that hand-written unit tests might miss (e.g. resolved vs ambiguous with
  varying candidate counts, mixed CC/non-CC batches).
- It provides strong guarantees that non-`none` behavior is unchanged.

**Test Plan**: Observe behavior on the UNFIXED code for `resolved`, `ambiguous`, credit-card, and
cancel flows, then write tests capturing that behavior and confirm it is identical after the fix.

**Test Cases**:
1. **Resolved auto-select preservation** — file matches exactly one account; observe no popup and
   direct processing on unfixed code; verify unchanged after fix.
2. **Ambiguous popup preservation** — file matches multiple accounts; observe popup opens with
   exactly those candidates on unfixed code; verify unchanged after fix (candidates are the
   matches, not the full known-accounts list).
3. **Cancel/abort preservation** — open the popup and cancel; observe pending state cleared and
   processing aborted; verify unchanged after fix for both the ambiguous- and none-opened popup.
4. **Credit-card path preservation** — `CSV_CC_*` / `RA_CC_*` files use the separate lookup and
   validation; verify unchanged after fix.

### Unit Tests

- The `none` branch opens the popup with `currentLookupData.bank_accounts` when the list is
  non-empty, and does NOT show the error.
- The `none` branch with an empty `bank_accounts` list shows `noAccountConfigured` and does not
  open the popup.
- Selecting an account from the popup opened by the `none` case resumes processing via
  `processFiles(account)` (reuses `handleAccountSelected`).
- The `ambiguous` branch still opens the popup with the matching candidates only.
- The `resolved` branch still auto-selects and processes without a popup.
- Credit-card files still route through the credit-card lookup/validation path.

### Property-Based Tests

- Generate tenants with random non-empty known-account lists and files that resolve to `none`;
  assert the popup candidates equal the full known-accounts list and no error is shown.
- Generate the empty-accounts case; assert the user is informed and no popup opens.
- Generate random `resolved` / `ambiguous` / credit-card scenarios and assert the observable
  behavior is identical between the original and fixed flows (preservation).

### Integration Tests

- Full import flow: import two Revolut CSVs for a tenant with no `REVO` account → popup lists the
  tenant's known accounts → select one → transactions load using the selected account.
- Context/batch flow: mixed batch (Revolut + Rabobank + credit-card) where the first non-CC file
  is `none`; verify the popup opens and, after selection, the batch processes with the chosen
  account.
- Cancel flow: open the `none`-case popup, cancel, and verify the import is aborted and state
  cleared.
