# Implementation Plan

## Overview

Fix the Debtors & Creditors overview to use ledger-balance-driven queries on the `mutaties` table instead of status-driven queries on `invoices.status`. This eliminates false "overdue" displays for invoices that have already been paid via bank transfers.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Ledger-Settled Clients Still Shown as Overdue
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate settled clients still appear in receivables
  - **Scoped PBT Approach**: Scope the property to concrete failing cases — clients where ledger balance on debtor account is zero (full payment exists) but `get_receivables()` still returns them
  - **Bug Condition from design**: `isBugCondition(input)` = ledger_balance <= 0 AND has_open_status_invoices (client has offsetting credits in `mutaties` on debtor account but invoices still have status 'sent'/'overdue')
  - **Test Setup**:
    - Create invoice(s) with status 'sent' or 'overdue' for a client
    - Create matching credit entry in `mutaties` on account 1300 (debtor account) with same ReferenceNumber = client_id
    - Ensure ledger balance = 0 (debit sum equals credit sum)
  - **Test Assertions** (expected behavior from design):
    - `get_receivables()` SHALL NOT include clients with zero/negative ledger balance
    - For combined payments: two invoices (€500 + €700) with single €1,200 credit → client excluded
    - For partial payments: invoice €1,000 with €600 credit → shown with €400 outstanding (not €1,000)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - proves the bug exists: settled clients appear in receivables, amounts show `grand_total` instead of ledger balance)
  - Document counterexamples found (e.g., "Client ACME with zero ledger balance still appears with €1,210.00 outstanding")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Unsettled Clients Shown with Correct Balance
  - **IMPORTANT**: Follow observation-first methodology
  - **Test Scope**: Clients where `isBugCondition` returns false — i.e., clients with positive ledger balance (no payment or only partial payment where balance remains > 0)
  - **Observation Phase** (run on UNFIXED code):
    - Observe: Client with invoice €800, no payments → ledger balance = €800 → appears in receivables (correct)
    - Observe: Client with invoice €1,000, partial payment €300 → ledger balance = €700 → currently shows €1,000 (buggy for amount, but client IS shown)
    - Observe: Client A's data never appears in Client B's tenant (tenant isolation)
    - Observe: Multiple invoices for same client aggregated correctly
  - **Property-Based Tests**:
    - For all clients with positive ledger balance on debtor account (debit_sum > credit_sum), the client SHALL appear in receivables
    - For all clients with no credit entries at all, the client SHALL appear with outstanding amount equal to their debit total
    - For all tenants, receivables SHALL only contain data where `administration = tenant` (tenant isolation)
  - **Why PBT**: Generates many combinations of invoice amounts and payment amounts automatically; catches edge cases with rounding, zero amounts, multiple invoices per client
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS for client presence (clients with positive balance are shown); note that amount accuracy may vary on unfixed code for partial payments
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.4, 3.6_

- [x] 3. Fix for debtors overdue reconciliation — replace status-driven query with ledger-balance query
  - [x] 3.1 Resolve debtor account from tenant parameters
    - Look up the tenant's configured `zzp.debtor_account` parameter (typically `1300`)
    - Add helper function or inline lookup to resolve the account code at query time
    - Fallback to default `1300` if parameter not configured
    - _Bug_Condition: isBugCondition(input) where receivables query ignores mutaties ledger_
    - _Expected_Behavior: System uses tenant-configurable debtor account for ledger queries_
    - _Preservation: Other tenant parameters and configuration unchanged_
    - _Requirements: 2.1, 2.5_

  - [x] 3.2 Replace `get_receivables()` query with ledger-balance query
    - Replace `SELECT ... FROM invoices WHERE status IN ('sent', 'overdue')` with ledger-balance computation
    - New query: `SELECT ReferenceNumber, SUM(CASE WHEN Debet = debtor_account THEN TransactionAmount ELSE 0 END) - SUM(CASE WHEN Credit = debtor_account THEN TransactionAmount ELSE 0 END) AS ledger_balance FROM mutaties WHERE administration = tenant GROUP BY ReferenceNumber`
    - Filter to `HAVING ledger_balance > 0` (only positive balances returned)
    - _Bug_Condition: isBugCondition(input) = ledger_balance <= 0 AND has_open_status_invoices_
    - _Expected_Behavior: Receivables endpoint returns only clients with positive ledger balance on debtor account_
    - _Preservation: Clients with genuinely outstanding balances continue to appear_
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 3.3 Enrich ledger results with invoice details via JOIN
    - JOIN back to `invoices` and `contacts` tables to provide display data (invoice numbers, dates, company names, due dates)
    - Ensure response shape is compatible with existing frontend expectations
    - Group invoice details per client alongside the ledger balance
    - _Bug_Condition: N/A (enrichment step)_
    - _Expected_Behavior: Response includes invoice details for display alongside ledger-based outstanding amounts_
    - _Preservation: Frontend display fields (invoice number, date, company, due date) remain available_
    - _Requirements: 2.1, 2.5_

  - [x] 3.4 Add automatic status reconciliation on page load
    - After computing ledger balances, UPDATE `invoices.status` to 'paid' for clients whose ledger balance is zero or negative
    - Match via JOIN on `contacts.client_id` = `mutaties.ReferenceNumber`
    - Only update invoices with status IN ('sent', 'overdue') — don't touch 'draft' or already 'paid'
    - This keeps status field consistent as secondary cache
    - _Bug_Condition: isBugCondition(input) = ledger_balance <= 0 AND has_open_status_invoices_
    - _Expected_Behavior: invoices.status updated to 'paid' when ledger confirms full settlement_
    - _Preservation: Manual Payment Check button still works, draft invoices unaffected_
    - _Requirements: 2.4_

  - [x] 3.5 Update frontend to use ledger-based totals
    - Update `ZZPDebtors.tsx` `loadData()` to display `ledger_balance` field from new endpoint response
    - Replace summation of `grand_total` with ledger-based `outstanding_amount` from backend
    - Minimal changes if backend response shape is preserved (same field names where possible)
    - _Bug_Condition: Frontend displays grand_total instead of ledger balance_
    - _Expected_Behavior: Frontend shows actual outstanding ledger balance per client_
    - _Preservation: All other frontend interactions (buttons, modals, navigation) unchanged_
    - _Requirements: 2.1, 2.5_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Ledger-Settled Clients Excluded from Receivables
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (settled clients not shown, amounts reflect ledger balance)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — settled clients excluded, partial payments show correct ledger balance)
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - Unsettled Clients Still Shown with Correct Balance
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — unsettled clients still shown, tenant isolation maintained)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite to confirm no regressions across the codebase
  - Verify bug condition test (Property 1) passes — settled clients excluded
  - Verify preservation test (Property 2) passes — unsettled clients still shown correctly
  - Verify tenant isolation holds across all scenarios
  - Verify frontend displays correct ledger-based amounts
  - Ask the user if questions arise

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3.1"] },
    { "id": 2, "tasks": ["3.2"] },
    { "id": 3, "tasks": ["3.3"] },
    { "id": 4, "tasks": ["3.4"] },
    { "id": 5, "tasks": ["3.5"] },
    { "id": 6, "tasks": ["3.6", "3.7"] },
    { "id": 7, "tasks": ["4"] }
  ]
}
```

## Notes

- The debtor account code is tenant-configurable via `zzp.debtor_account` parameter (default: `1300`)
- Property-based tests use `fast-check` (frontend) or `hypothesis` (backend/pytest) depending on where tests are placed
- The exploration test (task 1) is expected to FAIL on unfixed code — this confirms the bug exists
- The preservation test (task 2) is expected to PASS on unfixed code — this captures baseline behavior
- After implementation (task 3), both tests should PASS
- The `mutaties.ReferenceNumber` field holds the `client_id` linking transactions to specific clients
