# Bugfix Requirements Document

## Introduction

When a tenant imports a single Rabobank CSV (CSV_O) file that contains transactions for
two or more of the tenant's own bank accounts, rows belonging to the second (and
subsequent) account are silently dropped **before they are ever shown in the review
grid**: the import reports them as duplicates / "already loaded", nothing for that
account reaches the save step, and 0 rows are saved for that account — even though no
transactions for that account have ever been imported.

This was reported by a tenant importing a Rabobank CSV that covers both of the tenant's
accounts:

- Account 1002 "Lopende rekening" — IBAN `NL98RABO0174003390` — imports correctly
  (47 rows already present in `mutaties`, `Volgnr` 1..47).
- Account 1003 "Spaar rekening" — IBAN `NL60RABO1101699949` — fails; 0 rows in
  `mutaties`. The 5 rows for this account (`Volgnr` 1..5) are all silently filtered out
  as duplicates and never reach the grid or the save step. The account-selection popup
  correctly resolves to 1003, yet the 5 rows are not processed and nothing is saved.

Two earlier hypotheses have been investigated against the production `finance` database
and the actual CSV and **disproven**:

- **IBAN-to-general-ledger-account resolution** is NOT the defect. Both accounts are
  correctly mapped for the tenant, per-row account resolution works
  (`processRabobankTransaction` resolves `Debet`/`Credit` per row from
  `lookupData.bank_accounts`), and the account-selection popup is confirmation only.
  IBAN resolution and the popup SHALL NOT be modified.
- **The backend `save_approved_transactions` duplicate check** is NOT the primary site.
  The dropped rows never reach the save step at all, so a backend-only fix cannot
  recover them.

### Confirmed root cause (primary): the frontend pre-display duplicate filter

The duplicate comparison happens in the FRONTEND, BEFORE the rows are shown in the review
grid (confirmed: "the records will not be loaded if they are equal so the comparison is
before the data is shown"). The flow in `frontend/src/components/BankingFileUpload.tsx`
→ `processFiles` is:

1. Each CSV row is parsed by `processRabobankTransaction` (in
   `frontend/src/components/BankingProcessor.utils.ts`), which sets:
   - `Ref1 = columns[0]` — the IBAN of THAT row,
   - `Ref2 = parseInt(columns[3] || '0').toString()` — the `Volgnr`, normalized to a
     plain integer (e.g. `"000000000000000001"` → `"1"`). This normalization is
     deliberate and consistent with how `mutaties` stores `Ref2`.
   - `Debet`/`Credit` resolved per row from `lookupData.bank_accounts` (per-account and
     correct).
2. `processFiles` then performs a SINGLE-ACCOUNT duplicate check:
   ```ts
   const iban = allTransactions[0]?.Ref1;                               // FIRST row's IBAN only
   const sequences = allTransactions.map(t => t.Ref2).filter(Boolean);  // ALL rows' Ref2, across all accounts
   // POST /api/banking/check-sequences { iban, sequences }
   ```
   Backend `banking_service.check_sequences(iban, sequences, tenant)` calls
   `get_existing_sequences(iban, administration=tenant)` — correctly scoped to that ONE
   `iban` — and returns `duplicates = [seq for seq in sequences if seq in existing_sequences]`.
3. The frontend then filters by `Ref2` membership alone, with NO per-account (`Ref1`)
   check:
   ```ts
   const filteredTransactions = allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2));
   ```

For a multi-account CSV, `iban` is taken from the first row only (e.g.
`NL98RABO0174003390`). The existing-sequence set returned is account NL98's stored
`Volgnr` (1..47). The second account `NL60RABO1101699949`'s rows carry `Volgnr` 1..5,
all members of the NL98 set, so they are flagged as duplicates and filtered out before
display. The 5 NL60 rows never reach the grid or the save step.

There are two defects in `processFiles`:

- **(a)** It assumes a single IBAN per file (`allTransactions[0]?.Ref1`).
- **(b)** It filters duplicates by `Ref2` membership alone, ignoring `Ref1`, so a `Ref2`
  that exists for a DIFFERENT account removes rows of the current account.

### Confirmed secondary site (defense-in-depth): the backend save-path gate

The authoritative duplicate gate in `backend/src/banking_processor.py` →
`save_approved_transactions` matches on `Ref2` scoped only by tenant, missing `Ref1`:

```sql
SELECT ID FROM mutaties WHERE Ref2 = %s AND administration = %s LIMIT 1
```

Because the frontend currently drops the affected rows pre-display, this gate is not what
produced the reported symptom. However, it carries the same account-blindness: once the
primary frontend fix lets multi-account rows through, this gate could still wrongly skip
them. It SHOULD also be scoped by `Ref1` so correctness does not depend solely on the
frontend. This is a secondary, belt-and-suspenders layer; the PRIMARY fix is the frontend
per-account grouping.

## Bug Analysis

### Current Behavior (Defect)

What currently happens when a tenant imports a Rabobank CSV containing transactions for
more than one of the tenant's bank accounts:

1.1 WHEN a tenant imports a single Rabobank CSV containing more than one bank account THEN
the frontend `processFiles` duplicate check derives the IBAN from the FIRST parsed row
only (`allTransactions[0]?.Ref1`) and checks ALL rows' `Ref2` sequences against that one
account's existing sequences.

1.2 WHEN the frontend filters duplicates THEN it removes any row whose `Ref2` is in the
returned duplicate set WITHOUT checking the row's `Ref1` (bank account), so a `Ref2`
that exists for a DIFFERENT account of the same tenant removes rows of the current
account.

1.3 WHEN both accounts in the file carry Rabobank `Volgnr` sequences that overlap (because
`Volgnr` restarts per account, so both start at 1) THEN the second account's rows are
treated as duplicates of the first account's existing rows and are filtered out BEFORE
the review grid is shown, so they never reach the save step.

1.4 WHEN those rows are filtered out pre-display THEN the system reports them as
duplicates and saves 0 rows for the second account, even though no transactions for that
account have ever been imported.

1.5 WHEN the backend authoritative duplicate gate in `save_approved_transactions` runs
THEN it scopes the `Ref2` match only by `administration` (tenant) and omits `Ref1`, so
identical `Volgnr` values belonging to different accounts of the same tenant would be
indistinguishable even if such rows reached the save step.

### Expected Behavior (Correct)

What should happen instead for the same conditions:

2.1 WHEN a tenant imports a single Rabobank CSV containing more than one bank account THEN
the frontend pre-display duplicate check SHALL be performed PER bank account: for each
distinct `Ref1` in the parsed rows, call `check-sequences` with THAT `Ref1` and only that
account's `Ref2` sequences.

2.2 WHEN the frontend filters duplicates THEN a row SHALL be treated as a duplicate only
when a record with the SAME account (`Ref1`) AND the SAME `Ref2` already exists for the
tenant; each account's rows SHALL be filtered only against that same account's existing
sequences.

2.3 WHEN a second account's `Volgnr` sequences overlap another account's existing
sequences THEN the system SHALL still treat the second account's rows as new (because they
belong to a different account) and SHALL pass them to the review grid and the save step.

2.4 WHEN the backend authoritative duplicate gate in `save_approved_transactions` runs
THEN it SHALL scope the `Ref2` match to both the tenant (`administration`) AND the
specific bank account (`Ref1`), so a row is classified as a duplicate only when a matching
record exists for that same tenant and that same bank account (defense-in-depth behind the
primary frontend fix).

### Unchanged Behavior (Regression Prevention)

Existing behavior that must be preserved:

3.1 WHEN a tenant imports a single-account Rabobank CSV THEN the system SHALL CONTINUE TO
behave exactly as before (the per-account grouping degenerates to the existing
single-IBAN check).

3.2 WHEN a tenant re-imports the SAME bank account's rows with the SAME `Volgnr` / `Ref2`
values (same `Ref1` AND matching `Ref2` already in `mutaties` for the tenant) THEN the
system SHALL CONTINUE TO filter those rows as duplicates (now correctly scoped per
account).

3.3 WHEN rows are parsed by `processRabobankTransaction` THEN `Ref2` SHALL CONTINUE TO be
normalized via `parseInt(columns[3] || '0').toString()`, unchanged.

3.4 WHEN an imported IBAN is resolved to a general ledger bank account THEN the system
SHALL CONTINUE TO resolve the account per row via `processRabobankTransaction` /
`lookupData` as it does today, and the account-selection popup SHALL CONTINUE TO behave as
confirmation only — account resolution and the popup are NOT the defect and SHALL NOT be
modified.

3.5 WHEN a tenant imports CSV rows containing zero-amount lines THEN the system SHALL
CONTINUE TO skip those zero-amount lines (`processRabobankTransaction` returns null for
amount 0), unchanged.

3.6 WHEN a tenant imports CSV rows targeting a closed fiscal year THEN the system SHALL
CONTINUE TO block the import for those rows with the existing closed-period error.

3.7 WHEN a tenant imports CSV rows for a bank account IBAN that belongs to a different
tenant THEN the system SHALL CONTINUE TO reject the import with the existing
wrong-tenant / access-denied behavior.
