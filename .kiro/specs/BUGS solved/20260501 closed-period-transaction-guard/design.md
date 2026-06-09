# Closed Period Transaction Guard — Bugfix Design

## Overview

Transactions can currently be saved to fiscal years that have already been closed via the year-end closure process. The `year_closure_status` table tracks closed years and `YearEndClosureService._is_year_closed()` already performs the check, but no validation exists in the transaction saving pipeline. This fix adds a closed-period guard to the two transaction saving entry points: `TransactionLogic.save_approved_transactions()` (used by invoice approval and all `InvoiceBookingHelper` booking flows) and `BankingProcessor.save_approved_transactions()` (used by banking CSV import). The guard extracts the year from each transaction's `TransactionDate`, queries `year_closure_status` for the tenant, and rejects the entire batch if any transaction targets a closed year.

## Glossary

- **Bug_Condition (C)**: A transaction's `TransactionDate` falls within a fiscal year that has a record in `year_closure_status` for the same `administration` (tenant)
- **Property (P)**: When C holds, the save operation SHALL raise a `ClosedPeriodError` before any database insert occurs, identifying which transactions target closed periods
- **Preservation**: All transactions with dates in open (non-closed) fiscal years SHALL continue to save successfully with identical behavior to the current implementation
- **`TransactionLogic.save_approved_transactions()`**: Central method in `transaction_logic.py` that saves a list of approved transactions to the `mutaties` table. Used by `/api/approve-transactions` and all `InvoiceBookingHelper` booking methods
- **`BankingProcessor.save_approved_transactions()`**: Separate method in `banking_processor.py` that saves banking import transactions with duplicate detection. Has its own database interaction, not delegated to `TransactionLogic`
- **`year_closure_status`**: Table tracking closed fiscal years per tenant. Columns: `administration`, `year`, `closed_date`, `closed_by`, etc.
- **`YearEndClosureService._is_year_closed()`**: Existing private method that queries `year_closure_status` — currently only used within the year-end closure workflow itself

## Bug Details

### Bug Condition

The bug manifests when any transaction saving flow receives transactions with a `TransactionDate` whose year exists in `year_closure_status` for the given `administration`. Neither `TransactionLogic.save_approved_transactions()` nor `BankingProcessor.save_approved_transactions()` check the closure status before inserting into `mutaties`.

**Formal Specification:**

```
FUNCTION isBugCondition(transaction)
  INPUT: transaction of type Dict with keys TransactionDate, Administration
  OUTPUT: boolean

  year := EXTRACT_YEAR(transaction.TransactionDate)
  administration := transaction.Administration

  RETURN EXISTS(
    SELECT 1 FROM year_closure_status
    WHERE administration = administration
    AND year = year
  )
END FUNCTION
```

### Examples

- **Invoice approval in closed year**: User approves a transaction with `TransactionDate = '2023-06-15'` and `Administration = 'TenantA'`. Year 2023 is closed in `year_closure_status`. Current behavior: transaction is saved. Expected: `ClosedPeriodError` raised, no insert occurs.
- **Outgoing invoice booking in closed year**: `InvoiceBookingHelper.book_outgoing_invoice()` creates entries with `invoice_date = '2022-11-01'`. Year 2022 is closed. Current behavior: entries saved via `TransactionLogic.save_approved_transactions()`. Expected: `ClosedPeriodError` raised before any insert.
- **Banking import in closed year**: `BankingProcessor.save_approved_transactions()` processes a CSV with transactions dated `'2023-03-20'`. Year 2023 is closed. Current behavior: transactions saved (if not duplicates). Expected: rejected with closed-period error.
- **Mixed batch**: A batch contains 3 transactions: two in 2024 (open) and one in 2023 (closed). Current behavior: all 3 saved. Expected: entire batch rejected, error identifies the 2023 transaction.
- **Edge case — no closed years**: `year_closure_status` has no entries for the tenant. All transactions should save normally regardless of date.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Transactions with dates in open (non-closed) fiscal years save successfully with identical insert behavior
- Zero-amount transaction skipping logic remains unchanged (skipped before closed-period check is relevant)
- `BankingProcessor` duplicate detection continues to work as before for open-period transactions
- `InvoiceBookingHelper` booking flows (outgoing, incoming, credit notes) continue to work for open-period dates
- The year-end closure process itself (`YearEndClosureService.close_year()`) continues to create closure and opening balance transactions via direct `cursor.execute()` — these bypass `save_approved_transactions` entirely
- Error handling for FK constraint violations (invalid account numbers) remains unchanged
- The `db.transaction()` context manager commit/rollback behavior is preserved

**Scope:**
All inputs where NO transaction in the batch has a `TransactionDate` in a closed fiscal year should be completely unaffected by this fix. This includes:

- All transactions with dates in years not present in `year_closure_status`
- All transactions when `year_closure_status` has no entries for the tenant
- Zero-amount transactions (skipped before the guard applies)

## Hypothesized Root Cause

Based on the bug analysis, the root cause is straightforward:

1. **Missing validation step**: `TransactionLogic.save_approved_transactions()` iterates over transactions and inserts them directly without checking whether the transaction date falls in a closed fiscal year. The method was written before the year-end closure feature existed.

2. **Separate code path for banking**: `BankingProcessor.save_approved_transactions()` has its own independent implementation that also lacks any closed-period check. It was not updated when year-end closure was added.

3. **Private method not reusable**: `YearEndClosureService._is_year_closed()` is a private method on the service class. It queries `year_closure_status` but is only called within the closure workflow itself (validation, reopen). There is no public utility function or shared service method that the transaction saving pipeline can call.

4. **No database-level constraint**: There is no trigger or check constraint on the `mutaties` table that would prevent inserts for closed periods at the database level. The guard must be implemented in application code.

## Correctness Properties

Property 1: Bug Condition — Transactions in closed fiscal years are rejected

_For any_ batch of transactions where at least one transaction has a `TransactionDate` whose year exists in `year_closure_status` for the given `administration`, the `save_approved_transactions()` function SHALL raise a `ClosedPeriodError` before any database insert occurs, and the error SHALL identify which transactions target closed periods.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

Property 2: Preservation — Transactions in open fiscal years save successfully

_For any_ batch of transactions where NO transaction has a `TransactionDate` in a closed fiscal year (including when `year_closure_status` has no entries for the tenant), the `save_approved_transactions()` function SHALL save all non-zero-amount transactions successfully, producing the same result as the original (unfixed) function.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/src/db_exceptions.py`

**Change**: Add `ClosedPeriodError` exception class

**Specific Changes**:

1. **Add `ClosedPeriodError`**: A new exception class inheriting from `DatabaseError` that carries the list of offending transactions and their closed years. This follows the existing exception hierarchy pattern (`IntegrityError`, `OperationalError`, etc.).

---

**File**: `backend/src/transaction_logic.py`

**Function**: `save_approved_transactions()`

**Specific Changes**:

1. **Extract distinct years and administrations**: Before the insert loop, collect all unique `(year, administration)` pairs from the transaction batch (excluding zero-amount transactions).
2. **Query `year_closure_status`**: For each administration, query the closed years in a single query using `WHERE administration = %s AND year IN (...)`.
3. **Reject if any closed year found**: If any transaction targets a closed year, raise `ClosedPeriodError` with details about which transactions are in closed periods. This happens before the `db.transaction()` context, so no partial inserts occur.
4. **Import `ClosedPeriodError`**: Add import from `db_exceptions`.

---

**File**: `backend/src/banking_processor.py`

**Function**: `save_approved_transactions()`

**Specific Changes**:

1. **Add closed-period check**: Before the transaction loop, extract distinct years and administrations from the batch, query `year_closure_status`, and reject if any closed year is found.
2. **Import `ClosedPeriodError`**: Add import from `db_exceptions`.
3. **Use `DatabaseManager` for the check query**: The check should use `self.db.execute_query()` rather than the raw cursor already opened for the save loop, keeping the validation separate from the save logic.

---

**File**: `backend/src/routes/invoice_routes.py`

**Function**: `approve_transactions()`

**Specific Changes**:

1. **Catch `ClosedPeriodError`**: Add a specific except clause for `ClosedPeriodError` that returns a 400 response with `{'success': False, 'error': str(e)}` so the frontend receives a clear message about the closed period.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that mock `year_closure_status` as having a closed year, then call `save_approved_transactions()` with transactions dated in that closed year. Run these tests on the UNFIXED code to observe that transactions are saved without error (confirming the bug).

**Test Cases**:

1. **TransactionLogic closed-year save**: Call `TransactionLogic.save_approved_transactions()` with a transaction dated in a closed year — expect it to save (bug confirmed on unfixed code)
2. **BankingProcessor closed-year save**: Call `BankingProcessor.save_approved_transactions()` with a transaction dated in a closed year — expect it to save (bug confirmed on unfixed code)
3. **Mixed batch save**: Call `save_approved_transactions()` with a mix of open and closed year transactions — expect all to save (bug confirmed on unfixed code)
4. **InvoiceBookingHelper path**: Call `book_outgoing_invoice()` with an invoice date in a closed year — expect it to save through `TransactionLogic` (bug confirmed on unfixed code)

**Expected Counterexamples**:

- Transactions with dates in closed fiscal years are inserted into `mutaties` without any error
- Possible causes confirmed: no validation step exists in either save method

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL batch WHERE ANY transaction IN batch HAS isBugCondition(transaction) DO
  result := save_approved_transactions_fixed(batch)
  ASSERT result RAISES ClosedPeriodError
  ASSERT no rows inserted into mutaties
  ASSERT error message identifies closed-period transactions
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL batch WHERE NO transaction IN batch HAS isBugCondition(transaction) DO
  ASSERT save_approved_transactions_original(batch) = save_approved_transactions_fixed(batch)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many transaction batches with random dates, amounts, and account numbers across open fiscal years
- It catches edge cases like empty batches, single-transaction batches, and batches with zero-amount transactions
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for transactions in open years, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Open-year transactions preservation**: Verify transactions with dates in open years save successfully after the fix, producing the same saved count and inserted rows
2. **Zero-amount skipping preservation**: Verify zero-amount transactions continue to be skipped regardless of date
3. **No closed years preservation**: Verify that when `year_closure_status` is empty, all transactions save normally
4. **BankingProcessor duplicate detection preservation**: Verify duplicate detection in `BankingProcessor` continues to work for open-year transactions

### Unit Tests

- Test `ClosedPeriodError` exception class carries correct attributes
- Test `TransactionLogic.save_approved_transactions()` raises `ClosedPeriodError` for closed-year transactions
- Test `BankingProcessor.save_approved_transactions()` raises `ClosedPeriodError` for closed-year transactions
- Test entire batch is rejected when any transaction targets a closed year (no partial saves)
- Test error message identifies which transactions are in closed periods
- Test zero-amount transactions in closed years are skipped (not flagged as closed-period violations)
- Test transactions in open years save successfully after the fix
- Test when `year_closure_status` has no entries, all transactions are allowed

### Property-Based Tests

- Generate random transaction batches with dates across multiple years, with a randomly chosen subset of years marked as closed. Verify that batches containing any closed-year transaction raise `ClosedPeriodError`, and batches with only open-year transactions save successfully.
- Generate random open-year transaction batches and verify the fixed function produces identical results to the original function (preservation).
- Generate random administrations with varying closed-year configurations and verify tenant isolation (closing years for TenantA does not affect TenantB).

### Integration Tests

- Test the full `/api/approve-transactions` endpoint returns 400 with closed-period error message
- Test `InvoiceBookingHelper.book_outgoing_invoice()` raises `ClosedPeriodError` for closed-year invoices
- Test `InvoiceBookingHelper.book_incoming_invoice()` raises `ClosedPeriodError` for closed-year invoices
- Test `InvoiceBookingHelper.book_credit_note()` raises `ClosedPeriodError` for closed-year credit notes
- Test that year-end closure process (`close_year()`) still works after the fix (its transactions bypass `save_approved_transactions`)
