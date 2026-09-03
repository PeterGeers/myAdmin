# Bugfix Requirements Document

## Introduction

When importing bank statement files (CSV/TSV), the banking processor must determine which configured bank account the file belongs to. For some file formats the IBAN is embedded in the data (e.g., Rabobank column 0), providing a deterministic match. For other formats (e.g., Revolut) the file contains no IBAN — the system infers the account using a heuristic filter. When that filter matches multiple accounts, the system silently picks the first result from the database sort order, assigning all transactions to the wrong ledger account. The underlying principle: **whenever the account resolution strategy yields more than one candidate, the system must ask the user to choose.**

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a bank statement file is imported AND the account resolution strategy yields multiple candidate bank accounts THEN the system silently picks the first match (sorted by `ORDER BY Account`) without user input

1.2 WHEN the silently-selected account is not the user's intended target THEN all imported transactions are assigned to the wrong ledger account and wrong IBAN in Ref1

1.3 WHEN transactions carry the wrong IBAN in Ref1 THEN the duplicate sequence checker fails to find existing sequences, allowing duplicates or preventing correct deduplication

1.4 WHEN a new bank file format is added that does not embed an IBAN THEN the same ambiguity problem will occur because no disambiguation mechanism exists

### Expected Behavior (Correct)

2.1 WHEN the account resolution strategy yields exactly one candidate THEN the system SHALL automatically select that account without showing a dialog

2.2 WHEN the account resolution strategy yields multiple candidates THEN the system SHALL present a selection dialog allowing the user to choose which account to import into, before processing begins

2.3 WHEN the user selects an account from the dialog THEN the system SHALL use that account consistently for IBAN validation, Ref1 assignment, and ledger account (Debet/Credit) assignment

2.4 WHEN the account resolution strategy yields zero candidates THEN the system SHALL display an error message and abort processing

2.5 WHEN the user cancels the selection dialog THEN the system SHALL abort processing and return to the file selection state without importing any transactions

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the account resolution strategy yields exactly one candidate (regardless of file type) THEN the system SHALL CONTINUE TO auto-select without a dialog

3.2 WHEN a credit card file is imported (`CSV_CC_` or `RA_CC_` prefix) THEN the system SHALL CONTINUE TO use the credit card account lookup mechanism unchanged (separate from bank account resolution)

3.3 WHEN `processRevolutTransaction` or `processRabobankTransaction` receives a resolved bank account object THEN it SHALL CONTINUE TO process transactions identically regardless of how the account was resolved

3.4 WHEN the duplicate sequence checker receives the correct IBAN in Ref1 THEN it SHALL CONTINUE TO correctly identify and filter duplicate transactions

3.5 WHEN file type detection identifies a file format THEN the system SHALL CONTINUE TO use the same detection logic unchanged

---

## Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type BankFileImportContext
         where X.candidates = resolveAccountCandidates(X.fileType, X.fileContent, X.tenantBankAccounts)
  OUTPUT: boolean
  RETURN |X.candidates| > 1
END FUNCTION
```

**Resolution strategies per file type:**

- **Revolut** (`account-statement*` or `.tsv`): filter `bank_accounts` where `rekeningNummer.includes('REVO')`
- **Rabobank** (`CSV_*` non-CC): exact match `bank_accounts` where `rekeningNummer === iban_from_column_0`
- **Credit card** (`CSV_CC_`/`RA_CC_`): separate mechanism, out of scope

### Fix Checking Property

```pascal
// Property: When multiple candidates exist, user must choose
FOR ALL X WHERE isBugCondition(X) DO
  result ← processFileImport'(X)
  ASSERT result.userWasPrompted = true
  ASSERT result.selectedAccount ∈ X.candidates
  ASSERT result.transactions.ALL(t => t.Ref1 = result.selectedAccount.rekeningNummer)
  ASSERT result.transactions.ALL(t => t.Account = result.selectedAccount.Account)
END FOR
```

### Preservation Checking Property

```pascal
// Property: Single-candidate and zero-candidate behavior unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT processFileImport(X) = processFileImport'(X)
END FOR
```
