# Banking Import Account-Scoped Duplicate Detection Bugfix Design

## Overview

When a tenant imports a single Rabobank CSV (`CSV_O`) file that contains transactions for
two or more of the tenant's own bank accounts, the rows belonging to the second (and any
subsequent) account are silently dropped **before they are ever shown in the review
grid**. The import reports them as duplicates / "already loaded", nothing for that account
reaches the save step, and 0 rows are saved for that account, even though no transactions
for that account have ever been imported.

The reported case is tenant `kimgeers` importing a Rabobank CSV covering two accounts:
account 1002 "Lopende rekening" — IBAN `NL98RABO0174003390` — already has 47 rows in
`mutaties` (`Volgnr` 1..47) and imports correctly, while account 1003 "Spaar rekening" —
IBAN `NL60RABO1101699949` — has 0 rows in `mutaties` and fails. Its 5 rows (`Volgnr` 1..5)
are all silently filtered out as duplicates and never reach the grid or the save step. The
account-selection popup correctly resolves to 1003, yet the 5 rows are not processed and
nothing is saved.

The confirmed root cause is the **frontend pre-display duplicate filter** in
`frontend/src/components/BankingFileUpload.tsx` → `processFiles`. The duplicate comparison
happens in the FRONTEND, BEFORE the rows are shown in the review grid, so a backend-only
fix cannot recover the dropped rows. `processFiles` derives the IBAN from the FIRST parsed
row only (`allTransactions[0]?.Ref1`), checks ALL rows' `Ref2` sequences against that one
account's existing sequences, and then filters by `Ref2` membership alone with no
per-account (`Ref1`) check (`allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2))`).
For a multi-account CSV, the first row's IBAN (`NL98`) determines the whole check; the
second account (`NL60`) carries overlapping low `Volgnr` values (1..5) that are all members
of `NL98`'s existing set, so every `NL60` row is flagged duplicate and dropped pre-display.

The fix is in two layers:

- **PRIMARY — frontend `processFiles`.** Group the parsed rows by `Ref1` (bank account);
  for each distinct `Ref1`, call `check-sequences` with THAT `Ref1` and only that account's
  `Ref2` sequences; filter each account's rows only against that same account's returned
  duplicates; combine the kept rows and pass them to `onTransactionsLoaded`. The
  duplicates-filtered message reflects totals across accounts.
- **SECONDARY (defense-in-depth) — backend `save_approved_transactions`.** The authoritative
  gate in `backend/src/banking_processor.py` matches `Ref2` scoped only by `administration`
  (tenant), omitting `Ref1`. It did NOT produce the reported symptom (rows were dropped
  pre-display, never reaching the save step), but once the frontend fix lets multi-account
  rows through, this gate could still wrongly skip them. It SHALL also be scoped by `Ref1`
  so correctness does not depend solely on the frontend.

Deliberately left unchanged: `processRabobankTransaction` account resolution and `Ref2`
normalization, the account-selection popup, the backend `check_sequences` endpoint,
`get_existing_sequences` (already `Ref1`-scoped), the zero-amount skip, the closed-period
guard, and the wrong-tenant rejection.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a parsed import row whose
  bank account (`Ref1`) differs from the FIRST parsed row's `Ref1`, and whose `Ref2`
  (Rabobank `Volgnr`) collides with the `Ref2` of an existing `mutaties` record belonging to
  a DIFFERENT account under the SAME tenant, while no `mutaties` record exists for that row's
  own `(Ref1, Ref2)`. The single-account frontend check mis-classifies such a genuinely new
  row as a duplicate and drops it before the review grid.
- **Property (P)**: The desired behavior for inputs satisfying C — the row is treated as new,
  survives the per-account pre-display dedupe, is shown in the review grid, and reaches the
  save step, because its `(administration, Ref1, Ref2)` triple does not exist in `mutaties`.
- **Preservation**: Existing behavior that must remain unchanged for inputs not satisfying C
  — single-account imports, same-account re-import filtering, `Ref2` normalization,
  IBAN→GL-account resolution and the account-selection popup, zero-amount skipping,
  closed-period blocking, and wrong-tenant rejection.
- **`processFiles`**: Callback in `frontend/src/components/BankingFileUpload.tsx` that parses
  the selected files into `Transaction[]`, performs the pre-display duplicate check, and
  calls `onTransactionsLoaded` with the surviving rows. It contains the two primary defects:
  (a) `const iban = allTransactions[0]?.Ref1` assumes a single IBAN per file; (b)
  `allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2))` filters by `Ref2`
  membership alone, ignoring `Ref1`.
- **`processRabobankTransaction`**: Function in
  `frontend/src/components/BankingProcessor.utils.ts` that parses one Rabobank CSV row into a
  `Transaction`. Sets `Ref1 = columns[0]` (per-row IBAN), `Ref2 = parseInt(columns[3] || '0').toString()`
  (`Volgnr` normalized to a plain integer), and resolves `Debet`/`Credit` per account from
  `lookupData.bank_accounts`. Correct — not modified.
- **`check_sequences`**: Method in `backend/src/services/banking_service.py` behind
  `POST /api/banking/check-sequences`. Takes a single `iban`, a list of `sequences`, and the
  tenant; calls `get_existing_sequences(iban, administration=tenant)` and returns
  `duplicates = [seq for seq in sequences if seq in existing_sequences]`. Correctly scoped to
  the one `iban` passed to it — not modified; the frontend simply must call it once per
  account.
- **`get_existing_sequences`**: Method in `backend/src/database_banking_queries.py` returning
  existing `Ref2` values for a given `Ref1` (IBAN) within the last 2 years, optionally scoped
  by `administration`. Already `Ref1`-scoped and correct — NOT changed.
- **`save_approved_transactions`**: Method in `backend/src/banking_processor.py` that runs the
  closed-period guard, then the authoritative duplicate detection, then the insert. Its
  primary `Ref2` check (`WHERE Ref2 = %s AND administration = %s`) omits `Ref1` — the
  secondary, defense-in-depth site of the fix.
- **`Ref1`**: The bank account IBAN, set by `processRabobankTransaction` from CSV column 0 and
  stored on each `mutaties` row. It identifies which bank account a row belongs to.
- **`Ref2`**: The Rabobank sequence number (`Volgnr`), parsed from CSV column 3 and normalized
  to a plain integer by `processRabobankTransaction`. Unique only within a single bank account
  and **restarts at 1 for each account**.
- **`Volgnr`**: Rabobank's per-account running sequence number, the CSV source of `Ref2`.
  Zero-padded in the CSV (e.g. `000000000000000001`); normalized to the plain integer form
  (`"1"`) by `processRabobankTransaction`, consistent with how `mutaties.Ref2` is stored.

## Bug Details

### Bug Condition

The bug manifests when a tenant imports a single Rabobank CSV containing more than one of
the tenant's bank accounts. `processFiles` derives one IBAN from the first parsed row
(`allTransactions[0]?.Ref1`), checks ALL rows' `Ref2` against that single account's existing
sequences via `check-sequences`, and filters duplicates by `Ref2` membership alone — never
checking the row's own `Ref1`. Any later-account row whose `Volgnr` happens to match the
first account's existing `Volgnr` is therefore dropped before the review grid, even though it
is genuinely new for its own account.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ParsedImport
         { rows: list of ParsedRow, administration: tenant }
         where ParsedRow = { Ref1: iban, Ref2: volgnr, TransactionAmount, ... }
  OUTPUT: boolean   // true when at least one row is wrongly dropped pre-display

  IF input.rows IS EMPTY THEN RETURN false
  tenant   := input.administration
  firstRef1 := input.rows[0].Ref1          // the single IBAN processFiles uses today

  // Does ANY row get wrongly classified as a duplicate under the single-account check?
  RETURN EXISTS row IN input.rows WHERE
      row.TransactionAmount != 0
      AND row.Ref2 IS NOT EMPTY

      // (a) the row belongs to a DIFFERENT account than the first row's IBAN
      AND row.Ref1 != firstRef1

      // (b) its Volgnr collides with a DIFFERENT account's existing sequence
      //     under the same tenant (what firstRef1's existing set contains)
      AND EXISTS record IN mutaties WHERE
              record.administration = tenant
              AND record.Ref1 = firstRef1
              AND record.Ref2 = row.Ref2

      // (c) ...but THIS account has no such record (the row is genuinely new)
      AND NOT EXISTS record IN mutaties WHERE
              record.administration = tenant
              AND record.Ref1 = row.Ref1
              AND record.Ref2 = row.Ref2
END FUNCTION
```

Under the unfixed `processFiles`, every row satisfying clauses (a)+(b) is in
`checkResult.duplicates` (because the check ran against `firstRef1`'s existing set) and is
removed by the `Ref2`-only filter — so it never reaches `onTransactionsLoaded`, the grid, or
the save step. Under the fixed `processFiles` (per-account grouping, filter each account's
rows only against that account's own returned duplicates), clause (c) guarantees the row is
not a duplicate for its own account, so it survives and is shown.

### Examples

- **Reported case — kimgeers, 5-row NL60 drop (bug triggers).** Tenant `kimgeers` imports a
  CSV with two accounts. `NL98RABO0174003390` already has `mutaties` rows `Ref2 = 1..47`
  (account 1002); the new `NL60RABO1101699949` rows carry `Ref2 = 1..5` (account 1003).
  - *Expected:* all 5 `NL60` rows pass the per-account dedupe, appear in the grid, and are
    saved.
  - *Actual (unfixed):* `iban = allTransactions[0]?.Ref1 = NL98`; `check-sequences` returns
    `NL98`'s existing `1..47`; the `Ref2`-only filter removes `NL60` rows `1..5` as
    duplicates → 0 shown, 0 saved. (Popup correctly resolved to 1003; rows still dropped.)
- **Single-account CSV (bug does NOT trigger — preservation).** A file for only
  `NL98RABO0174003390`. Every row's `Ref1` equals `firstRef1`, so clause (a) is false;
  `isBugCondition` is false. Per-account grouping degenerates to one group — the exact
  existing single-IBAN check — and behavior is byte-for-byte identical.
- **Same-account re-import (bug does NOT trigger — preservation).** `kimgeers` re-imports
  `NL98` with `Ref2 = 1..47`. For each row, a record exists for its OWN `(Ref1, Ref2)`, so
  clause (c) is false; `isBugCondition` is false. The rows are still correctly filtered as
  duplicates — now per account — both before and after the fix.
- **Edge case — empty/zero `Ref2` or zero amount.** A row with no `Volgnr` or amount 0 fails
  the `TransactionAmount != 0` / `Ref2 IS NOT EMPTY` guards (and `processRabobankTransaction`
  already returns `null` for amount 0), so it is unaffected by this fix.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Single-account Rabobank CSV imports SHALL continue to behave exactly as before — the
  per-account grouping degenerates to the existing single-IBAN check (Req 3.1).
- Re-importing the SAME bank account's rows with the SAME `Volgnr` / `Ref2` (same `Ref1` AND
  matching `Ref2` already in `mutaties` for the tenant) SHALL continue to be filtered as
  duplicates — now correctly scoped per account (Req 3.2).
- `processRabobankTransaction` SHALL continue to normalize `Ref2` via
  `parseInt(columns[3] || '0').toString()`, unchanged (Req 3.3).
- IBAN→GL-account resolution SHALL continue to resolve the account per row via
  `processRabobankTransaction` / `lookupData`, and the account-selection popup SHALL continue
  to behave as confirmation only — neither is the defect, neither is modified (Req 3.4).
- Zero-amount lines SHALL continue to be skipped (`processRabobankTransaction` returns `null`
  for amount 0), unchanged (Req 3.5).
- Rows targeting a closed fiscal year SHALL continue to be blocked with the existing
  closed-period error (Req 3.6).
- Imports for an IBAN belonging to a different tenant SHALL continue to be rejected with the
  existing wrong-tenant / access-denied behavior (Req 3.7).

**Scope:**
All inputs that do NOT satisfy the bug condition SHALL be completely unaffected by this fix.
This includes:
- Single-account CSV imports and rows whose own `(administration, Ref1, Ref2)` triple already
  exists (true same-account duplicates).
- Rows with no `Ref2` / zero-amount rows / closed-period rows (existing guards run unchanged).
- Imports for IBANs owned by a different tenant (wrong-tenant rejection path).
- The account-selection popup and IBAN→GL-account resolution behavior.

**Note:** The expected correct behavior for buggy inputs is defined in Correctness Property 1
below; this section defines what must NOT change.

## Hypothesized Root Cause

This root cause is **CONFIRMED** — verified by reading the frontend/backend code and checked
against the production `finance` database and the actual CSV.

1. **Frontend single-account pre-display duplicate filter (CONFIRMED — PRIMARY cause).**
   `processFiles` in `BankingFileUpload.tsx` takes `const iban = allTransactions[0]?.Ref1`
   (the FIRST row's IBAN only) and `const sequences = allTransactions.map(t => t.Ref2).filter(Boolean)`
   (ALL rows across all accounts), POSTs them to `check-sequences`, then filters with
   `allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2))` — a `Ref2`
   membership test with NO `Ref1` check. Two defects: (a) single-IBAN assumption
   `allTransactions[0]?.Ref1`; (b) `Ref2`-only filter ignoring `Ref1`. For a multi-account
   CSV, the second account's overlapping low `Volgnr` values match the first account's existing
   set and are dropped before the grid.

2. **Per-account `Volgnr` restart (CONFIRMED — triggering mechanism).** Rabobank's `Volgnr`
   restarts at 1 for each bank account, so every account in a single CSV starts at low numbers
   — exactly what produces the cross-account `Ref2` collision that the single-account check
   mishandles.

3. **Backend `save_approved_transactions` tenant-only gate (CONFIRMED — SECONDARY site,
   defense-in-depth).** The authoritative gate runs
   `SELECT ID FROM mutaties WHERE Ref2 = %s AND administration = %s LIMIT 1`, omitting `Ref1`.
   It did NOT cause the reported symptom (rows were dropped pre-display and never reached it),
   but once the frontend fix lets multi-account rows through, this gate could still wrongly
   skip them, so it SHOULD also be scoped by `Ref1`.

**Disproven hypotheses (explicitly out of scope):**
- **IBAN→GL-account resolution.** Both accounts are correctly mapped for the tenant,
  `processRabobankTransaction` resolves `Debet`/`Credit` per row from `lookupData.bank_accounts`,
  and the account-selection popup is confirmation only. The popup correctly resolved to 1003 in
  the reported case. Resolution and the popup are NOT the defect and SHALL NOT be modified.
- **Backend-only root cause.** The dropped rows never reach `save_approved_transactions`, so a
  backend-only fix cannot recover them. The backend gate is a secondary, belt-and-suspenders
  layer, not the primary cause. (`get_existing_sequences` is ALREADY `Ref1`-scoped and is NOT
  changed.)

## Correctness Properties

Property 1: Bug Condition — Per-Account Pre-Display Dedupe Keeps Cross-Account Rows

_For any_ parsed import where the bug condition holds (`isBugCondition` returns true — a row
whose `Ref1` differs from the first row's `Ref1`, whose `Ref2` collides with a different
account's existing sequences under the same tenant, and for which no record exists for its own
`(Ref1, Ref2)`), the fixed `processFiles` SHALL group rows by `Ref1`, check each account's
`Ref2` sequences against ONLY that account's existing sequences, keep every row that is not a
duplicate for its own account, pass it to `onTransactionsLoaded` so it is shown in the review
grid, and report duplicate totals aggregated across accounts.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation — Unchanged Behavior for Non-Colliding Inputs

_For any_ input where the bug condition does NOT hold (`isBugCondition` returns false), the
fixed code SHALL produce the same result as the original code, preserving: single-account CSV
imports (per-account grouping degenerates to the single-IBAN check), same-account re-import
filtering (a matching `(administration, Ref1, Ref2)` record still filters the row), `Ref2`
normalization in `processRabobankTransaction`, IBAN→GL-account resolution and the
account-selection popup, zero-amount line skipping, closed-period blocking, and wrong-tenant /
access-denied rejection.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

The confirmed root cause requires a PRIMARY frontend change and a SECONDARY, defense-in-depth
backend change. No schema change is required; account resolution, the popup, `check_sequences`,
`get_existing_sequences`, and all other guards are untouched.

**PRIMARY — File**: `frontend/src/components/BankingFileUpload.tsx`

**Function**: `processFiles`

1. **Group parsed rows by `Ref1` for the duplicate check.** Replace the single-account block:
   ```ts
   // before (defective)
   const iban = allTransactions[0]?.Ref1;                               // FIRST row only
   const sequences = allTransactions.map(t => t.Ref2).filter(Boolean);  // ALL rows
   // POST /api/banking/check-sequences { iban, sequences }
   // ...
   const filteredTransactions = allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2));
   ```
   with per-account grouping:
   - Build groups keyed by `t.Ref1` from `allTransactions` (rows with a falsy `Ref1` can be
     passed through unchanged / treated as their own group).
   - For each distinct `Ref1`, collect that account's `Ref2` sequences (`.filter(Boolean)`) and
     call `check-sequences` with THAT `Ref1` and only that account's sequences.
   - Filter each account's rows against ONLY that account's returned `duplicates`
     (`groupRows.filter(t => !groupDuplicates.includes(t.Ref2))`), so a `Ref2` that exists for a
     different account does not remove rows of the current account.
   - Combine the kept rows across all groups and pass them to `onTransactionsLoaded`.

2. **Aggregate the duplicates-filtered message across accounts.** Sum the kept-row count and the
   duplicate count over all account groups so `messages.duplicatesFiltered` (`new` /
   `duplicates`) reflects totals, falling back to `messages.transactionsLoaded` when no
   duplicates were found — matching today's two message paths.

3. **Keep the request shape and `test_mode`.** Each per-account call still POSTs
   `{ iban, sequences, test_mode }`; only the scoping (one call per account) changes.

**SECONDARY (defense-in-depth) — File**: `backend/src/banking_processor.py`

**Function**: `save_approved_transactions`

4. **Scope the primary `Ref2` duplicate check by bank account.** Change the authoritative gate
   from tenant-only to tenant + account:
   ```sql
   -- before (account-blind)
   SELECT ID FROM mutaties WHERE Ref2 = %s AND administration = %s LIMIT 1
   -- after (account-scoped)
   SELECT ID FROM mutaties WHERE Ref2 = %s AND Ref1 = %s AND administration = %s LIMIT 1
   ```
   Pass `transaction.get("Ref1")` as the new bound parameter alongside the existing `ref2` and
   `administration` parameters. Keep parameterized `%s` placeholders (no string interpolation)
   and keep the existing tenant scope intact. This ensures that once the frontend fix lets
   multi-account rows through, the authoritative gate does not re-introduce the account-blind
   drop.

**Explicitly NOT changed:**
- `processRabobankTransaction` account resolution and `Ref2` normalization
  (`parseInt(columns[3] || '0').toString()`).
- The account-selection popup and IBAN→GL-account resolution.
- `banking_service.check_sequences` and `get_existing_sequences` — the endpoint already scopes
  to the one `iban` it is given, and `get_existing_sequences` is already `Ref1`-scoped.
- The secondary text/amount/date duplicate check, the zero-amount skip, the closed-period
  guard, and the wrong-tenant rejection in the save path.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach across BOTH layers: first, surface
counterexamples that demonstrate the bug on the unfixed code (cross-account `Volgnr`
collisions dropped before the grid in the frontend, and account-blind skips in the backend
gate), then verify each fix recovers those rows while preserving every unchanged behavior.

Frontend tests use the repo's existing vitest + React Testing Library + `@fast-check/vitest`
setup (tests live under `frontend/src/**/__tests__/*.test.tsx` and `frontend/tests/unit/`),
mocking `authenticatedPost('/api/banking/check-sequences', …)` so each per-account call returns
only that account's existing sequences and asserting on `onTransactionsLoaded` / the status
message. Backend tests run against the `testfinance` schema (`test_mode=True`) with seeded
`rekeningschema` and `mutaties` fixtures reproducing the overlapping-`Volgnr` scenario; no
production data is touched.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix, in both
layers. Confirm (or refute) that (i) the single-account frontend filter drops cross-account
rows pre-display, and (ii) the tenant-only backend gate would also skip them. If refuted,
re-hypothesize.

**Test Plan**:
- *Frontend*: Render `BankingFileUpload` (or drive `processFiles` directly) with a parsed set
  containing two accounts — `NL98` rows with `Ref2 = 1..47` as "existing" and new `NL60` rows
  with `Ref2 = 1..5`. Mock `check-sequences` so a call for `NL98` returns `1..47` and a call for
  `NL60` returns `[]`. On the UNFIXED code, only one call is made (for the first row's IBAN) and
  the `Ref2`-only filter drops the `NL60` rows — assert `onTransactionsLoaded` received 0 `NL60`
  rows.
- *Backend*: Seed `testfinance.mutaties` for the tenant with `Ref1 = NL98`, `Ref2 = 1..47`.
  Drive `save_approved_transactions` with `NL60` rows (`Ref2 = 1..5`, same tenant). On the
  UNFIXED gate, observe the rows skipped as "duplicate (Ref2 match)" and 0 saved.

**Test Cases**:
1. **Frontend cross-account drop**: two-account parse (`NL98` existing `1..5`, new `NL60`
   `1..5`); assert all 5 `NL60` rows reach `onTransactionsLoaded` (will FAIL on unfixed code — 0
   reach it).
2. **Frontend single second-account row**: `NL98` existing `1`, one new `NL60` row `Ref2 = 1`;
   assert it reaches the grid (will FAIL on unfixed code — filtered out).
3. **Backend cross-account collision dropped**: seed `NL98` `Ref2 = 1..5`; save 5 `NL60` rows
   `Ref2 = 1..5`; assert `saved_count == 5` (will FAIL on unfixed gate — 0 saved).
4. **Edge — out-of-order first row**: parse where the first row belongs to `NL60` and later
   rows to `NL98`; assert both accounts' genuinely new rows survive (characterizes the
   `allTransactions[0]?.Ref1` single-IBAN assumption; will FAIL on unfixed code for whichever
   account is not first).

**Expected Counterexamples**:
- Frontend: `onTransactionsLoaded` receives 0 rows for the non-first account; the
  duplicates-filtered message reports the second account's rows as duplicates.
- Backend: `saved_count == 0` / "Skipping duplicate (Ref2 match)" for `NL60` rows whose only
  match is an `NL98` record.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed code produces the
expected behavior (the row survives the per-account pre-display dedupe and is shown, and the
backend gate saves it).

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  shown  := processFiles_fixed(input)                 // frontend: rows passed to onTransactionsLoaded
  ASSERT every wrongly-dropped row IS IN shown
  saved  := save_approved_transactions_fixed(shown)   // backend secondary gate
  ASSERT every such row rowWasSaved AND NOT skippedAsRef2Duplicate
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed code
produces the same result as the original code, in both layers.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT processFiles_original(input)               = processFiles_fixed(input)
  ASSERT save_approved_transactions_original(input) = save_approved_transactions_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing (via `@fast-check/vitest` on the frontend and a PBT
library on the backend) is recommended for preservation checking because:
- It generates many inputs across the domain (one vs many accounts, `Volgnr` ranges,
  existing-row configurations, zero amounts, closed years, wrong tenants).
- It catches edge cases that hand-written unit tests might miss.
- It gives a strong guarantee that non-colliding inputs are unchanged.

**Test Plan**: Observe behavior on the UNFIXED code for single-account imports, same-account
re-imports, `Ref2` normalization, resolution + popup, zero-amount, closed-period, and
wrong-tenant inputs, then write tests asserting the fixed code matches that behavior.

**Test Cases**:
1. **Single-account import preserved**: a one-account CSV produces exactly one `check-sequences`
   call and the same surviving rows on fixed as on unfixed code (Req 3.1).
2. **Same-account re-import still filtered**: re-import `NL98` `Ref2 = 1..47`; assert all rows
   filtered as duplicates — now per account — on fixed code (Req 3.2).
3. **`Ref2` normalization preserved**: assert `processRabobankTransaction` still yields
   `Ref2 = parseInt(columns[3] || '0').toString()` and that the grouping compares on that
   normalized value (Req 3.3).
4. **Resolution + popup preserved**: assert account resolution per row and the account-selection
   popup behavior are unchanged (Req 3.4).
5. **Zero-amount / closed-period / wrong-tenant preserved**: assert zero-amount skipping,
   closed-period blocking, and wrong-tenant rejection are byte-for-byte unchanged
   (Req 3.5, 3.6, 3.7).

### Unit Tests

- Frontend `processFiles`: for a multi-account parse, one `check-sequences` call per distinct
  `Ref1`, each with only that account's sequences; rows filtered only against their own
  account's duplicates; aggregated duplicates-filtered message.
- Frontend `processFiles`: single-account parse makes exactly one call and matches prior
  behavior.
- Backend `save_approved_transactions`: the primary gate skips a row only when a matching
  `(administration, Ref1, Ref2)` record exists; a cross-account `Ref2` collision (same tenant,
  different `Ref1`) is saved; a same-account duplicate is still skipped.
- Edge cases: empty `Ref2`, zero amount, out-of-order first row.

### Property-Based Tests

- Frontend (`@fast-check/vitest`): generate parses with a random number of accounts and random
  overlapping/distinct `Volgnr` sequences; assert a row survives the pre-display dedupe iff no
  record exists for its OWN `(Ref1, Ref2)` — Property 1 and Property 2 as one invariant.
- Backend: generate random `(tenant, Ref1, Ref2)` triples with seeded `mutaties`; assert a row
  is skipped iff a record with the same `(administration, Ref1, Ref2)` already exists.
- Generate non-colliding inputs (single account, unique `Volgnr`, zero amounts, closed years,
  wrong tenant) and assert the fixed code matches the original behavior (Property 2).

### Integration Tests

- Full import flow for the reported case: `kimgeers`-style fixture, `NL98` seeded with
  `Ref2 = 1..47`, import a two-account CSV → assert all 5 `NL60` rows are shown in the grid and
  saved, `duplicate_count == 0` for `NL60`, and `NL98`'s already-present rows still filtered.
- Re-import the same two-account CSV → assert the second run filters every row as a duplicate
  (now account-scoped) in both layers, confirming dedupe is correct in both directions
  (Req 3.2).
- Mixed file with a second-account block plus a closed-period row → assert the new
  second-account rows import and the closed-period rows are blocked with the existing error
  (Req 3.6).
