# Table Filter Framework v2 — Reference Guide

## Architecture Overview

The framework has three layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  Components (render UI)                                         │
│  FilterPanel · GenericFilter · YearFilter · FilterableHeader    │
├─────────────────────────────────────────────────────────────────┤
│  Hooks (state + logic)                                          │
│  useColumnFilters · useTableSort · useFilterableTable            │
│  useTableConfig (parameter-driven, 3 complex tables only)       │
├─────────────────────────────────────────────────────────────────┤
│  Services                                                       │
│  parameterService.ts · Parameter Admin API                      │
└─────────────────────────────────────────────────────────────────┘
```

**Layer 1 — Services**: The existing `parameterService.ts` fetches configuration from the backend parameter system (scope inheritance: user → role → tenant → system).

**Layer 2 — Hooks**: Custom React hooks manage filter state, sort state, debounce, and data transformation. They are composable — `useFilterableTable` composes `useColumnFilters` + `useTableSort`.

**Layer 3 — Components**: `FilterableHeader` renders a `<Th>` with label + sort indicator + text filter input. `FilterPanel` / `GenericFilter` / `YearFilter` render dropdown and multi-select filters above the table.

---

## The Hybrid Approach

Text search filters live **inside column headers** via `FilterableHeader` for direct visual association. Dropdown, multi-select, and year filters remain **above the table** in `FilterPanel`.

```tsx
// Hybrid layout: dropdowns above, text search in headers
<Box>
  {/* Dropdown filters above the table */}
  <FilterPanel config={filterPanelConfig} />

  <Table>
    <Thead>
      <Tr>
        {/* Text search filters inside column headers */}
        <FilterableHeader
          label="Account"
          filterValue={filters.Account}
          onFilterChange={(v) => setFilter("Account", v)}
          sortable
          sortDirection={sortField === "Account" ? sortDirection : null}
          onSort={() => handleSort("Account")}
        />
        {/* ... more columns */}
      </Tr>
    </Thead>
    <Tbody>
      {processedData.map((row) => (
        <Tr
          key={row.id}
          _hover={{ bg: "gray.700", cursor: "pointer" }}
          onClick={() => handleRowClick(row)}
        >
          <Td>{row.Account}</Td>
        </Tr>
      ))}
    </Tbody>
  </Table>
</Box>
```

**When to use which filter type:**

| Filter Type            | Placement                                     | Use When                                                 |
| ---------------------- | --------------------------------------------- | -------------------------------------------------------- |
| Text search            | Column header (`FilterableHeader`)            | Free-text substring matching on a column                 |
| Single-select dropdown | Above table (`FilterPanel` + `GenericFilter`) | Filtering by a fixed set of options (e.g., status, type) |
| Multi-select checkbox  | Above table (`FilterPanel` + `GenericFilter`) | Filtering by multiple values simultaneously              |
| Year filter            | Above table (`FilterPanel` + `YearFilter`)    | Filtering by fiscal year                                 |

---

## Hooks

### useColumnFilters

Manages column filter state with debounce and case-insensitive substring matching.

**Location:** `frontend/src/hooks/useColumnFilters.ts`

```typescript
import { useColumnFilters } from "../hooks/useColumnFilters";

const { filters, setFilter, resetFilters, filteredData, hasActiveFilters } =
  useColumnFilters<MyRow>(
    data,
    { name: "", status: "", amount: "" },
    { debounceMs: 150 },
  );
```

**Parameters:**

- `data: T[]` — Source data array
- `initialFilters: Record<string, string>` — Keys define filterable columns (values start as `''`)
- `options?: { debounceMs?: number }` — Debounce delay (default: 150ms)

**Returns:**
| Property | Type | Description |
|---|---|---|
| `filters` | `Record<string, string>` | Current filter values (for input binding) |
| `setFilter` | `(key, value) => void` | Update a single filter |
| `resetFilters` | `() => void` | Clear all filters to `''` |
| `filteredData` | `T[]` | Data after applying all active filters |
| `hasActiveFilters` | `boolean` | True if any filter is non-empty |

**Filtering rules:**

- Case-insensitive substring matching
- All active filters must pass for a row to be included (AND logic)
- If a filter key does not exist on a row, the filter passes (row not excluded)
- Null/undefined field values are converted to `''` before matching

---

### useTableSort

Manages sort field, direction toggle, and applies sorting.

**Location:** `frontend/src/hooks/useTableSort.ts`

```typescript
import { useTableSort } from "../hooks/useTableSort";

const { sortField, sortDirection, handleSort, sortedData, getSortIndicator } =
  useTableSort<MyRow>(data, "name", "asc");
```

**Parameters:**

- `data: T[]` — Source data array
- `defaultField?: string` — Initial sort field (default: `null` = no sort)
- `defaultDirection?: SortDirection` — Initial direction (default: `'asc'`)

**Returns:**
| Property | Type | Description |
|---|---|---|
| `sortField` | `string \| null` | Active sort field |
| `sortDirection` | `SortDirection` | `'asc'` or `'desc'` |
| `handleSort` | `(field) => void` | Toggle sort (same field = flip, new field = asc) |
| `sortedData` | `T[]` | Data after sorting |
| `getSortIndicator` | `(field) => string` | Returns `'↑'`, `'↓'`, or `''` |

**Sorting rules:**

- Strings: case-insensitive via `localeCompare({ sensitivity: 'base' })`
- Numbers: numeric comparison
- Null/undefined: always sort to end regardless of direction

---

### useFilterableTable

Composes `useColumnFilters` + `useTableSort` into a single hook. Filtering is applied **before** sorting.

**Location:** `frontend/src/hooks/useFilterableTable.ts`

```typescript
import { useFilterableTable } from "../hooks/useFilterableTable";

const {
  filters,
  setFilter,
  resetFilters,
  hasActiveFilters,
  sortField,
  sortDirection,
  handleSort,
  getSortIndicator,
  processedData,
} = useFilterableTable<MyRow>(data, {
  initialFilters: { name: "", status: "" },
  defaultSort: { field: "name", direction: "asc" },
  debounceMs: 150,
});
```

**Config:**
| Property | Type | Description |
|---|---|---|
| `initialFilters` | `Record<string, string>` | Keys define filterable columns |
| `defaultSort?` | `{ field, direction }` | Optional initial sort |
| `debounceMs?` | `number` | Debounce delay (default: 150ms) |

**Returns:** All properties from `useColumnFilters` + `useTableSort`, plus `processedData` (the final filtered-then-sorted array).

---

### useTableConfig (Parameter-Driven)

Reads table column configuration from the parameter system. **Only for complex CRUD tables** with many columns.

**Location:** `frontend/src/hooks/useTableConfig.ts`

```typescript
import { useTableConfig } from "../hooks/useTableConfig";

const tableConfig = useTableConfig("chart_of_accounts");
// tableConfig.columns, tableConfig.filterableColumns, tableConfig.defaultSort, tableConfig.pageSize
```

**Supported entities:** `'chart_of_accounts'` | `'parameters'` | `'banking_mutaties'`

**Returns:**
| Property | Type | Description |
|---|---|---|
| `columns` | `string[]` | Ordered visible column keys |
| `filterableColumns` | `string[]` | Columns that get a filter input |
| `defaultSort` | `{ field, direction }` | Default sort config |
| `pageSize` | `number` | Rows per page |
| `loading` | `boolean` | True while fetching from API |
| `error` | `string \| null` | Error message (null = no error) |

**Behavior:**

- Returns hardcoded defaults immediately (no blank screen while loading)
- Merges parameter overrides from the API when they arrive
- Falls back to defaults on error (logs error, doesn't break rendering)
- Parameters are tenant-scoped and editable in the ParameterManagement UI

---

## Components

### FilterableHeader

Renders a `<Th>` with column label, optional sort indicator, and optional text filter input.

**Location:** `frontend/src/components/filters/FilterableHeader.tsx`

```tsx
import { FilterableHeader } from "../components/filters/FilterableHeader";

<FilterableHeader
  label="Account Name"
  filterValue={filters.AccountName}
  onFilterChange={(v) => setFilter("AccountName", v)}
  sortable
  sortDirection={sortField === "AccountName" ? sortDirection : null}
  onSort={() => handleSort("AccountName")}
  placeholder="Search..."
  isNumeric={false}
/>;
```

**Props:**
| Prop | Type | Description |
|---|---|---|
| `label` | `string` | Column label text |
| `filterValue?` | `string` | Current filter value (omit to disable filter) |
| `onFilterChange?` | `(value) => void` | Called on input change |
| `sortable?` | `boolean` | Enable sort indicator (default: false) |
| `sortDirection?` | `'asc' \| 'desc' \| null` | Current sort direction for this column |
| `onSort?` | `() => void` | Called on sort click |
| `placeholder?` | `string` | Input placeholder (default: "Filter...") |
| `isNumeric?` | `boolean` | Right-align for numeric columns |

**Accessibility:**

- `aria-label="Filter by {label}"` on the filter input
- `aria-sort="ascending|descending|none"` on the `<Th>` when sortable
- `role="button"` and `aria-label="Sort by {label}"` on the sort click area

---

## When to Use useTableConfig vs Hardcoded Config

| Scenario                                    | Approach                             | Example                           |
| ------------------------------------------- | ------------------------------------ | --------------------------------- |
| Complex CRUD table with many columns (8+)   | `useTableConfig`                     | ChartOfAccounts, BankingProcessor |
| Tenant needs to customize column visibility | `useTableConfig`                     | ParameterManagement               |
| Simple CRUD table (< 8 columns)             | Hardcoded `INITIAL_FILTERS` constant | ZZPProducts, ZZPContacts          |
| Report table (read-only, fixed layout)      | Hardcoded or no filters              | ProfitLossReport                  |
| Table with only dropdown filters            | `FilterPanel` only, no hooks needed  | BnbFutureReport                   |

**Rule of thumb:** If a tenant admin might want to show/hide columns or change the default sort without a code change, use `useTableConfig`. Otherwise, hardcode the config.

---

## Default Dark Theme Styling

All table components use these consistent dark theme values:

| Element                 | Property        | Value        |
| ----------------------- | --------------- | ------------ |
| Table container         | `bg`            | `gray.800`   |
| Table header (`<Th>`)   | `bg`            | `gray.700`   |
| Header label text       | `color`         | `gray.300`   |
| Header label            | `fontSize`      | `xs`         |
| Header label            | `fontWeight`    | `bold`       |
| Header label            | `textTransform` | `uppercase`  |
| Filter input            | `bg`            | `gray.600`   |
| Filter input            | `color`         | `white`      |
| Filter input            | `size`          | `xs`         |
| Sort indicator (active) | `color`         | `orange.300` |
| Row hover               | `bg`            | `gray.700`   |
| Row hover               | `cursor`        | `pointer`    |
| Table text              | `color`         | `white`      |

---

## Accepted Exceptions

These components are **exempt** from the standard table/filter patterns:

| Component                      | Reason                                            | Pattern Used           |
| ------------------------------ | ------------------------------------------------- | ---------------------- |
| BankConnect                    | Wizard-style per-row actions (connect/disconnect) | Per-row action buttons |
| HealthCheck                    | Monitoring dashboard with "View Details" per row  | Per-row detail button  |
| InvoiceLineEditor              | Editable line-item table (inline editing)         | Inline inputs in cells |
| Small config tables (< 5 rows) | Filtering adds no value                           | No filters             |
| Wizard UIs                     | Multi-step flows with different interaction model | Step-based navigation  |

---

## Reference Implementations

### 1. Simple CRUD Table — `ZZPProducts.tsx`

**Pattern:** `useFilterableTable` + `FilterableHeader` with hardcoded config.

**Key characteristics:**

- Hardcoded `INITIAL_FILTERS` constant defining all filterable columns
- `useFilterableTable` for combined filter + sort
- `FilterableHeader` for every column (all sortable + filterable)
- Row-click opens modal for CRUD
- No `useTableConfig` (simple table, no tenant customization needed)

**File:** `frontend/src/pages/ZZPProducts.tsx`

```tsx
const INITIAL_FILTERS: Record<string, string> = {
  product_code: "",
  name: "",
  product_type: "",
  unit_price: "",
  vat_code: "",
  unit_of_measure: "",
  external_reference: "",
};

const {
  filters,
  setFilter,
  handleSort,
  sortField,
  sortDirection,
  processedData,
} = useFilterableTable<Product>(products, {
  initialFilters: INITIAL_FILTERS,
  defaultSort: { field: "product_code", direction: "asc" },
});

// Helper for sortDirection prop
const columnSortDirection = (field: string): "asc" | "desc" | null =>
  sortField === field ? sortDirection : null;
```

### 2. Hybrid + Parameter-Driven — `ChartOfAccounts.tsx`

**Pattern:** `useTableConfig` + `useFilterableTable` + `FilterableHeader` with dynamic columns.

**Key characteristics:**

- `useTableConfig('chart_of_accounts')` loads column/filter config from parameters
- `initialFilters` derived dynamically from `tableConfig.filterableColumns`
- Column visibility driven by `tableConfig.columns`
- Tenant admins can customize via ParameterManagement UI
- Column labels mapped via `useColumnLabels()` helper

**File:** `frontend/src/components/TenantAdmin/ChartOfAccounts.tsx`

```tsx
const tableConfig = useTableConfig("chart_of_accounts");

const initialFilters = useMemo(
  () =>
    Object.fromEntries(tableConfig.filterableColumns.map((col) => [col, ""])),
  [tableConfig.filterableColumns],
);

const {
  filters,
  setFilter,
  handleSort,
  sortField,
  sortDirection,
  processedData,
} = useFilterableTable<Account>(accounts, {
  initialFilters,
  defaultSort: tableConfig.defaultSort,
});

// Render only configured columns
{
  tableConfig.columns.map((col) => (
    <FilterableHeader
      key={col}
      label={columnLabels[col] || col}
      filterValue={
        tableConfig.filterableColumns.includes(col) ? filters[col] : undefined
      }
      onFilterChange={(v) => setFilter(col, v)}
      sortable
      sortDirection={sortField === col ? sortDirection : null}
      onSort={() => handleSort(col)}
    />
  ));
}
```

### 3. Report Table with Multiple Sections — `ProfitLoss.tsx`

**Pattern:** Multiple `useFilterableTable` instances for different data sections.

**Key characteristics:**

- Two separate `useFilterableTable` calls (mutaties + BNB data)
- `FilterableHeader` with selective filtering (some columns sort-only, some filter + sort)
- Combined with `FilterPanel` + `YearFilter` above the table (hybrid approach)
- Read-only report data (no row-click modal)

**File:** `frontend/src/components/ProfitLoss.tsx`

```tsx
// Mutaties section
const { filters: mutatiesFilters, setFilter: setMutatiesFilter, ... } =
  useFilterableTable<MutatiesRecord>(mutatiesData, {
    initialFilters: MUTATIES_INITIAL_FILTERS,
  });

// BNB section
const { filters: bnbFilters, setFilter: setBnbFilter, ... } =
  useFilterableTable<BnbRecord>(bnbData, {
    initialFilters: BNB_INITIAL_FILTERS,
  });
```

---

## Migration Checklist

Use this checklist when converting an existing component to the v2 framework:

### Pre-Migration

- [ ] Identify current filter pattern (standalone `<Input>`/`<Select>`, `FilterPanel`, or manual `useState`)
- [ ] Identify current sort pattern (manual `handleSort` boilerplate or none)
- [ ] Identify row-click pattern (cell-click, row-click, or per-row buttons)
- [ ] Determine if `useTableConfig` is needed (complex table with 8+ columns, tenant customization)

### Implementation

- [ ] Define `INITIAL_FILTERS` constant (or derive from `useTableConfig().filterableColumns`)
- [ ] Replace manual filter `useState` + `useEffect` + `useMemo` with `useFilterableTable`
- [ ] Replace `<Th><Input .../></Th>` patterns with `<FilterableHeader>`
- [ ] Replace manual sort `useState` + toggle handler with hook's `handleSort`
- [ ] Move dropdown/multi-select filters to `FilterPanel` above the table (if not already)
- [ ] Move `onClick` from `<Td>` to `<Tr>` for full row-click
- [ ] Add `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` to clickable `<Tr>`
- [ ] Remove `cursor="pointer"` and underline styling from individual cells
- [ ] Use `processedData` for rendering instead of manually filtered/sorted arrays

### Post-Migration

- [ ] Verify all existing functionality preserved (filters, sort, modals, data fetching)
- [ ] Verify dark theme styling matches (gray.700 headers, gray.600 inputs, gray.300 labels)
- [ ] Verify accessibility (`aria-label` on inputs, `aria-sort` on headers)
- [ ] Remove unused imports (`useState` for filter state, old filter components)
- [ ] Commit: `refactor(ComponentName): migrate to table-filter-framework-v2`

### Common Patterns to Remove

```tsx
// BEFORE: Manual filter boilerplate (~25 lines) — REMOVE
const [filterName, setFilterName] = useState("");
const [debouncedFilter, setDebouncedFilter] = useState("");
useEffect(() => {
  const timer = setTimeout(() => setDebouncedFilter(filterName), 150);
  return () => clearTimeout(timer);
}, [filterName]);
const filteredData = useMemo(
  () =>
    data.filter((row) =>
      row.name.toLowerCase().includes(debouncedFilter.toLowerCase()),
    ),
  [data, debouncedFilter],
);

// AFTER: Single hook call
const { filters, setFilter, processedData } = useFilterableTable(data, {
  initialFilters: { name: "" },
});
```

```tsx
// BEFORE: Manual sort boilerplate (~15 lines) — REMOVE
const [sortField, setSortField] = useState('name');
const [sortDir, setSortDir] = useState<'asc'|'desc'>('asc');
const handleSort = (field: string) => {
  if (field === sortField) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
  else { setSortField(field); setSortDir('asc'); }
};

// AFTER: Included in useFilterableTable
const { handleSort, sortField, sortDirection } = useFilterableTable(data, { ... });
```

```tsx
// BEFORE: Inline filter input in <Th> — REMOVE
<Th bg="gray.700">
  <VStack>
    <Text fontSize="xs" color="gray.300">Name</Text>
    <Input size="xs" bg="gray.600" color="white"
      value={filterName} onChange={e => setFilterName(e.target.value)} />
  </VStack>
</Th>

// AFTER: FilterableHeader component
<FilterableHeader
  label="Name"
  filterValue={filters.name}
  onFilterChange={(v) => setFilter('name', v)}
  sortable
  sortDirection={sortField === 'name' ? sortDirection : null}
  onSort={() => handleSort('name')}
/>
```
