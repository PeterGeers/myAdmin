# Bugfix Requirements Document

## Introduction

When processing invoices via AI extraction, the system generates a VAT (BTW) transaction record with an incorrect amount that contradicts the parsed invoice data. The AI correctly parses the invoice and returns `vat_amount: 0.0`, yet the system produces a BTW record with €6.37 — a stale amount from a previous invoice for the same vendor. In a financial administration system, generating a transaction with an amount that doesn't match the parsed source data is a data integrity violation.

The core issue: the system discards the explicitly parsed VAT amount (€0.00) and substitutes a historical template value. The parsed vendor data is the source of truth — the system must use it, not ignore it.

**Two defects are at play:**

1. **VAT amount not propagated:** In `invoice_service.py` (template path), `vendor_data` is built from the formatted `transactions` list rather than from the raw AI extraction result. When VAT is €0.00, no VAT transaction exists in the list, so `vat_amount` is never set in `vendor_data`.

2. **Unsafe template fallback:** In `transaction_logic.py` `prepare_new_transactions`, when `vat_amount` is missing from `vendor_data`, the method falls back to the template's historical amount — silently using a value that has no relation to the current invoice.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the AI extraction returns vat_amount €0.00 AND the formatted transactions list contains no VAT transaction AND there are previous template transactions for the vendor THEN the system generates a BTW record using the template's historical VAT amount instead of the parsed €0.00

1.2 WHEN building vendor_data for the template path THEN the system only sets vat_amount if a second transaction with "VAT" in the description exists in the formatted list, discarding the explicitly parsed vat_amount from the AI extraction result

1.3 WHEN prepare_new_transactions processes the second template transaction (BTW) AND vendor_data does not contain vat_amount THEN the system falls back to template.TransactionAmount without any validation that this matches the current invoice's parsed data

### Expected Behavior (Correct)

2.1 WHEN the AI extraction returns vat_amount €0.00 AND there are previous template transactions for the vendor THEN the system SHALL use €0.00 as the VAT amount for the BTW record (which will then be filtered out by the existing zero-amount skip logic in save_approved_transactions)

2.2 WHEN building vendor_data for any code path THEN the system SHALL always include vat_amount from the parsed extraction data, defaulting to 0 when no VAT information is available — never omitting the key

2.3 WHEN prepare_new_transactions processes the BTW template transaction THEN the VAT amount SHALL come from the current invoice's parsed data, never from the template's historical amount

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the AI extraction returns a non-zero vat_amount AND there are previous template transactions THEN the system SHALL CONTINUE TO generate the BTW record with the correct VAT amount from the current invoice's parsed data

3.2 WHEN the AI extraction returns a non-zero vat_amount AND there are no previous template transactions (new vendor path) THEN the system SHALL CONTINUE TO generate default transaction records with the correct VAT amount for manual entry

3.3 WHEN save_approved_transactions receives a transaction with amount 0 THEN the system SHALL CONTINUE TO skip that transaction silently (existing zero-amount filter)

3.4 WHEN the template has Debet/Credit account assignments for the BTW record THEN the system SHALL CONTINUE TO use those account assignments for non-zero VAT records

3.5 WHEN vendor_data contains booking-specific fields (accommodation_name, commission_type, invoice_number) THEN the system SHALL CONTINUE TO use those for description and reference formatting
