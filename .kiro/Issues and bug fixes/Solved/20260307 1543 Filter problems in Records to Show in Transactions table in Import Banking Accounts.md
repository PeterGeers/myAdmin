# Bug Report: Filter Problems in Records to Show

**Date**: 2026-03-07 15:43  
**Component**: Banking Processor - Transactions Table  
**Severity**: Medium  
**Status**: ✅ RESOLVED

## Issue Description

The "Records to show" filter in the Transactions (Mutaties) table was not responding to user selection. When clicking different options (50, 250, 500, 1000), the display remained stuck at 100 records.

## Location

- **File**: `frontend/src/components/BankingProcessor.tsx`
- **Component**: Mutaties TabPanel
- **Filter**: "Records to show" dropdown (lines ~1431-1439)

## Root Cause

Type mismatch in the filter configuration causing the selection logic to fail:

1. **State Type**: `displayLimit` is stored as a `number` (e.g., `100`)
2. **HTML Select Behavior**: The `<select>` element always returns string values (e.g., `"250"`)
3. **Custom getOptionValue**: Was returning raw numbers instead of strings
4. **Comparison Failure**: `"250" !== 250` caused the option lookup to fail
5. **No State Update**: When no matching option is found, the state doesn't update

### Code Flow

```typescript
// Before fix:
getOptionValue: (val) => val; // Returns number: 250

// In GenericFilter.handleSingleSelectChange:
const selectedValue = event.target.value; // String: "250"
const selectedOption = availableOptions.find(
  (opt) => getValueFn(opt) === selectedValue, // 250 !== "250" ❌
);
// selectedOption is undefined, onChange not called
```

## Solution

Fixed the type handling in the filter configuration:

### Changes Made

**File**: `frontend/src/components/BankingProcessor.tsx` (lines ~1431-1439)

```typescript
// BEFORE:
{
  type: 'single',
  label: 'Records to show',
  options: [50, 100, 250, 500, 1000],
  value: displayLimit,
  onChange: (value) => setDisplayLimit(value),
  getOptionLabel: (val) => String(val),
  getOptionValue: (val) => val  // ❌ Returns number
}

// AFTER:
{
  type: 'single',
  label: 'Records to show',
  options: [50, 100, 250, 500, 1000],
  value: displayLimit,
  onChange: (value) => setDisplayLimit(Number(value)),  // ✅ Convert string to number
  getOptionLabel: (val) => String(val),
  getOptionValue: (val) => String(val)  // ✅ Return string for comparison
}
```

### Fix Explanation

1. **getOptionValue**: Changed to return `String(val)` to match the string value from the select element
2. **onChange**: Added `Number(value)` conversion to maintain the numeric state type

## Testing

✅ Verified the filter now works correctly:

- Selecting 50 shows 50 records
- Selecting 100 shows 100 records
- Selecting 250 shows 250 records
- Selecting 500 shows 500 records
- Selecting 1000 shows 1000 records

## Related Components

This issue could potentially affect other single-select filters using numeric options:

- **GenericFilter.tsx**: The base filter component (handles string comparisons correctly)
- **FilterPanel.tsx**: The container component (passes through values correctly)

## Lessons Learned

1. **Type Consistency**: When using custom `getOptionValue` functions, ensure they return strings to match HTML select behavior
2. **Type Conversion**: Always convert back to the expected state type in the `onChange` handler
3. **Testing**: Test filters with different data types (strings, numbers, objects) to catch type mismatches

## Prevention

For future filter implementations:

```typescript
// ✅ GOOD: Consistent string handling for numeric options
{
  type: 'single',
  options: [10, 20, 30],
  value: numericState,
  onChange: (value) => setNumericState(Number(value)),
  getOptionValue: (val) => String(val)
}

// ❌ BAD: Type mismatch
{
  type: 'single',
  options: [10, 20, 30],
  value: numericState,
  onChange: (value) => setNumericState(value),
  getOptionValue: (val) => val  // Returns number, but select returns string
}
```

## Impact

- **User Impact**: Medium - Users couldn't change the number of displayed records
- **Data Impact**: None - No data corruption or loss
- **Workaround**: None available before fix

## Resolution Time

- **Reported**: 2026-03-07 15:43
- **Diagnosed**: 2026-03-07 15:45
- **Fixed**: 2026-03-07 15:50
- **Total Time**: ~7 minutes
