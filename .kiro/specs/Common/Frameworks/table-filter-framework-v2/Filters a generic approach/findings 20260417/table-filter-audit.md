# Table & Filter Compliance Audit — 2026-04-17

## Generic Filter Framework Standard

The standard is defined in `.kiro/specs/Common/Filters a generic approach/` and implemented in `frontend/src/components/filters/`. Key components:

- **GenericFilter\<T\>** — Base reusable filter (single/multi-select)
- **YearFilter** — Specialized year selection wrapper
- **FilterPanel** — Container for organizing multiple filters (horizontal/vertical/grid)
- **SearchFilterConfig** — Text-based column search filters
- **types.ts** — FilterConfig, SingleSelectFilterConfig, MultiSelectFilterConfig, SearchFilterConfig

### Expected patterns per `ui-patterns.md`:

| Aspect         | Standard                                                                                |
| -------------- | --------------------------------------------------------------------------------------- |
| **Table**      | Chakra `Table variant="simple"`, dark bg (`gray.800`), `overflowX="auto"`               |
| **Row hover**  | `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`                                        |
| **Row click**  | Opens modal for CRUD — no per-row action buttons                                        |
| **Filters**    | Use `FilterPanel` / `GenericFilter` — between header and table, never inline in columns |
| **Actions**    | Primary buttons (Add, Export) in page header, right-aligned, `colorScheme="orange"`     |
| **Badges**     | Status shown as `Badge` components                                                      |
| **Responsive** | Hide non-essential columns on mobile via `display={{ base: 'none', md: 'table-cell' }}` |
| **Sorting**    | Sortable column headers where applicable                                                |

---

## Inventory of All Table-Containing Components

### A. CRUD / Management Tables (row-click → modal expected)

| #   | Source File                                        | Last Updated | Uses Generic Framework                                         | Filters in Column Headers              | Clickable Rows → Modal            | Compliant        | Notes                                                                       |
| --- | -------------------------------------------------- | ------------ | -------------------------------------------------------------- | -------------------------------------- | --------------------------------- | ---------------- | --------------------------------------------------------------------------- |
| 1   | `pages/ZZPContacts.tsx`                            | 2026-04-15   | ❌ No (standalone `Select` for type filter)                    | ❌ No (filter in page header)          | ✅ Yes                            | ⚠️ Partial       | Filter should use `FilterPanel`; otherwise exemplary                        |
| 2   | `pages/ZZPProducts.tsx`                            | 2026-04-16   | ❌ No (no filters)                                             | N/A                                    | ✅ Yes                            | ✅ Good          | No filters needed (small dataset). Follows pattern well                     |
| 3   | `pages/ZZPInvoices.tsx`                            | 2026-04-17   | ❌ No (standalone `Input` + `Select`)                          | ❌ No (filter in page header)          | ✅ Yes (navigates to detail page) | ⚠️ Partial       | Filters should use `FilterPanel`                                            |
| 4   | `pages/ZZPDebtors.tsx`                             | 2026-04-17   | ❌ No (no filters)                                             | N/A                                    | ✅ Yes (expand/collapse groups)   | ✅ Good          | Grouped table with expand — appropriate pattern                             |
| 5   | `pages/ZZPTimeTracking.tsx`                        | 2026-04-17   | ❌ No (standalone `Select` + `Input`)                          | ❌ No (filter in page header)          | ✅ Yes (card + table views)       | ⚠️ Partial       | Filters should use `FilterPanel`                                            |
| 6   | `components/BankingProcessor.tsx`                  | 2026-04-05   | ✅ Yes (`FilterPanel`)                                         | ❌ No (uses `FilterPanel` above table) | ✅ Yes                            | ✅ Good          | Reference implementation. Uses `FilterPanel` for STR tab                    |
| 7   | `components/TenantAdmin/ChartOfAccounts.tsx`       | 2026-03-26   | ✅ Yes (`FilterPanel` + `SearchFilterConfig`)                  | ❌ No (uses `FilterPanel` above table) | ✅ Yes                            | ✅ Good          | Exemplary use of search filters                                             |
| 8   | `components/TenantAdmin/ParameterManagement.tsx`   | 2026-04-16   | ✅ Yes (`FilterPanel` + `SearchFilterConfig`)                  | ❌ No (uses `FilterPanel` above table) | ✅ Yes (if not system scope)      | ✅ Good          | Exemplary use of search filters                                             |
| 9   | `components/TenantAdmin/TaxRateManagement.tsx`     | 2026-04-13   | ❌ No (standalone `Select` for type filter)                    | ❌ No (filter in page header)          | ✅ Yes (if editable)              | ⚠️ Partial       | Filter should use `FilterPanel`                                             |
| 10  | `components/TenantAdmin/UserManagement.tsx`        | 2026-04-08   | ❌ No (standalone `Input` + `Select`)                          | ❌ No (filter in page header)          | ✅ Yes (cell-click on email)      | ⚠️ Partial       | Uses cell-click instead of full row-click; filters should use `FilterPanel` |
| 11  | `components/TenantAdmin/CredentialsManagement.tsx` | 2026-02-13   | ❌ No (no filters)                                             | N/A                                    | ❌ No (no row click)              | ⚠️ Partial       | Small dataset, no row-click needed. Missing hover effect                    |
| 12  | `components/Assets/AssetList.tsx`                  | 2026-03-26   | ❌ No (standalone `Input` + `Select`)                          | ❌ No (filter in page header)          | ✅ Yes (opens detail modal)       | ⚠️ Partial       | Filters should use `FilterPanel`                                            |
| 13  | `components/SysAdmin/TenantManagement.tsx`         | 2026-03-25   | ✅ Yes (`FilterPanel` + `SearchFilterConfig` + `FilterConfig`) | ❌ No (uses `FilterPanel` above table) | ✅ Yes (cell-click on admin name) | ⚠️ Partial       | Uses cell-click instead of full row-click                                   |
| 14  | `components/SysAdmin/RoleManagement.tsx`           | 2026-02-18   | ❌ No (no filters)                                             | N/A                                    | ✅ Yes (cell-click on role name)  | ⚠️ Partial       | Uses cell-click instead of full row-click                                   |
| 15  | `components/SysAdmin/ProvisioningPanel.tsx`        | 2026-04-05   | ❌ No (no filters)                                             | N/A                                    | ❌ No (action button in row)      | ❌ Non-compliant | Has "Provision" button per row; should use row-click → modal                |
| 16  | `components/ClosedYearsTable.tsx`                  | 2026-03-03   | ❌ No (no filters)                                             | N/A                                    | ❌ No (action button in row)      | ❌ Non-compliant | Has "Reopen" button per row; should use row-click → modal                   |

### B. Report Tables (read-only, row-click optional)

| #   | Source File                            | Last Updated | Uses Generic Framework                | Filters in Column Headers      | Clickable Rows          | Compliant        | Notes                                                |
| --- | -------------------------------------- | ------------ | ------------------------------------- | ------------------------------ | ----------------------- | ---------------- | ---------------------------------------------------- |
| 17  | `reports/AangifteIbReport.tsx`         | 2026-03-03   | ✅ Yes (`FilterPanel`)                | ❌ No                          | ✅ Expand/collapse rows | ✅ Good          |                                                      |
| 18  | `reports/BalanceReport.tsx`            | 2026-04-10   | ✅ Yes (`YearFilter`)                 | ❌ No                          | ❌ Read-only            | ✅ Good          |                                                      |
| 19  | `reports/BnbActualsReport.tsx`         | 2026-03-05   | ✅ Yes (via report group)             | ❌ No                          | ❌ Read-only            | ✅ Good          |                                                      |
| 20  | `reports/BtwReport.tsx`                | 2026-02-18   | ✅ Yes (via report group)             | ❌ No                          | ❌ Read-only            | ✅ Good          |                                                      |
| 21  | `reports/ReferenceAnalysisReport.tsx`  | 2026-02-18   | ✅ Yes (`FilterPanel`)                | ❌ No                          | ❌ Read-only            | ✅ Good          |                                                      |
| 22  | `reports/BnbReturningGuestsReport.tsx` | 2026-02-18   | ❌ No (no filters)                    | N/A                            | ✅ Expand/collapse      | ✅ Good          | No filters needed                                    |
| 23  | `reports/BnbViolinsReport.tsx`         | 2026-02-18   | ✅ Yes (via report group)             | ❌ No                          | N/A (chart)             | ✅ Good          |                                                      |
| 24  | `reports/BnbYearMonthMatrix.tsx`       | 2026-03-05   | ❌ No (no filters)                    | N/A                            | ❌ Read-only            | ✅ Good          | Matrix layout, no filters needed                     |
| 25  | `reports/BnbCountryBookingsReport.tsx` | 2026-02-18   | ❌ No                                 | N/A                            | ❌ Read-only            | ✅ Good          |                                                      |
| 26  | `reports/BnbFutureReport.tsx`          | 2026-02-18   | ❌ No (standalone `Select`)           | ❌ No                          | ❌ Read-only            | ⚠️ Partial       | Filter should use `FilterPanel`                      |
| 27  | `reports/BnbRevenueReport.tsx`         | 2026-02-18   | ❌ No                                 | N/A                            | ❌ Read-only            | ✅ Good          |                                                      |
| 28  | `reports/MutatiesReport.tsx`           | 2026-02-18   | ❌ No (standalone `Input` + `Select`) | ✅ Yes (inline column filters) | ❌ Read-only            | ❌ Non-compliant | Has inline column header filters — violates standard |
| 29  | `reports/ProfitLossReport.tsx`         | 2026-04-10   | ✅ Yes (`FilterPanel`)                | ❌ No                          | ✅ Expand/collapse      | ✅ Good          |                                                      |
| 30  | `reports/ToeristenbelastingReport.tsx` | 2026-02-18   | ❌ No                                 | N/A                            | ❌ Read-only            | ✅ Good          |                                                      |
| 31  | `reports/YearEndClosureReport.tsx`     | 2026-03-03   | ❌ No                                 | N/A                            | ❌ Read-only            | ✅ Good          |                                                      |

### C. Specialized / Embedded Tables

| #   | Source File                                | Last Updated | Uses Generic Framework      | Filters in Column Headers      | Clickable Rows                 | Compliant        | Notes                                                                      |
| --- | ------------------------------------------ | ------------ | --------------------------- | ------------------------------ | ------------------------------ | ---------------- | -------------------------------------------------------------------------- |
| 32  | `components/BankConnect.tsx`               | 2026-01-25   | ❌ No                       | N/A                            | ❌ No (action buttons in rows) | ❌ Non-compliant | Wizard-style UI with per-row action buttons. Acceptable for wizard pattern |
| 33  | `components/ProfitLoss.tsx`                | 2026-02-01   | ❌ No (standalone `Select`) | ✅ Yes (inline column filters) | ❌ Read-only                   | ❌ Non-compliant | Legacy monolith. Has inline column header filters                          |
| 34  | `components/STRInvoice.tsx`                | 2026-02-18   | ❌ No                       | N/A                            | ❌ Read-only                   | ✅ Acceptable    | Invoice display table — no filters needed                                  |
| 35  | `components/zzp/InvoiceLineEditor.tsx`     | 2026-04-16   | N/A                         | N/A                            | N/A                            | ✅ Acceptable    | Editable line-item table (not a list view). Per-row delete is appropriate  |
| 36  | `components/TenantAdmin/StorageTab.tsx`    | 2026-04-13   | ❌ No                       | N/A                            | ❌ Read-only config tables     | ✅ Acceptable    | Small config display tables inside accordions                              |
| 37  | `components/SysAdmin/HealthCheck.tsx`      | 2026-02-18   | ❌ No                       | N/A                            | ❌ No (action button in row)   | ⚠️ Partial       | Has "View Details" button per row. Acceptable for monitoring UI            |
| 38  | `components/SysAdmin/ModuleManagement.tsx` | 2026-04-16   | N/A                         | N/A                            | N/A                            | ✅ Acceptable    | Not a table — uses VStack with Switch toggles                              |
| 39  | `components/SysAdmin/SystemTaxRates.tsx`   | 2026-04-13   | N/A                         | N/A                            | N/A                            | ✅ Good          | Wrapper around TaxRateManagement                                           |
| 40  | `components/DuplicateWarningDialog.tsx`    | 2026-02-18   | N/A                         | N/A                            | N/A                            | ✅ Acceptable    | Dialog with comparison table — not a list view                             |

---

## Summary Statistics

### Generic Filter Framework Adoption

| Category               | Using Framework | Not Using (should) | Not Applicable | Total  |
| ---------------------- | --------------- | ------------------ | -------------- | ------ |
| CRUD/Management tables | 5               | 9                  | 2              | 16     |
| Report tables          | 7               | 2                  | 6              | 15     |
| Specialized/Embedded   | 0               | 1                  | 8              | 9      |
| **Total**              | **12**          | **12**             | **16**         | **40** |

**Adoption rate (where applicable): 50%** (12 of 24 components that should use the framework)

### Filters in Column Headers (violation of standard)

| File                         | Issue                                  |
| ---------------------------- | -------------------------------------- |
| `reports/MutatiesReport.tsx` | Inline text filters in `<Th>` elements |
| `components/ProfitLoss.tsx`  | Inline text filters in `<Th>` elements |

**Only 2 files** have filters embedded in column headers — both are older components.

### Row-Click → Modal Compliance (CRUD tables only)

| Pattern                      | Count | Files                                                                                                                                                    |
| ---------------------------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ✅ Full row-click → modal    | 10    | ZZPContacts, ZZPProducts, ZZPInvoices, ZZPDebtors, ZZPTimeTracking, BankingProcessor, ChartOfAccounts, ParameterManagement, TaxRateManagement, AssetList |
| ⚠️ Cell-click (not full row) | 3     | UserManagement, TenantManagement, RoleManagement                                                                                                         |
| ❌ Per-row action buttons    | 2     | ClosedYearsTable, ProvisioningPanel                                                                                                                      |
| ❌ No row interaction        | 1     | CredentialsManagement                                                                                                                                    |

### Table Styling Compliance

| Aspect                       | Compliant                | Non-compliant                                         |
| ---------------------------- | ------------------------ | ----------------------------------------------------- |
| Dark background (`gray.800`) | Most files               | BankConnect (uses Card), ProfitLoss (uses `gray.600`) |
| Hover effect on rows         | Most CRUD tables         | CredentialsManagement, BankConnect                    |
| `overflowX="auto"` wrapper   | Most files               | Some older components                                 |
| Responsive column hiding     | ZZPContacts, ZZPProducts | Most other files                                      |

---

## Priority Remediation List

### High Priority (actively used, clearly non-compliant)

1. **`reports/MutatiesReport.tsx`** — Move inline column filters to `FilterPanel` above table
2. **`components/ProfitLoss.tsx`** — Move inline column filters to `FilterPanel` above table (legacy monolith — consider if this file is being phased out)
3. **`components/ClosedYearsTable.tsx`** — Replace per-row "Reopen" button with row-click → modal pattern
4. **`components/SysAdmin/ProvisioningPanel.tsx`** — Replace per-row "Provision" button with row-click → modal pattern

### Medium Priority (should adopt framework for consistency)

5. **`pages/ZZPContacts.tsx`** — Replace standalone `Select` with `FilterPanel`
6. **`pages/ZZPInvoices.tsx`** — Replace standalone `Input` + `Select` with `FilterPanel`
7. **`pages/ZZPTimeTracking.tsx`** — Replace standalone `Select` + `Input` with `FilterPanel`
8. **`components/TenantAdmin/TaxRateManagement.tsx`** — Replace standalone `Select` with `FilterPanel`
9. **`components/Assets/AssetList.tsx`** — Replace standalone `Input` + `Select` with `FilterPanel`
10. **`components/TenantAdmin/UserManagement.tsx`** — Replace standalone filters with `FilterPanel`; change cell-click to full row-click
11. **`components/SysAdmin/TenantManagement.tsx`** — Change cell-click to full row-click (already uses `FilterPanel`)
12. **`components/SysAdmin/RoleManagement.tsx`** — Change cell-click to full row-click

### Low Priority (acceptable deviations)

13. **`components/BankConnect.tsx`** — Wizard-style UI, per-row buttons acceptable
14. **`components/SysAdmin/HealthCheck.tsx`** — Monitoring UI, per-row "View Details" acceptable
15. **`reports/BnbFutureReport.tsx`** — Replace standalone `Select` with `FilterPanel`

---

## Exemplary Implementations (reference for refactoring)

These files best demonstrate the standard and can serve as templates:

1. **`pages/ZZPProducts.tsx`** — Clean CRUD table with row-click modal, responsive columns, badges
2. **`components/TenantAdmin/ChartOfAccounts.tsx`** — `FilterPanel` with `SearchFilterConfig`, row-click modal
3. **`components/TenantAdmin/ParameterManagement.tsx`** — `FilterPanel` with 5 search filters, row-click modal
4. **`components/BankingProcessor.tsx`** — Original reference implementation, `FilterPanel` usage
5. **`reports/ProfitLossReport.tsx`** — Report with `FilterPanel`, expand/collapse rows

---

## Ideas for Improving `.kiro/steering/ui-patterns.md`

Based on this audit, the current steering file is missing several details that would help prevent the inconsistencies found. Proposed additions:

### 1. Expand the Filters section

The current Filters section is too brief. It should:

- Explicitly name the framework components (`GenericFilter`, `YearFilter`, `FilterPanel`, `SearchFilterConfig`)
- State that standalone `Select`, `Input`, or custom filter components must not be used for list view filtering
- Provide code snippets for the three common patterns: single dropdown, multiple search filters, year filter
- Clarify that filters must never be embedded in `<Th>` column header elements
- Add default styling props for dark backgrounds: `labelColor="white"`, `bg="gray.600"`, `color="white"`

### 2. Clarify row-click behavior in Table Layout

The current rule says "Row click opens detail/edit Modal" but doesn't distinguish between:

- **Full row-click** (the `<Tr>` has `onClick`) — this is the standard
- **Cell-click** (only one `<Td>` like the name/email has `onClick`) — this is a deviation found in UserManagement, TenantManagement, RoleManagement

Add: "Use full row-click (`onClick` on `<Tr>`), not cell-level click handlers on individual columns."

### 3. Add acceptable exceptions

Some components legitimately deviate from the standard. Document these:

- **Wizard-style UIs** (BankConnect): per-row action buttons acceptable when the primary interaction is a single action per row
- **Monitoring dashboards** (HealthCheck): per-row "View Details" acceptable
- **Editable line-item tables** (InvoiceLineEditor): per-row delete buttons appropriate for inline editing
- **Small config tables** (StorageTab): read-only display tables inside accordions don't need row-click

### 4. Add Table Layout details

Missing specifics that would prevent inconsistencies:

- `size="sm"` as default table size
- Column header color: `color="gray.400"` on all `<Th>` elements
- Empty state: show a centered message row with `colSpan` when no data
- Delete button in modals: red ghost, positioned at `mr="auto"` (far left)
- Modal background: `bg="gray.800"` or `bg="gray.700"`, text `color="white"`

### 5. Add reference implementations

Point to the exemplary files so developers know where to look:

- **CRUD table**: `pages/ZZPProducts.tsx`
- **Table with search filters**: `components/TenantAdmin/ChartOfAccounts.tsx`
- **Report table**: `reports/ProfitLossReport.tsx`

### 6. Add responsive column hiding guidance

Currently only mentioned briefly. Should emphasize that most CRUD tables are missing this — only ZZPContacts and ZZPProducts do it properly. Add as a checklist item for new tables.

### 7. Link to this audit

Add a reference to the findings document so future developers can see the current state:
`Audit findings: .kiro/specs/Common/Filters a generic approach/findings 20260417/`

---

## Impact Analysis: Moving Filters into Column Headers

### Context

The current standard places filters in a `FilterPanel` above the table. An alternative is to place filter inputs directly inside `<Th>` column header cells (Excel-like pattern). Two files already do this: `MutatiesReport.tsx` and `ProfitLoss.tsx`.

### Pros of filters in column headers

- **Direct visual association** — the filter sits right above the data it filters, no guessing which filter maps to which column
- **Space efficient** — no separate filter bar eating vertical space, especially valuable on data-dense screens like ChartOfAccounts with 8 filter fields
- **Familiar pattern** — Excel-like behavior that most users intuitively understand
- **Scales with columns** — adding a new column automatically means adding a filter slot, no separate FilterPanel config to maintain

### Cons / impact

**1. Breaks the generic filter framework**

The `FilterPanel` / `GenericFilter` / `SearchFilterConfig` architecture is designed for a filter bar above the table. Moving filters into `<Th>` elements means:

- `FilterPanel` becomes irrelevant for column-based search filters
- A new component would be needed (`FilterableTableHeader` or `ColumnFilter`) that renders `<Input>` inside `<Th>`
- The `SearchFilterConfig` type still works conceptually but the rendering layer changes completely

**2. Multi-select and dropdown filters don't fit well in headers**

`FilterPanel` supports `single`, `multi`, `search`, and `range` types. Column headers work well for text search (`<Input>`), but multi-select checkboxes and dropdowns in `<Th>` cells get cramped and awkward — especially on narrow columns like "Status" or "Type".

**3. Mixed filter types become harder**

Reports like ReferenceAnalysisReport combine year multi-select + text search + account multi-select. Putting all of those in column headers doesn't work because:

- The year filter spans across all data, not one column
- The account filter is a multi-select dropdown that needs space
- Some filters (like "Analyze" button) are actions, not column filters

**4. Responsive design gets harder**

When columns are hidden on mobile (`display={{ base: 'none', md: 'table-cell' }}`), their filters disappear too. With a separate FilterPanel, filters remain accessible regardless of which columns are visible.

**5. Sortable headers + filter inputs compete for space**

Several tables have sortable column headers (AssetList, UserManagement, TenantManagement, ProfitLoss). Adding a filter input in the same `<Th>` alongside a sort indicator creates a cluttered header.

### Recommendation: Hybrid approach

A hybrid approach gives the best of both worlds:

| Filter type                          | Placement                   | Rationale                                       |
| ------------------------------------ | --------------------------- | ----------------------------------------------- |
| **Text search per column**           | In column headers (`<Th>`)  | Direct association, Excel-like, space efficient |
| **Dropdown / multi-select**          | Above table (`FilterPanel`) | Needs space, doesn't map 1:1 to a column        |
| **Year / period selectors**          | Above table (`FilterPanel`) | Spans all data, not column-specific             |
| **Action buttons** (Analyze, Export) | Page header, right-aligned  | Not filters — keep separate                     |

### Implementation idea: `FilterableTableHeader` component

Create a standardized component for the in-column pattern:

```tsx
// Renders a <Th> with column label + optional <Input> filter below it
<FilterableTableHeader
  label="Description"
  sortable
  sortDirection={sortDir}
  onSort={() => handleSort("description")}
  filterValue={filters.description}
  onFilterChange={(v) => setFilters((prev) => ({ ...prev, description: v }))}
  filterPlaceholder="Filter..."
/>
```

This would:

- Standardize the layout (label on top, input below, sort icon)
- Handle debounce internally
- Match the dark theme styling (`bg="gray.700"`, `color="white"`)
- Be optional per column (some columns don't need filters)

### Files that would benefit most from in-column filters

These files have many text-search filters that map 1:1 to columns:

| File                                  | Current approach                          | Columns with filters                                          |
| ------------------------------------- | ----------------------------------------- | ------------------------------------------------------------- |
| `ChartOfAccounts.tsx`                 | `FilterPanel` with 8 `SearchFilterConfig` | Account, Name, Lookup, SubParent, Parent, VW, Tax, Parameters |
| `ParameterManagement.tsx`             | `FilterPanel` with 5 `SearchFilterConfig` | Namespace, Key, Value, Type, Scope                            |
| `BankingProcessor.tsx` (mutaties tab) | Standalone `<Input>` in `<Th>`            | All 13 columns                                                |
| `MutatiesReport.tsx`                  | Standalone `<Input>` in `<Th>`            | Multiple columns                                              |

### Files that should keep `FilterPanel` above the table

These files have filters that don't map to individual columns:

| File                          | Why keep FilterPanel                                        |
| ----------------------------- | ----------------------------------------------------------- |
| `ReferenceAnalysisReport.tsx` | Year multi-select + reference search + account multi-select |
| `AangifteIbReport.tsx`        | Single year selector                                        |
| `BtwReport.tsx`               | Year + quarter selectors                                    |
| `TenantManagement.tsx`        | Search + status dropdown (already uses FilterPanel well)    |
| `TaxRateManagement.tsx`       | Type dropdown filter                                        |
| `ZZPContacts.tsx`             | Type dropdown filter                                        |
| `AssetList.tsx`               | Search + status + category dropdowns                        |

### Conclusion

A pure "all filters in column headers" approach would break for dropdown/multi-select filters and responsive design. The hybrid approach — text search in headers, dropdowns above — gives the best UX while keeping the framework useful. The key new component needed is `FilterableTableHeader`.

---

## Helper Functions & Hooks to Support the Hybrid Approach

### Problem: Repeated Boilerplate

The audit found the same patterns copy-pasted across 10+ files. Three categories of boilerplate stand out:

**1. Column filter state + debounce** (found in 5 files)

Every file with column filters repeats this ~20-line block:

```tsx
const [searchFilters, setSearchFilters] = useState({ col1: '', col2: '', ... });
const [debouncedFilters, setDebouncedFilters] = useState(searchFilters);

useEffect(() => {
  const timer = setTimeout(() => setDebouncedFilters(searchFilters), 150);
  return () => clearTimeout(timer);
}, [searchFilters]);

const filtered = data.filter(row =>
  Object.entries(debouncedFilters).every(([key, value]) => {
    if (!value) return true;
    return row[key]?.toString().toLowerCase().includes(value.toLowerCase());
  })
);
```

Found in: `BankingProcessor.tsx`, `ChartOfAccounts.tsx`, `ParameterManagement.tsx`, `ProfitLoss.tsx`, `MutatiesReport.tsx`, `BnbRevenueReport.tsx`

**2. Sort state + toggle logic** (found in 7 files)

Every sortable table repeats this ~15-line block:

```tsx
const [sortField, setSortField] = useState("");
const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

const handleSort = (field: string) => {
  if (sortField === field) {
    setSortDirection(sortDirection === "asc" ? "desc" : "asc");
  } else {
    setSortField(field);
    setSortDirection("asc");
  }
};
```

Found in: `AssetList.tsx`, `ProfitLoss.tsx`, `MutatiesReport.tsx`, `TenantManagement.tsx`, `UserManagement.tsx`, `SystemAdmin.tsx`, `BnbRevenueReport.tsx`

**3. Filter input rendering in `<Th>`** (found in 3 files)

BankingProcessor alone has 13 nearly identical `<Th>` filter inputs:

```tsx
<Th p={1}>
  <Input
    size="xs"
    placeholder="..."
    value={columnFilters.X}
    onChange={(e) =>
      setColumnFilters((prev) => ({ ...prev, X: e.target.value }))
    }
    bg="gray.600"
    color="white"
  />
</Th>
```

Found in: `BankingProcessor.tsx` (13 columns), `ProfitLoss.tsx` (7+10 columns), `MutatiesReport.tsx` (7 columns)

---

### Proposed Helper Functions & Hooks

#### 1. `useColumnFilters<T>` — Custom hook for column filter state + debounce + filtering

Replaces the 20-line boilerplate with a one-liner.

```tsx
// frontend/src/hooks/useColumnFilters.ts

interface UseColumnFiltersOptions {
  debounceMs?: number; // default: 150
  matchMode?: "includes" | "regex"; // default: 'includes'
}

function useColumnFilters<T extends Record<string, any>>(
  data: T[],
  initialFilters: Record<string, string>,
  options?: UseColumnFiltersOptions,
) {
  // Returns:
  return {
    filters, // current filter values (for binding to inputs)
    setFilter, // (key: string, value: string) => void
    resetFilters, // () => void — clears all filters
    filteredData, // T[] — debounced, filtered result
    hasActiveFilters, // boolean — true if any filter is non-empty
  };
}
```

**Usage in ChartOfAccounts (before → after):**

Before: 30+ lines of state, useEffect, useMemo

```tsx
// Before: 30+ lines
const [searchFilters, setSearchFilters] = useState({ Account: '', AccountName: '', ... });
useEffect(() => { /* filter logic */ }, [searchFilters, accounts]);
```

After: 1 line

```tsx
const { filters, setFilter, resetFilters, filteredData, hasActiveFilters } =
  useColumnFilters(accounts, { Account: '', AccountName: '', AccountLookup: '', ... });
```

#### 2. `useTableSort<T>` — Custom hook for sort state + toggle + sorted data

Replaces the 15-line sort boilerplate.

```tsx
// frontend/src/hooks/useTableSort.ts

function useTableSort<T>(
  data: T[],
  defaultField?: keyof T,
  defaultDirection?: "asc" | "desc",
) {
  // Returns:
  return {
    sortField, // current sort field
    sortDirection, // 'asc' | 'desc'
    handleSort, // (field: keyof T) => void — toggles direction
    sortedData, // T[] — sorted result
    getSortIndicator, // (field: keyof T) => '↑' | '↓' | '' — for display in <Th>
  };
}
```

**Usage in AssetList (before → after):**

Before: 20+ lines

```tsx
const [sortField, setSortField] = useState<SortField>('purchase_date');
const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
const handleSort = (field: SortField) => { ... };
const sorted = [...assets].sort((a, b) => { ... });
```

After: 1 line

```tsx
const { sortField, sortDirection, handleSort, sortedData, getSortIndicator } =
  useTableSort(assets, "purchase_date", "desc");
```

#### 3. `FilterableHeader` — Component for filter input in `<Th>`

Replaces the repeated `<Th><Input .../></Th>` pattern.

```tsx
// frontend/src/components/filters/FilterableHeader.tsx

interface FilterableHeaderProps {
  label: string;
  filterValue: string;
  onFilterChange: (value: string) => void;
  sortable?: boolean;
  sortDirection?: "asc" | "desc" | null;
  onSort?: () => void;
  placeholder?: string;
  maxW?: string;
  isNumeric?: boolean;
}
```

**Usage in BankingProcessor (before → after):**

Before: 13 identical `<Th>` blocks, each 3 lines

```tsx
<Th p={1}>
  <Input
    size="xs"
    placeholder="ID"
    value={columnFilters.ID}
    onChange={(e) =>
      setColumnFilters((prev) => ({ ...prev, ID: e.target.value }))
    }
    bg="gray.600"
    color="white"
  />
</Th>
```

After: 1 line per column

```tsx
<FilterableHeader
  label="ID"
  filterValue={filters.ID}
  onFilterChange={(v) => setFilter("ID", v)}
  placeholder="ID"
/>
```

#### 4. `useFilterableTable<T>` — Combined hook (filters + sort + pagination)

For components that need all three, a single hook that composes `useColumnFilters` + `useTableSort`:

```tsx
// frontend/src/hooks/useFilterableTable.ts

function useFilterableTable<T extends Record<string, any>>(
  data: T[],
  config: {
    initialFilters: Record<string, string>;
    defaultSort?: { field: keyof T; direction: "asc" | "desc" };
    pageSize?: number;
    debounceMs?: number;
  },
) {
  // Returns everything from both hooks plus:
  return {
    // From useColumnFilters
    filters,
    setFilter,
    resetFilters,
    hasActiveFilters,
    // From useTableSort
    sortField,
    sortDirection,
    handleSort,
    getSortIndicator,
    // Combined
    processedData, // filtered + sorted + paginated
    totalFiltered, // count after filtering (before pagination)
    // Pagination (optional)
    currentPage,
    setCurrentPage,
    totalPages,
  };
}
```

**Usage in BankingProcessor mutaties tab:**

Before: ~50 lines of state + effects + memos
After:

```tsx
const {
  filters, setFilter, resetFilters,
  sortField, handleSort, getSortIndicator,
  processedData, totalFiltered,
} = useFilterableTable(mutaties, {
  initialFilters: { ID: '', TransactionNumber: '', TransactionDate: '', ... },
  defaultSort: { field: 'TransactionDate', direction: 'desc' },
  pageSize: 100,
});
```

---

### Impact Summary

| Helper               | Files that benefit | Lines saved per file              | Total lines saved (est.) |
| -------------------- | ------------------ | --------------------------------- | ------------------------ |
| `useColumnFilters`   | 6 files            | ~25 lines                         | ~150                     |
| `useTableSort`       | 7 files            | ~15 lines                         | ~105                     |
| `FilterableHeader`   | 3 files            | ~40 lines (BankingProcessor: ~80) | ~160                     |
| `useFilterableTable` | 3-4 complex files  | ~50 lines                         | ~175                     |
| **Total**            |                    |                                   | **~590 lines**           |

### Where to put them

```
frontend/src/
├── hooks/
│   ├── useColumnFilters.ts      ← NEW
│   ├── useTableSort.ts          ← NEW
│   └── useFilterableTable.ts    ← NEW (composes the above two)
├── components/filters/
│   ├── FilterableHeader.tsx     ← NEW
│   ├── FilterPanel.tsx          ← KEEP (for above-table dropdown/multi-select filters)
│   ├── GenericFilter.tsx        ← KEEP
│   ├── YearFilter.tsx           ← KEEP
│   └── types.ts                 ← EXTEND (add FilterableHeaderProps)
```

### Relationship to existing framework

These helpers **complement** the existing `FilterPanel` / `GenericFilter` framework — they don't replace it:

| Concern                                   | Existing framework              | New helpers                             |
| ----------------------------------------- | ------------------------------- | --------------------------------------- |
| Dropdown/multi-select filters above table | `FilterPanel` + `GenericFilter` | —                                       |
| Year selection                            | `YearFilter`                    | —                                       |
| Text search in column headers             | — (ad-hoc)                      | `FilterableHeader` + `useColumnFilters` |
| Sort toggle                               | — (ad-hoc)                      | `useTableSort`                          |
| Combined filter+sort+paginate             | — (ad-hoc)                      | `useFilterableTable`                    |
| Filter type definitions                   | `types.ts`                      | Extends `types.ts`                      |

The hybrid approach from the previous section becomes concrete:

- **Above-table filters** → `FilterPanel` (already exists)
- **In-column text filters** → `FilterableHeader` + `useColumnFilters` (new)
- **Sort** → `useTableSort` (new)
- **All-in-one** → `useFilterableTable` (new, composes the above)

---

## Clarification: Components vs Hooks vs Utility Functions

The filter/table framework has three distinct layers. Understanding the distinction matters for deciding where new code belongs.

### Layer definitions

| Layer                | What it does                                      | Has UI? | Has React state? | Examples in codebase                                          |
| -------------------- | ------------------------------------------------- | ------- | ---------------- | ------------------------------------------------------------- |
| **Component**        | Renders DOM elements (inputs, dropdowns, tables)  | ✅ Yes  | ✅ Yes           | `FilterPanel`, `GenericFilter`, `YearFilter`                  |
| **Custom hook**      | Manages state + logic, returns data to components | ❌ No   | ✅ Yes           | `useAccountLookup`, `useTypedTranslation`, `useTenantModules` |
| **Utility function** | Pure logic — no React, no state, no rendering     | ❌ No   | ❌ No            | `generateYearOptions`, `formatCurrency`, `formatDate`         |

### Where existing pieces fit

`FilterPanel` and `GenericFilter` are **components** — they render UI. They don't help with the state management, debounce, or filtering logic. Each consuming component still wires that up manually, which is why the same 20-30 lines of boilerplate appear in 6+ files.

### The full architecture (existing + proposed)

```
┌─────────────────────────────────────────────────────┐
│  UTILITY FUNCTIONS (pure logic, no React)           │
│                                                     │
│  generateYearOptions()   formatCurrency()           │
│  formatDate()                                       │
└──────────────────────┬──────────────────────────────┘
                       │ used by
┌──────────────────────▼──────────────────────────────┐
│  CUSTOM HOOKS (state + logic, no UI)                │
│                                                     │
│  useColumnFilters()    ← NEW: filter state,         │
│                          debounce, apply filtering   │
│  useTableSort()        ← NEW: sort state, toggle,   │
│                          apply sorting               │
│  useFilterableTable()  ← NEW: composes both +        │
│                          pagination                  │
│  useAccountLookup()    (existing)                    │
│  useTenantModules()    (existing)                    │
└──────────────────────┬──────────────────────────────┘
                       │ feeds data into
┌──────────────────────▼──────────────────────────────┐
│  COMPONENTS (renders UI)                            │
│                                                     │
│  Above-table filters:                               │
│    FilterPanel         (existing — dropdown/multi)   │
│    GenericFilter       (existing — single control)   │
│    YearFilter          (existing — year-specific)    │
│                                                     │
│  In-column filters:                                 │
│    FilterableHeader    ← NEW: <Th> with label +      │
│                          input + sort indicator      │
│                                                     │
│  Table itself:                                      │
│    Chakra Table/Thead/Tbody/Tr/Th/Td (Chakra UI)    │
└─────────────────────────────────────────────────────┘
```

### How they connect in a typical component

```tsx
// Page component (e.g., ChartOfAccounts)

// 1. Hook provides state + logic (no UI)
const { filters, setFilter, resetFilters, filteredData, hasActiveFilters } =
  useColumnFilters(accounts, { Account: '', AccountName: '', ... });

const { handleSort, getSortIndicator, sortedData } =
  useTableSort(filteredData, 'Account', 'asc');

// 2. Above-table component renders dropdown filters (UI)
<FilterPanel filters={[
  { type: 'single', label: 'Type', options: types, value: typeFilter, onChange: setTypeFilter }
]} />

// 3. Table header component renders in-column filters (UI)
<Thead>
  <Tr>
    <FilterableHeader label="Account" filterValue={filters.Account}
      onFilterChange={(v) => setFilter('Account', v)}
      sortable sortDirection={getSortIndicator('Account')}
      onSort={() => handleSort('Account')} />
    ...
  </Tr>
</Thead>

// 4. Table body uses the processed data from hooks
<Tbody>
  {sortedData.map(row => <Tr key={row.id}>...</Tr>)}
</Tbody>
```

### Key takeaway

The existing `FilterPanel`/`GenericFilter` components handle **rendering** of above-table filters. The proposed hooks (`useColumnFilters`, `useTableSort`, `useFilterableTable`) handle the **logic** that is currently duplicated as boilerplate in every consuming component. The proposed `FilterableHeader` component handles **rendering** of in-column filters. All three layers work together.

---

## Migration Status: COMPLETE ✅

**Date completed:** 2026-04-18

The Table Filter Framework v2 migration is fully complete. All 16 target components have been migrated to the new standard:

- **Foundation hooks** (`useColumnFilters`, `useTableSort`, `useFilterableTable`, `useTableConfig`) and `FilterableHeader` component are implemented and tested with both unit tests and property-based tests.
- **Exemplary upgrades** (ChartOfAccounts, ParameterManagement, BankingProcessor) use parameter-driven config via `useTableConfig`.
- **High-priority migrations** (MutatiesReport, ProfitLoss, ProvisioningPanel) use `useFilterableTable` + `FilterableHeader`.
- **Medium-priority migrations** (ZZPContacts, ZZPInvoices, ZZPTimeTracking, TaxRateManagement, AssetList, UserManagement, TenantManagement, RoleManagement) use `FilterPanel` with proper row-click patterns.
- **Low-priority migrations** (BnbFutureReport) complete.
- **Accepted exceptions** (BankConnect, HealthCheck) retain their specialized patterns as documented.
- **Dead code removed**: ClosedYearsTable, YearClosureWizard, YearEndClosure page, YearEndClosureReport, SystemAdmin.tsx, SystemAdmin.old.tsx.

Full framework reference: `.kiro/specs/Common/Filters a generic approach/TABLE_FILTER_FRAMEWORK_V2.md`
