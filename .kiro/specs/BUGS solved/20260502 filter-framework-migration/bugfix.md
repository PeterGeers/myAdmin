# Bugfix Requirements Document

## Introduction

Five pages/components in the application use inconsistent, non-standard filter and sort implementations instead of the established Table Filter Framework v2 (`useFilterableTable` hook, `FilterableHeader` component). This causes inconsistent UX across the application (different filter patterns, missing sort indicators, no debounce, missing accessibility attributes), harder maintenance due to duplicated filter/sort boilerplate, and missing framework features like `aria-sort`, `aria-label`, and standardized dark theme styling. Additionally, the BNB Revenue Analysis page has unnecessary `startDate`/`endDate` fields that should be removed.

**Note on STR Invoice Generator:** The STR Invoice Generator is actually `STRInvoice.tsx` (not `InvoiceGenerator.tsx` which is a separate receipt/kassabon generator). `STRInvoice.tsx` displays a bookings table (546+ rows) with columns: Reservation Code, Guest Name, Channel, Listing, Check-in, Nights, Amount, and an Action column with per-row "Generate Invoice" buttons. It uses manual `useState`-based search filtering, `startDate`/`endDate` fields that trigger API reloads, and lacks the framework's `FilterableHeader`, sort capability, debounce, and accessibility attributes.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user views the BNB Revenue Analysis page (`BnbRevenueReport.tsx`) THEN the system displays manual `useState`-based filter inputs (`bnbSearchFilters`) and a custom `handleBnbSort` function with inline sort indicators (`↑`/`↓`) instead of using `useFilterableTable` and `FilterableHeader`, resulting in no debounce, no `aria-sort` attributes, and no `aria-label` on filter inputs.

1.2 WHEN a user views the BNB Revenue Analysis page THEN the system displays `startDate` and `endDate` filter fields (`bnbFilters.dateFrom`, `bnbFilters.dateTo`) that should not be present.

1.3 WHEN a user views the BNB Revenue Analysis page THEN the system renders filter inputs in a separate `Card` above the table using raw `<Input>` components with `bg="gray.600"` but without `FilterableHeader` placement inside column headers, breaking the hybrid approach (text search in headers, dropdowns above).

1.4 WHEN a user views the BNB Returning Guests page (`BnbReturningGuestsReport.tsx`) THEN the system displays a table with no column filters and no sort capability — the guest name and count columns are not filterable or sortable, and there are no `aria-sort` or `aria-label` attributes.

1.5 WHEN a user views the Email Log panel (`EmailLogPanel.tsx`) THEN the system displays manual `useState`-based filter inputs (`recipientFilter`, `statusFilter`) with a raw `<Input>` and `<Select>` in an `HStack` above the table, instead of using `useFilterableTable` and `FilterableHeader` for text search in column headers, resulting in no debounce on the recipient filter, no sort capability, no `aria-sort` attributes, and no `aria-label` on the status dropdown.

1.6 WHEN a user views the Check Reference Numbers tab in BankingProcessor (`BankingProcessor.tsx`, Check Reference tab) THEN the system displays a summary table and a details table with no column filters and no sort capability — the reference, count, amount, transaction number, date, and description columns are not filterable or sortable, and there are no `aria-sort` or `aria-label` attributes.

1.7 WHEN a user views the Check Reference Numbers summary table THEN the system displays a per-row "Details" action button (`<Button size="xs" colorScheme="blue">Details</Button>`) instead of using the standard row-click-opens-detail pattern.

1.8 WHEN a user views the STR Invoice Generator page (`STRInvoice.tsx`) THEN the system displays a bookings table with manual `useState`-based search filtering (no debounce), `startDate`/`endDate` fields that trigger full API reloads, per-row "Generate Invoice" action buttons instead of row-click, no sort capability on any column, no `FilterableHeader` components, no `aria-sort` attributes, and no `aria-label` on filter inputs. The table also lacks dark theme styling (missing `bg="gray.800"` container, `bg="gray.700"` headers, hover rows).

### Expected Behavior (Correct)

2.1 WHEN a user views the BNB Revenue Analysis page THEN the system SHALL use `useFilterableTable` hook for combined filter and sort state, and `FilterableHeader` components in column headers for text search with debounce, `aria-sort` attributes on sortable columns, and `aria-label` on filter inputs.

2.2 WHEN a user views the BNB Revenue Analysis page THEN the system SHALL NOT display `startDate` or `endDate` filter fields — these fields and their associated state/API parameters SHALL be removed entirely.

2.3 WHEN a user views the BNB Revenue Analysis page THEN the system SHALL render text search filters inside column headers using `FilterableHeader` (hybrid approach), with dropdown filters (channel, listing, amount selector) remaining above the table in a `FilterPanel` or equivalent.

2.4 WHEN a user views the BNB Returning Guests page THEN the system SHALL use `useFilterableTable` hook and `FilterableHeader` components to provide sortable and filterable columns (guest name, count) with debounce, `aria-sort`, and `aria-label` attributes.

2.5 WHEN a user views the Email Log panel THEN the system SHALL use `useFilterableTable` hook and `FilterableHeader` components for text search in column headers (recipient, type, subject, sent by) with debounce, and use a `FilterPanel` or `GenericFilter` above the table for the status dropdown filter, with `aria-sort` on sortable columns and `aria-label` on all filter inputs.

2.6 WHEN a user views the Check Reference Numbers tab THEN the system SHALL use `useFilterableTable` hook and `FilterableHeader` components for both the summary table (reference, count, amount columns) and the details table (transaction number, date, amount, description columns) with debounce, `aria-sort`, and `aria-label` attributes.

2.7 WHEN a user views the Check Reference Numbers summary table THEN the system SHALL use row-click to show reference details (replacing the per-row "Details" button), following the standard UI pattern of row-click-opens-detail.

2.8 WHEN a user views the STR Invoice Generator page (`STRInvoice.tsx`) THEN the system SHALL use `useFilterableTable` hook and `FilterableHeader` components for text search in column headers (reservation code, guest name, channel, listing, check-in, nights, amount) with debounce, `aria-sort` on sortable columns, and `aria-label` on filter inputs. The `startDate`/`endDate` fields SHALL remain as they control the API data range (not client-side filtering). The per-row "Generate Invoice" button is an ACCEPTED EXCEPTION (it triggers an action/workflow, not a detail view). The table SHALL use dark theme styling (`bg="gray.800"` container, `bg="gray.700"` headers, `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` on rows).

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user applies filters on the BNB Revenue Analysis page THEN the system SHALL CONTINUE TO correctly filter data by channel, listing, and guest name with case-insensitive substring matching, and the amount column selector (gross, net, channel fee, tourist tax, VAT) SHALL CONTINUE TO show/hide columns as before.

3.2 WHEN a user sorts columns on the BNB Revenue Analysis page THEN the system SHALL CONTINUE TO sort by check-in date, check-out date, channel, listing, nights, amounts, and guest name with correct ascending/descending toggle behavior.

3.3 WHEN a user clicks a guest row on the BNB Returning Guests page THEN the system SHALL CONTINUE TO expand/collapse the guest's booking details inline, showing check-in, check-out, channel, listing, nights, gross, net, and reservation code with summary totals.

3.4 WHEN a user filters email logs by recipient or status on the Email Log panel THEN the system SHALL CONTINUE TO correctly filter and display matching log entries with date, recipient, type, tenant (sysadmin mode), subject, status badge, sent by, and error columns.

3.5 WHEN a user selects a ledger and clicks "Check References" on the Check Reference Numbers tab THEN the system SHALL CONTINUE TO fetch and display the reference summary with reference number, transaction count, and total amount, and clicking a reference SHALL CONTINUE TO show the transaction details.

3.6 WHEN a user exports BNB data to CSV THEN the system SHALL CONTINUE TO generate a correct CSV file with all visible columns and filtered data.

3.7 WHEN a user clicks "Generate Invoice" on a booking row in the STR Invoice Generator THEN the system SHALL CONTINUE TO open the billing address modal, allow optional custom billing details, generate the invoice via API, and display the invoice preview modal with print functionality.

3.8 WHEN the STR Invoice Generator loads THEN the system SHALL CONTINUE TO fetch all bookings within the date range from the API, display the total count, and support the language selector (Dutch/English) for invoice generation.

3.9 WHEN the Email Log panel is in sysadmin mode THEN the system SHALL CONTINUE TO show the Tenant column and fetch logs for all tenants, and in tenant mode SHALL CONTINUE TO filter by the current tenant.
