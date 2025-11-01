# myAdmin Frontend Unit Test Plan
# Run all tests once (no watch mode)
npm test -- --watchAll=false

# Run with coverage report
npm test -- --coverage --watchAll=false

# Run specific test file
npm test -- app.routing.test.tsx --watchAll=false
npm test -- app.theme.test.tsx --watchAll=false

## Overview
Comprehensive unit testing strategy for React TypeScript frontend using Jest, React Testing Library, and modern testing practices.

## Test Framework Stack
- **Jest** - Test runner and assertion library
- **React Testing Library** - Component testing utilities
- **@testing-library/user-event** - User interaction simulation
- **@testing-library/jest-dom** - Custom Jest matchers
- **MSW (Mock Service Worker)** - API mocking
- **TypeScript** - Type safety in tests

## Core Components to Test

### 1. App Component (`App.tsx`)
**Priority: High**
- [x] **Routing**: Navigation between different tabs/views
- [x] **Theme Provider**: Chakra UI theme application
- [x] **Error Boundaries**: Error handling and display
- [x] **Loading States**: Initial app loading behavior
- [x] **Authentication**: User session management

### 2. Banking Processor (`BankingProcessor.tsx`)
**Priority: High**
- [x] **File Upload**: CSV/TSV file selection and validation
- [x] **Mode Toggle**: Test/Production mode switching
- [x] **File Processing**: Transaction parsing and display
- [x] **Pattern Application**: Historical pattern matching
- [x] **Data Validation**: Form validation and error handling
- [x] **API Integration**: Backend communication
- [x] **Table Operations**: Sorting, filtering, pagination
- [x] **Edit Functionality**: Inline editing of transactions

### 3. myAdmin Reports (`myAdminReports.tsx`)
**Priority: High**
- [x] **Tab Navigation**: Multiple report tab switching
- [x] **Data Visualization**: Chart rendering (Recharts)
- [x] **Filter Controls**: Year, administration, listing filters
- [x] **Export Functions**: HTML/XLSX export functionality
- [x] **Interactive Charts**: Violin plots, box plots, trends
- [x] **Data Aggregation**: Summary statistics display
- [x] **Responsive Design**: Mobile/desktop layouts

### 4. PDF Upload Form (`PDFUploadForm.tsx`)
**Priority: Medium**
- [x] **File Selection**: PDF file upload interface
- [x] **Drag & Drop**: File drop zone functionality
- [x] **Progress Tracking**: Upload progress indication
- [x] **Vendor Selection**: Folder/vendor categorization
- [x] **Transaction Preview**: Extracted transaction display
- [x] **Edit Interface**: Transaction modification
- [x] **Save Operations**: Database persistence

### 5. PDF Validation (`PDFValidation.tsx`)
**Priority: Medium**
- [x] **Progress Bar**: Real-time validation progress
- [x] **URL Validation**: Google Drive URL checking
- [x] **Filter Controls**: Year/administration filtering
- [x] **Results Display**: Validation results table
- [x] **Manual Updates**: URL correction interface
- [x] **Status Indicators**: Validation status display

### 6. STR Processor (`STRProcessor.tsx`)
**Priority: Medium**
- [x] **Platform Selection**: Airbnb/Booking.com/Direct
- [x] **File Processing**: Revenue file parsing
- [x] **Status Separation**: Realized vs planned bookings
- [x] **Summary Display**: Revenue calculations
- [x] **Data Tables**: Booking data presentation
- [x] **Save Operations**: Database persistence

### 7. Profit & Loss (`ProfitLoss.tsx`)
**Priority: Low**
- [x] **Report Generation**: P&L statement creation
- [x] **Period Selection**: Date range filtering
- [x] **Account Grouping**: Chart of accounts organization
- [x] **Export Functions**: Report export capabilities

## Test Categories

### Unit Tests
**Focus: Individual component behavior**
- Component rendering
- Props handling
- State management
- Event handlers
- Utility functions
- Type safety

### Integration Tests
**Focus: Component interaction**
- Parent-child communication
- Context providers
- API integration
- Form submissions
- Navigation flows

### Accessibility Tests
**Focus: A11y compliance**
- Screen reader compatibility
- Keyboard navigation
- ARIA attributes
- Color contrast
- Focus management

### Visual Regression Tests
**Focus: UI consistency**
- Component snapshots
- Layout stability
- Responsive design
- Theme application

## Test Infrastructure

### 1. Test Setup Files
```typescript
// setupTests.ts
import '@testing-library/jest-dom';
import { server } from './mocks/server';

// jest.config.js
module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/src/setupTests.ts'],
  moduleNameMapping: {
    '\\.(css|less|scss)$': 'identity-obj-proxy'
  }
};
```

### 2. Mock Service Worker Setup
```typescript
// mocks/handlers.ts
import { rest } from 'msw';

export const handlers = [
  rest.get('/api/folders', (req, res, ctx) => {
    return res(ctx.json(['General', 'Booking.com']));
  }),
  // Additional API mocks
];
```

### 3. Test Utilities
```typescript
// test-utils.tsx
import { render } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import theme from '../theme';

const AllTheProviders = ({ children }) => {
  return (
    <ChakraProvider theme={theme}>
      {children}
    </ChakraProvider>
  );
};

const customRender = (ui, options) =>
  render(ui, { wrapper: AllTheProviders, ...options });

export * from '@testing-library/react';
export { customRender as render };
```

## Priority Test Files

### High Priority
1. `App.test.tsx` - Main application component
2. `BankingProcessor.test.tsx` - Core banking functionality
3. `myAdminReports.test.tsx` - Reporting dashboard
4. `components/__tests__/common.test.tsx` - Shared utilities

### Medium Priority
5. `PDFUploadForm.test.tsx` - PDF processing
6. `PDFValidation.test.tsx` - URL validation
7. `STRProcessor.test.tsx` - STR data processing

### Low Priority
8. `ProfitLoss.test.tsx` - P&L reporting
9. `hooks/__tests__/` - Custom hooks testing
10. `utils/__tests__/` - Utility functions

## Test Data Requirements

### Mock Data Files
```typescript
// __mocks__/data.ts
export const mockTransactions = [
  {
    id: 1,
    date: '2023-01-01',
    description: 'Test Transaction',
    amount: 100.00,
    account: '1000'
  }
];

export const mockBankingData = [
  {
    Date: '2023-01-01',
    Description: 'Payment',
    Amount: -50.00,
    Balance: 950.00
  }
];
```

### API Response Mocks
- Banking processor responses
- Report data responses
- File upload responses
- Validation results
- Error responses

## Testing Patterns

### Component Testing Pattern
```typescript
describe('ComponentName', () => {
  beforeEach(() => {
    // Setup
  });

  it('renders correctly', () => {
    render(<ComponentName />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('handles user interactions', async () => {
    const user = userEvent.setup();
    render(<ComponentName />);
    
    await user.click(screen.getByRole('button'));
    expect(mockFunction).toHaveBeenCalled();
  });
});
```

### API Integration Testing
```typescript
it('fetches and displays data', async () => {
  server.use(
    rest.get('/api/data', (req, res, ctx) => {
      return res(ctx.json(mockData));
    })
  );

  render(<Component />);
  
  await waitFor(() => {
    expect(screen.getByText('Data loaded')).toBeInTheDocument();
  });
});
```

## Coverage Requirements

### Minimum Coverage Targets
- **Statements**: 80%
- **Branches**: 75%
- **Functions**: 80%
- **Lines**: 80%

### Critical Path Coverage
- User workflows: 95%
- Error handling: 90%
- API integration: 85%
- Form validation: 90%

## Test Execution Scripts

### Package.json Scripts
```json
{
  "scripts": {
    "test": "react-scripts test",
    "test:coverage": "react-scripts test --coverage --watchAll=false",
    "test:ci": "CI=true react-scripts test --coverage --watchAll=false",
    "test:debug": "react-scripts --inspect-brk test --runInBand --no-cache"
  }
}
```

### Coverage Configuration
```json
{
  "jest": {
    "collectCoverageFrom": [
      "src/**/*.{ts,tsx}",
      "!src/**/*.d.ts",
      "!src/index.tsx",
      "!src/reportWebVitals.ts"
    ],
    "coverageThreshold": {
      "global": {
        "statements": 80,
        "branches": 75,
        "functions": 80,
        "lines": 80
      }
    }
  }
}
```

## Accessibility Testing

### A11y Test Requirements
- Screen reader navigation
- Keyboard-only operation
- Focus management
- ARIA labels and roles
- Color contrast compliance
- Form accessibility

### Testing Tools
- `@testing-library/jest-dom`
- `jest-axe` for automated a11y testing
- Manual keyboard navigation testing
- Screen reader testing (NVDA/JAWS)

## Performance Testing

### Metrics to Test
- Component render times
- Bundle size impact
- Memory usage
- Re-render optimization
- Lazy loading effectiveness

### Tools
- React DevTools Profiler
- Bundle analyzer
- Lighthouse CI
- Performance monitoring

## Browser Compatibility Testing

### Target Browsers
- Chrome (latest 2 versions)
- Firefox (latest 2 versions)
- Safari (latest 2 versions)
- Edge (latest 2 versions)

### Mobile Testing
- iOS Safari
- Android Chrome
- Responsive design validation
- Touch interaction testing

## Continuous Integration

### CI Pipeline Requirements
- Automated test execution
- Coverage reporting
- Visual regression testing
- Accessibility auditing
- Performance monitoring
- Bundle size tracking

### Quality Gates
- All tests must pass
- Coverage thresholds met
- No accessibility violations
- Performance budgets maintained
- TypeScript compilation successful

## Test Maintenance

### Regular Tasks
- Update test data
- Refactor obsolete tests
- Add tests for new features
- Review coverage reports
- Update mock responses

### Best Practices
- Keep tests simple and focused
- Use descriptive test names
- Avoid implementation details
- Test user behavior, not code
- Maintain test independence