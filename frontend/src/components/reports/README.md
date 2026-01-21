# Reports Refactoring Plan

## Overview

This directory contains the refactored report components, split from the monolithic `myAdminReports.tsx` file (4000+ lines) into smaller, maintainable components.

## Structure

### Main Components

- **MyAdminReportsNew.tsx** - Main entry point with two top-level tabs
- **BnbReportsGroup.tsx** - Container for all BNB-related reports
- **FinancialReportsGroup.tsx** - Container for all financial reports

### Individual Report Components (To Be Created)

#### BNB Reports

1. **BnbRevenueReport.tsx** - BNB Revenue analysis with date filters and charts
2. **BnbActualsReport.tsx** - BNB Actuals with expandable year/quarter/month views
3. **BnbViolinsReport.tsx** - Violin charts for price and stay duration distribution
4. **BnbReturningGuestsReport.tsx** - Returning guests analysis
5. **BnbFutureReport.tsx** - Future bookings overview
6. **ToeristenbelastingReport.tsx** - Tourist tax reporting

#### Financial Reports

7. **MutatiesReport.tsx** - Transactions (P&L) with filtering and export
8. **ActualsReport.tsx** - Actuals dashboard with hierarchical data
9. **BtwReport.tsx** - BTW (VAT) declaration generation
10. **ReferenceAnalysisReport.tsx** - Reference number analysis with trends
11. **AangifteIbReport.tsx** - Income tax declaration (Aangifte IB)

## Migration Steps

### Phase 1: Setup ✅

- [x] Create directory structure
- [x] Create group components (BnbReportsGroup, FinancialReportsGroup)
- [x] Create main component (MyAdminReportsNew)

### Phase 2: Extract Individual Reports

For each report:

1. Extract the TabPanel content from myAdminReports.tsx
2. Create a new component file
3. Move state management and API calls
4. Import and use in the appropriate group component
5. Test functionality

### Phase 3: Shared Utilities

Create shared utilities for:

- **formatAmount()** - Amount formatting with different display formats
- **renderExpandableBnbData()** - Expandable BNB table rendering
- **renderHierarchicalData()** - Hierarchical financial data rendering
- **renderBalanceData()** - Balance sheet rendering

### Phase 4: Testing & Migration

1. Test each individual component
2. Update App.tsx to use MyAdminReportsNew
3. Deprecate old myAdminReports.tsx
4. Update tests

## Benefits

### Maintainability

- Each report is self-contained and easier to understand
- Changes to one report don't affect others
- Easier to onboard new developers

### Performance

- Can implement lazy loading for individual reports
- Reduced initial bundle size
- Better code splitting

### Testing

- Easier to write unit tests for individual components
- Can test reports in isolation
- Better test coverage

### Collaboration

- Multiple developers can work on different reports simultaneously
- Reduced merge conflicts
- Clear ownership of components

## Component Template

```typescript
import React, { useState, useEffect } from 'react';
import { Card, CardBody, CardHeader, Heading, VStack } from '@chakra-ui/react';
import { buildApiUrl } from '../../config';

interface ReportNameReportProps {
  // Props if needed
}

const ReportNameReport: React.FC<ReportNameReportProps> = () => {
  // State management
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    // Filter state
  });

  // API calls
  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await fetch(buildApiUrl('/api/endpoint'));
      const result = await response.json();
      if (result.success) {
        setData(result.data);
      }
    } catch (err) {
      console.error('Error fetching data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">Report Name</Heading>
        </CardHeader>
        <CardBody>
          {/* Report content */}
        </CardBody>
      </Card>
    </VStack>
  );
};

export default ReportNameReport;
```

## Next Steps

1. Start with the simplest report (e.g., MutatiesReport)
2. Extract and test
3. Move to more complex reports
4. Create shared utilities as patterns emerge
5. Complete migration and deprecate old file

## Notes

- Keep the original myAdminReports.tsx until all reports are migrated and tested
- Use feature flags if needed to switch between old and new implementations
- Document any breaking changes or API modifications
