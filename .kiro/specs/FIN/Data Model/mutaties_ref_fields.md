# Mutaties Reference Fields — Usage Guide

**Date:** 2026-03-26
**Table:** `mutaties` (and `mutaties_test`)

The `mutaties` table has 4 reference fields (`Ref1` through `Ref4`) plus `ReferenceNumber`. All fields are context-sensitive — their meaning depends on the source of the transaction.

---

## ReferenceNumber — Invoice reconciliation and sub-summaries

The `ReferenceNumber` field serves two key purposes:

**1. Invoice reconciliation** — The "Check by Reference Number" function (`GET /api/reporting/check-reference`) verifies that all invoices are booked and paid:

- Groups all transactions by `ReferenceNumber`
- Calculates `SUM(Amount)` per reference
- Zero balance = invoice fully paid (debet + payment cancel out)
- Non-zero balance = invoice outstanding (unpaid or partially paid)
- Used for debtor/creditor reconciliation (accounts 1300 Debiteuren, 1600 Crediteuren)

**2. Sub-summaries at all levels** — `ReferenceNumber` enables grouping and subtotals throughout the reporting system:

- Group transactions by reference in any report (P&L, balance sheet, actuals)
- Drill down from account totals → reference subtotals → individual transactions
- Filter reports by reference to see all related bookings (e.g., all entries for one invoice, one import batch, one BTW period)

This is why `ReferenceNumber` must never be overwritten — it's the primary grouping and reconciliation key across the entire system.

---

## Field overview

| Field             | Type    | Indexed                   | Purpose                                                                |
| ----------------- | ------- | ------------------------- | ---------------------------------------------------------------------- |
| `ReferenceNumber` | VARCHAR | Yes                       | Primary reference — invoice number, import batch, or source identifier |
| `Ref1`            | VARCHAR | Yes (composite with Ref2) | Context-sensitive — meaning depends on transaction source              |
| `Ref2`            | VARCHAR | Yes (composite with Ref1) | Context-sensitive — meaning depends on transaction source              |
| `Ref3`            | VARCHAR | No                        | Context-sensitive — meaning depends on transaction source              |
| `Ref4`            | VARCHAR | No                        | Context-sensitive — meaning depends on transaction source              |

---

## Usage by transaction source

| Source                   | ReferenceNumber              | Ref1                   | Ref2                                                    | Ref3                | Ref4             |
| ------------------------ | ---------------------------- | ---------------------- | ------------------------------------------------------- | ------------------- | ---------------- |
| Banking — Rabobank       | `Rabo YYYY-MM-DD`            | IBAN                   | Sequence number (integer)                               | Balance amount      | —                |
| Banking — Revolut        | `Revolut YYYY-MM-DD`         | IBAN                   | `description_balance_datetime` (3 parts, `_` separated) | Balance amount      | —                |
| Invoice processing (PDF) | Invoice number / folder name | —                      | —                                                       | Google Drive URL    | Invoice filename |
| STR channel import       | Booking reference            | `BnB YYYYMM` (period)  | —                                                       | —                   | —                |
| BTW aangifte             | `BTW`                        | `BTW aangifte {admin}` | `YYYY-Q{n}` (period)                                    | Payment instruction | —                |
| Toeristenbelasting       | `Toeristenbelasting`         | Period reference       | —                                                       | —                   | —                |
| Year-end closure         | `Jaarafsluiting YYYY`        | —                      | —                                                       | —                   | —                |
| Asset depreciation       | `Asset-{id}`                 | `ASSET-{asset_id}`     | Period (e.g., `2026-Q1`)                                | —                   | —                |
| Asset purchase           | Invoice number               | `ASSET-{asset_id}`     | —                                                       | Google Drive URL    | Invoice filename |
| Asset disposal           | `Disposal-{id}`              | `ASSET-{asset_id}`     | —                                                       | —                   | —                |

---

## Key patterns

### Banking transactions — Rabobank

- `Ref1` = IBAN of the bank account
- `Ref2` = sequence number from the bank (integer)
- `Ref3` = balance amount after transaction
- Gap detection uses `Ref2`: `WHERE Ref1 = {iban} ORDER BY CAST(Ref2 AS UNSIGNED)` — checks for non-consecutive sequence numbers

### Banking transactions — Revolut

- `Ref1` = IBAN of the bank account
- `Ref2` = composite string: `description_balance_datetime` (3 parts separated by `_`)
  - Part 1: description
  - Part 2: balance amount
  - Part 3: datetime (`YYYY-MM-DD HH:MM:SS`)
- `Ref3` = balance amount (used for running balance validation)
- Balance gap detection compares calculated running balance against `Ref3`

### Invoice transactions

- `Ref3` = Google Drive URL to the invoice PDF
- `Ref4` = filename of the invoice
- `ReferenceNumber` = invoice number or folder name

### STR transactions

- `Ref1` = period identifier like `BnB 202603`
- Used for grouping all STR transactions for a given month

### BTW transactions

- `Ref1` = `BTW aangifte {administration}`
- `Ref2` = quarter like `2026-Q1`

### Asset transactions (new)

- `Ref1` = `ASSET-{asset_id}` — links all transactions for one asset
- `Ref2` = depreciation period (e.g., `2026-Q1`, `2026-M03`)
- Query: `SELECT * FROM mutaties WHERE Ref1 = 'ASSET-42' AND administration = 'TenantName'`

---

## Rules

1. All Ref fields are context-sensitive — their meaning depends on the transaction source
2. `ReferenceNumber` is the primary identifier — never overwrite it for asset linking
3. For Rabo banking: `Ref2` = sequence number (gap detection), `Ref3` = balance
4. For Revolut banking: `Ref2` = composite string (description + balance + datetime), `Ref3` = balance
5. For invoice transactions: `Ref3` = Google Drive URL, `Ref4` = filename
6. For asset transactions: `Ref1` uses the pattern `ASSET-{id}` to link to the `assets` table
7. The `Ref1 + Ref2` composite index exists for performance — used by banking lookups
