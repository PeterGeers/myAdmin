# Implementation Plan

## Phase 1: BnbReturningGuestsReport — Add Framework (Simplest)

- [x] 1. Migrate BnbReturningGuestsReport to Table Filter Framework v2
  - **File**: `frontend/src/components/reports/BnbReturningGuestsReport.tsx`
  - **Estimated time**: 2–3 hours
  - This is the simplest migration — no existing filters/sort to remove, just add the framework

  - [x] 1.1 Add `useFilterableTable` hook with INITIAL_FILTERS
    - Import `useFilterableTable` from `../../hooks/useFilterableTable`
    - Define `INITIAL_FILTERS: Record<string, string> = { guestName: "", aantal: "" }`
    - Initialize hook with `returningGuests` data, `defaultSort: { field: "aantal", direction: "desc" }`
    - _Requirements: 2.4_

  - [x] 1.2 Replace `<Th>` elements with `<FilterableHeader>` components
    - Import `FilterableHeader` from `../filters/FilterableHeader`
    - Replace guest name `<Th>` with `<FilterableHeader label={t('tables.guestName')} filterValue={filters.guestName} onFilterChange={(v) => setFilter('guestName', v)} sortable sortDirection={...} onSort={...} />`
    - Replace count `<Th>` with `<FilterableHeader label={t('bnb.count')} filterValue={filters.aantal} onFilterChange={(v) => setFilter('aantal', v)} sortable sortDirection={...} onSort={...} isNumeric />`
    - Keep expand/collapse `<Th>` as plain (no filter/sort)
    - _Requirements: 2.4_

  - [x] 1.3 Update rendering to use `processedData`
    - Replace `returningGuests.map(...)` with `processedData.map(...)` in the table body
    - Row-click `handleGuestClick` stays unchanged on `<Tr onClick>`
    - Update guest count display to use `processedData.length`
    - _Preservation: Row-click expand/collapse, API fetch on mount, summary totals — all unchanged_
    - _Requirements: 2.4, 3.3_

  - [x] 1.4 Clean up unused imports
    - Remove any unused imports after migration
    - Verify component renders correctly with framework
    - _Requirements: 2.4_

---

## Phase 2: EmailLogPanel — Replace Manual Filters

- [x] 2. Migrate EmailLogPanel to Table Filter Framework v2
  - **File**: `frontend/src/components/shared/EmailLogPanel.tsx`
  - **Estimated time**: 3–4 hours
  - Replace manual `recipientFilter`/`statusFilter` useState with framework hook

  - [x] 2.1 Add `useFilterableTable` hook with INITIAL_FILTERS
    - Import `useFilterableTable` from `../../hooks/useFilterableTable`
    - Define `INITIAL_FILTERS: Record<string, string> = { recipient: "", email_type: "", subject: "", sent_by: "", status: "" }`
    - Add `administration: ""` to INITIAL_FILTERS when `mode === 'sysadmin'` (conditional)
    - Initialize hook with `logs` data, `defaultSort: { field: "created_at", direction: "desc" }`
    - _Requirements: 2.5_

  - [x] 2.2 Replace `<Th>` elements with `<FilterableHeader>` components
    - Import `FilterableHeader` from `../filters/FilterableHeader`
    - Replace Date `<Th>` with sortable-only `<FilterableHeader>` (no filter input, just sort)
    - Replace Recipient, Type, Subject, Sent by, Status `<Th>` with full `<FilterableHeader>` (filter + sort)
    - Conditionally render Tenant `<FilterableHeader>` when `mode === 'sysadmin'`
    - Error column stays as plain `<Th>` (no filter/sort needed)
    - _Requirements: 2.5, 3.9_

  - [x] 2.3 Apply dark theme styling
    - Add `bg="gray.800"` to table container `<Box>`
    - Ensure `<Thead>` uses `bg="gray.700"` (via FilterableHeader)
    - Add `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` to `<Tr>` rows
    - Ensure `color="white"` on `<Td>` elements (currently `color="gray.300"` — keep as-is for consistency with existing style)
    - _Requirements: 2.5_

  - [x] 2.4 Remove old filter/sort boilerplate
    - Remove `useState` for `recipientFilter` and `statusFilter`
    - Remove `<InputGroup>` with `<SearchIcon>` and `<Input>` for recipient filter
    - Remove `<Select>` for status filter (replaced by FilterableHeader text search on status column)
    - Remove status filtering logic from `fetchLogs` callback — all filtering is now client-side via hook
    - Remove `recipientFilter` from `fetchLogs` API params — fetch all logs up to `limit`, filter client-side
    - Keep limit `<Select>` and Refresh `<Button>` above the table
    - _Requirements: 2.5_

  - [x] 2.5 Update rendering to use `processedData`
    - Replace `logs.map(...)` with `processedData.map(...)` in the table body
    - Update count display: `Showing {processedData.length} of {logs.length} log(s)`
    - _Preservation: Limit selector, sysadmin mode tenant column, tenant-scoped fetching — all unchanged_
    - _Requirements: 2.5, 3.4, 3.9_

---

## Phase 3: STRInvoice — Per-Column Filtering + Dark Theme

- [x] 3. Migrate STRInvoice to Table Filter Framework v2
  - **File**: `frontend/src/components/STRInvoice.tsx`
  - **Estimated time**: 4–5 hours
  - Replace manual single-search-box with per-column FilterableHeader, add dark theme

  - [x] 3.1 Add `useFilterableTable` hook with INITIAL_FILTERS
    - Import `useFilterableTable` from `./hooks/useFilterableTable` (adjust path)
    - Define `INITIAL_FILTERS: Record<string, string> = { reservationCode: "", guestName: "", channel: "", listing: "", checkinDate: "", nights: "", amountGross: "" }`
    - Initialize hook with `allBookings` data, `defaultSort: { field: "checkinDate", direction: "desc" }`
    - _Requirements: 2.8_

  - [x] 3.2 Replace `<Th>` elements with `<FilterableHeader>` components
    - Import `FilterableHeader` from `./components/filters/FilterableHeader` (adjust path)
    - Replace Reservation Code, Guest Name, Channel, Listing, Check-in `<Th>` with `<FilterableHeader>` (filter + sort)
    - Replace Nights, Amount `<Th>` with `<FilterableHeader isNumeric>` (filter + sort)
    - Keep Action `<Th>` as plain (no filter/sort — contains "Generate Invoice" button)
    - _Requirements: 2.8_

  - [x] 3.3 Apply dark theme styling
    - Wrap table in `<Box bg="gray.800" borderRadius="md" p={4}>`
    - Add `color="white"` to all `<Td>` elements
    - Add `_hover={{ bg: 'gray.700' }}` to `<Tr>` rows (visual consistency, no onClick on row)
    - FilterableHeader handles header bg and filter input styling automatically
    - _Requirements: 2.8_

  - [x] 3.4 Remove old filter/sort boilerplate
    - Remove `useState` for `searchQuery`
    - Remove `useState` for `searchResults` (replaced by `processedData`)
    - Remove `searchBookings` function
    - Remove manual `onChange` filter logic in the search `<Input>` (the inline `allBookings.filter(...)`)
    - Remove "Filter" and "Clear" buttons (framework handles filtering via column headers)
    - Keep `startDate`/`endDate` fields (control API data range — accepted exception)
    - Keep language `<Select>`, "Reload" button, billing modal, invoice preview modal
    - _Requirements: 2.8_

  - [x] 3.5 Update rendering to use `processedData`
    - Replace `searchResults.map(...)` with `processedData.map(...)` in the table body
    - Update count display: `Showing {processedData.length} of {allBookings.length} bookings`
    - Update "no results" condition to check `processedData.length === 0 && hasActiveFilters`
    - Per-row "Generate Invoice" button stays unchanged (accepted exception)
    - _Preservation: startDate/endDate API reload, language selector, billing modal, invoice preview, print — all unchanged_
    - _Requirements: 2.8, 3.7, 3.8_

---

## Phase 4: BnbRevenueReport — Replace Manual Filter/Sort, Remove Date Fields

- [x] 4. Migrate BnbRevenueReport to Table Filter Framework v2
  - **File**: `frontend/src/components/reports/BnbRevenueReport.tsx`
  - **Estimated time**: 5–6 hours
  - Most complex migration: replace manual filter + sort, remove date fields, keep amount selector

  - [x] 4.1 Add `useFilterableTable` hook with INITIAL_FILTERS
    - Import `useFilterableTable` from `../../hooks/useFilterableTable`
    - Define `INITIAL_FILTERS: Record<string, string> = { channel: "", listing: "", guestName: "", checkinDate: "", checkoutDate: "" }`
    - Initialize hook with `bnbData`, `defaultSort: { field: "checkinDate", direction: "desc" }`
    - _Requirements: 2.1_

  - [x] 4.2 Replace `<Th>` elements with `<FilterableHeader>` components
    - Replace Check-in, Check-out, Channel, Listing, Nights, Guest Name `<Th>` with `<FilterableHeader>` (filter + sort)
    - Replace amount columns (Gross, Net, Channel Fee, Tourist Tax, VAT) with `<FilterableHeader sortable isNumeric>` — sort-only, no filter input (conditional on `selectedAmounts`)
    - Remove inline `cursor="pointer"` + `onClick` + `↑`/`↓` text from all `<Th>` elements
    - _Requirements: 2.1, 2.3_

  - [x] 4.3 Remove date fields and old filter/sort boilerplate
    - Remove `bnbFilters.dateFrom` and `bnbFilters.dateTo` state fields
    - Remove `<Input type="date">` elements for start/end date
    - Remove `dateFrom`/`dateTo` from `fetchBnbData` API params (backend defaults to Jan 1 → today)
    - Remove `useState` for `bnbSortField`, `bnbSortDirection`, `bnbSearchFilters`
    - Remove `handleBnbSort` function entirely
    - Remove `filteredBnbData` useMemo entirely
    - Remove separate `<Card>` with raw `<Input>` filter fields (channel, listing, guestName search inputs)
    - Keep amount selector `<Menu>` above the table
    - Keep "Update BNB Data" and "Export CSV" buttons
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 4.4 Update rendering to use `processedData`
    - Replace `filteredBnbData.slice(0, 100).map(...)` with `processedData.map(...)` (framework handles display)
    - Update `exportBnbCsv` to use `processedData` instead of `filteredBnbData`
    - Update CSV filename (no longer has dateFrom/dateTo — use current date or generic name)
    - _Preservation: Amount column selector show/hide, CSV export with filtered data, channel/listing dropdown filters — all unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.6_

---

## Phase 5: Check Reference Numbers — Two Tables, Row-Click

- [x] 5. Migrate Check Reference Numbers tab to Table Filter Framework v2
  - **File**: `frontend/src/components/BankingProcessor.tsx` (Check Reference tab section)
  - **Estimated time**: 4–5 hours
  - Two tables (summary + details), replace per-row button with row-click

  - [x] 5.1 Add `useFilterableTable` hooks for both tables
    - Import `useFilterableTable` from `../hooks/useFilterableTable`
    - Summary table: `REF_SUMMARY_FILTERS = { ReferenceNumber: "", transaction_count: "", total_amount: "" }`, defaultSort `{ field: "ReferenceNumber", direction: "asc" }`
    - Details table: `REF_DETAILS_FILTERS = { TransactionNumber: "", TransactionDate: "", Amount: "", TransactionDescription: "" }`, defaultSort `{ field: "TransactionDate", direction: "desc" }`
    - Use destructured aliases: `filters: refSummaryFilters`, `filters: refDetailsFilters`, etc.
    - _Requirements: 2.6_

  - [x] 5.2 Replace `<Th>` elements with `<FilterableHeader>` in both tables
    - Summary table: Replace Reference, Count, Total Amount `<Th>` with `<FilterableHeader>` (filter + sort)
    - Remove "Actions" `<Th>` column entirely
    - Details table: Replace Transaction Number, Date, Amount, Description `<Th>` with `<FilterableHeader>` (filter + sort)
    - _Requirements: 2.6_

  - [x] 5.3 Replace per-row "Details" button with row-click
    - Remove `<Button size="xs" colorScheme="blue">Details</Button>` from summary table rows
    - Remove `<Td>` containing the Details button
    - Add `onClick={() => fetchReferenceDetails(row.ReferenceNumber)}` to summary `<Tr>`
    - Add `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` to summary `<Tr>`
    - Highlight selected row: `bg={selectedReference === row.ReferenceNumber ? 'gray.600' : 'transparent'}`
    - _Requirements: 2.7_

  - [x] 5.4 Update rendering to use `processedData`
    - Replace `refSummaryData.map(...)` with `processedRefSummary.map(...)` in summary table
    - Replace `selectedReferenceDetails.map(...)` with `processedRefDetails.map(...)` in details table
    - Update summary count display to use `processedRefSummary.length`
    - Keep ledger `<Select>` and "Check References" `<Button>` above the table (API controls)
    - _Preservation: Ledger selector, Check References fetch, reference detail display — all unchanged_
    - _Requirements: 2.6, 2.7, 3.5_

---

## Phase 6: Property-Based Tests (Optional\*)

- [x] 6. Write property-based tests for filter/sort equivalence
  - [x] \*6.1 Write bug condition exploration test
    - **Property 1: Bug Condition** — Missing Framework Usage
    - **IMPORTANT**: Write this property-based test BEFORE implementing the fix (or run against unfixed code snapshot)
    - **GOAL**: Surface counterexamples that demonstrate the bug exists
    - **Scoped PBT Approach**: For each component, generate random data arrays and verify that the current (unfixed) code lacks `aria-sort` attributes and `FilterableHeader` components
    - Test that rendering BnbRevenueReport with random BnbRecord[] produces `<Th>` elements without `aria-sort` (from Bug Condition in design)
    - Test that rendering BnbReturningGuestsReport produces no filter inputs in table headers
    - Test that rendering EmailLogPanel produces no `aria-label` on filter inputs
    - Run test on UNFIXED code — expect FAILURE (this confirms the bug exists)
    - Document counterexamples found (e.g., "`<Th>` rendered without aria-sort attribute")
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 1.8_

  - [x] \*6.2 Write preservation property tests (BEFORE implementing fix)
    - **Property 2: Preservation** — Filter Output Equivalence
    - **IMPORTANT**: Follow observation-first methodology
    - **BnbRevenueReport filter equivalence**: For random `BnbRecord[]` + filter strings, verify `useFilterableTable` output matches manual `filteredBnbData` useMemo logic (case-insensitive substring on channel, listing, guestName)
    - **BnbRevenueReport sort equivalence**: For random `BnbRecord[]` + sort field/direction, verify hook sort matches `handleBnbSort` for string, numeric, and date fields
    - **EmailLogPanel filter equivalence**: For random `EmailLogEntry[]` + filter strings, verify hook output matches manual recipient/status filter logic
    - **STRInvoice filter migration**: For random `Booking[]` + per-column filter strings, verify hook per-column filtering produces correct subset (note: per-column is stricter than original all-column search — this is a behavioral improvement)
    - Write property-based tests using `@fast-check/vitest` with `fc.array(fc.record(...))` generators
    - Verify tests PASS on unfixed code (for the filter logic functions extracted in isolation)
    - _Requirements: 3.1, 3.2, 3.4, 3.6_

  - [x] \*6.3 Verify exploration test passes after all migrations
    - **Property 1: Expected Behavior** — Framework Usage Confirmed
    - **IMPORTANT**: Re-run the SAME test from task 6.1 — do NOT write a new test
    - After all 5 components are migrated, re-run the bug condition test
    - **EXPECTED OUTCOME**: Test PASSES (confirms all components now use framework)
    - _Requirements: 2.1, 2.4, 2.5, 2.6, 2.8_

  - [x] \*6.4 Verify preservation tests still pass after all migrations
    - **Property 2: Preservation** — Filter Output Still Equivalent
    - **IMPORTANT**: Re-run the SAME tests from task 6.2 — do NOT write new tests
    - After all 5 components are migrated, re-run preservation tests
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in filter/sort behavior)
    - _Requirements: 3.1, 3.2, 3.4, 3.6_

- [x] 7. Checkpoint — Ensure all migrations complete and tests pass
  - Verify each component renders correctly with framework hooks
  - Verify dark theme styling is consistent across all 5 components
  - Verify accessibility attributes (`aria-sort`, `aria-label`) present on all migrated tables
  - Run full frontend test suite to catch regressions
  - Ensure all tests pass, ask the user if questions arise
