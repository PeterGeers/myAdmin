# Revolut Dutch Status Filter Bugfix Design

## Overview

The `processRevolutTransaction` function in `BankingProcessor.tsx` only checks for English status values (`REVERTED`, `PENDING`) to filter out non-completed transactions. When Revolut CSV statements are exported in Dutch (or any other language), non-completed transactions with status like `IN BEHANDELING` bypass the filter, get processed with empty `Saldo`/`Datum voltooid` fields, and produce `NaN` in the Ref2 reference — breaking duplicate detection.

The fix uses a **language-independent structural check**: filter out any transaction where the completion date or balance field is empty. This works regardless of CSV export language because non-completed transactions always have these fields empty. The existing English status checks are kept as a secondary safety layer.

Additionally, the Ref2 format is changed from `[beschrijving]_[saldo]_[startdatum]` to `[beschrijving]_[saldo]_[datum voltooid]`. The completion date (`Datum voltooid`) is when the transaction is actually processed/settled, making it a better basis for duplicate detection than the initiation date (`Startdatum`). `TransactionDate` remains as `Startdatum` (date part only) since that's the user-facing transaction date. A database migration is required to update existing Revolut Ref2 values.

## Glossary

- **Bug_Condition (C)**: A Revolut CSV transaction where the completion date (`Datum voltooid` / `Completed Date`, column index 3) is empty OR the balance (`Saldo` / `Balance`, column index 9) is empty — indicating a non-completed transaction
- **Property (P)**: When the bug condition holds, `processRevolutTransaction` returns an empty array (transaction is filtered out, no Ref2 with `NaN` is generated)
- **Preservation**: Completed transactions (both completion date and balance filled) continue to be processed identically — same Ref2 format, same transaction output, same duplicate detection behavior
- **processRevolutTransaction**: The function in `frontend/src/components/BankingProcessor.tsx` (line ~109) that converts a single Revolut CSV row into zero or more `Transaction` objects
- **getColIdx**: Helper function inside `processRevolutTransaction` that finds column indices by header name with positional fallback — supports Dutch and English column names
- **Ref2**: A composite reference string (`[beschrijving]_[saldo]_[datum voltooid]`) used for duplicate detection across uploads. Changed from `[startdatum]` to `[datum voltooid]` because the completion date is when the transaction is actually settled, providing a more accurate and unique reference for duplicate detection
- **saldoIdx**: The resolved column index for the balance/saldo column, already computed via `getColIdx(['saldo', 'balance'], 9)`

## Bug Details

### Bug Condition

The bug manifests when a Revolut CSV transaction is not yet completed. Non-completed transactions have empty values in the completion date column (index 3) and the balance column (index 9). The current code only checks the status text for English values `REVERTED` and `PENDING`, so Dutch statuses like `IN BEHANDELING`, `TERUGGEDRAAID`, or `GEWEIGERD` pass through. The empty saldo then produces `NaN` via `parseFloat(''.replace(',', '.')).toFixed(2)`, which corrupts the Ref2 reference.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type { columns: string[], header?: string[] }
  OUTPUT: boolean

  completionDateIdx ← getColIdx(['datum voltooid', 'completed date', 'completed'], 3)
  saldoIdx ← getColIdx(['saldo', 'balance'], 9)

  completionDate ← input.columns[completionDateIdx] OR ''
  saldoRaw ← input.columns[saldoIdx] OR ''

  RETURN completionDate.trim() = '' OR saldoRaw.trim() = ''
END FUNCTION
```

### Examples

- **Dutch pending transaction**: `Kaartbetaling,Betaalrekening,2026-04-16 12:07:04,,Albert Heijn,-29.06,0.00,EUR,IN BEHANDELING,` → completion date is empty, saldo is empty → should be filtered out, but currently passes through and generates Ref2 `Albert Heijn_NaN_2026-04-16 12:07:04`
- **English pending transaction**: `Card payment,Current,2026-04-16 12:07:04,,Albert Heijn,-29.06,0.00,EUR,PENDING,` → completion date is empty, saldo is empty → currently filtered by `PENDING` check (works), but structural check would also catch it
- **Completed transaction (Dutch)**: `Kaartbetaling,Betaalrekening,2026-03-01 15:27:29,2026-03-01 03:18:36,Hotel Lelystad,-37.00,0.00,EUR,VOLTOOID,1290.32` → both fields filled → should be processed normally
- **Edge case — saldo present but completion date empty**: A hypothetical row with balance filled but no completion date → should still be filtered out (incomplete transaction)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Completed transactions (both completion date and balance filled) must continue to produce `Transaction` objects with the updated Ref2 format `[beschrijving]_[saldo]_[datum voltooid]`
- The existing `REVERTED`/`PENDING` English status check must remain as a secondary filter
- The `amount === 0 && fee === 0` zero-value filter must continue to work
- Fee transactions must continue to be generated when `fee > 0`
- The `getColIdx` helper must continue to resolve columns by name with positional fallback
- The `saldo` formatting (`parseFloat(...).toFixed(2)`) for completed transactions must remain unchanged

**Scope:**
All transactions where BOTH the completion date AND balance fields are non-empty should be completely unaffected by this fix. This includes:

- All completed Dutch transactions (status `VOLTOOID`)
- All completed English transactions (status `COMPLETED`)
- Transactions in any other language with filled structural fields
- Zero-amount transactions (still filtered by existing `amount === 0 && fee === 0` check)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is:

1. **English-only status filter**: Line ~141 checks `status.includes('REVERTED') || status.includes('PENDING')` — this only works for English CSV exports. Dutch exports use `IN BEHANDELING` (pending), `TERUGGEDRAAID` (reverted), `GEWEIGERD` (declined), which don't match.

2. **No structural field validation**: The function reads `saldoRaw` from the CSV but defaults empty values to `'0'` (line ~139: `columns[saldoIdx] || '0'`), masking the fact that the field is actually empty. The completion date column is never checked at all.

3. **NaN propagation**: When `saldoRaw` is empty, the fallback `'0'` produces `saldo = "0.00"` — but the real issue is that the transaction should never reach Ref2 generation. In the actual CSV, the empty saldo column combined with the `|| '0'` fallback means the saldo becomes `"0.00"` rather than `NaN`. However, if the column is truly absent (not just empty string but undefined), `columns[saldoIdx]` returns `undefined`, and `undefined || '0'` still gives `'0'`. The core problem remains: non-completed transactions should not be processed at all.

4. **Missing completion date column lookup**: The function already uses `getColIdx` for 6 columns (startdatum, beschrijving, bedrag, kosten, status, saldo) but does NOT look up the completion date column (`Datum voltooid` / `Completed Date`, index 3), which is the most reliable indicator of transaction completion.

## Correctness Properties

Property 1: Bug Condition - Non-completed transactions are filtered out

_For any_ Revolut CSV transaction row where the completion date field (column index 3) is empty OR the balance/saldo field (column index 9) is empty, the fixed `processRevolutTransaction` function SHALL return an empty array, producing no `Transaction` objects and no Ref2 values.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Completed transactions produce correct output with updated Ref2

_For any_ Revolut CSV transaction row where BOTH the completion date field AND the balance/saldo field are non-empty (indicating a completed transaction), the fixed `processRevolutTransaction` function SHALL produce `Transaction[]` output with the updated Ref2 format `[beschrijving]_[saldo]_[datum voltooid]`, correct transaction amounts, and all other fields unchanged (TransactionDate still uses Startdatum date part).

**Validates: Requirements 3.1, 3.2, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `frontend/src/components/BankingProcessor.tsx`

**Function**: `processRevolutTransaction` (line ~109)

**Specific Changes**:

1. **Add completion date column lookup**: Add a `getColIdx` call for the completion date column:

   ```typescript
   const datumVoltooidIdx = getColIdx(
     ["datum voltooid", "completed date", "completed"],
     3,
   );
   ```

   Place this alongside the existing column index lookups (after `saldoIdx`).

2. **Read completion date and raw saldo values**: Read the raw column values before any transformation:

   ```typescript
   const datumVoltooidRaw = columns[datumVoltooidIdx] || "";
   ```

   Read `saldoRaw` before the `|| '0'` fallback to check for emptiness:

   ```typescript
   const saldoRawValue = columns[saldoIdx] || "";
   ```

3. **Add structural field filter BEFORE existing status check**: Insert the new filter before the `REVERTED`/`PENDING` check (before line ~141):

   ```typescript
   // Language-independent filter: skip non-completed transactions (empty completion date or balance)
   if (!datumVoltooidRaw.trim() || !saldoRawValue.trim()) return transactions;
   ```

4. **Keep existing REVERTED/PENDING check**: The existing English status check on line ~141 remains unchanged as a secondary safety layer.

5. **Change Ref2 to use completion date instead of start date**: Update the Ref2 construction for both main and fee transactions:

   ```typescript
   // Main transaction Ref2 — use datum voltooid (settlement date) instead of startdatum
   const ref2 = [beschrijving, saldo, datumVoltooidRaw].join("_");
   ```

   ```typescript
   // Fee transaction Ref2 — same change
   const feeRef2 = ["Revo Charges", saldo, datumVoltooidRaw].join("_");
   ```

   `TransactionDate` remains as `startdatum.split(' ')[0]` — no change to the user-facing date.

6. **Preserve saldo processing**: The existing `saldoRaw` variable (with `|| '0'` fallback) and `saldo` formatting remain unchanged for completed transactions — they will only be reached when both structural fields are non-empty.

### Change Summary

The fix involves two parts:

**Part 1: Frontend filter + Ref2 format change** (in `processRevolutTransaction`):

- Adds 4 lines for the structural field filter (completion date column lookup, raw value reads, filter check)
- Changes Ref2 from `[beschrijving]_[saldo]_[startdatum]` to `[beschrijving]_[saldo]_[datum voltooid]` for both main and fee transactions
- `TransactionDate` remains as `Startdatum` (date part only) — no change

**Part 2: Database migration** (migration script):

The original Revolut CSV files for 2026 are available at `.kiro/specs/FIN/BankingProcessor/Revolut/` (14 files covering Jan–Apr 2026). These contain both `Startdatum` and `Datum voltooid` for every completed transaction.

Migration approach:

1. Parse all 14 CSV files, extract completed transactions (status `VOLTOOID`, non-empty `Datum voltooid` and `Saldo`)
2. Build a lookup map: old Ref2 (`[beschrijving]_[saldo]_[startdatum]`) → new Ref2 (`[beschrijving]_[saldo]_[datum voltooid]`)
3. Deduplicate across overlapping CSV files (same transaction appears in multiple exports)
4. For each entry in the lookup, update the matching record in `mutaties` WHERE `Ref1 = 'NL08REVO7549383472'` AND `Ref2 = old_ref2`
5. Run in dry-run mode first to report what would change, then apply

The `saldo` value in Ref2 must be formatted to 2 decimals (matching the frontend's `parseFloat(...).toFixed(2)`) for the lookup to match.

Pre-2025 Revolut data (if any) uses a different Ref2 format and is out of scope for this migration.

**Duplicate detection compatibility**: After migration, all 2026 Revolut records will use the new `Datum voltooid` format. New uploads will generate the same format, so duplicate detection works correctly.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call `processRevolutTransaction` with Dutch CSV rows containing empty completion date and empty saldo fields. Run these tests on the UNFIXED code to observe that transactions are incorrectly processed.

**Test Cases**:

1. **Dutch pending transaction**: Pass a row with status `IN BEHANDELING`, empty completion date, empty saldo → expect empty array, but unfixed code will return a transaction (will fail on unfixed code)
2. **Dutch declined transaction**: Pass a row with status `GEWEIGERD`, empty completion date, empty saldo → expect empty array, but unfixed code will return a transaction (will fail on unfixed code)
3. **Multiple Dutch pending rows**: Pass several non-completed Dutch rows → expect all filtered, but unfixed code processes them (will fail on unfixed code)
4. **Empty saldo NaN check**: Pass a row with empty saldo → check if Ref2 contains `NaN` (will demonstrate NaN issue on unfixed code)

**Expected Counterexamples**:

- `processRevolutTransaction` returns a non-empty `Transaction[]` for Dutch pending transactions
- The returned transaction's `Ref2` field contains `NaN` (e.g., `Albert Heijn_NaN_2026-04-16 12:07:04`) or `0.00` depending on the `|| '0'` fallback behavior
- Possible causes: status filter only checks English values, no structural field validation

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := processRevolutTransaction_fixed(input)
  ASSERT result = [] (empty array)
  // No Ref2 with NaN is generated
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT processRevolutTransaction_original(input) = processRevolutTransaction_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many transaction rows with random but valid completion dates and saldo values
- It catches edge cases in saldo formatting (decimal separators, large numbers, negative values)
- It provides strong guarantees that completed transaction processing is unchanged

**Test Plan**: Observe behavior on UNFIXED code first for completed transactions (both Dutch and English), then write property-based tests capturing that behavior.

**Test Cases**:

1. **Completed Dutch transaction preservation**: Observe that completed Dutch transactions (status `VOLTOOID`, filled completion date and saldo) produce correct output on unfixed code, then verify identical output after fix
2. **Completed English transaction preservation**: Observe that completed English transactions produce correct output on unfixed code, then verify identical output after fix
3. **REVERTED/PENDING preservation**: Observe that English `REVERTED` and `PENDING` transactions are still filtered on unfixed code, then verify same behavior after fix
4. **Zero-amount preservation**: Observe that zero-amount transactions are still filtered, then verify same behavior after fix
5. **Fee transaction preservation**: Observe that fee transactions are generated correctly for completed transactions, then verify identical output after fix

### Unit Tests

- Test `processRevolutTransaction` with Dutch pending row (empty completion date + empty saldo) → returns `[]`
- Test with Dutch declined row (empty completion date + empty saldo) → returns `[]`
- Test with English `PENDING` row → returns `[]` (existing behavior preserved)
- Test with English `REVERTED` row → returns `[]` (existing behavior preserved)
- Test with completed Dutch row (all fields filled) → returns correct `Transaction[]`
- Test with completed English row (all fields filled) → returns correct `Transaction[]`
- Test edge case: saldo filled but completion date empty → returns `[]`
- Test edge case: completion date filled but saldo empty → returns `[]`
- Test edge case: both fields have whitespace only → returns `[]`

### Property-Based Tests

- Generate random completed transaction rows (non-empty completion date, non-empty saldo, random amounts/descriptions) and verify the fixed function produces identical output to the original function
- Generate random non-completed transaction rows (empty completion date OR empty saldo, random status text in various languages) and verify the fixed function returns `[]`
- Generate random column orderings with headers and verify `getColIdx` correctly resolves completion date column

### Integration Tests

- Process a full Dutch Revolut CSV file (like the sample `account-statement_2026-03-01_2026-04-16_nl-nl_96bd74.csv`) and verify pending rows at the end are filtered while completed rows are processed
- Process the same file twice and verify duplicate detection works correctly for completed transactions
- Process a mixed-language scenario (if applicable) and verify structural filtering works regardless of status text
