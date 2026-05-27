# Bug Report: Import Banking Accounts - Use Generic Filters

**Date**: 2026-02-07 17:47  
**Severity**: Medium (UI Improvement)  
**Component**: Frontend - BankingProcessor  
**Status**: ✅ **SOLVED**

## Problem Description

The Import Banking Accounts >> Mutaties page had several UI issues:

1. **Uses custom year filter** instead of the generic filter system ✅ FIXED
2. **Records limit dropdown** is separate, should be in FilterPanel ✅ FIXED
3. **Has refresh button** - unnecessary since auto-refresh works ✅ REMOVED

## Solution Applied

### Quick Fix Implementation

Replaced custom filters with generic `FilterPanel` component and removed unnecessary refresh button.

**Changes Made**:

- Replaced custom year dropdown with `FilterPanel` using multi-select filter config
- Moved records limit dropdown into `FilterPanel` as single-select filter
- Removed refresh button (auto-refresh works perfectly)

**Files Modified**:

- `frontend/src/components/BankingProcessor.tsx` (lines ~1-50, ~1355-1380)

**Implementation**:

```tsx
<FilterPanel
  layout="horizontal"
  filters={[
    {
      type: "multi",
      label: "Year",
      options: filterOptions.years,
      value: mutatiesFilters.years,
      onChange: (years) => setMutatiesFilters((prev) => ({ ...prev, years })),
    },
    {
      type: "single",
      label: "Records to show",
      options: [50, 100, 250, 500, 1000],
      value: displayLimit,
      onChange: (value) => setDisplayLimit(value),
      getOptionLabel: (val) => String(val),
      getOptionValue: (val) => val,
    },
  ]}
  labelColor="white"
  bg="gray.600"
  color="white"
/>
```

### Verification

✅ TypeScript compilation passes  
✅ User tested - auto-refresh works nicely  
✅ Refresh button removed as unnecessary

## Note on File Size

**File is 2,179 lines** - more than 2x the recommended maximum (1,000 lines)!

This file needs comprehensive refactoring beyond this quick fix.

## Future Work

### Comprehensive Refactoring Spec Created

Created refactoring spec for future work:
`.kiro/specs/FIN/BankingProcessor/README.md`

### Proposed Structure (Future)

```
components/banking/
├── BankingProcessor.tsx (200 lines) - Main container
├── BankingUploadTab.tsx (300 lines)
├── BankingMutatiesTab.tsx (400 lines)
├── BankingAccountsTab.tsx (300 lines)
├── STRChannelTab.tsx (400 lines)
├── hooks/
│   ├── useBankingData.ts
│   └── useBankingFilters.ts
└── utils/
    ├── csvParser.ts
    └── transactionProcessors.ts
```

**Estimated Effort**: 3-4 days for full refactoring

---

**Reported By**: User  
**Fixed By**: Kiro AI  
**Date Reported**: 2026-02-07 17:47  
**Date Fixed**: 2026-02-07 18:20  
**Status**: ✅ Complete - All issues resolved
