# Reports Module Split - FIN and STR

## Overview

Split the monolithic "myAdmin Reports" into separate FIN Reports and STR Reports modules for better organization and module-based access control.

## Changes Made

### 1. New Components Created

#### `frontend/src/components/FINReports.tsx`

- Dedicated component for Financial (FIN) reports
- Shows only `FinancialReportsGroup`
- Checks for Finance module permissions: `Finance_CRUD`, `Finance_Read`, `Finance_Export`
- Clean, focused component without tabs

#### `frontend/src/components/STRReports.tsx`

- Dedicated component for STR (Short-Term Rental) reports
- Shows only `BnbReportsGroup`
- Checks for STR module permissions: `STR_CRUD`, `STR_Read`, `STR_Export`
- Clean, focused component without tabs

### 2. Menu Updates (`frontend/src/App.tsx`)

#### Old Menu:

- Single button: "📈 myAdmin Reports" (shown if user has FIN OR STR access)

#### New Menu:

- Two separate buttons:
  - "📊 FIN Reports" (purple) - shown only if user has FIN module access
  - "📈 STR Reports" (cyan) - shown only if user has STR module access

### 3. Routing Updates

#### New Routes:

- `fin-reports` → Shows FINReports component
- `str-reports` → Shows STRReports component
- `powerbi` → Legacy route, redirects to FINReports

#### Page Types:

Updated `PageType` to include: `'fin-reports' | 'str-reports'`

### 4. Module Access Protection

#### Auto-redirect on tenant switch:

- If user switches to tenant without FIN access while on FIN Reports → redirect to menu
- If user switches to tenant without STR access while on STR Reports → redirect to menu

## Benefits

### 1. **Better Organization**

- Clear separation between FIN and STR reporting
- No more confusing tabs
- Each module has its own dedicated page

### 2. **Improved Security**

- Users only see buttons for modules they have access to
- Automatic redirect if access is lost (tenant switch)
- Cleaner permission checks

### 3. **Better UX**

- Direct access to relevant reports
- No need to navigate through tabs
- Clear visual distinction (different colors and icons)

### 4. **Maintainability**

- Smaller, focused components
- Easier to modify FIN or STR reports independently
- Reduced code complexity

## File Structure

```
frontend/src/components/
├── FINReports.tsx          # NEW - FIN module reports
├── STRReports.tsx          # NEW - STR module reports
├── MyAdminReportsNew.tsx   # KEPT - Legacy component (can be removed later)
└── reports/
    ├── BnbReportsGroup.tsx         # STR reports group
    └── FinancialReportsGroup.tsx   # FIN reports group
```

## Migration Path

### For Users:

- Old "myAdmin Reports" button → Now split into two buttons
- Users with both modules see both buttons
- Users with one module see only their button
- No data loss or functionality change

### For Developers:

- `MyAdminReportsNew.tsx` can be deprecated/removed in future
- New components are simpler and easier to maintain
- Clear module boundaries

## Testing Checklist

- [x] FIN Reports button shows only for users with Finance permissions
- [x] STR Reports button shows only for users with STR permissions
- [x] FIN Reports page shows Financial reports correctly
- [x] STR Reports page shows BNB reports correctly
- [x] Auto-redirect works when switching tenants
- [x] Legacy `powerbi` route still works (redirects to FIN Reports)
- [x] No console errors or warnings
- [x] Build completes successfully

## Future Improvements

1. Remove `MyAdminReportsNew.tsx` completely (no longer needed)
2. Add breadcrumbs for better navigation
3. Consider adding quick links between FIN and STR reports for users with both modules
4. Add module-specific help/documentation links
