# myAdmin Frontend Test Infrastructure Summary

## Quick Test Execution

### Run All Tests (single execution)

```bash
npm run test:run
```

### Run All Tests (watch mode)

```bash
npm test
```

### Run with Coverage

```bash
npx vitest run --coverage
```

### Run Specific Test Files

```bash
npx vitest run src/components/App.routing.test.tsx
npx vitest run src/components/App.theme.test.tsx
```

## Test Framework Stack

- **Vitest** — Test runner and assertion library (replaces Jest)
- **React Testing Library** — Component testing utilities
- **@testing-library/user-event** — User interaction simulation
- **@testing-library/jest-dom** — Custom matchers
- **@fast-check/vitest** — Property-based testing
- **vitest-axe** — Accessibility testing
- **MSW (Mock Service Worker)** — API mocking
- **TypeScript** — Type safety in tests

## Test Infrastructure

### Configuration

- **Framework**: Vitest (configured in `vite.config.ts`)
- **Environment**: jsdom for DOM simulation
- **Setup file**: `src/setupTests.ts`
- **Globals**: `describe`, `it`, `expect`, `vi` available globally

### Test Utilities & Setup

- **File**: `setupTests.ts` — Vitest DOM extensions, polyfills, global mocks
- **Mocking**: `vi.fn()`, `vi.mock()`, `vi.spyOn()` (Vitest API)
- **Providers**: Chakra UI theme provider wrapping
- **Custom Render**: Enhanced render with providers

## Test Categories

### Unit Tests

- Component rendering and props
- State management and hooks
- Event handlers and user interactions
- Utility functions and helpers
- TypeScript type safety

### Integration Tests

- API communication with backend
- Form submissions and data flow
- Navigation and routing
- Context providers and state sharing

### Property-Based Tests

- Randomized input testing via fast-check
- Invariant verification across input ranges
- Edge case discovery

### Accessibility Tests

- Automated a11y testing via vitest-axe
- ARIA attributes and roles
- Keyboard navigation

### E2E Tests

- Playwright-based end-to-end tests
- Located in `tests/e2e/`
- Run separately via `npm run test:e2e`

## Test Execution Scripts

```json
{
  "scripts": {
    "test": "vitest",
    "test:run": "vitest run",
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui"
  }
}
```

## Mocking Patterns

### Vitest Mocking

```typescript
import { vi } from "vitest";

vi.mock("../services/apiService");
const mockFn = vi.fn();
vi.spyOn(obj, "method");
```

### MSW for API Mocking

```typescript
import { http, HttpResponse } from "msw";

const handlers = [
  http.get("/api/folders", () => {
    return HttpResponse.json(["General", "Booking.com"]);
  }),
];
```

## Current Status

- **Test Runner**: Vitest (migrated from Jest)
- **Build Tool**: Vite 8.x
- **109 test files** migrated to Vitest API
- **Property-based tests** via @fast-check/vitest
- **Accessibility tests** via vitest-axe
- **E2E tests** via Playwright
