# API Migration Plan - Add JWT Authentication

## Overview

All components currently using direct `fetch()` calls need to be migrated to use the authenticated API service functions.

## Components Requiring Migration

Based on the 401 errors, these components need immediate attention:

### Reports Components

1. **BnbRevenueReport.tsx** - Line 109
   - `/api/reports/bnb-table`
2. **BnbActualsReport.tsx** - ✅ MIGRATED
   - `/api/bnb/bnb-listing-data` (migrated from `/api/reports/bnb-listing-data`)
   - `/api/bnb/bnb-channel-data` (migrated from `/api/reports/bnb-channel-data`)
   - `/api/bnb/bnb-filter-options` (migrated from `/api/reports/bnb-filter-options`)

3. **BnbViolinsReport.tsx** - Lines 299, 317
   - `/api/bnb/bnb-violin-data`
   - `/api/bnb/bnb-filter-options`

4. **ToeristenbelastingReport.tsx** - Lines 31, 51
   - `/api/toeristenbelasting/generate-report` (POST)
   - `/api/toeristenbelasting/available-years`

5. **BnbReturningGuestsReport.tsx** - Line 65
   - `/api/bnb/bnb-returning-guests`

6. **MutatiesReport.tsx** - Line 92
   - `/api/reports/mutaties-table`

7. **ActualsReport.tsx** - Lines 331, 338, 352
   - `/api/reports/actuals-balance`
   - `/api/reports/actuals-profitloss`
   - `/api/reports/available-years`

8. **BtwReport.tsx** - Line 33
   - `/api/reports/available-years`

9. **AangifteIbReport.tsx** - Line 70
   - `/api/reports/aangifte-ib`

## Migration Pattern

### Before (Old Code):

```typescript
const response = await fetch(buildApiUrl("/api/reports/bnb-table", params));
const data = await response.json();
```

### After (New Code):

```typescript
import { authenticatedGet } from "../services/apiService";

const response = await authenticatedGet(
  buildApiUrl("/api/reports/bnb-table", params),
);
const data = await response.json();
```

### For POST requests:

```typescript
// Before
const response = await fetch(
  buildApiUrl("/api/toeristenbelasting/generate-report"),
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filters),
  },
);

// After
import { authenticatedPost } from "../services/apiService";

const response = await authenticatedPost(
  "/api/toeristenbelasting/generate-report",
  filters,
);
```

## Priority Order

1. **High Priority** (User-facing reports):
   - BnbRevenueReport.tsx
   - BnbActualsReport.tsx
   - ActualsReport.tsx
   - MutatiesReport.tsx

2. **Medium Priority**:
   - BnbViolinsReport.tsx
   - BnbReturningGuestsReport.tsx
   - ToeristenbelastingReport.tsx
   - BtwReport.tsx
   - AangifteIbReport.tsx

3. **Low Priority** (Other components):
   - All other components with fetch calls

## Estimated Time

- Per component: 5-10 minutes
- Total for high priority: ~40 minutes
- Total for all components: ~2-3 hours

## Testing After Migration

For each migrated component:

1. Login to the app
2. Navigate to the component
3. Verify data loads correctly
4. Check browser console for errors
5. Verify JWT token is in request headers (Network tab)

## Next Steps

1. Start with high-priority components
2. Test each component after migration
3. Rebuild frontend: `npm run build`
4. Verify in browser
