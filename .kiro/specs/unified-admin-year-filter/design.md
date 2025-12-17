# Design Document

## Overview

The unified Administration and Year filter component will consolidate the separate filter controls currently used throughout myAdmin Reports into a single, cohesive interface. This design maintains all existing functionality while improving user experience through a more streamlined interface.

The component will be built as a reusable React component that can adapt to different filter state structures and requirements across various tabs in the myAdmin Reports interface.

## Architecture

### Component Structure

```
UnifiedAdminYearFilter
├── AdministrationSection
│   ├── Label
│   └── Select (Chakra UI)
└── YearSection
    ├── Label
    └── MultiSelectMenu (Chakra UI Menu + Checkboxes)
```

### Integration Points

The component will integrate with existing myAdmin Reports tabs:

- Actuals Dashboard (actualsFilters)
- BNB Actuals (bnbActualsFilters - years only)
- BTW Declaration (btwFilters)
- Reference Analysis (refAnalysisFilters)
- BNB Violins (bnbViolinFilters - years only)
- Aangifte IB (aangifteIbFilters)

### State Management

The component will use a callback pattern to communicate filter changes back to parent components, maintaining the existing state management patterns in myAdmin Reports.

## Components and Interfaces

### UnifiedAdminYearFilter Component

```typescript
interface UnifiedAdminYearFilterProps {
  // Administration filter props
  administrationValue: string;
  onAdministrationChange: (value: string) => void;
  administrationOptions: Array<{ value: string; label: string }>;
  showAdministration?: boolean;

  // Year filter props
  yearValues: string[];
  onYearChange: (values: string[]) => void;
  availableYears: string[];
  showYears?: boolean;
  multiSelectYears?: boolean; // false for single select like BTW

  // Styling and layout
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  disabled?: boolean;
}
```

### Filter State Adapters

To maintain compatibility with existing filter structures, adapter functions will map between the unified component interface and specific filter state objects:

```typescript
// Adapter for actualsFilters
const createActualsFilterAdapter = (
  filters: ActualsFilters,
  setFilters: (filters: ActualsFilters) => void,
  availableYears: string[]
) => ({
  administrationValue: filters.administration,
  onAdministrationChange: (value: string) =>
    setFilters((prev) => ({ ...prev, administration: value })),
  administrationOptions: [
    { value: "all", label: "All" },
    { value: "GoodwinSolutions", label: "GoodwinSolutions" },
    { value: "PeterPrive", label: "PeterPrive" },
  ],
  yearValues: filters.years,
  onYearChange: (values: string[]) =>
    setFilters((prev) => ({ ...prev, years: values })),
  availableYears,
  multiSelectYears: true,
});
```

## Data Models

### Filter Configuration

```typescript
interface FilterConfig {
  administrations: AdministrationOption[];
  years: YearOption[];
  defaults: {
    administration: string;
    years: string[];
  };
}

interface AdministrationOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface YearOption {
  value: string;
  label: string;
  disabled?: boolean;
}
```

### Component State

```typescript
interface UnifiedFilterState {
  isAdminMenuOpen: boolean;
  isYearMenuOpen: boolean;
  isLoading: boolean;
  error: string | null;
}
```

## Correctness Properties

_A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees._

### Property Reflection

After analyzing the acceptance criteria, I identified several testable properties and consolidated redundant ones:

**Consolidation Analysis:**

- Properties for component rendering (1.1, 1.2, 4.1, 4.4) - combined into comprehensive rendering property
- Properties for state management (1.3, 1.4, 2.4, 2.5) - combined into unified state consistency property
- Properties for configuration handling (3.1, 3.2, 3.3, 3.5) - combined into configuration adaptability property
- Properties for selection behavior (2.1, 2.2, 2.3, 4.3) - combined into selection behavior property
- Properties for error handling (5.1, 5.2, 5.3, 5.4, 5.5) - combined into error handling property
- Properties for visual feedback (4.2, 4.5) - combined into interaction feedback property

### Property 1: Component Rendering Consistency

_For any_ valid filter configuration and props, the unified filter component should render all required elements (administration section when showAdministration=true, year section when showYears=true) with consistent styling, appropriate placeholder text, and proper accessibility attributes
**Validates: Requirements 1.1, 1.2, 4.1, 4.4**

### Property 2: State Management and API Consistency

_For any_ filter state change (administration or year selection), the component should trigger the appropriate callback with correct values, maintain state isolation from other components, and preserve backward compatibility with existing filter state structures
**Validates: Requirements 1.3, 1.4, 2.4, 2.5, 3.4**

### Property 3: Selection Behavior Correctness

_For any_ valid selection operation (single administration, multiple years, or mixed selections), the component should handle all supported administration options, manage multi-select year functionality correctly, and display current selections clearly
**Validates: Requirements 2.1, 2.2, 2.3, 4.3**

### Property 4: Configuration Adaptability

_For any_ valid component configuration (different prop combinations, state structures, or layout contexts), the component should adapt its behavior appropriately while maintaining core functionality and fitting within existing UI layouts
**Validates: Requirements 3.1, 3.2, 3.3, 3.5**

### Property 5: Error Handling Robustness

_For any_ error condition (empty options, API failures, invalid selections, or component lifecycle events), the component should handle errors gracefully, provide appropriate user feedback, validate inputs, and clean up resources properly
**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

### Property 6: Interaction Feedback Consistency

_For any_ user interaction (hover, loading states, or disabled states), the component should provide appropriate visual feedback, loading indicators, and maintain interaction consistency with the existing myAdmin Reports interface
**Validates: Requirements 4.2, 4.5**

## Error Handling

### Error Scenarios

1. **Missing Options Data**: When administration or year options fail to load
2. **Invalid Selections**: When selected values are not in available options
3. **Network Failures**: When API calls for filter options fail
4. **State Inconsistencies**: When parent state and component state become misaligned

### Error Recovery

- Graceful degradation with disabled states
- Retry mechanisms for failed API calls
- Validation and correction of invalid selections
- Clear error messages for users

## Testing Strategy

### Unit Testing Approach

Unit tests will focus on:

- Component rendering with different prop combinations
- Event handling and callback execution
- State management and updates
- Error boundary behavior
- Accessibility compliance

### Property-Based Testing Approach

Property-based tests will use **React Testing Library** with **@fast-check/jest** for property generation. Each test will run a minimum of 100 iterations to ensure comprehensive coverage.

**Property Test Implementation Requirements:**

- Each property-based test must include a comment referencing the design document property
- Tests must use the format: `**Feature: unified-admin-year-filter, Property {number}: {property_text}**`
- Generate realistic filter configurations and state combinations
- Validate component behavior across all input variations

**Test Data Generation:**

- Administration options: Generate arrays of 1-5 administration objects
- Year arrays: Generate arrays of 1-10 years between 2020-2030
- Filter states: Generate valid combinations of selected administrations and years
- Component props: Generate valid prop combinations with different show/hide flags

### Integration Testing

Integration tests will verify:

- Compatibility with existing myAdmin Reports tabs
- Proper state synchronization with parent components
- API call consistency with original implementations
- Performance impact on existing workflows
