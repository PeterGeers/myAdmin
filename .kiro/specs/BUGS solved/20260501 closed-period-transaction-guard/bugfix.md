# Bugfix Requirements Document

## Introduction

When importing invoices (or booking transactions through any other path), the system allows transactions to be saved with a `TransactionDate` that falls within an already closed fiscal year. The `year_closure_status` table tracks which years have been closed, and the `_is_year_closed()` check already exists in `YearEndClosureService`, but no validation is performed in the transaction saving pipeline. This means users can accidentally corrupt closed-period accounting data, undermining the integrity of year-end closures.

All transaction saving flows are affected: invoice approval (`/api/approve-transactions`), invoice booking (outgoing, incoming, credit notes via `InvoiceBookingHelper`), and banking import (`BankingProcessor.save_approved_transactions`). The central fix point is `TransactionLogic.save_approved_transactions()`, which is the shared method used by invoice approval and invoice booking, plus `BankingProcessor.save_approved_transactions()` which has its own implementation.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user approves transactions via `/api/approve-transactions` with a `TransactionDate` in a closed fiscal year THEN the system saves the transaction to the `mutaties` table without any validation or error

1.2 WHEN `InvoiceBookingHelper.book_outgoing_invoice()` books an outgoing invoice with an `invoice_date` in a closed fiscal year THEN the system saves the transaction to the `mutaties` table without any validation or error

1.3 WHEN `InvoiceBookingHelper.book_incoming_invoice()` books an incoming invoice with an `invoice_date` in a closed fiscal year THEN the system saves the transaction to the `mutaties` table without any validation or error

1.4 WHEN `InvoiceBookingHelper.book_credit_note()` books a credit note with an `invoice_date` in a closed fiscal year THEN the system saves the transaction to the `mutaties` table without any validation or error

1.5 WHEN `BankingProcessor.save_approved_transactions()` imports banking transactions with a `TransactionDate` in a closed fiscal year THEN the system saves the transaction to the `mutaties` table without any validation or error

### Expected Behavior (Correct)

2.1 WHEN a user approves transactions via `/api/approve-transactions` with a `TransactionDate` in a closed fiscal year THEN the system SHALL reject the transaction and return a clear error message indicating the period is closed

2.2 WHEN `InvoiceBookingHelper.book_outgoing_invoice()` attempts to book an outgoing invoice with an `invoice_date` in a closed fiscal year THEN the system SHALL raise a validation error before any database insert occurs

2.3 WHEN `InvoiceBookingHelper.book_incoming_invoice()` attempts to book an incoming invoice with an `invoice_date` in a closed fiscal year THEN the system SHALL raise a validation error before any database insert occurs

2.4 WHEN `InvoiceBookingHelper.book_credit_note()` attempts to book a credit note with an `invoice_date` in a closed fiscal year THEN the system SHALL raise a validation error before any database insert occurs

2.5 WHEN `BankingProcessor.save_approved_transactions()` attempts to import banking transactions with a `TransactionDate` in a closed fiscal year THEN the system SHALL reject those transactions and return a clear error message indicating the period is closed

2.6 WHEN a batch of transactions contains a mix of transactions in open and closed periods THEN the system SHALL reject the entire batch and identify which transactions have dates in closed periods

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user approves transactions with a `TransactionDate` in an open (non-closed) fiscal year THEN the system SHALL CONTINUE TO save the transaction successfully

3.2 WHEN `InvoiceBookingHelper` books invoices or credit notes with dates in open fiscal years THEN the system SHALL CONTINUE TO save the transactions successfully

3.3 WHEN `BankingProcessor` imports banking transactions with dates in open fiscal years THEN the system SHALL CONTINUE TO save the transactions successfully

3.4 WHEN zero-amount transactions are submitted (regardless of date) THEN the system SHALL CONTINUE TO skip them silently as before

3.5 WHEN the `year_closure_status` table has no entries for an administration THEN the system SHALL CONTINUE TO allow all transactions (no years are closed)

3.6 WHEN the year-end closure process itself creates closure transactions and opening balance entries (with dates like `{year}-12-31` and `{year+1}-01-01`) THEN the system SHALL CONTINUE TO allow these internal bookings regardless of closure status
