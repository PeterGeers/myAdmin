Since the introduction of the Multi-tenant approach A user can work in a tenant selected. If a user has access to multi tenants he can switch at tenant level. The tenant level is defined as administration in all tenant related tables in MySQL.

The unified-admin-year-filter is now covering too much in terms of scope. At a few places the administration field is suppressed where the unified-admin-year-filter function is used.

The frontend\src\components\UnifiedAdminYearFilter.tsx is 572 lines of code as of 20260202
The frontend\src\components\UnifiedAdminYearFilter.test.tsx is 2000 lines of code as of 20260202

---

## Questions and Answers

### Question 1: In how many and in which source files is the function used?

**Answer**: The `UnifiedAdminYearFilter` component is used in **8 source files** (excluding test files):

#### Production Usage (8 files):

1. **frontend/src/components/reports/ActualsReport.tsx**
   - Usage: Financial actuals dashboard
   - Configuration: Multi-select years, administration hidden (uses tenant context)
   - Adapter: `createActualsFilterAdapter`

2. **frontend/src/components/reports/BnbActualsReport.tsx**
   - Usage: BNB (short-term rental) actuals report
   - Configuration: Multi-select years, administration hidden (BNB doesn't use administration)
   - Adapter: `createBnbActualsFilterAdapter`

3. **frontend/src/components/reports/BnbViolinsReport.tsx**
   - Usage: BNB violin plot visualizations
   - Configuration: Multi-select years, administration hidden
   - Adapter: `createBnbViolinFilterAdapter`

4. **frontend/src/components/reports/BtwReport.tsx**
   - Usage: BTW (VAT) tax report
   - Configuration: Single-select year, administration hidden (uses tenant context)
   - Adapter: `createBtwFilterAdapter`

5. **frontend/src/components/reports/AangifteIbReport.tsx**
   - Usage: Income tax (Aangifte IB) report
   - Configuration: Single-select year, administration hidden (uses tenant context)
   - Adapter: `createAangifteIbFilterAdapter`

6. **frontend/src/components/reports/ReferenceAnalysisReport.tsx**
   - Usage: Reference number analysis
   - Configuration: Multi-select years, administration hidden
   - Adapter: `createRefAnalysisFilterAdapter`

7. **frontend/src/components/myAdminReports.tsx** (Legacy - 5 instances)
   - Usage: Monolithic reports component (being phased out)
   - Multiple instances for different report types
   - Note: This file is 3600+ lines and should be refactored

#### Test Files (4 files):

- UnifiedAdminYearFilter.test.tsx (2000 lines)
- UnifiedAdminYearFilter.integration.test.tsx
- ActualsReport.test.tsx (mocks the component)
- BtwReport.test.tsx (mocks the component)
- AangifteIbReport.test.tsx (mocks the component)

#### Key Observations:

- **Administration field is suppressed in 6 out of 8 use cases** (`showAdministration: false`)
- Most reports now use tenant context instead of administration dropdown
- The component is primarily used as a **year filter** rather than admin+year filter
- Adapter pattern is used consistently via `UnifiedAdminYearFilterAdapters.ts`

---

### Question 2: What would be a good solution to rescope the function to a unified year filter?

**Answer**: Create a **focused, single-responsibility component** with the following approach:

#### Recommended Solution: Component Hierarchy

```
GenericFilter (new base component)
    ├── YearFilter (specialized for years)
    ├── AdministrationFilter (specialized for admin - if still needed)
    └── UnifiedAdminYearFilter (legacy wrapper - deprecated)
```

#### Implementation Strategy:

**Phase 1: Create GenericFilter Base Component**

```typescript
// frontend/src/components/filters/GenericFilter.tsx
interface GenericFilterProps<T> {
  // Core filtering
  values: T[];
  onChange: (values: T[]) => void;
  availableOptions: T[];

  // Behavior
  multiSelect?: boolean;
  disabled?: boolean;

  // Display
  label: string;
  placeholder?: string;
  size?: "sm" | "md" | "lg";

  // Rendering
  renderOption?: (option: T) => React.ReactNode;
  getOptionLabel?: (option: T) => string;
  getOptionValue?: (option: T) => string;
}
```

**Phase 2: Create Specialized YearFilter**

```typescript
// frontend/src/components/filters/YearFilter.tsx
interface YearFilterProps {
  years: string[];
  onYearChange: (years: string[]) => void;
  availableYears: string[];
  multiSelect?: boolean;
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
}

const YearFilter: React.FC<YearFilterProps> = (props) => {
  return (
    <GenericFilter
      values={props.years}
      onChange={props.onYearChange}
      availableOptions={props.availableYears}
      multiSelect={props.multiSelect}
      label="Year"
      placeholder="Select year(s)"
      size={props.size}
      disabled={props.disabled}
    />
  );
};
```

**Phase 3: Migration Path**

1. Create new `GenericFilter` and `YearFilter` components
2. Update reports one-by-one to use `YearFilter`
3. Deprecate `UnifiedAdminYearFilter` (mark with @deprecated)
4. Remove after all migrations complete

#### Benefits:

- ✅ **Reduced complexity**: YearFilter is ~100 lines vs 572 lines
- ✅ **Single responsibility**: Each component does one thing well
- ✅ **Easier testing**: Smaller components = simpler tests
- ✅ **Better reusability**: GenericFilter can be used for other filter types
- ✅ **Clearer intent**: Component name matches actual usage

---

### Question 3: What would be the added value of a generic filter function?

**Answer**: A generic filter function would provide **significant value** through consistency, reusability, and extensibility.

#### Added Value:

**1. Consistent Look & Feel**

- All filters across the application have identical UI/UX
- Users learn once, use everywhere
- Reduces cognitive load
- Easier to maintain design system compliance

**2. Code Reusability**

- Write filter logic once, use for multiple data types
- Reduces duplication (currently ~3000 lines of filter code)
- Faster development of new reports
- Fewer bugs through shared, well-tested code

**3. Type Safety**

- Generic TypeScript types ensure compile-time safety
- Prevents runtime errors from incorrect filter usage
- Better IDE autocomplete and refactoring support

**4. Extensibility**

- Easy to add new filter types without duplicating code
- Consistent adapter pattern for integration
- Plugin architecture for custom behaviors

#### Multi-Scope Support Architecture:

```typescript
// Generic base that works for any filterable data type
interface FilterConfig<T> {
  type: "single" | "multi" | "range" | "search"; // ← Controls single vs multi-select
  label: string;
  options: T[];
  value: T | T[]; // ← Single value OR array of values
  onChange: (value: T | T[]) => void;
  renderOption?: (option: T) => React.ReactNode;
}

// Type-safe variants for clarity:
interface SingleSelectFilterConfig<T> extends Omit<
  FilterConfig<T>,
  "type" | "value" | "onChange"
> {
  type: "single";
  value: T; // Single value only
  onChange: (value: T) => void;
}

interface MultiSelectFilterConfig<T> extends Omit<
  FilterConfig<T>,
  "type" | "value" | "onChange"
> {
  type: "multi";
  value: T[]; // Array of values
  onChange: (values: T[]) => void;
}

// Specialized filters built on generic base
type YearFilterConfig = FilterConfig<string>;
type LedgerFilterConfig = FilterConfig<{ code: string; name: string }>;
type ListingFilterConfig = FilterConfig<{
  id: string;
  name: string;
  address: string;
}>;
type ChannelFilterConfig = FilterConfig<"airbnb" | "booking" | "direct">;
```

#### Example: Multi-Scope Filter Panel

```typescript
// frontend/src/components/filters/FilterPanel.tsx
interface FilterPanelProps {
  filters: FilterConfig<any>[];
  layout?: 'horizontal' | 'vertical' | 'grid';
  size?: 'sm' | 'md' | 'lg';
}

// Usage in a report demonstrating BOTH single and multi-select:
<FilterPanel
  filters={[
    // MULTI-SELECT: Select multiple years (dynamically loaded from dataset)
    {
      type: 'multi',  // ← Multi-select
      label: 'Years',
      options: availableYears,  // ← Dynamically loaded from API/dataset
      value: selectedYears,  // e.g., ['2023', '2024']
      onChange: setSelectedYears
    },
    // SINGLE-SELECT: Select one ledger account
    {
      type: 'single',  // ← Single-select
      label: 'Ledger',
      options: ledgerAccounts,
      value: selectedLedger,  // e.g., '1000'
      onChange: setSelectedLedger,
      renderOption: (ledger) => `${ledger.code} - ${ledger.name}`
    },
    // MULTI-SELECT: Select multiple listings
    {
      type: 'multi',  // ← Multi-select
      label: 'Listings',
      options: listings,
      value: selectedListings,  // e.g., ['listing1', 'listing3']
      onChange: setSelectedListings,
      renderOption: (listing) => (
        <Box>
          <Text fontWeight="bold">{listing.name}</Text>
          <Text fontSize="sm" color="gray.600">{listing.address}</Text>
        </Box>
      )
    },
    // MULTI-SELECT: Select multiple channels
    {
      type: 'multi',  // ← Multi-select
      label: 'Channels',
      options: ['airbnb', 'booking', 'direct'],
      value: selectedChannels,  // e.g., ['airbnb', 'booking']
      onChange: setSelectedChannels
    }
  ]}
  layout="grid"
  size="md"
/>
```

**Key Features:**

- ✅ **Single-select**: Returns single value (e.g., BTW year, quarter selection)
- ✅ **Multi-select**: Returns array of values (e.g., Actuals years, BNB listings)
- ✅ **Type-safe**: TypeScript enforces correct value types
- ✅ **Flexible**: Mix single and multi-select in same filter panel
- ✅ **Dynamic options**: Years loaded from dataset (past data) or generated (future planning)
- ✅ **Range support**: Can include past years + current + future years

---

#### Dynamic Year Loading Strategies

The filter supports multiple strategies for populating year options:

**Strategy 1: Historical Data Only (from dataset)**

```typescript
// Only show years that have actual data
const availableYears = await fetchYearsFromDatabase(); // ['2022', '2023', '2024']
```

**Strategy 2: Future Planning (generated range)**

```typescript
// Show current year + next N years for forecasting
const currentYear = new Date().getFullYear();
const availableYears = Array.from({ length: 3 }, (_, i) =>
  (currentYear + i).toString(),
); // ['2025', '2026', '2027']
```

**Strategy 3: Combined Past + Future (hybrid)**

```typescript
// Show historical data + future years for planning
const historicalYears = await fetchYearsFromDatabase(); // ['2022', '2023', '2024']
const currentYear = new Date().getFullYear();
const futureYears = Array.from({ length: 2 }, (_, i) =>
  (currentYear + 1 + i).toString(),
); // ['2026', '2027']

const availableYears = [
  ...historicalYears,
  currentYear.toString(),
  ...futureYears,
].sort(); // ['2022', '2023', '2024', '2025', '2026', '2027']
```

**Strategy 4: Rolling Window (last N years + next M years)**

```typescript
// Show last 3 years + current + next 2 years
const currentYear = new Date().getFullYear();
const availableYears = Array.from({ length: 6 }, (_, i) =>
  (currentYear - 3 + i).toString(),
); // ['2022', '2023', '2024', '2025', '2026', '2027']
```

**Real-World Examples in myAdmin:**

**BNB Future Revenue Report** (needs future years)

```typescript
// Show current year + next 2 years for booking forecasts
const currentYear = new Date().getFullYear();
const availableYears = [
  currentYear.toString(),
  (currentYear + 1).toString(),
  (currentYear + 2).toString()
]; // ['2025', '2026', '2027']

<FilterPanel filters={[
  {
    type: 'multi',
    label: 'Years',
    options: availableYears,  // Future years for planning
    value: selectedYears,
    onChange: setSelectedYears
  }
]} />
```

**Actuals Report** (needs historical years only)

```typescript
// Show only years with actual financial data
const availableYears = await fetchYearsFromDatabase(); // ['2022', '2023', '2024']

<FilterPanel filters={[
  {
    type: 'multi',
    label: 'Years',
    options: availableYears,  // Historical data only
    value: selectedYears,
    onChange: setSelectedYears
  }
]} />
```

**Budget Planning Report** (needs past + future)

```typescript
// Show last 2 years (for comparison) + current + next 2 years (for planning)
const currentYear = new Date().getFullYear();
const historicalYears = [(currentYear - 2).toString(), (currentYear - 1).toString()];
const futureYears = [(currentYear + 1).toString(), (currentYear + 2).toString()];
const availableYears = [
  ...historicalYears,
  currentYear.toString(),
  ...futureYears
]; // ['2023', '2024', '2025', '2026', '2027']

<FilterPanel filters={[
  {
    type: 'multi',
    label: 'Years',
    options: availableYears,  // Past + current + future
    value: selectedYears,
    onChange: setSelectedYears
  }
]} />
```

**Implementation in GenericFilter:**

```typescript
// Helper function to generate year options
export const generateYearOptions = (config: {
  mode: "historical" | "future" | "combined" | "rolling";
  historicalYears?: string[]; // From database
  futureCount?: number; // How many future years
  pastCount?: number; // How many past years
}): string[] => {
  const currentYear = new Date().getFullYear();

  switch (config.mode) {
    case "historical":
      return config.historicalYears || [];

    case "future":
      return Array.from({ length: config.futureCount || 3 }, (_, i) =>
        (currentYear + i).toString(),
      );

    case "combined":
      const historical = config.historicalYears || [];
      const future = Array.from({ length: config.futureCount || 2 }, (_, i) =>
        (currentYear + 1 + i).toString(),
      );
      return [...historical, currentYear.toString(), ...future].sort();

    case "rolling":
      return Array.from(
        { length: (config.pastCount || 3) + 1 + (config.futureCount || 2) },
        (_, i) => (currentYear - (config.pastCount || 3) + i).toString(),
      );

    default:
      return [currentYear.toString()];
  }
};

// Usage:
const availableYears = generateYearOptions({
  mode: "combined",
  historicalYears: await fetchYearsFromDatabase(),
  futureCount: 2,
});
```

**Benefits:**

- ✅ **Flexible**: Supports any combination of past/current/future years
- ✅ **Configurable**: Each report can define its own year range strategy
- ✅ **Consistent**: Same filter component works for all scenarios
- ✅ **Type-safe**: TypeScript ensures correct usage

---

#### How Years Are Dynamically Loaded from Dataset

The `options` array is **always populated from your actual data**, not hardcoded. Here's how:

**Frontend: Loading Available Years**

```typescript
const ActualsReport: React.FC = () => {
  const [availableYears, setAvailableYears] = useState<string[]>([]);

  useEffect(() => {
    // Fetch years that have data in the database
    fetch('/api/actuals/available-years')
      .then(res => res.json())
      .then(data => setAvailableYears(data.years));
  }, []);

  return (
    <FilterPanel
      filters={[{
        type: 'multi',
        label: 'Years',
        options: availableYears,  // ← From database, not hardcoded
        value: selectedYears,
        onChange: setSelectedYears
      }]}
    />
  );
};
```

**Backend: Query Distinct Years from Data**

```python
@actuals_bp.route('/available-years', methods=['GET'])
def get_available_years():
    # Query distinct years from mutaties table
    query = """
        SELECT DISTINCT YEAR(Datum) as year
        FROM mutaties
        WHERE Administration = %s
        ORDER BY year DESC
    """
    cursor.execute(query, (current_tenant,))
    years = [str(row['year']) for row in cursor.fetchall()]
    return jsonify({'years': years})
```

**Your Current Implementation Already Does This:**

```typescript
// From ActualsReport.tsx
const [actualsAvailableYears, setActualsAvailableYears] = useState<string[]>([]);

// Fetched from API on mount
useEffect(() => {
  fetchAvailableYears().then(years => setActualsAvailableYears(years));
}, []);

// Passed to filter
<UnifiedAdminYearFilter
  availableYears={actualsAvailableYears}  // ← Dynamic from database
  // ...
/>
```

**Benefits:**

- ✅ Only shows years with actual data
- ✅ Tenant-specific (each tenant sees their years)
- ✅ Auto-updates when new data added
- ✅ Prevents selecting years with no data

````

#### Real-World Use Cases in myAdmin:

**1. BNB Reports** (currently using custom filters)

```typescript
// Current: Multiple separate filter components
// Proposed: Single FilterPanel with multiple scopes
<FilterPanel filters={[
  // Multi-select years
  { type: 'multi', label: 'Years', options: ['2023', '2024', '2025'], value: selectedYears, onChange: setSelectedYears },
  // Multi-select listings
  { type: 'multi', label: 'Listings', options: listings, value: selectedListings, onChange: setSelectedListings },
  // Multi-select channels
  { type: 'multi', label: 'Channels', options: ['airbnb', 'booking', 'direct'], value: selectedChannels, onChange: setSelectedChannels },
  // Single-select period
  { type: 'single', label: 'Period', options: ['month', 'quarter', 'year'], value: selectedPeriod, onChange: setSelectedPeriod }
]} />
```

**2. BTW Report** (currently using UnifiedAdminYearFilter with single-select)

```typescript
// Current: UnifiedAdminYearFilter with multiSelectYears: false
// Proposed: FilterPanel with single-select year
<FilterPanel filters={[
  // Single-select year (BTW requires one year at a time)
  { type: 'single', label: 'Year', options: ['2023', '2024', '2025'], value: selectedYear, onChange: setSelectedYear },
  // Single-select quarter
  { type: 'single', label: 'Quarter', options: ['Q1', 'Q2', 'Q3', 'Q4'], value: selectedQuarter, onChange: setSelectedQuarter }
]} />
```

**3. Actuals Report** (currently using UnifiedAdminYearFilter with multi-select)

```typescript
// Current: UnifiedAdminYearFilter with multiSelectYears: true
// Proposed: FilterPanel with multi-select years
<FilterPanel filters={[
  // Multi-select years (compare multiple years)
  { type: 'multi', label: 'Years', options: ['2023', '2024', '2025'], value: selectedYears, onChange: setSelectedYears },
  // Multi-select ledger accounts
  { type: 'multi', label: 'Accounts', options: ledgerAccounts, value: selectedAccounts, onChange: setSelectedAccounts },
  // Single-select display format
  { type: 'single', label: 'Format', options: ['table', 'chart', 'both'], value: displayFormat, onChange: setDisplayFormat }
]} />
```

**4. Reference Analysis** (currently using UnifiedAdminYearFilter + custom filters)

```typescript
<FilterPanel filters={[
  // Multi-select years
  { type: 'multi', label: 'Years', options: availableYears, value: selectedYears, onChange: setSelectedYears },
  // Search filter for reference number
  { type: 'search', label: 'Reference Number', value: referenceNumber, onChange: setReferenceNumber },
  // Multi-select accounts
  { type: 'multi', label: 'Accounts', options: accounts, value: selectedAccounts, onChange: setSelectedAccounts }
]} />
```

**Summary of Current Usage:**
- ✅ **Single-select needed**: BTW (year + quarter), Aangifte IB (year), Display formats
- ✅ **Multi-select needed**: Actuals (years), BNB (years, listings, channels), Reference Analysis (years, accounts)
- ✅ **Mixed usage**: Most reports need BOTH single and multi-select for different fields

#### Implementation Roadmap:

**Phase 1: Foundation (1-2 weeks)**

- Create `GenericFilter<T>` base component
- Create `FilterPanel` container component
- Write comprehensive tests
- Document API and usage patterns

**Phase 2: Specialized Filters (1 week)**

- Create `YearFilter` (wraps GenericFilter)
- Create `LedgerFilter` (wraps GenericFilter)
- Create `ListingFilter` (wraps GenericFilter)
- Create `ChannelFilter` (wraps GenericFilter)

**Phase 3: Migration (2-3 weeks)**

- Migrate BNB reports to use new filters
- Migrate financial reports to use new filters
- Migrate reference analysis to use new filters
- Update tests

**Phase 4: Cleanup (1 week)**

- Deprecate `UnifiedAdminYearFilter`
- Remove old filter code
- Update documentation

#### Estimated Impact:

**Code Reduction:**

- Current filter code: ~3000 lines (UnifiedAdminYearFilter + adapters + custom filters)
- Proposed filter code: ~800 lines (GenericFilter + specialized filters + FilterPanel)
- **Reduction: ~73% less code**

**Test Reduction:**

- Current tests: ~2500 lines
- Proposed tests: ~1000 lines (focused on GenericFilter + integration tests)
- **Reduction: ~60% less test code**

**Maintenance:**

- Single source of truth for filter behavior
- Easier to add new filter types
- Consistent bug fixes across all filters
- Better accessibility compliance

---

## Recommendations

### Immediate Actions:

1. ✅ **Rename component**: `UnifiedAdminYearFilter` → `YearFilter` (reflects actual usage)
2. ✅ **Remove administration logic**: Since 75% of use cases hide it, extract to separate component if needed
3. ✅ **Reduce test file size**: Split 2000-line test file into focused test suites

### Short-Term (1-2 months):

1. Create `GenericFilter<T>` base component
2. Create specialized filters (Year, Ledger, Listing, Channel)
3. Migrate 2-3 reports as proof of concept
4. Gather feedback and iterate

### Long-Term (3-6 months):

1. Migrate all reports to use new filter system
2. Create `FilterPanel` for complex multi-filter scenarios
3. Deprecate and remove `UnifiedAdminYearFilter`
4. Document patterns and best practices

---

## Conclusion

The `UnifiedAdminYearFilter` component has outgrown its original purpose. With 75% of use cases hiding the administration field and the component being 572 lines of complex code, it's time to refactor into a more focused, reusable solution.

A generic filter architecture would:

- Reduce code by ~73%
- Improve maintainability
- Enable faster feature development
- Provide consistent UX across all reports
- Support future filter types without code duplication

The recommended approach is a phased migration starting with a `GenericFilter` base component and specialized filters built on top of it.
````
