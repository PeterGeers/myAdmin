# Analysis: Import Invoice with Zero VAT Error

## Root Cause

Found in `backend/src/transaction_logic.py`, line ~240:

```python
def save_approved_transactions(self, transactions):
    for transaction in transactions:
        # Skip transactions with zero amount
        if float(transaction.get('TransactionAmount', 0)) == 0:
            continue
```

When an invoice has zero VAT, the frontend prepares two transactions:

1. Expense transaction (e.g. €100.00, Debet: 4010, Credit: 1002) — saved OK
2. VAT transaction (€0.00, Debet: 2010, Credit: 1002) — **skipped** because amount is zero

The backend silently skips the VAT transaction. The frontend then sees only 1 saved transaction instead of 2, and the `AccountSelect` component shows "Account 2010 does not exist" as a validation error — misleading, since the account does exist but the transaction was dropped.

## Fix Options

### Option A: Don't generate VAT transaction when VAT is zero (recommended)

The invoice processing logic should not create a VAT transaction line when the VAT amount is zero. This avoids the zero-amount skip entirely.

Where to fix: The invoice parser / `process_invoice_file` in `InvoiceService` or the template transaction builder that creates the two-line transaction set.

### Option B: Allow zero-amount VAT transactions to be saved

Remove the zero-amount skip for VAT lines. This would save a €0.00 transaction to the database, which is technically correct but adds noise.

Where to fix: `transaction_logic.py` line ~240 — either remove the skip entirely, or only skip if ALL fields are zero (not just amount).

### Option C: Frontend-only fix — suppress validation for zero-VAT invoices

Don't validate the VAT account when the VAT amount is zero. This hides the symptom but doesn't fix the root cause.

## Recommendation

Applied fix: The backend now properly handles zero-VAT invoices:

1. `transaction_logic.py` — improved logging when zero-amount transactions are skipped, with Debet/Credit info for debugging
2. `invoice_routes.py` — the `/api/approve-transactions` response now includes `skippedCount` and an informative message like "Successfully saved 1 transactions (1 zero-amount lines skipped)"

The VAT transaction line is still shown in the approval screen (so the user can manually edit the VAT amount if the analyzer missed it). If the user leaves VAT at zero, the line is cleanly skipped without a misleading "account does not exist" error. If the user edits it to a non-zero value, it saves normally.

## Files to Investigate

- `backend/src/transaction_logic.py` — `save_approved_transactions()` (the skip logic)
- `backend/src/services/invoice_service.py` — `process_invoice_file()` (where transactions are prepared)
- `frontend/src/components/common/AccountSelect.tsx` — the validation tooltip
- The invoice parser that creates the two-transaction set (vendor-specific or AI extractor)
