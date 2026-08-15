# Bugfix Requirements Document

## Introduction

The Debtors & Creditors overview in the ZZP module incorrectly shows invoices as "overdue" even when matching bank payments already exist in the `mutaties` table. This affects the accuracy of the receivables overview and creates confusion for users who see outstanding balances that have already been settled. The root cause is threefold: payment reconciliation only runs on manual trigger (not on page load), the receivables query relies solely on `invoices.status` rather than the actual ledger balance on account 1600, and the payment matching logic cannot handle combined payments that cover multiple invoices.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a bank payment exists in `mutaties` that credits account 1600 (debtors) for the full amount of an invoice AND the user loads the Debtors & Creditors page THEN the system still displays that invoice as "overdue" because `invoices.status` was never updated to 'paid'

1.2 WHEN a single bank payment covers multiple invoices (combined payment) AND the total bank amount equals the sum of those invoices THEN the system cannot match the payment because `PaymentCheckHelper._match_invoice()` compares the bank transaction amount against each individual invoice's `grand_total` separately

1.3 WHEN the Debtors & Creditors page loads THEN the system automatically calls `markOverdue()` to flag past-due invoices but does NOT automatically run payment reconciliation, creating a one-directional status update that only marks invoices as overdue but never resolves them

1.4 WHEN the receivables endpoint `/api/zzp/debtors/receivables` is called THEN the system queries `WHERE status IN ('sent', 'overdue')` on the invoices table without checking whether offsetting credit entries on account 1600 already exist in the ledger

### Expected Behavior (Correct)

2.1 WHEN the Debtors & Creditors page is opened THEN the system SHALL compute outstanding balances directly from the transaction table (`mutaties`), using the ledger balance on account 1600 per client reference as the single source of truth — the `invoices.status` field SHALL NOT be used to determine what is shown as outstanding

2.2 WHEN the ledger balance for a client on account 1600 is zero (sum of debits equals sum of credits) THEN the system SHALL NOT display any invoices for that client in the receivables overview, regardless of `invoices.status`

2.3 WHEN a single bank payment covers multiple invoices (combined payment) AND the total bank amount equals the sum of those invoices THEN the system SHALL correctly reflect this in the ledger balance — no special matching logic is needed because the ledger naturally nets debits and credits per client

2.4 WHEN the Debtors & Creditors page is opened THEN the system SHALL also update `invoices.status` to 'paid' for any invoices whose client ledger balance on account 1600 shows full settlement — this keeps the status field consistent as a secondary cache, but the displayed data SHALL always be driven by the ledger

2.5 WHEN the receivables endpoint is called THEN the system SHALL return only clients with a positive ledger balance on account 1600 (debit sum > credit sum), with the outstanding amount being the actual ledger balance rather than `invoices.grand_total`

### Unchanged Behavior (Regression Prevention)

3.1 WHEN an invoice has no matching payment in `mutaties` (no credit entry on account 1600 for that client) THEN the system SHALL CONTINUE TO display it as outstanding with correct overdue status based on due date

3.2 WHEN an invoice has only a partial payment (ledger balance on account 1600 is positive but less than original invoice total) THEN the system SHALL CONTINUE TO display the client as having an outstanding balance (showing the actual remaining ledger balance)

3.3 WHEN the user manually clicks the "Payment Check" button THEN the system SHALL CONTINUE TO run the explicit payment matching process and update invoice statuses — this remains as a convenience action for bulk status updates

3.4 WHEN an invoice with status 'sent' is not yet past due date THEN the system SHALL CONTINUE TO display it with correct status in the receivables overview (only if the client has a positive ledger balance)

3.5 WHEN invoices are correctly marked as 'paid' in the database AND the ledger balance confirms settlement THEN the system SHALL CONTINUE TO exclude them from the receivables overview

3.6 WHEN calculating receivables for a tenant THEN the system SHALL CONTINUE TO isolate data by `administration` column and not show cross-tenant data
