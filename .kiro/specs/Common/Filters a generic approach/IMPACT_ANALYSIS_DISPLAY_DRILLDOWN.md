# Impact Analysis: Display Format & Drill Down Level Filters

**Date:** 2026-02-07  
**Component:** ActualsReport  
**Scope:** Integrate Display Format and Drill Down Level into generic filter framework

---

## Executive Summary

This analysis evaluates the feasibility and impact of migrating two additional ActualsReport controls into the generic filter framework:

1. **Display Format** (dropdown: 2dec, 0dec, k, m)
2. **Drill Down Level** (button group: year, quarter, month)

**Recommendation:** ✅ **Proceed with migration** - Both controls fit well into the generic filter framework with moderate effort and significant benefits.

---

## Current Implementation Analysis

### A) Display Format Control

**Current State:**

```typescript
// State
const [displayFormat, setDisplayFormat] = useState<string>('2dec');

// UI (Chakra Select)
<Select
  value={displayFormat}
  onChange={(e) => setDisplayFormat(e.target.value)}
  bg="gray.600"
  color="white"
  size="sm"
>
  <option value="2dec">€1,234.56 (2 decimals)</option>
  <option value="0dec">€1,235 (whole numbers)</option>
  <option value="k">€1.2K (thousands)</option>
  <option value="m">€1.2M (millions)</option>
</Select>
```

**Characteristics:**

- **Type:** Single-select dropdown
- **Options:** 4 fixed options (2dec, 0dec, k, m)
- **Behavior:** Immediate effect on display (no API call)
- **Scope:** Report-specific (formatting logic)
- **State:** Simple string value

**Usage:**

- Used in `formatAmount()` function throughout the report
- Affects all monetary displays (tables, charts, tooltips)
- No side effects beyond visual formatting

---

### B) Drill Down Level Control

**Current State:**

```typescript
// State
const [drillDownLevel, setDrillDownLevel] = useState<'year' | 'quarter' | 'month'>('year');

// UI (Button Group)
<HStack>
  <Button
    colorScheme={drillDownLevel === 'year' ? 'orange' : 'gray'}
    onClick={() => {
      setDrillDownLevel('year');
      setExpandedParents(new Set());
    }}
  >
    📅 Year
  </Button>
  <Button colorScheme={drillDownLevel === 'quarter' ? 'orange' : 'gray'} ...>
    📊 Quarter
  </Button>
  <Button colorScheme={drillDownLevel === 'month' ? 'orange' : 'gray'} ...>
    📈 Month
  </Button>
</HStack>
```

**Characteristics:**

- **Type:** Single-select button group (radio-like behavior)
- **Options:** 3 fixed options (year, quarter, month)
- **Behavior:** Triggers API call to fetch data at different granularity
- **Scope:** Report-specific (affects data structure)
- **State:** Union type ('year' | 'quarter' | 'month')
- **Side Effects:**
  - Clears expanded parents
  - Triggers `fetchActualsData()` via useEffect
  - Changes table column structure

**Usage:**

- Used in `getColumnKeys()` to determine table columns
- Passed to API as `groupBy` parameter
- Affects data aggregation level

---

## Proposed Migration to Generic Filter Framework

### Option 1: Use GenericFilter (Recommended)

Both controls can use `GenericFilter<string>` with single-select mode.

#### A) Display Format as GenericFilter

```typescript
// Type definition
interface DisplayFormatOption {
  value: string;
  label: string;
  description: string;
}

const displayFormatOptions: DisplayFormatOption[] = [
  { value: '2dec', label: '€1,234.56', description: '2 decimals' },
  { value: '0dec', label: '€1,235', description: 'whole numbers' },
  { value: 'k', label: '€1.2K', description: 'thousands' },
  { value: 'm', label: '€1.2M', description: 'millions' }
];

// Usage with GenericFilter
<GenericFilter<DisplayFormatOption>
  values={displayFormatOptions.filter(opt => opt.value === displayFormat)}
  onChange={(values) => setDisplayFormat(values[0]?.value || '2dec')}
  availableOptions={displayFormatOptions}
  label="Display Format"
  size="sm"
  getOptionLabel={(opt) => `${opt.label} (${opt.description})`}
  getOptionValue={(opt) => opt.value}
/>
```

**Benefits:**

- Consistent UI with other filters
- Type-safe option handling
- Reusable across reports
- Easy to extend with new formats

**Drawbacks:**

- Slightly more complex than raw Select
- Requires option object structure

---

#### B) Drill Down Level as GenericFilter

```typescript
// Type definition
interface DrillDownOption {
  value: 'year' | 'quarter' | 'month';
  label: string;
  icon: string;
  description: string;
}

const drillDownOptions: DrillDownOption[] = [
  { value: 'year', label: 'Year', icon: '📅', description: 'Yearly Summary' },
  { value: 'quarter', label: 'Quarter', icon: '📊', description: 'Quarterly Breakdown' },
  { value: 'month', label: 'Month', icon: '📈', description: 'Monthly Detail' }
];

// Usage with GenericFilter
<GenericFilter<DrillDownOption>
  values={drillDownOptions.filter(opt => opt.value === drillDownLevel)}
  onChange={(values) => {
    const newLevel = values[0]?.value || 'year';
    setDrillDownLevel(newLevel);
    setExpandedParents(new Set());
  }}
  availableOptions={drillDownOptions}
  label="Drill Down Level"
  size="sm"
  getOptionLabel={(opt) => `${opt.icon} ${opt.label}`}
  getOptionValue={(opt) => opt.value}
  renderOption={(opt) => (
    <Box>
      <Text fontWeight="bold">{opt.icon} {opt.label}</Text>
      <Text fontSize="xs" color="gray.500">{opt.description}</Text>
    </Box>
  )}
/>
```

**Benefits:**

- Consistent with filter system
- Type-safe
- Custom rendering for icons and descriptions
- Dropdown is more compact than button group

**Drawbacks:**

- Loses visual "button group" appearance
- Less immediately obvious which option is selected
- Requires click to see options (vs. all visible buttons)

---

### Option 2: Create Specialized Filter Components

Create dedicated filter components that wrap GenericFilter with specific behavior.

#### A) DisplayFormatFilter

```typescript
// frontend/src/components/filters/DisplayFormatFilter.tsx
export interface DisplayFormatFilterProps {
  value: string;
  onChange: (value: string) => void;
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
}

export function DisplayFormatFilter({
  value,
  onChange,
  size = 'md',
  disabled = false
}: DisplayFormatFilterProps) {
  const options = [
    { value: '2dec', label: '€1,234.56 (2 decimals)' },
    { value: '0dec', label: '€1,235 (whole numbers)' },
    { value: 'k', label: '€1.2K (thousands)' },
    { value: 'm', label: '€1.2M (millions)' }
  ];

  return (
    <GenericFilter<typeof options[0]>
      values={options.filter(opt => opt.value === value)}
      onChange={(values) => onChange(values[0]?.value || '2dec')}
      availableOptions={options}
      label="Display Format"
      size={size}
      disabled={disabled}
      getOptionLabel={(opt) => opt.label}
      getOptionValue={(opt) => opt.value}
    />
  );
}
```

**Benefits:**

- Encapsulates format options
- Simple API for consumers
- Reusable across reports
- Easy to maintain

---

#### B) DrillDownLevelFilter

```typescript
// frontend/src/components/filters/DrillDownLevelFilter.tsx
export type DrillDownLevel = 'year' | 'quarter' | 'month';

export interface DrillDownLevelFilterProps {
  value: DrillDownLevel;
  onChange: (value: DrillDownLevel) => void;
  onLevelChange?: (value: DrillDownLevel) => void; // Optional callback for side effects
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  isLoading?: boolean;
}

export function DrillDownLevelFilter({
  value,
  onChange,
  onLevelChange,
  size = 'md',
  disabled = false,
  isLoading = false
}: DrillDownLevelFilterProps) {
  const options = [
    { value: 'year' as DrillDownLevel, label: '📅 Year', description: 'Shows annual totals' },
    { value: 'quarter' as DrillDownLevel, label: '📊 Quarter', description: 'Shows quarterly data' },
    { value: 'month' as DrillDownLevel, label: '📈 Month', description: 'Shows monthly granularity' }
  ];

  const handleChange = (values: typeof options) => {
    const newValue = values[0]?.value || 'year';
    onChange(newValue);
    onLevelChange?.(newValue);
  };

  return (
    <GenericFilter<typeof options[0]>
      values={options.filter(opt => opt.value === value)}
      onChange={handleChange}
      availableOptions={options}
      label="Drill Down Level"
      size={size}
      disabled={disabled}
      isLoading={isLoading}
      getOptionLabel={(opt) => opt.label}
      getOptionValue={(opt) => opt.value}
      renderOption={(opt) => (
        <Box>
          <Text fontWeight="bold">{opt.label}</Text>
          <Text fontSize="xs" color="gray.500">{opt.description}</Text>
        </Box>
      )}
    />
  );
}
```

**Benefits:**

- Type-safe with DrillDownLevel union type
- Encapsulates drill-down logic
- Optional callback for side effects (clearing expanded parents)
- Reusable across reports with drill-down functionality

---

### Option 3: Use FilterPanel with All Filters

Combine all three filters (Year, Display Format, Drill Down) into a single FilterPanel.

```typescript
<FilterPanel
  layout="horizontal"
  size="sm"
  filters={[
    {
      type: 'multi',
      label: 'Years',
      options: availableYears,
      value: selectedYears,
      onChange: setSelectedYears
    },
    {
      type: 'single',
      label: 'Display Format',
      options: [
        { value: '2dec', label: '€1,234.56 (2 decimals)' },
        { value: '0dec', label: '€1,235 (whole numbers)' },
        { value: 'k', label: '€1.2K (thousands)' },
        { value: 'm', label: '€1.2M (millions)' }
      ],
      value: { value: displayFormat, label: '' },
      onChange: (val) => setDisplayFormat(val.value),
      getOptionLabel: (opt) => opt.label,
      getOptionValue: (opt) => opt.value
    },
    {
      type: 'single',
      label: 'Drill Down Level',
      options: [
        { value: 'year', label: '📅 Year' },
        { value: 'quarter', label: '📊 Quarter' },
        { value: 'month', label: '📈 Month' }
      ],
      value: { value: drillDownLevel, label: '' },
      onChange: (val) => {
        setDrillDownLevel(val.value);
        setExpandedParents(new Set());
      },
      getOptionLabel: (opt) => opt.label,
      getOptionValue: (opt) => opt.value
    }
  ]}
/>
```

**Benefits:**

- All filters in one place
- Consistent layout and spacing
- Responsive design built-in
- Unified filter management

**Drawbacks:**

- More complex configuration
- Less flexibility for individual filter positioning
- Harder to add non-filter elements (like Update button)

---

## Impact Assessment

### Code Changes Required

#### Minimal Changes (Option 1: Direct GenericFilter)

- **Files Modified:** 1 (ActualsReport.tsx)
- **Lines Changed:** ~50 lines
- **New Files:** 0
- **Effort:** 1-2 hours

#### Moderate Changes (Option 2: Specialized Filters)

- **Files Modified:** 1 (ActualsReport.tsx)
- **New Files:** 2 (DisplayFormatFilter.tsx, DrillDownLevelFilter.tsx)
- **Lines Added:** ~150 lines (new components)
- **Lines Changed:** ~30 lines (ActualsReport)
- **Effort:** 3-4 hours

#### Significant Changes (Option 3: FilterPanel)

- **Files Modified:** 1 (ActualsReport.tsx)
- **Lines Changed:** ~80 lines
- **Effort:** 2-3 hours
- **Risk:** Higher (more complex refactoring)

---

### Benefits

#### Consistency

- ✅ All filters use same UI pattern
- ✅ Consistent styling across reports
- ✅ Unified user experience

#### Maintainability

- ✅ Centralized filter logic
- ✅ Easier to update filter behavior
- ✅ Reusable components

#### Type Safety

- ✅ TypeScript generics ensure type safety
- ✅ Compile-time error checking
- ✅ Better IDE autocomplete

#### Extensibility

- ✅ Easy to add new display formats
- ✅ Easy to add new drill-down levels
- ✅ Can reuse in other reports

#### Testing

- ✅ Leverage existing GenericFilter tests
- ✅ Specialized filters get dedicated tests
- ✅ Consistent test patterns

---

### Drawbacks

#### User Experience

- ⚠️ Drill Down Level loses "button group" visual
- ⚠️ Requires click to see options (vs. all visible)
- ⚠️ May be less intuitive for drill-down selection

#### Development Effort

- ⚠️ Requires refactoring existing code
- ⚠️ Need to update tests
- ⚠️ Documentation updates needed

#### Complexity

- ⚠️ More abstraction layers
- ⚠️ Slightly more complex configuration
- ⚠️ Learning curve for new developers

---

## Compatibility Analysis

### Display Format

- ✅ **Fully Compatible** - Simple dropdown, no special behavior
- ✅ No API dependencies
- ✅ No side effects
- ✅ Works with GenericFilter single-select mode

### Drill Down Level

- ⚠️ **Mostly Compatible** - Requires side effect handling
- ⚠️ Triggers API call (via useEffect)
- ⚠️ Clears expanded parents state
- ⚠️ Changes table structure
- ✅ Can use GenericFilter with onChange callback

---

## Recommendation

### Recommended Approach: **Option 2 (Specialized Filters)**

**Rationale:**

1. **Best Balance:** Combines reusability with simplicity
2. **Type Safety:** Dedicated components with proper types
3. **Encapsulation:** Hides complexity from consumers
4. **Reusability:** Can be used in other reports
5. **Maintainability:** Easy to update and test
6. **Flexibility:** Can customize behavior per filter

### Implementation Plan

#### Phase 1: Create Specialized Filters (2-3 hours)

1. Create `DisplayFormatFilter.tsx`
2. Create `DrillDownLevelFilter.tsx`
3. Add unit tests for both components
4. Update types.ts with new filter types

#### Phase 2: Migrate ActualsReport (1-2 hours)

1. Replace Display Format Select with DisplayFormatFilter
2. Replace Drill Down Level buttons with DrillDownLevelFilter
3. Update state management
4. Test functionality

#### Phase 3: Documentation (1 hour)

1. Update README.md with new filter examples
2. Add JSDoc documentation
3. Update migration guide

**Total Effort:** 4-6 hours

---

## Alternative: Keep Current Implementation

### When to Keep Current Implementation

Consider keeping the current implementation if:

- ❌ These controls are truly unique to ActualsReport
- ❌ No other reports need similar functionality
- ❌ The button group UI is critical for UX
- ❌ Development time is extremely limited

### Hybrid Approach

Keep Drill Down Level as button group, migrate only Display Format:

- ✅ Maintains visual button group for drill-down
- ✅ Gets consistency benefits for display format
- ✅ Lower risk, less effort
- ⚠️ Inconsistent filter patterns

---

## Risk Assessment

### Low Risk

- ✅ Display Format migration (simple dropdown)
- ✅ No breaking changes to API
- ✅ No data structure changes

### Medium Risk

- ⚠️ Drill Down Level migration (side effects)
- ⚠️ UX change from buttons to dropdown
- ⚠️ Need to handle expanded parents clearing

### Mitigation Strategies

1. **Thorough Testing:** Test all drill-down scenarios
2. **User Feedback:** Get feedback on dropdown vs. buttons
3. **Gradual Rollout:** Migrate Display Format first
4. **Rollback Plan:** Keep old code commented for quick revert

---

## Success Criteria

### Must Have

- ✅ All existing functionality preserved
- ✅ No regressions in data display
- ✅ TypeScript compilation passes
- ✅ All tests pass
- ✅ No performance degradation

### Should Have

- ✅ Improved code maintainability
- ✅ Consistent UI patterns
- ✅ Reusable components
- ✅ Better type safety

### Nice to Have

- ✅ Improved UX (debatable for drill-down)
- ✅ Reduced code duplication
- ✅ Better documentation

---

## Conclusion

**Recommendation:** ✅ **Proceed with Option 2 (Specialized Filters)**

Both Display Format and Drill Down Level can be successfully migrated to the generic filter framework with moderate effort and significant long-term benefits. The specialized filter approach provides the best balance of reusability, maintainability, and type safety while keeping the implementation simple for consumers.

**Next Steps:**

1. Get stakeholder approval for UX change (buttons → dropdown for drill-down)
2. Create DisplayFormatFilter and DrillDownLevelFilter components
3. Migrate ActualsReport to use new filters
4. Update documentation and tests
5. Consider applying to other reports with similar needs

**Estimated Timeline:** 1 day (4-6 hours development + testing)

---

**Document Version:** 1.0  
**Last Updated:** 2026-02-07  
**Author:** Kiro AI Assistant  
**Status:** Ready for Review
