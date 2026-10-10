# Implementation Plan: Transactions Export

## Overview

A tight, frontend-only change in two parts, both converging on the shared `frontend/src/utils/csvExport.ts` utility (already-tested RFC-4180 escaping + UTF-8 BOM via `downloadCsv`).

- **Part (a)** adds an "Export to CSV" control to `BankingMutatiesTab.tsx` that exports the **full** `processedData` (not the display-limited `displayedData`).
- **Part (b)** standardizes `MutatiesReport.tsx`'s hand-rolled `exportMutatiesCsv` onto the shared utility while preserving the exact headers, column order, filename, and adding the BOM — pinning the Debit=`Reknum` / Credit=`AccountName` contract in a pure, tested helper.

Tasks are ordered so pure helpers and their unit tests land **before** component wiring (test-before-migrate). No backend change is required — the `/api/reports/mutaties-table` SELECT already returns `Reknum` and `AccountName`. Testing follows the repo's Vitest + RTL conventions; pure helpers are unit-tested without rendering. Property-based tests are marked optional (`*`) given the ASAP scope.

## Tasks

- [x] 1. Part (a) — Transactions table export
  - [x] 1.1 Create pure CSV helper for the transactions table
    - Create `frontend/src/components/banking/transactionsCsv.ts`
    - Export `CsvColumn` interface, `transactionsCsvColumns(headers)` returning the ordered 8-column config (TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, Debet, Credit, ReferenceNumber, Administration), `buildTransactionsCsv(columns, rows)` delegating to `generateCsvFromObjects`, and `transactionsCsvFilename(now?)` producing `transactions-YYYY-MM-DD.csv`
    - Read RAW field values only (no locale formatting); escaping handled by the shared util
    - _Requirements: 2.1, 2.4, 3.1, 3.3, 4.1_

  - [x] 1.2 Write unit tests for the transactions CSV helper
    - Create `frontend/src/components/banking/transactionsCsv.test.ts`
    - Mapping completeness + raw values: header line equals configured headers in order; every data line contains all 8 columns; `TransactionAmount`/`TransactionDate` cells equal `String(raw)` with no `€`, thousands separators, or locale date output — **Property 1 — Validates: Requirements 2.1, 2.4, 3.3**
    - Full-dataset count: build with 250 rows (> display limit) and assert exactly 250 data lines + 1 header — **Property 2 — Validates: Requirements 2.2**
    - Order preservation: shuffled input, assert `TransactionNumber` column sequence equals input order — **Property 3 — Validates: Requirements 2.3**
    - RFC-4180 escaping: fields with comma, embedded double quote, and newline are quoted with internal quotes doubled (references shared `csvExport.ts` as the escaping impl under test) — **Property 4 — Validates: Requirements 4.1, 4.2**
    - Filename: `transactionsCsvFilename(new Date('2026-02-03'))` returns `transactions-2026-02-03.csv`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.3, 4.1, 4.2_

  - [x] 1.3 Add banking i18n keys for the export control
    - Add the nested `mutaties.export` block to `frontend/src/locales/en/banking.json` and `frontend/src/locales/nl/banking.json` (en + nl values per design: `exportToCsv`, `trxNumber`, `date`, `description`, `amount`, `debit`, `credit`, `reference`, `administration`)
    - _Requirements: 1.3, 3.2_

  - [x] 1.4 Wire the "Export to CSV" button into BankingMutatiesTab
    - In `frontend/src/components/banking/BankingMutatiesTab.tsx`, add a `handleExportCsv` `useCallback` reading the FULL `processedData`, resolving headers via `t('mutaties.export.*')`, building with `buildTransactionsCsv`, and downloading via `downloadCsv(csv, transactionsCsvFilename())`; early-return when `processedData` is empty
    - Add the `Button` into the existing `HStack` beside "Add new record": `size="sm"`, distinct `colorScheme="blue"`, `isDisabled` when `processedData.length === 0`, `data-testid="export-transactions-csv-button"`, i18n label `mutaties.export.exportToCsv`
    - Do NOT add row-selection checkboxes; leave table markup and on-screen cell formatting unchanged
    - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 7.1, 7.2_

  - [x] 1.5 Add lightweight render test for the export button
    - Render `BankingMutatiesTab` with sample data: assert `data-testid="export-transactions-csv-button"` is present and labelled from the `banking` namespace
    - Render with empty `mutaties`: assert the button is disabled
    - Assert no checkbox inputs were added to the table
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Checkpoint — Part (a) complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Part (b) — FIN report export standardization
  - [x] 3.1 Create pure CSV helper for the report export
    - Create `frontend/src/components/reports/mutatiesCsv.ts`
    - Export `MutatiesCsvRow` interface, `mutatiesCsvHeaders(labels)` returning the fixed order `[date, reference, description, amount, debit, credit, administration]`, and `mapMutatiesRow(row)` returning cells in matching order with Debit = `row.Reknum` (account code) and Credit = `row.AccountName` (account name), RAW values only
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.2, 8.1_

  - [x] 3.2 Write unit tests for the report CSV helper
    - Create `frontend/src/components/reports/mutatiesCsv.test.ts`
    - Debit/Credit contract: `mapMutatiesRow(row)[4] === row.Reknum` and `mapMutatiesRow(row)[5] === row.AccountName` — **Property 5 — Validates: Requirements 5.1, 5.2, 5.4, 6.2**
    - Header order: `mutatiesCsvHeaders(labels)` returns `[date, reference, description, amount, debit, credit, administration]`; `mapMutatiesRow` cells match that order — _Requirements: 5.3, 8.1_
    - Raw values: Amount cell equals the raw number, Date cell equals the raw `TransactionDate` string (no `formatCurrency`/`formatDate`) — _Requirements: 5.4_
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.2_

  - [x] 3.3 Refactor exportMutatiesCsv onto the shared utility
    - In `frontend/src/components/reports/MutatiesReport.tsx`, rewrite `exportMutatiesCsv` to use `mutatiesCsvHeaders` + `mapMutatiesRow` + `generateCsv` + `downloadCsv`
    - Preserve the exact header labels/order (`tables.date`, `tables.reference`, `tables.description`, `tables.amount`, `tables.debit`, `tables.credit`, `filters.administration`), the raw-value column order, and the filename `mutaties-{dateFrom}-{dateTo}.csv`; the BOM is now added via `downloadCsv`
    - Keep the existing `data-testid="export-csv-button"` test green (button + handler wiring preserved)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 8.1, 8.2_

- [x] 4. Final verification
  - Run frontend lint and the affected Vitest suites (`transactionsCsv.test.ts`, `mutatiesCsv.test.ts`, `BankingMutatiesTab`, `MutatiesReport.test.tsx`) plus the typecheck/build; confirm all green
  - _Requirements: 4.1, 4.2, 4.3, 6.2, 8.1, 8.2_

## Notes

- **No backend change.** `/api/reports/mutaties-table` (`get_mutaties_table`) already SELECTs `Reknum` and `AccountName` from `vw_mutaties`, so the Debit=code / Credit=name contract holds end-to-end. A backend correction is a **contingency only** per Requirement 6.3 — create a backend task **only if** investigation shows the deployed Debit/Credit does not equal code/name. The report mapping unit test (3.2) is the regression guard.
- Tasks marked with `*` are optional and can be skipped for the ASAP deploy; given scope, property-based tests are intentionally kept as a small hand-rolled generator rather than a PBT library.
- Tasks are ordered helpers → tests → component wiring (test-before-migrate), so no orphaned code is left unintegrated.
- The shared `frontend/src/utils/csvExport.ts` escaping/BOM behavior is treated as an already-tested dependency, not re-tested here.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "3.1"] },
    { "id": 1, "tasks": ["1.2", "1.4", "3.2", "3.3"] },
    { "id": 2, "tasks": ["1.5"] }
  ]
}
```
