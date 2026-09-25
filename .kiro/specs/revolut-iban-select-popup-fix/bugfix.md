# Bugfix Requirements Document

## Introduction

When importing bank statement files that do not match any configured bank account — for
example two Revolut CSV files (`account-statement_*.csv`) for a tenant that has no Revolut
account configured — the banking import shows the message "No matching bank account
configured for this file type." and stops. The user has no way to proceed.

Previously, when no configured account matched the file, the import offered a selectable
list of the tenant's known IBAN / bank accounts so the user could pick which account the
import should map to. That account-selection popup no longer appears for the
"no match" case. This is a regression: the "no match" outcome now dead-ends at an error
message instead of falling back to manual account selection.

The message and the terminal "none" outcome originate in the account-resolution step of
the banking upload flow: `resolveAccountCandidates` returns `status: 'none'` when no
configured account matches a file, and the upload component reacts to that status by
displaying the error and aborting rather than opening the selection popup.

## Bug Analysis

### Current Behavior (Defect)

When a non-credit-card bank file is imported and no configured account matches it (the
resolution yields zero candidates), the system reports an error and cancels the import
instead of letting the user choose an account.

1.1 WHEN a non-credit-card bank statement file is imported AND the account resolution
finds zero matching configured accounts (resolution status is `none`) THEN the system
displays the message "No matching bank account configured for this file type." and aborts
the import.

1.2 WHEN two Revolut CSV files (`account-statement_*.csv`) are imported for a tenant that
has no configured account whose account number contains `REVO` THEN the system displays
"No matching bank account configured for this file type." and does not present any account
choices.

1.3 WHEN the resolution status is `none` THEN the system does NOT open the account-selection
popup, so the user cannot map the import to any of the tenant's known IBAN / bank accounts.

### Expected Behavior (Correct)

When no configured account matches the file, the system should fall back to the
account-selection popup, listing the tenant's known IBAN / bank accounts so the user can
pick the target account and continue the import.

2.1 WHEN a non-credit-card bank statement file is imported AND the account resolution finds
zero matching configured accounts THEN the system SHALL open the account-selection popup
populated with the tenant's known bank accounts (IBAN / account) instead of aborting with
an error.

2.2 WHEN two Revolut CSV files are imported for a tenant that has no `REVO` account
configured THEN the system SHALL present the selectable list of the tenant's known IBAN /
bank accounts so the user can choose which account the import maps to.

2.3 WHEN the user selects an account from the popup presented for the "no match" case THEN
the system SHALL resume processing the selected files using the chosen account, exactly as
it already does after the user selects an account in the ambiguous (multiple-match) case.

2.4 WHEN the tenant has no configured bank accounts at all (the known-accounts list would be
empty) THEN the system SHALL still inform the user that no account is available rather than
showing an empty popup.

### Unchanged Behavior (Regression Prevention)

The fix must only change what happens for the "no matching account" outcome. All other
resolution outcomes and the existing popup mechanics must behave exactly as they do today.

3.1 WHEN the account resolution finds exactly one matching configured account (status
`resolved`) THEN the system SHALL CONTINUE TO auto-select that account and process the
files without showing any popup.

3.2 WHEN the account resolution finds multiple matching configured accounts (status
`ambiguous`) THEN the system SHALL CONTINUE TO open the account-selection popup with those
matching candidates and process using the user's selection.

3.3 WHEN the user selects an account in the popup THEN the system SHALL CONTINUE TO resume
processing with the selected account, and WHEN the user cancels the popup THEN the system
SHALL CONTINUE TO abort processing and clear the pending state.

3.4 WHEN credit card files (`CSV_CC_*` / `RA_CC_*`) are imported THEN the system SHALL
CONTINUE TO use the separate credit-card lookup and validation path unchanged.

3.5 WHEN a Rabobank / IBAN-bearing file matches a single configured account THEN the system
SHALL CONTINUE TO resolve and process it using that account as it does today.

## Bug Condition and Properties

### Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type BankFileImportContext
    // X.file           - the selected file (non-credit-card)
    // X.fileContent     - the file text
    // X.bankAccounts    - the tenant's configured bank accounts
  OUTPUT: boolean

  // Not applicable to credit card files (handled by a separate path)
  IF isCreditCardFile(X.file) THEN RETURN false

  resolution ← resolveAccountCandidates(X.file, X.fileContent, X.bankAccounts)

  // The bug is triggered when resolution finds no matching account,
  // because the flow shows an error instead of the selection popup.
  RETURN resolution.status = 'none'
END FUNCTION
```

### Property: Fix Checking

```pascal
// For every "no match" import, the fixed flow opens the account-selection
// popup with the tenant's known accounts (when any exist) instead of aborting.
FOR ALL X WHERE isBugCondition(X) DO
  behavior ← handleImport'(X)
  IF X.bankAccounts is non-empty THEN
    ASSERT popupShown(behavior) = true
    ASSERT popupCandidates(behavior) = X.bankAccounts   // all known accounts
    ASSERT errorMessageShown(behavior) = false
  ELSE
    ASSERT userInformedNoAccount(behavior) = true       // no empty popup
  END IF
END FOR
```

### Property: Preservation Checking

```pascal
// For every input that is NOT the "no match" case, the fixed flow behaves
// identically to the original flow.
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT handleImport(X) = handleImport'(X)
END FOR
```

**Key definitions**
- **F** (`handleImport`): the current import flow, where resolution status `none` shows the
  "No matching bank account configured for this file type." error and aborts.
- **F'** (`handleImport'`): the fixed import flow, where resolution status `none` opens the
  account-selection popup listing the tenant's known IBAN / bank accounts.
- **Counterexample**: importing the two example Revolut files
  (`.agent-output/account-statement_2026-08-01_2026-09-25_en-us_468cd1.csv` and
  `.agent-output/account-statement_2026-08-01_2026-09-25_en-us_4428f6.csv`) for a tenant
  with no `REVO` account shows the error and no popup.
