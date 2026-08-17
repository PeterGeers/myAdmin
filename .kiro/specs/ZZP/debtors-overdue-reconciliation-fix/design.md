# Debtors Overdue Reconciliation Fix — Bugfix Design

## Overview

The Debtors & Creditors page in the ZZP module incorrectly shows invoices as "overdue" even when matching bank payments already exist in `mutaties`. The root cause is that the receivables endpoint (`/api/zzp/debtors/receivables`) queries `invoices.status` rather than computing outstanding balances from the actual ledger (account 1300 — the tenant's debtor account). This fix replaces the status-driven query with a ledger-balance-driven query that uses `mutaties` as the single source of truth, and adds automatic invoice status reconciliation on page load.

## Glossary

- **Bug_Condition (C)**: The condition where an invoice appears as outstanding in the receivables overview despite having a zero or negative ledger balance on the debtor account for that client
- **Property (P)**: The receivables endpoint returns only clients with a positive debtor-account ledger balance, showing the actual outstanding amount from the ledger
- **Preservation**: Mouse-click behavior, manual Payment Check button, overdue marking, tenant isolation, and partial-payment display must remain unchanged
- **mutaties**: The transactions table — single source of truth for all financial entries
- **vw_mutaties**: View over `mutaties` providing filtered access to transactions
- **debtor_account**: The tenant-configurable account code (typically `1300`) that represents accounts receivable. Configured via `zzp.debtor_account` parameter
- **ReferenceNumber**: Field in `mutaties` that holds the `client_id` of the contact, linking transactions to specific clients
- **ledger balance**: For a given client on the debtor account: `SUM(amount WHERE Debet = debtor_account) - SUM(amount WHERE Credit = debtor_account)`, filtered by `ReferenceNumber = client_id`

## Bug Details

### Bug Condition

The bug manifests when a bank payment exists in `mutaties` that credits the debtor account for a client, but the receivables page still shows that client's invoices as outstanding. This happens because `get_receivables()` queries `invoices WHERE status IN ('sent', 'overdue')` without consulting the ledger. Additionally, `mark_overdue()` runs on page load but `run_payment_check()` does not, creating a one-directional status update that only marks invoices as overdue but never resolves them.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type { tenant, client_id, debtor_account }
  OUTPUT: boolean

  LET debit_sum = SUM(TransactionAmount) FROM mutaties
    WHERE administration = tenant
      AND ReferenceNumber = client_id
      AND Debet = debtor_account

  LET credit_sum = SUM(TransactionAmount) FROM mutaties
    WHERE administration = tenant
      AND ReferenceNumber = client_id
      AND Credit = debtor_account

  LET ledger_balance = debit_sum - credit_sum

  LET has_open_status_invoices = EXISTS(
    SELECT 1 FROM invoices i
    JOIN contacts c ON i.contact_id = c.id
    WHERE i.administration = tenant
      AND c.client_id = client_id
      AND i.status IN ('sent', 'overdue')
  )

  RETURN ledger_balance <= 0 AND has_open_status_invoices
END FUNCTION
```

### Examples

- **Example 1**: Invoice INV-2026-0001 for €1,210.00 sent to client "ACME". Bank payment of €1,210.00 exists in `mutaties` crediting account 1300 with ReferenceNumber="ACME". Ledger balance = €1,210.00 - €1,210.00 = €0.00. **Expected**: Not shown. **Actual**: Shown as overdue (€1,210.00 outstanding).

- **Example 2**: Two invoices INV-0001 (€500) and INV-0002 (€700) sent to client "BETA". Single bank payment of €1,200.00 credits account 1300. Ledger balance = €1,200.00 - €1,200.00 = €0.00. **Expected**: Not shown. **Actual**: Both shown as overdue because `_match_invoice()` compares €1,200 against each individual invoice total and finds no exact match.

- **Example 3**: Invoice INV-0003 for €1,000.00 sent to client "GAMMA". Partial payment of €600 received. Ledger balance = €1,000.00 - €600.00 = €400.00. **Expected**: Shown with €400.00 outstanding. **Actual**: Shown with €1,000.00 outstanding (uses `grand_total` instead of ledger balance).

- **Example 4**: Invoice INV-0004 for €800.00 sent to client "DELTA". No payment received. Ledger balance = €800.00 - €0.00 = €800.00 > 0. **Expected**: Shown with €800.00 outstanding. **Actual**: Correctly shown (non-buggy case).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Mouse clicks on action buttons (Send Reminder, Payment Check, Check Overdue) must continue to work exactly as before
- The manual "Payment Check" button must continue to run `PaymentCheckHelper.run_payment_check()` and update invoice statuses
- The "Check Overdue" button must continue to call `mark_overdue()` explicitly
- Tenant isolation via `administration` column must remain enforced
- The aging analysis endpoint must continue to function
- The payables (creditors) endpoint must continue to function unchanged
- Invoice send/booking flow that creates debit entries in `mutaties` must remain unchanged

**Scope:**
All inputs that do NOT involve the receivables overview computation should be completely unaffected by this fix. This includes:

- The payables endpoint (`/api/zzp/debtors/payables`)
- The aging endpoint (`/api/zzp/debtors/aging`)
- The send reminder endpoint
- Invoice creation, editing, sending, and PDF generation
- All other ZZP module functionality (time tracking, contacts, products)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Status-driven query instead of ledger-driven query**: `get_receivables()` in `zzp_debtor_routes.py` queries `invoices WHERE status IN ('sent', 'overdue')` and sums `grand_total`. It never checks `mutaties` for offsetting credit entries. The ledger is ignored entirely.

2. **No automatic reconciliation on page load**: The frontend `loadData()` calls `markOverdue()` silently before loading data, but does NOT call `runPaymentCheck()`. This means invoices only get marked overdue (one direction) but never automatically resolved when payments arrive.

3. **Payment matching cannot handle combined payments**: `PaymentCheckHelper._match_invoice()` compares each bank transaction amount against individual invoice `grand_total` values. A single payment covering multiple invoices (e.g., €1,200 for two invoices of €500 + €700) cannot match because €1,200 ≠ €500 and €1,200 ≠ €700.

4. **Outstanding amount uses `grand_total` instead of ledger balance**: Even if payment matching were improved, the displayed amount would still be `grand_total` rather than the actual remaining balance from the ledger.

## Correctness Properties

Property 1: Bug Condition — Ledger-Settled Clients Excluded from Receivables

_For any_ client where the ledger balance on the debtor account is zero or negative (sum of debit entries equals or is exceeded by sum of credit entries for that client's ReferenceNumber), the fixed receivables endpoint SHALL NOT include that client in the response, regardless of `invoices.status`.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation — Unsettled Clients Still Shown with Correct Balance

_For any_ client where the ledger balance on the debtor account is positive (debit sum exceeds credit sum), the fixed receivables endpoint SHALL include that client with the outstanding amount equal to the actual ledger balance, preserving the ability to see genuinely outstanding receivables.

**Validates: Requirements 3.1, 3.2, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/src/routes/zzp_debtor_routes.py`

**Function**: `get_receivables()`

**Specific Changes**:

1. **Replace the status-driven query with a ledger-balance query**: Instead of querying `invoices WHERE status IN ('sent', 'overdue')`, query `mutaties` directly to compute per-client ledger balances on the debtor account. Group by `ReferenceNumber` (which holds `client_id`) and compute `SUM(CASE WHEN Debet = debtor_account THEN TransactionAmount ELSE 0 END) - SUM(CASE WHEN Credit = debtor_account THEN TransactionAmount ELSE 0 END)` per client.

2. **Filter to positive balances only**: Only return clients where the computed ledger balance is positive (> 0), satisfying requirements 2.2 and 2.5.

3. **Resolve debtor account from tenant parameters**: Look up the tenant's configured `zzp.debtor_account` parameter (typically `1300`) to use in the ledger query.

4. **Enrich with invoice details**: After computing outstanding balances from the ledger, JOIN back to `invoices` and `contacts` to provide the display data (invoice numbers, dates, company names) needed by the frontend.

5. **Add automatic status reconciliation**: After computing ledger balances, update `invoices.status` to `'paid'` for clients whose ledger balance is zero, keeping the status field consistent as a secondary cache (requirement 2.4).

**File**: `frontend/src/pages/ZZPDebtors.tsx`

**Function**: `loadData()`

**Specific Changes**:

6. **Update frontend to use ledger-based totals**: The frontend currently sums `grand_total` from the grouped response. After the backend change, it should display the `ledger_balance` field returned by the new endpoint response. Minimal frontend changes needed if the backend response shape is preserved.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call the current `get_receivables()` route handler with a database containing both invoices (status='sent'/'overdue') and matching credit entries in `mutaties` on the debtor account. Run these tests on the UNFIXED code to observe that settled invoices still appear in the response.

**Test Cases**:

1. **Fully Paid Invoice Test**: Create invoice + matching credit entry in mutaties. Call `get_receivables()`. Assert invoice still appears (will fail on unfixed code — it WILL appear, confirming the bug).
2. **Combined Payment Test**: Create two invoices + single credit entry covering both. Call `get_receivables()`. Assert both invoices appear (will fail on unfixed code — they WILL appear).
3. **Partial Payment Test**: Create invoice + partial credit entry. Call `get_receivables()`. Assert the displayed amount equals `grand_total` rather than ledger remainder (will confirm bug on unfixed code).
4. **No Payment Test**: Create invoice with no credit entries. Call `get_receivables()`. Assert invoice appears with correct total (should pass — non-buggy case).

**Expected Counterexamples**:

- Fully settled invoices appear in receivables output despite zero ledger balance
- Outstanding amounts show `grand_total` instead of actual ledger balance
- Possible causes: query only checks `invoices.status`, never consults `mutaties`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := get_receivables_fixed(input.tenant)
  LET client_in_result = any(r.contact.client_id == input.client_id for r in result.data)
  ASSERT NOT client_in_result  -- settled clients excluded
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  -- Client has positive ledger balance (genuinely outstanding)
  result := get_receivables_fixed(input.tenant)
  LET client_entry = find(r.contact.client_id == input.client_id for r in result.data)
  ASSERT client_entry IS NOT NULL
  ASSERT client_entry.total == ledger_balance(input.tenant, input.client_id)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many combinations of invoice amounts and payment amounts automatically
- It catches edge cases (rounding, zero amounts, multiple invoices per client) that manual tests might miss
- It provides strong guarantees that genuinely outstanding balances are always displayed correctly

**Test Plan**: Observe behavior on UNFIXED code first for clients with no payments (these should be displayed correctly), then write property-based tests capturing that positive-balance clients always appear.

**Test Cases**:

1. **Unpaid Invoice Preservation**: Verify that invoices with no corresponding credit entries continue to appear with correct amounts
2. **Partial Payment Display**: Verify that partially paid clients appear with the correct remaining ledger balance
3. **Tenant Isolation Preservation**: Verify that receivables for tenant A never include data from tenant B
4. **Multi-Invoice Client**: Verify that a client with multiple outstanding invoices shows correct aggregate ledger balance

### Unit Tests

- Test ledger balance computation with exact payment amounts
- Test ledger balance computation with combined payments
- Test ledger balance computation with partial payments
- Test that zero-balance clients are excluded from results
- Test that negative-balance clients (overpayment) are excluded
- Test tenant isolation in the ledger query
- Test debtor account parameter resolution

### Property-Based Tests

- Generate random invoice amounts and payment amounts, verify that the receivables response correctly reflects the ledger balance (positive → shown, zero/negative → excluded)
- Generate random multi-client scenarios with varied payment states, verify aggregate totals are correct
- Generate random tenant configurations, verify cross-tenant isolation holds

### Integration Tests

- Test full flow: create invoice → send (books debit entry) → simulate bank payment (credit entry) → load receivables → verify exclusion
- Test combined payment flow: create multiple invoices → single credit entry → verify correct ledger balance shown
- Test status reconciliation: verify `invoices.status` is updated to 'paid' when ledger shows zero balance on page load
