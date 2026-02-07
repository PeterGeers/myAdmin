# Filter System Documentation

## Overview

The myAdmin filter system provides a flexible, type-safe, and reusable approach to filtering data across reports. It replaces the legacy `UnifiedAdminYearFilter` component with a modular architecture that reduces code by ~73% while improving maintainability.

**Key Benefits:**

- Type-safe with TypeScript generics
- Supports single and multi-select modes
- Responsive design (mobile-friendly)
- Consistent UI across all reports
- Easy to extend with new filter types
- Comprehensive test coverage (80%+)

## Architecture

```
Filter System
├── GenericFilter<T>        # Base component (works with any data type)
├── YearFilter              # Specialized year filter
├── FilterPanel             # Container for multiple filters
├── types.ts                # TypeScript type definitions
└── utils/
    └── yearGenerator.ts    # Year option generation utilities
```

## Components

### GenericFilter<T>

The foundation of the filter system. A reusable component that works with any data type through TypeScript generics.

**Features:**

- Single-select mode (dropdown)
- Multi-select mode (checkbox menu)
- Loading and error states
- Custom option rendering
- Accessible (ARIA labels, keyboard navigation)

**Props:**

```typescript
interface GenericFilterProps<T> {
  // Core filtering
  values: T[]; // Current selected values
  onChange: (values: T[]) => void; // Callback when selection changes
  availableOptions: T[]; // Available options to select from

  // Behavior
  multiSelect?: boolean; // Enable multi-select mode (default: false)
  disabled?: boolean; // Disable the filter

  // Display
  label: string; // Label for the filter
  placeholder?: string; // Placeholder text when no selection
  size?: "sm" | "md" | "lg"; // Size variant

  // Rendering
  renderOption?: (option: T) => React.ReactNode; // Custom option renderer
  getOptionLabel?: (option: T) => string; // Get display label from option
  getOptionValue?: (option: T) => string; // Get unique value from option

  // State
  isLoading?: boolean; // Show loading state
  error?: string | null; // Error message to display
}
```

**Example - String Filter:**

```typescript
<GenericFilter<string>
  values={[selectedYear]}
  onChange={(values) => setSelectedYear(values[0])}
  availableOptions={['2023', '2024', '2025']}
  label="Year"
  placeholder="Select year"
/>
```

**Example - Object Filter:**

```typescript
interface Listing {
  id: string;
  name: string;
  address: string;
}

<GenericFilter<Listing>
  values={selectedListings}
  onChange={setSelectedListings}
  availableOptions={listings}
  multiSelect
  label="Listings"
  getOptionLabel={(listing) => listing.name}
  getOptionValue={(listing) => listing.id}
  renderOption={(listing) => (
    <Box>
      <Text fontWeight="bold">{listing.name}</Text>
      <Text fontSize="sm">{listing.address}</Text>
    </Box>
  )}
/>
```

---

### YearFilter

A specialized wrapper around `GenericFilter<string>` for year selection. Provides year-specific defaults and optional dynamic year generation.

**Features:**

- Default label "Year"
- Default placeholders based on mode
- Optional year generation (historical, future, combined, rolling)
- Works in both single and multi-select modes

**Props:**

```typescript
interface YearFilterProps extends Omit<
  GenericFilterProps<string>,
  "label" | "placeholder" | "getOptionLabel" | "getOptionValue"
> {
  label?: string; // Custom label (default: "Year")
  placeholder?: string; // Custom placeholder
  yearConfig?: YearGenerationConfig; // Optional year generation config
}
```

**Example - Single-Select (BTW Report):**

```typescript
<YearFilter
  values={selectedYear ? [selectedYear] : []}
  onChange={(values) => setSelectedYear(values[0] || '')}
  availableOptions={['2022', '2023', '2024', '2025']}
/>
```

**Example - Multi-Select (Actuals Report):**

```typescript
<YearFilter
  values={selectedYears}
  onChange={setSelectedYears}
  availableOptions={['2022', '2023', '2024', '2025']}
  multiSelect
/>
```

**Example - Dynamic Year Generation:**

```typescript
<YearFilter
  values={selectedYears}
  onChange={setSelectedYears}
  availableOptions={[]}
  multiSelect
  yearConfig={{
    mode: 'combined',
    historicalYears: historicalYears,  // From database
    futureCount: 2                      // Current + next 2 years
  }}
/>
```

---

### FilterPanel

A container component for organizing multiple filters with flexible layout options.

**Features:**

- Three layout modes: horizontal, vertical, grid
- Responsive design (mobile breakpoints)
- Supports mixing filter types
- Consistent spacing and alignment
- Default color scheme optimized for dark backgrounds

**Default Colors:**

- Label text: `white` (for dark gray backgrounds)
- Filter background: `gray.600` (dark gray)
- Filter text: `white`
- Selected values: `orange.500` background with `white` text

**Props:**

```typescript
interface FilterPanelProps {
  filters: FilterConfig<any>[]; // Array of filter configurations
  layout?: "horizontal" | "vertical" | "grid"; // Layout mode (default: 'horizontal')
  size?: "sm" | "md" | "lg"; // Size variant for all filters (default: 'md')
  spacing?: number; // Spacing between filters (default: 4)
  disabled?: boolean; // Disable all filters
  gridColumns?: number; // Number of columns for grid layout (default: 2)
  gridMinWidth?: string; // Minimum width for grid items (default: '200px')
  labelColor?: string; // Label text color (default: 'white')
  bg?: string; // Filter background color (default: 'gray.600')
  color?: string; // Filter text color (default: 'white')
}
```

**Example - Horizontal Layout:**

```typescript
<FilterPanel
  layout="horizontal"
  filters={[
    {
      type: 'single',
      label: 'Year',
      options: ['2023', '2024', '2025'],
      value: selectedYear,
      onChange: setSelectedYear
    },
    {
      type: 'single',
      label: 'Quarter',
      options: ['Q1', 'Q2', 'Q3', 'Q4'],
      value: selectedQuarter,
      onChange: setSelectedQuarter
    }
  ]}
/>
```

**Example - Grid Layout:**

```typescript
<FilterPanel
  layout="grid"
  gridColumns={3}
  filters={[
    {
      type: 'multi',
      label: 'Years',
      options: ['2022', '2023', '2024', '2025'],
      value: selectedYears,
      onChange: setSelectedYears
    },
    {
      type: 'multi',
      label: 'Listings',
      options: listings,
      value: selectedListings,
      onChange: setSelectedListings,
      getOptionLabel: (listing) => listing.name
    },
    {
      type: 'multi',
      label: 'Channels',
      options: ['airbnb', 'booking', 'direct'],
      value: selectedChannels,
      onChange: setSelectedChannels
    }
  ]}
/>
```

---

## Usage Examples

### Single Year Selection (BTW Report)

BTW reports require selecting a single year and quarter.

```typescript
import { FilterPanel } from '../components/filters/FilterPanel';

function BtwReport() {
  const [selectedYear, setSelectedYear] = useState<string>('2024');
  const [selectedQuarter, setSelectedQuarter] = useState<string>('Q1');

  return (
    <Card>
      <CardBody>
        <FilterPanel
          layout="horizontal"
          filters={[
            {
              type: 'single',
              label: 'Year',
              options: ['2022', '2023', '2024', '2025'],
              value: selectedYear,
              onChange: setSelectedYear
            },
            {
              type: 'single',
              label: 'Quarter',
              options: ['Q1', 'Q2', 'Q3', 'Q4'],
              value: selectedQuarter,
              onChange: setSelectedQuarter
            }
          ]}
        />

        <Button onClick={() => generateReport(selectedYear, selectedQuarter)}>
          Generate BTW Report
        </Button>
      </CardBody>
    </Card>
  );
}
```

---

### Multi-Year Selection (Actuals Report)

Actuals reports allow comparing multiple years.

```typescript
import { YearFilter } from '../components/filters/YearFilter';

function ActualsReport() {
  const [selectedYears, setSelectedYears] = useState<string[]>(['2023', '2024']);
  const [availableYears, setAvailableYears] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // Load available years from database
    setIsLoading(true);
    fetchAvailableYears()
      .then(years => setAvailableYears(years))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <Card>
      <CardBody>
        <YearFilter
          values={selectedYears}
          onChange={setSelectedYears}
          availableOptions={availableYears}
          multiSelect
          isLoading={isLoading}
        />

        <Button onClick={() => generateReport(selectedYears)}>
          Generate Actuals Report
        </Button>
      </CardBody>
    </Card>
  );
}
```

---

### Combined Filters (BNB Report)

BNB reports use multiple filters: years, listings, and channels.

```typescript
import { FilterPanel } from '../components/filters/FilterPanel';

function BnbActualsReport() {
  const [selectedYears, setSelectedYears] = useState<string[]>(['2024']);
  const [selectedListings, setSelectedListings] = useState<string[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>(['airbnb', 'booking']);

  const listings = [
    { id: '1', name: 'Beach House', address: '123 Ocean Dr' },
    { id: '2', name: 'Mountain Cabin', address: '456 Peak Rd' }
  ];

  return (
    <Card>
      <CardBody>
        <FilterPanel
          layout="grid"
          gridColumns={3}
          filters={[
            {
              type: 'multi',
              label: 'Years',
              options: ['2022', '2023', '2024', '2025'],
              value: selectedYears,
              onChange: setSelectedYears
            },
            {
              type: 'multi',
              label: 'Listings',
              options: listings,
              value: selectedListings,
              onChange: setSelectedListings,
              getOptionLabel: (listing) => listing.name,
              getOptionValue: (listing) => listing.id,
              renderOption: (listing) => (
                <Box>
                  <Text fontWeight="bold">{listing.name}</Text>
                  <Text fontSize="sm" color="gray.600">{listing.address}</Text>
                </Box>
              )
            },
            {
              type: 'multi',
              label: 'Channels',
              options: ['airbnb', 'booking', 'direct'],
              value: selectedChannels,
              onChange: setSelectedChannels
            }
          ]}
        />

        <Button onClick={() => generateReport(selectedYears, selectedListings, selectedChannels)}>
          Generate BNB Report
        </Button>
      </CardBody>
    </Card>
  );
}
```

---

### Dynamic Year Loading Strategies

The filter system supports four year generation modes:

#### 1. Historical Years Only

Load years from database (existing data only).

```typescript
<YearFilter
  values={selectedYears}
  onChange={setSelectedYears}
  availableOptions={[]}
  multiSelect
  yearConfig={{
    mode: 'historical',
    historicalYears: ['2020', '2021', '2022', '2023', '2024']
  }}
/>
```

#### 2. Future Years Only

Generate current year + N future years (for planning).

```typescript
<YearFilter
  values={selectedYears}
  onChange={setSelectedYears}
  availableOptions={[]}
  multiSelect
  yearConfig={{
    mode: 'future',
    futureCount: 3  // Current + next 3 years
  }}
/>
// Generates: [2026, 2027, 2028, 2029] (if current year is 2026)
```

#### 3. Combined (Historical + Future)

Mix historical data with future planning years.

```typescript
<YearFilter
  values={selectedYears}
  onChange={setSelectedYears}
  availableOptions={[]}
  multiSelect
  yearConfig={{
    mode: 'combined',
    historicalYears: historicalYears,  // From database
    futureCount: 2                      // + next 2 years
  }}
/>
// Example: ['2022', '2023', '2024', '2026', '2027', '2028']
```

#### 4. Rolling Window

Last N years + current + next M years.

```typescript
<YearFilter
  values={selectedYears}
  onChange={setSelectedYears}
  availableOptions={[]}
  multiSelect
  yearConfig={{
    mode: 'rolling',
    pastCount: 3,    // Last 3 years
    futureCount: 2   // + current + next 2 years
  }}
/>
// Example (2026): ['2023', '2024', '2025', '2026', '2027', '2028']
```

---

## Migration Guide

### From UnifiedAdminYearFilter to FilterPanel

The new filter system replaces `UnifiedAdminYearFilter` with a more flexible architecture.

#### Before (UnifiedAdminYearFilter)

```typescript
import { UnifiedAdminYearFilter } from '../components/UnifiedAdminYearFilter';
import { createActualsFilterAdapter } from '../components/UnifiedAdminYearFilterAdapters';

function ActualsReport() {
  const [filters, setFilters] = useState({
    administration: 'all',
    years: ['2023', '2024']
  });

  return (
    <UnifiedAdminYearFilter
      {...createActualsFilterAdapter(filters, setFilters, availableYears)}
      showAdministration={true}
      multiSelectYears={true}
    />
  );
}
```

#### After (FilterPanel)

```typescript
import { YearFilter } from '../components/filters/YearFilter';

function ActualsReport() {
  const [selectedYears, setSelectedYears] = useState<string[]>(['2023', '2024']);
  // Note: Administration filter removed - uses tenant context instead

  return (
    <YearFilter
      values={selectedYears}
      onChange={setSelectedYears}
      availableOptions={availableYears}
      multiSelect
    />
  );
}
```

### Key Changes

1. **No Administration Filter**: The new system uses tenant context instead of administration filtering. Users work within a selected tenant, eliminating the need for administration selection in 75% of reports.

2. **Simpler State Management**: Direct state management instead of adapter pattern.

3. **Type Safety**: Full TypeScript support with generics.

4. **Flexible Layouts**: Use `FilterPanel` for multiple filters with different layout options.

### Migration Checklist

- [ ] Replace `UnifiedAdminYearFilter` import with `YearFilter` or `FilterPanel`
- [ ] Remove administration filter state (uses tenant context)
- [ ] Update state management (remove adapter pattern)
- [ ] Change `multiSelectYears` prop to `multiSelect`
- [ ] Update onChange handler to work with arrays
- [ ] Remove `showAdministration` and `showYears` props
- [ ] Test filter functionality
- [ ] Update tests to use new filter components

---

## Troubleshooting

### Issue: Filter not updating when options change

**Problem:** Filter displays old options even after `availableOptions` prop changes.

**Solution:** Ensure `availableOptions` is properly memoized or comes from state:

```typescript
// ❌ Bad: Creates new array on every render
<YearFilter
  availableOptions={['2023', '2024', '2025']}
  // ...
/>

// ✅ Good: Use state or useMemo
const availableYears = useMemo(() => ['2023', '2024', '2025'], []);
<YearFilter
  availableOptions={availableYears}
  // ...
/>
```

---

### Issue: onChange not called in single-select mode

**Problem:** `onChange` callback not triggered when selecting an option.

**Solution:** Ensure you're handling the array format correctly:

```typescript
// ❌ Bad: Expecting single value
<YearFilter
  values={[selectedYear]}
  onChange={(value) => setSelectedYear(value)}  // Wrong: value is an array
  // ...
/>

// ✅ Good: Extract first element from array
<YearFilter
  values={selectedYear ? [selectedYear] : []}
  onChange={(values) => setSelectedYear(values[0] || '')}
  // ...
/>
```

---

### Issue: Multi-select filter shows "0 selected" instead of placeholder

**Problem:** Filter displays "0 selected" when no items are selected.

**Solution:** Pass an empty array, not undefined or null:

```typescript
// ❌ Bad: Undefined or null values
<YearFilter
  values={selectedYears || null}
  // ...
/>

// ✅ Good: Empty array
<YearFilter
  values={selectedYears || []}
  // ...
/>
```

---

### Issue: Custom renderOption not working

**Problem:** Custom option rendering not applied.

**Solution:** Ensure you're also providing `getOptionLabel` and `getOptionValue`:

```typescript
// ❌ Bad: Only renderOption
<GenericFilter
  renderOption={(item) => <Text>{item.name}</Text>}
  // ...
/>

// ✅ Good: All three functions
<GenericFilter
  renderOption={(item) => <Text>{item.name}</Text>}
  getOptionLabel={(item) => item.name}
  getOptionValue={(item) => item.id}
  // ...
/>
```

---

### Issue: FilterPanel filters not aligned properly

**Problem:** Filters in horizontal layout have inconsistent heights.

**Solution:** Use `align="end"` (default) or ensure all filters have labels:

```typescript
// ✅ Good: All filters have labels
<FilterPanel
  layout="horizontal"
  filters={[
    { type: 'single', label: 'Year', /* ... */ },
    { type: 'single', label: 'Quarter', /* ... */ }
  ]}
/>
```

---

### Issue: Year generation not working

**Problem:** `yearConfig` prop not generating years.

**Solution:** Ensure `availableOptions` is empty when using `yearConfig`:

```typescript
// ❌ Bad: Both availableOptions and yearConfig provided
<YearFilter
  availableOptions={['2023', '2024']}
  yearConfig={{ mode: 'future', futureCount: 3 }}
  // ...
/>

// ✅ Good: Empty availableOptions when using yearConfig
<YearFilter
  availableOptions={[]}
  yearConfig={{ mode: 'future', futureCount: 3 }}
  // ...
/>
```

---

### Issue: TypeScript errors with FilterConfig

**Problem:** TypeScript complains about filter configuration types.

**Solution:** Use the specific filter config types:

```typescript
import { SingleSelectFilterConfig, MultiSelectFilterConfig } from "./types";

// ✅ Good: Type-safe filter configs
const yearFilter: MultiSelectFilterConfig<string> = {
  type: "multi",
  label: "Years",
  options: ["2023", "2024", "2025"],
  value: selectedYears,
  onChange: setSelectedYears,
};
```

---

## Type Definitions

### FilterConfig<T>

Base filter configuration interface.

```typescript
interface FilterConfig<T> {
  type: FilterType; // 'single' | 'multi' | 'range' | 'search'
  label: string;
  options: T[];
  value: T | T[];
  onChange: (value: T | T[]) => void;
  renderOption?: (option: T) => React.ReactNode;
  getOptionLabel?: (option: T) => string;
  getOptionValue?: (option: T) => string;
  placeholder?: string;
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  isLoading?: boolean;
  error?: string | null;
}
```

### SingleSelectFilterConfig<T>

Type-safe single-select filter configuration.

```typescript
interface SingleSelectFilterConfig<T> extends Omit<
  FilterConfig<T>,
  "type" | "value" | "onChange"
> {
  type: "single";
  value: T;
  onChange: (value: T) => void;
}
```

### MultiSelectFilterConfig<T>

Type-safe multi-select filter configuration.

```typescript
interface MultiSelectFilterConfig<T> extends Omit<
  FilterConfig<T>,
  "type" | "value" | "onChange"
> {
  type: "multi";
  value: T[];
  onChange: (values: T[]) => void;
}
```

### YearGenerationConfig

Configuration for dynamic year generation.

```typescript
interface YearGenerationConfig {
  mode: "historical" | "future" | "combined" | "rolling";
  historicalYears?: string[]; // For 'historical' and 'combined' modes
  futureCount?: number; // For 'future', 'combined', and 'rolling' modes
  pastCount?: number; // For 'rolling' mode
}
```

---

## Best Practices

### 1. Use Specific Filter Types

Prefer specialized filters over generic ones when available:

```typescript
// ✅ Good: Use YearFilter for years
<YearFilter values={years} onChange={setYears} availableOptions={yearOptions} />

// ❌ Avoid: Using GenericFilter for years
<GenericFilter<string> label="Year" values={years} onChange={setYears} availableOptions={yearOptions} />
```

### 2. Memoize Filter Configurations

Prevent unnecessary re-renders by memoizing filter configs:

```typescript
const filters = useMemo(() => [
  {
    type: 'multi',
    label: 'Years',
    options: availableYears,
    value: selectedYears,
    onChange: setSelectedYears
  }
], [availableYears, selectedYears]);

<FilterPanel filters={filters} />
```

### 3. Handle Loading States

Show loading indicators while fetching filter options:

```typescript
<YearFilter
  values={selectedYears}
  onChange={setSelectedYears}
  availableOptions={years}
  isLoading={isLoadingYears}
  multiSelect
/>
```

### 4. Provide Error Feedback

Display errors when filter options fail to load:

```typescript
<YearFilter
  values={selectedYears}
  onChange={setSelectedYears}
  availableOptions={years}
  error={error ? 'Failed to load years' : null}
  multiSelect
/>
```

### 5. Use Appropriate Layouts

Choose layouts based on number of filters and screen size:

- **Horizontal**: 2-3 filters, desktop-focused
- **Vertical**: Mobile-first, any number of filters
- **Grid**: 4+ filters, responsive design

---

## Testing

The filter system includes comprehensive test coverage:

- **GenericFilter**: 40 unit tests + 7 property-based tests
- **YearFilter**: 30+ unit tests covering all modes
- **FilterPanel**: 43 unit tests covering all layouts

### Running Tests

```bash
# Run all filter tests
npm test -- --testPathPattern=filters

# Run specific component tests
npm test -- GenericFilter.test.tsx
npm test -- YearFilter.test.tsx
npm test -- FilterPanel.test.tsx

# Run with coverage
npm test -- --coverage --testPathPattern=filters
```

---

## Performance Considerations

### Memoization

Use `useMemo` for expensive computations:

```typescript
const filteredData = useMemo(() => {
  return data.filter((item) => selectedYears.includes(item.year));
}, [data, selectedYears]);
```

### Debouncing

For search filters, debounce onChange callbacks:

```typescript
const debouncedSearch = useMemo(
  () => debounce((value: string) => setSearchTerm(value), 300),
  [],
);
```

### Lazy Loading

Load filter options only when needed:

```typescript
useEffect(() => {
  if (isFilterOpen) {
    fetchFilterOptions();
  }
}, [isFilterOpen]);
```

---

## Accessibility

All filter components follow WCAG 2.1 AA guidelines:

- ✅ Keyboard navigation (Tab, Enter, Space, Arrow keys)
- ✅ ARIA labels and roles
- ✅ Screen reader support
- ✅ Focus management
- ✅ Color contrast compliance

---

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

---

## Related Documentation

- [GenericFilter API](./GenericFilter.tsx) - Component source with JSDoc
- [YearFilter API](./YearFilter.tsx) - Component source with JSDoc
- [FilterPanel API](./FilterPanel.tsx) - Component source with JSDoc
- [Type Definitions](./types.ts) - Complete TypeScript types
- [Year Generator](./utils/yearGenerator.ts) - Year generation utilities

---

## Support

For issues or questions:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review the [Usage Examples](#usage-examples)
3. Consult the inline JSDoc documentation in component files
4. Check existing tests for usage patterns

---

**Last Updated:** 2026-02-07  
**Version:** 1.0.0  
**Status:** Production Ready
