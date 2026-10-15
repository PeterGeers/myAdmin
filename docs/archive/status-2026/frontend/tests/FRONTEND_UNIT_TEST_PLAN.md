# myAdmin Frontend Unit Test Plan

## Quick Start

```bash
# Run all tests once (no watch mode)
npm run test:run

# Run with coverage report
npx vitest run --coverage

# Run specific test file
npx vitest run src/components/App.routing.test.tsx
npx vitest run src/components/App.theme.test.tsx
```

## Overview

Comprehensive unit testing strategy for React TypeScript frontend using Vitest, React Testing Library, and modern testing practices.

## Test Framework Stack

- **Vitest** — Test runner and assertion library
- **React Testing Library** — Component testing utilities
- **@testing-library/user-event** — User interaction simulation
- **@testing-library/jest-dom** — Custom matchers (compatible with Vitest)
- **@fast-check/vitest** — Property-based testing
- **vitest-axe** — Accessibility testing
- **MSW (Mock Service Worker)** — API mocking
- **TypeScript** — Type safety in tests

## Core Components to Test

### 1. App Component (`App.tsx`) — Priority: High

- [x] Routing: Navigation between different tabs/views
- [x] Theme Provider: Chakra UI theme application
- [x] Error Boundaries: Error handling and display
- [x] Loading States: Initial app loading behavior
- [x] Authentication: User session management

### 2. Banking Processor (`BankingProcessor.tsx`) — Priority: High

- [x] File Upload: CSV/TSV file selection and validation
- [x] Mode Toggle: Test/Production mode switching
- [x] File Processing: Transaction parsing and display
- [x] Pattern Application: Historical pattern matching
- [x] Data Validation: Form validation and error handling
- [x] API Integration: Backend communication
- [x] Table Operations: Sorting, filtering, pagination
- [x] Edit Functionality: Inline editing of transactions

### 3. myAdmin Reports (`myAdminReports.tsx`) — Priority: High

- [x] Tab Navigation: Multiple report tab switching
- [x] Data Visualization: Chart rendering (Recharts)
- [x] Filter Controls: Year, administration, listing filters
- [x] Export Functions: HTML/XLSX export functionality

### 4. PDF Upload Form (`PDFUploadForm.tsx`) — Priority: Medium

- [x] File Selection: PDF file upload interface
- [x] Drag & Drop: File drop zone functionality
- [x] Progress Tracking: Upload progress indication
- [x] Vendor Selection: Folder/vendor categorization

### 5. STR Processor (`STRProcessor.tsx`) — Priority: Medium

- [x] Platform Selection: Airbnb/Booking.com/Direct
- [x] File Processing: Revenue file parsing
- [x] Status Separation: Realized vs planned bookings

### 6. Profit & Loss (`ProfitLoss.tsx`) — Priority: Low

- [x] Report Generation: P&L statement creation
- [x] Period Selection: Date range filtering
- [x] Export Functions: Report export capabilities

## Test Infrastructure

### Vitest Configuration (in vite.config.ts)

```typescript
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/setupTests.ts',
  css: true,
  include: ['src/**/*.{test,spec}.{ts,tsx}'],
}
```

### Test Utilities

```typescript
// test-utils.tsx
import { render } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import theme from '../theme';

const AllTheProviders = ({ children }) => (
  <ChakraProvider theme={theme}>{children}</ChakraProvider>
);

const customRender = (ui, options) =>
  render(ui, { wrapper: AllTheProviders, ...options });

export * from '@testing-library/react';
export { customRender as render };
```

## Testing Patterns

### Component Testing

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('ComponentName', () => {
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

### Mocking with Vitest

```typescript
import { vi } from "vitest";
import { authenticatedGet } from "../services/apiService";

vi.mock("../services/apiService");

it("loads data", async () => {
  const mockResponse = { ok: true, json: async () => ({ data: [] }) };
  (authenticatedGet as ReturnType<typeof vi.fn>).mockResolvedValue(
    mockResponse,
  );
  // Test component
});
```

### Property-Based Testing

```typescript
import { test } from "@fast-check/vitest";
import * as fc from "fast-check";

test.prop([fc.integer(), fc.integer()])("addition is commutative", (a, b) => {
  expect(a + b).toBe(b + a);
});
```

## Coverage Requirements

### Minimum Coverage Targets

- **Statements**: 80%
- **Branches**: 75%
- **Functions**: 80%
- **Lines**: 80%

## Test Execution Scripts

```json
{
  "scripts": {
    "test": "vitest",
    "test:run": "vitest run"
  }
}
```

## Accessibility Testing

### Tools

- `vitest-axe` for automated a11y testing
- Manual keyboard navigation testing
- Screen reader testing (NVDA/JAWS)

## Best Practices

1. Keep tests simple and focused
2. Use descriptive test names
3. Avoid implementation details
4. Test user behavior, not code
5. Maintain test independence
6. Use `vi.fn()`, `vi.mock()`, `vi.spyOn()` (Vitest API)
