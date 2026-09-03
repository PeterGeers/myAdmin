# Ambiguous Bank Account Resolution — Bugfix Design

## Overview

When importing bank statement files, the system must resolve which configured bank account the file targets. The current code uses `.find()` which returns the first match — when multiple accounts match the resolution criteria, this silently picks the wrong one. The fix introduces a generic account resolution layer: resolve candidates per file type, auto-select if one, prompt the user if many, error if none.

## Glossary

- **Bug Condition (C)**: Any bank file import where the resolution strategy yields more than one candidate account
- **Property (P)**: When multiple candidates exist, the user must select the target account before processing begins
- **Preservation**: Single-candidate auto-selection, zero-candidate error handling, credit card processing, and transaction utility functions remain unchanged
- **candidates**: The set of bank accounts matching the resolution strategy for a given file type
- **resolveAccountCandidates**: A new function that encapsulates the resolution logic per file type, returning 0, 1, or N matching accounts

## Bug Details

### Bug Condition

The bug manifests when the account resolution strategy for a file type yields more than one candidate from the tenant's configured bank accounts. The `.find()` call returns the first array element, which depends on database sort order (`ORDER BY Account`) — always the lowest account number.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type BankFileImportContext
  OUTPUT: boolean
  candidates = resolveAccountCandidates(input.fileType, input.fileContent, input.tenantBankAccounts)
  RETURN |candidates| > 1
END FUNCTION
```

### Examples

- **Example 1 (Revolut)**: Tenant has accounts 1021 (NL08REVO7549383472) and 1022 (NL44REVO9988776655). User imports `account-statement_2026-07-01.csv` for account 1022. System assigns to 1021 because it sorts first.
- **Example 2 (Rabobank edge case)**: Tenant has two bank_accounts entries with the same IBAN (misconfigured). `.find(ba => ba.rekeningNummer === iban)` returns the first one.
- **Example 3 (Single account)**: Tenant has one Revolut account. System auto-selects. Correct behavior — must be preserved.
- **Example 4 (Zero accounts)**: Tenant has no Revolut accounts. System shows error. Correct behavior — must be preserved.

## Hypothesized Root Cause

1. **Non-deterministic-looking `.find()` selection**: The code uses `.find()` which always returns the first match. With DB results sorted by `ORDER BY Account`, the lowest account number wins — which may not be the intended target.

2. **Missing disambiguation step**: No branching logic for `.filter(...).length > 1` exists. The code was designed for single-account scenarios.

3. **Duplicate lookup calls**: The same resolution logic (`.find()`) appears in multiple places (validation and processing). Both must use the same resolved account.

4. **No user signal in file**: Unlike Rabobank where the IBAN is in the data, Revolut files contain no account identifier. The system cannot determine intent without asking.

## Fix Implementation

### Architecture: Generic Account Resolution Layer

Introduce a `resolveAccountCandidates` function that encapsulates the per-file-type resolution strategy:

```typescript
type BankAccount = { rekeningNummer: string; Account: string; administration: string };

type ResolutionResult =
  | { status: 'resolved'; account: BankAccount }
  | { status: 'ambiguous'; candidates: BankAccount[] }
  | { status: 'none' };

function resolveAccountCandidates(
  file: File,
  fileContent: string,
  bankAccounts: BankAccount[]
): ResolutionResult {
  const isRevolutFile = file.name.toLowerCase().endsWith('.tsv') ||
                        file.name.toLowerCase().startsWith('account-statement');
  const isCreditCard = file.name.startsWith('CSV_CC_') || file.name.startsWith('RA_CC_');

  if (isCreditCard) {
    // Credit cards use separate lookup — not in scope
    return { status: 'resolved', account: null as any }; // handled elsewhere
  }

  let candidates: BankAccount[];

  if (isRevolutFile) {
    candidates = bankAccounts.filter(ba => ba.rekeningNummer.includes('REVO'));
  } else {
    // Rabobank / other: extract IBAN from first data row, column 0
    const rows = fileContent.split('\n').filter(r => r.trim());
    const firstDataRow = rows[1]; // skip header
    const iban = firstDataRow?.split(',')[0]?.trim().replace(/"/g, '') || '';
    candidates = bankAccounts.filter(ba => ba.rekeningNummer === iban);
  }

  if (candidates.length === 0) return { status: 'none' };
  if (candidates.length === 1) return { status: 'resolved', account: candidates[0] };
  return { status: 'ambiguous', candidates };
}
```

### Changes Required

**File**: `frontend/src/components/BankingFileUpload.tsx`

1. **Add `resolveAccountCandidates` utility** (can be in BankingProcessor.utils.ts or inline)
2. **Add state** for account selection dialog:
   - `showAccountDialog: boolean`
   - `accountCandidates: BankAccount[]`
   - `pendingProcessing: { files: File[], lookupData: LookupData } | null`
3. **Refactor `processFiles`**:
   - After fetching lookupData, call `resolveAccountCandidates` for each file
   - If any file yields 'ambiguous' → show dialog, pause processing
   - After user selects → resume with selected account
   - If 'none' → show error, abort
   - If 'resolved' → proceed automatically (current behavior)
4. **Add Chakra UI Modal** for account selection:
   - Title: "Select Bank Account" (generic, not Revolut-specific)
   - Show each candidate: Account number + IBAN
   - Select → close dialog, resume processing
   - Cancel → abort, return to file selection
5. **Use resolved account consistently**:
   - Pass to validation check (replacing `.find()` at line ~131)
   - Pass to `processRevolutTransaction` (replacing `.find()` at line ~171)
   - For Rabobank: pass to `processRabobankTransaction` or validate before calling it

**File**: `frontend/src/components/BankingProcessor.utils.ts`
- No changes to `processRevolutTransaction` or `processRabobankTransaction` — they already accept a resolved account object

**Files**: `frontend/src/locales/{en,nl}/banking.json`
- Add generic translation keys (not Revolut-branded):
  - `accountSelection.title` — "Select Bank Account" / "Selecteer Bankrekening"
  - `accountSelection.description` — "Multiple bank accounts match this file. Please select which account to import into." / "Meerdere bankrekeningen komen overeen met dit bestand. Selecteer in welke rekening u wilt importeren."
  - `accountSelection.cancel` — "Cancel" / "Annuleren"
  - `accountSelection.noAccountConfigured` — "No matching bank account configured for this file type." / "Geen passende bankrekening geconfigureerd voor dit bestandstype."

### Rabobank Consideration

The Rabobank path currently does its own `.find()` inside `processRabobankTransaction`:
```typescript
const bankLookup = lookupData.bank_accounts.find(ba => ba.rekeningNummer === iban);
```
For exact IBAN matches this is almost always unique. But for the generalized fix, the resolution should happen BEFORE calling `processRabobankTransaction`. Two options:
1. Pre-resolve at BankingFileUpload level, pass the resolved account to the utility
2. Keep utility as-is, just add the ambiguity check at the BankingFileUpload level before entering the processing loop

**Decision**: Option 2 — check for ambiguity at BankingFileUpload level. If ambiguous, show dialog. If resolved, let `processRabobankTransaction` do its own `.find()` as before (since we've already confirmed it will match exactly one). This minimizes refactoring of the utility function.

## Correctness Properties

**Property 1: Bug Condition — User Selection for Multiple Candidates**

For any bank file import where `resolveAccountCandidates` returns `{ status: 'ambiguous' }`, the component MUST show a selection dialog and use the user-selected account for all processing.

_Validates: Requirements 2.2, 2.3_

**Property 2: Preservation — Single Candidate and Non-Ambiguous Processing**

For any import where the resolution yields exactly one candidate, or zero candidates, or credit card files, the behavior MUST remain identical to the current implementation.

_Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5_

## Testing Strategy

### Bug Condition Tests (must FAIL on unfixed code)
- Multiple Revolut accounts → no dialog shown (confirms bug)
- Multiple accounts matching same IBAN (Rabobank edge case) → no dialog shown (confirms bug)

### Fix Validation Tests (must PASS after fix)
- Multiple Revolut accounts → dialog shown → user picks → correct account used
- Multiple accounts matching same IBAN → dialog shown → user picks → correct account used
- Dialog cancel → no transactions processed

### Preservation Tests (must PASS on both unfixed and fixed code)
- Single Revolut account → auto-select, no dialog
- Single Rabobank IBAN match → auto-select, no dialog
- Zero Revolut accounts → error message
- Credit card files → separate lookup unchanged
- `processRevolutTransaction` output identical given same bankLookup input
