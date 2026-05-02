# Filter Framework Migration — Bugfix Design

## Overview

Five components use inconsistent, manual filter/sort implementations instead of the established Table Filter Framework v2. This migration replaces ad-hoc `useState`-based filtering, custom sort handlers, and inline sort indicators with the standard `useFilterableTable` hook and `FilterableHeader` component. The fix is purely client-side — no backend changes are required. The BNB Revenue API already defaults `dateFrom`/`dateTo` when omitted, so removing those fields from the frontend is safe.

## Glossary

- **Bug_Condition (C)**: A component renders a table without using `useFilterableTable` / `FilterableHeader`, resulting in missing debounce, missing `aria-sort`/`aria-label`, inconsistent dark theme, or non-standard filter/sort patterns
- **Property (P)**: After migration, each component uses the framework hooks/components, producing identical filtered/sorted output with proper accessibility attributes and consistent dark theme styling
- **Preservation**: All existing functionality — data fetching, CSV export, row-click expand, invoice generation, sysadmin mode — must remain unchanged
- **`useFilterableTable`**: Composable hook in `frontend/src/hooks/useFilterableTable.ts` that combines `useColumnFilters` + `useTableSort` with debounce, returning `processedData`
- **`FilterableHeader`**: Component in `frontend/src/components/filters/FilterableHeader.tsx` that renders a `<Th>` with label, sort indicator, and text filter input with `aria-sort` and `aria-label`
- **INITIAL_FILTERS**: A `Record<string, string>` constant defining filterable column keys with empty-string defaults, passed to `useFilterableTable`
- **Hybrid approach**: Text search filters inside column headers (`FilterableHeader`), dropdown/multi-select filters above the table (`FilterPanel`)

## Bug Details

### Bug Condition

The bug manifests when any of the five target components renders a table. Instead of using the framework's `useFilterableTable` hook and `FilterableHeader` component, they use manual `useState` for filter values, manual `useMemo` for filtering, custom sort handlers with inline `↑`/`↓` indicators, and raw `<Input>`/`<Select>` elements without accessibility attributes.

**Formal Specification:**

```
FUNCTION isBugCondition(component)
  INPUT: component of type ReactComponent rendering a data table
  OUTPUT: boolean

  RETURN component IN [BnbRevenueReport, BnbReturningGuestsReport, EmailLogPanel,
                        BankingProcessor_CheckRefTab, STRInvoice]
         AND (component.usesManualFilterState
              OR component.lacksFilterableHeader
              OR component.lacksAriaSortAttributes
              OR component.lacksAriaLabelOnInputs
              OR component.lacksDebounceOnFilters)
END FUNCTION
```

### Examples

- **BnbRevenueReport**: User types in channel filter → no debounce, every keystroke re-filters immediately. Column headers use `cursor="pointer"` + `onClick` with inline `↑`/`↓` text instead of `FilterableHeader`. No `aria-sort` on any `<Th>`. Date fields `dateFrom`/`dateTo` present but should not be.
- **BnbReturningGuestsReport**: User sees guest name and count columns with no filter inputs and no sort capability at all. Cannot search for a specific guest or sort by booking count.
- **EmailLogPanel**: User types in recipient filter → no debounce, triggers API call on every Enter key. Status dropdown is a raw `<Select>` without `aria-label`. No sort on any column.
- **Check Reference Numbers**: Summary table has a per-row "Details" `<Button>` instead of row-click. No filters or sort on reference, count, or amount columns.
- **STRInvoice**: User types in search box → manual `onChange` filters all columns at once (no per-column filtering). No sort capability. No dark theme styling (`bg="gray.800"` container missing). No `aria-sort` or `aria-label`.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- BnbRevenueReport: channel/listing/guest name case-insensitive substring filtering, amount column selector (gross, net, channel fee, tourist tax, VAT) show/hide, sort toggle on all columns, CSV export with filtered data
- BnbReturningGuestsReport: row-click expand/collapse guest bookings inline with summary totals, API fetch on mount
- EmailLogPanel: recipient and status filtering, limit selector (50/100/250/500), sysadmin mode showing Tenant column, tenant-scoped fetching
- Check Reference Numbers: ledger selector, "Check References" button fetch, reference detail display with transaction list
- STRInvoice: `startDate`/`endDate` controlling API data range, per-row "Generate Invoice" button (accepted exception), billing address modal, invoice preview modal with print, language selector, booking count display

**Scope:**
All non-table-rendering behavior is completely unaffected. Data fetching, API calls, modals, export, and business logic remain identical. Only the filter/sort state management and table header rendering change.

## Hypothesized Root Cause

This is not a traditional bug with a single root cause — it is a consistency/standards gap. The components were built before the Table Filter Framework v2 was established, or were not updated when the framework was introduced. The root causes per component:

1. **BnbRevenueReport**: Built with manual `useState` + `useMemo` filter pattern and custom `handleBnbSort` function. Predates framework adoption. Also includes `dateFrom`/`dateTo` fields that were part of the original design but are now unnecessary (the API defaults them).

2. **BnbReturningGuestsReport**: Simple report table — filters/sort were never added because the table was small. As data grows, users need to search and sort.

3. **EmailLogPanel**: Uses manual `useState` for `recipientFilter` and `statusFilter` with API-side filtering on recipient. No client-side debounce. No sort was ever implemented.

4. **Check Reference Numbers (BankingProcessor tab)**: Uses per-row "Details" button pattern that predates the row-click standard. No filters/sort were added to the summary or details tables.

5. **STRInvoice**: Uses a single `searchQuery` state that filters across all columns simultaneously (no per-column filtering). Manual `onChange` handler duplicates filter logic inline. No sort. No dark theme styling. `startDate`/`endDate` correctly stays (controls API range).

## Correctness Properties

Property 1: Bug Condition — Framework Hook Usage

_For any_ component in the migration set that renders a data table, the migrated version SHALL use `useFilterableTable` hook for combined filter + sort state and `FilterableHeader` components in column headers, producing `processedData` that is filtered-then-sorted with 150ms debounce.

**Validates: Requirements 2.1, 2.4, 2.5, 2.6, 2.8**

Property 2: Preservation — Filter Output Equivalence

_For any_ data set and filter input combination applied to a migrated component, the `processedData` output from `useFilterableTable` SHALL contain exactly the same rows as the original manual filter logic, preserving case-insensitive substring matching behavior.

**Validates: Requirements 3.1, 3.4, 3.6**

Property 3: Preservation — Sort Output Equivalence

_For any_ data set and sort field/direction applied to BnbRevenueReport, the `processedData` output from `useFilterableTable` SHALL produce the same row ordering as the original `handleBnbSort` function for string, numeric, and date fields.

**Validates: Requirements 3.2**

Property 4: Preservation — Existing Interactions Unchanged

_For any_ user interaction that does NOT involve column filtering or sorting (row-click expand, CSV export, invoice generation, API fetching, modal workflows), the migrated component SHALL produce exactly the same behavior as the original component.

**Validates: Requirements 3.3, 3.5, 3.6, 3.7, 3.8, 3.9**

Property 5: Bug Condition — Accessibility Attributes Present

_For any_ migrated table column rendered with `FilterableHeader`, the component SHALL include `aria-sort` on the `<Th>` element (ascending/descending/none) and `aria-label="Filter by {label}"` on the filter input.

**Validates: Requirements 2.1, 2.4, 2.5, 2.6, 2.8**

## Fix Implementation

### Changes Required

All changes are client-side only. No backend modifications needed — the BNB table API already defaults `dateFrom` to Jan 1 of current year and `dateTo` to today when parameters are omitted.

---

### Component 1: BnbRevenueReport.tsx

**File**: `frontend/src/components/reports/BnbRevenueReport.tsx`

**Remove:**

- `useState` for `bnbSortField`, `bnbSortDirection`, `bnbSearchFilters`
- `handleBnbSort` function (manual sort with `setBnbData`)
- `filteredBnbData` useMemo (manual filter logic)
- `bnbFilters.dateFrom` and `bnbFilters.dateTo` state and their `<Input type="date">` elements
- `dateFrom`/`dateTo` params from `fetchBnbData` API call
- Inline `cursor="pointer"` + `onClick` + `↑`/`↓` text on `<Th>` elements
- Separate `<Card>` with raw `<Input>` filter fields

**Add:**

```typescript
const INITIAL_FILTERS: Record<string, string> = {
  channel: "",
  listing: "",
  guestName: "",
  checkinDate: "",
  checkoutDate: "",
};

const {
  filters,
  setFilter,
  resetFilters,
  hasActiveFilters,
  handleSort,
  sortField,
  sortDirection,
  processedData,
} = useFilterableTable<BnbRecord>(bnbData, {
  initialFilters: INITIAL_FILTERS,
  defaultSort: { field: "checkinDate", direction: "desc" },
});
```

- Replace all `<Th>` with `<FilterableHeader>` for filterable/sortable columns
- Amount columns (gross, net, channelFee, touristTax, vat) get `FilterableHeader` with `sortable` but no `filterValue` (sort-only, conditional on `selectedAmounts`)
- Keep amount selector `<Menu>` above the table (dropdown filter pattern)
- Keep "Update BNB Data" and "Export CSV" buttons above the table
- Use `processedData` instead of `filteredBnbData` for rendering
- Update `exportBnbCsv` to use `processedData` instead of `filteredBnbData`

**API call change:**

```typescript
// BEFORE:
const params = new URLSearchParams({
  dateFrom: bnbFilters.dateFrom,
  dateTo: bnbFilters.dateTo,
  channel: bnbFilters.channel,
  listing: bnbFilters.listing,
});

// AFTER: No dateFrom/dateTo — backend defaults to Jan 1 → today
const params = new URLSearchParams({
  channel: bnbFilters.channel,
  listing: bnbFilters.listing,
});
```

---

### Component 2: BnbReturningGuestsReport.tsx

**File**: `frontend/src/components/reports/BnbReturningGuestsReport.tsx`

**Add:**

```typescript
const INITIAL_FILTERS: Record<string, string> = {
  guestName: "",
  aantal: "",
};

const {
  filters,
  setFilter,
  handleSort,
  sortField,
  sortDirection,
  processedData,
} = useFilterableTable<ReturningGuest>(returningGuests, {
  initialFilters: INITIAL_FILTERS,
  defaultSort: { field: "aantal", direction: "desc" },
});
```

- Replace plain `<Th>` for guest name and count with `<FilterableHeader>`
- The expand/collapse `+`/`−` column stays as a plain `<Th>` (no filter/sort needed)
- Use `processedData` instead of `returningGuests` for rendering the main table rows
- Row-click expand/collapse behavior is unchanged — `handleGuestClick` stays on `<Tr onClick>`

---

### Component 3: EmailLogPanel.tsx

**File**: `frontend/src/components/shared/EmailLogPanel.tsx`

**Remove:**

- `useState` for `recipientFilter`, `statusFilter`
- Raw `<InputGroup>` with `<SearchIcon>` and `<Input>` for recipient filter
- Raw `<Select>` for status filter
- Manual `filtered` logic inside `fetchLogs` for status

**Add:**

```typescript
const INITIAL_FILTERS: Record<string, string> = {
  recipient: "",
  email_type: "",
  subject: "",
  sent_by: "",
  status: "",
};

const {
  filters,
  setFilter,
  handleSort,
  sortField,
  sortDirection,
  processedData,
} = useFilterableTable<EmailLogEntry>(logs, {
  initialFilters: INITIAL_FILTERS,
  defaultSort: { field: "created_at", direction: "desc" },
});
```

- Replace all `<Th>` with `<FilterableHeader>` for filterable/sortable columns
- Status column: use `FilterableHeader` with text search (user types "delivered" to filter). The old dropdown with fixed options is replaced by the framework's text filter — simpler and consistent.
- Keep limit `<Select>` and Refresh `<Button>` above the table
- Sysadmin mode: conditionally render `<FilterableHeader>` for Tenant column when `mode === 'sysadmin'`
- Use `processedData` instead of `logs` for rendering
- Remove status filtering from `fetchLogs` — all filtering is now client-side via the hook

**Note:** The recipient filter currently triggers an API call with `?recipient=` param. After migration, all filtering is client-side on the fetched data set. The API call fetches all logs (up to `limit`), and `useFilterableTable` filters locally. This is consistent with how other framework-migrated tables work.

---

### Component 4: Check Reference Numbers (BankingProcessor.tsx)

**File**: `frontend/src/components/BankingProcessor.tsx` (Check Reference tab section)

**Summary Table — Add:**

```typescript
const REF_SUMMARY_FILTERS: Record<string, string> = {
  ReferenceNumber: "",
  transaction_count: "",
  total_amount: "",
};

const {
  filters: refSummaryFilters,
  setFilter: setRefSummaryFilter,
  handleSort: handleRefSummarySort,
  sortField: refSummarySortField,
  sortDirection: refSummarySortDirection,
  processedData: processedRefSummary,
} = useFilterableTable(refSummaryData, {
  initialFilters: REF_SUMMARY_FILTERS,
  defaultSort: { field: "ReferenceNumber", direction: "asc" },
});
```

**Details Table — Add:**

```typescript
const REF_DETAILS_FILTERS: Record<string, string> = {
  TransactionNumber: "",
  TransactionDate: "",
  Amount: "",
  TransactionDescription: "",
};

const {
  filters: refDetailsFilters,
  setFilter: setRefDetailsFilter,
  handleSort: handleRefDetailsSort,
  sortField: refDetailsSortField,
  sortDirection: refDetailsSortDirection,
  processedData: processedRefDetails,
} = useFilterableTable(selectedReferenceDetails, {
  initialFilters: REF_DETAILS_FILTERS,
  defaultSort: { field: "TransactionDate", direction: "desc" },
});
```

**Remove:**

- Per-row "Details" `<Button>` from summary table
- "Actions" `<Th>` column

**Add:**

- Row-click on summary table `<Tr>`: `onClick={() => fetchReferenceDetails(row.ReferenceNumber)}` with `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`
- Replace all `<Th>` in both tables with `<FilterableHeader>`
- Use `processedRefSummary` and `processedRefDetails` for rendering

**Note:** Since BankingProcessor.tsx is a large file, the Check Reference tab section changes are localized. The hook instances are scoped to the tab's rendering block.

---

### Component 5: STRInvoice.tsx

**File**: `frontend/src/components/STRInvoice.tsx`

**Remove:**

- `useState` for `searchQuery`
- `searchResults` state (replaced by `processedData`)
- `searchBookings` function
- Manual `onChange` filter logic in the search `<Input>`
- Raw `<Th>` elements without accessibility attributes
- "Filter" and "Clear" buttons (framework handles filtering via column headers)

**Keep (accepted exceptions and API controls):**

- `startDate` / `endDate` state and `<Input type="date">` fields (control API data range)
- Per-row "Generate Invoice" `<Button>` (accepted exception — triggers workflow)
- `loadAllBookings` function and "Reload" button
- Language `<Select>`
- Billing form modal and invoice preview modal

**Add:**

```typescript
const INITIAL_FILTERS: Record<string, string> = {
  reservationCode: "",
  guestName: "",
  channel: "",
  listing: "",
  checkinDate: "",
  nights: "",
  amountGross: "",
};

const {
  filters,
  setFilter,
  resetFilters,
  hasActiveFilters,
  handleSort,
  sortField,
  sortDirection,
  processedData,
} = useFilterableTable<Booking>(allBookings, {
  initialFilters: INITIAL_FILTERS,
  defaultSort: { field: "checkinDate", direction: "desc" },
});
```

- Replace all `<Th>` with `<FilterableHeader>` (except Action column which stays as plain `<Th>`)
- Add dark theme styling:
  - Table container: `bg="gray.800"`, `borderRadius="md"`, `p={4}`
  - Headers get `bg="gray.700"` via `FilterableHeader` (built-in)
  - Row hover: `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` — but since rows have a "Generate Invoice" button (not row-click), hover is for visual consistency only, no `onClick` on `<Tr>`
  - Filter inputs get `bg="gray.600"` via `FilterableHeader` (built-in)
  - Text: `color="white"` on `<Td>` elements
- Use `processedData` instead of `searchResults` for rendering
- Update count display to use `processedData.length` and `allBookings.length`

**Layout after migration:**

```
┌─────────────────────────────────────────────────────┐
│ STR Invoice Generator (title)                       │
│ [Alert: X bookings loaded]                          │
│                                                     │
│ [Start Date] [End Date] [Language ▼] [Reload]       │
│                                                     │
│ ┌─────────────────────────────────────────────────┐ │
│ │ Res.Code │ Guest  │ Channel │ ... │ Action      │ │
│ │ [filter] │[filter]│[filter] │     │             │ │
│ ├──────────┼────────┼─────────┼─────┼─────────────┤ │
│ │ ABC123   │ Smith  │ Airbnb  │ ... │[Gen Invoice]│ │
│ │ DEF456   │ Jones  │ Booking │ ... │[Gen Invoice]│ │
│ └─────────────────────────────────────────────────┘ │
│ Showing X of Y bookings                             │
└─────────────────────────────────────────────────────┘
```

---

### Dark Theme Consistency (All Components)

All five components must use these values (provided by `FilterableHeader` for headers, manually applied for containers/rows):

| Element               | Property | Value                                                                         |
| --------------------- | -------- | ----------------------------------------------------------------------------- |
| Table container       | `bg`     | `gray.800`                                                                    |
| Table header (`<Th>`) | `bg`     | `gray.700` (via FilterableHeader)                                             |
| Header label          | `color`  | `gray.300`, `fontSize="xs"`, `fontWeight="bold"`, `textTransform="uppercase"` |
| Filter input          | `bg`     | `gray.600` (via FilterableHeader)                                             |
| Sort indicator        | `color`  | `orange.300` (via FilterableHeader)                                           |
| Row hover             | `bg`     | `gray.700`                                                                    |
| Table text            | `color`  | `white`                                                                       |

### Accessibility (All Components)

All migrated tables get these attributes automatically via `FilterableHeader`:

- `aria-sort="ascending|descending|none"` on every sortable `<Th>`
- `aria-label="Filter by {label}"` on every filter `<Input>`
- `role="button"` and `aria-label="Sort by {label}"` on sort click areas

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, verify that the current (unfixed) components lack framework usage, then verify the migrated components produce equivalent output with proper accessibility.

### Exploratory Bug Condition Checking

**Goal**: Confirm that the current components lack framework hooks, accessibility attributes, and debounce before implementing the fix.

**Test Plan**: Write tests that render each component and assert the absence of framework patterns. Run on UNFIXED code to confirm the bug condition.

**Test Cases**:

1. **BnbRevenueReport Missing Accessibility**: Render component, assert no `aria-sort` attributes on `<Th>` elements (will fail on unfixed code — confirms bug)
2. **BnbReturningGuestsReport No Filters**: Render component, assert no `<input>` elements in table headers (will fail on unfixed code)
3. **EmailLogPanel No Debounce**: Render component, type in recipient filter, assert filter triggers immediately without debounce (will fail on unfixed code)
4. **STRInvoice No Dark Theme**: Render component, assert table container lacks `bg="gray.800"` (will fail on unfixed code)
5. **Check Ref Details Button Present**: Render summary table, assert per-row "Details" button exists (will fail on unfixed code — confirms non-standard pattern)

**Expected Counterexamples**:

- `<Th>` elements without `aria-sort` attribute
- Filter inputs without `aria-label` attribute
- No `FilterableHeader` components rendered
- Per-row action buttons where row-click should be used

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the migrated components use framework hooks and produce correct output.

**Pseudocode:**

```
FOR ALL component WHERE isBugCondition(component) DO
  migratedComponent := migrate(component)
  ASSERT migratedComponent.usesFilterableTableHook
  ASSERT migratedComponent.rendersFilterableHeaders
  ASSERT migratedComponent.hasAriaSortOnSortableColumns
  ASSERT migratedComponent.hasAriaLabelOnFilterInputs
  ASSERT migratedComponent.processedData == expectedFilteredSortedData
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (non-filter/sort interactions), the migrated components produce the same result as the original.

**Pseudocode:**

```
FOR ALL interaction WHERE NOT isBugCondition(interaction) DO
  ASSERT originalComponent.behavior(interaction) == migratedComponent.behavior(interaction)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many data sets and filter combinations automatically
- It catches edge cases in filter matching (empty strings, special characters, null values)
- It provides strong guarantees that `useFilterableTable` output matches the original manual logic

**Test Plan**: Capture the original filter/sort behavior by running the manual logic functions in isolation, then write property-based tests asserting the framework hook produces identical output.

**Test Cases**:

1. **BnbRevenueReport Filter Equivalence**: For random BNB data + filter strings, verify `useFilterableTable` output matches manual `filteredBnbData` useMemo logic
2. **BnbRevenueReport Sort Equivalence**: For random BNB data + sort field/direction, verify hook sort matches `handleBnbSort` output
3. **BnbRevenueReport CSV Export**: Verify exported CSV uses `processedData` and contains correct rows
4. **EmailLogPanel Filter Equivalence**: For random email logs + filter strings, verify hook output matches manual filter logic
5. **STRInvoice Filter Equivalence**: For random bookings + search strings, verify per-column filtering via hook matches original all-column search
6. **BnbReturningGuestsReport Expand/Collapse**: Verify row-click still triggers `handleGuestClick` and expands bookings
7. **Check Ref Row-Click**: Verify clicking summary row calls `fetchReferenceDetails` with correct reference number

### Unit Tests

- Test `INITIAL_FILTERS` constants have correct keys for each component
- Test that `FilterableHeader` renders with correct props for each column
- Test that amount column visibility toggle still works in BnbRevenueReport
- Test that sysadmin mode conditionally renders Tenant `FilterableHeader` in EmailLogPanel
- Test that STRInvoice "Generate Invoice" button still triggers billing modal
- Test that Check Ref summary row-click loads details (replaces button click)

### Property-Based Tests

- Generate random `BnbRecord[]` arrays and filter strings → verify `useFilterableTable` output matches manual filter logic (case-insensitive substring on channel, listing, guestName)
- Generate random `BnbRecord[]` arrays and sort field/direction → verify hook sort matches `handleBnbSort` for string, numeric, and date fields
- Generate random `EmailLogEntry[]` arrays and filter strings → verify hook output matches manual recipient/status filter
- Generate random `Booking[]` arrays and per-column filter strings → verify hook output is subset of original all-column search (note: per-column is stricter than all-column, so this is a behavioral change — test the new behavior)
- Generate random `ReturningGuest[]` arrays → verify filtering by guest name substring works correctly

### Integration Tests

- Render BnbRevenueReport with mock data, type in channel filter, verify table shows filtered rows after debounce
- Render BnbReturningGuestsReport, click sort on count column, verify rows reorder
- Render EmailLogPanel in sysadmin mode, verify Tenant column has FilterableHeader
- Render Check Reference tab, click summary row, verify details table appears (no Details button)
- Render STRInvoice, verify dark theme classes on container, verify "Generate Invoice" button still works
- Render STRInvoice, change startDate, verify API reload triggers (date range preserved)
