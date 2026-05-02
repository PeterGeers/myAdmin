# Frontend Testing Guide — Vitest + React Testing Library

## Overview

myAdmin uses **Vitest 4.x** as the test runner (migrated from Jest in April 2026). Tests run in a **jsdom** environment with **React Testing Library** for component testing and **fast-check 4.x** for property-based testing. Playwright handles e2e tests separately.

## Quick Reference

```bash
# Watch mode (development)
npm test

# Single run (CI)
npm run test:run

# Run specific file
npx vitest run src/__tests__/myFile.test.ts

# Run specific test by name
npx vitest run src/__tests__/myFile.test.ts -t "test name"

# Run with coverage
npx vitest run --coverage
```

## Configuration

### vite.config.ts (test block)

```typescript
test: {
  globals: true,          // describe, it, expect, vi available globally
  environment: 'jsdom',   // DOM simulation
  setupFiles: './src/setupTests.ts',
  css: true,              // Process CSS imports
  include: ['src/**/*.{test,spec}.{ts,tsx}', 'tests/**/*.{test,spec}.{ts,tsx}'],
  exclude: ['tests/e2e/**', 'node_modules/**', 'build/**'],
}
```

### Key differences from Jest

| Jest                   | Vitest                                                                       |
| ---------------------- | ---------------------------------------------------------------------------- |
| `jest.fn()`            | `vi.fn()`                                                                    |
| `jest.mock()`          | `vi.mock()`                                                                  |
| `jest.spyOn()`         | `vi.spyOn()`                                                                 |
| `jest.clearAllMocks()` | `vi.clearAllMocks()`                                                         |
| `jest.resetAllMocks()` | `vi.resetAllMocks()`                                                         |
| `jest.requireActual()` | `await vi.importActual()` (async!)                                           |
| `jest.useFakeTimers()` | `vi.useFakeTimers()`                                                         |
| `jest.setTimeout(ms)`  | `vi.setConfig({ testTimeout: ms })` or `{ timeout: ms }` on individual tests |
| `(x as jest.Mock)`     | `vi.mocked(x)`                                                               |
| `@fast-check/jest`     | `@fast-check/vitest`                                                         |
| `jest-axe`             | `vitest-axe`                                                                 |

### vi.importActual is async

```typescript
// Jest (sync)
jest.mock("./module", () => {
  const actual = jest.requireActual("./module");
  return { ...actual, myFn: jest.fn() };
});

// Vitest (async)
vi.mock("./module", async () => {
  const actual = await vi.importActual("./module");
  return { ...actual, myFn: vi.fn() };
});
```

## Test File Structure

### Standard test file

```typescript
import { vi } from 'vitest';
import { render, screen, waitFor } from '../test-utils';  // Custom render with ChakraProvider
import userEvent from '@testing-library/user-event';
import { MyComponent } from '../components/MyComponent';

// Mocks go here (hoisted to top by Vitest)
vi.mock('../services/apiService', () => ({
  authenticatedGet: vi.fn(),
  authenticatedPost: vi.fn(),
}));

describe('MyComponent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText(/expected text/i)).toBeInTheDocument();
  });
});
```

### Custom render (test-utils.tsx)

All component tests should import `render` from `test-utils` (not directly from `@testing-library/react`) to get the ChakraProvider wrapper:

```typescript
import { render, screen } from "../test-utils";
```

Exception: tests that mock `@chakra-ui/react` entirely should import from `@testing-library/react` directly.

## Mocking Patterns

### Mocking modules

```typescript
// Simple mock
vi.mock("../services/apiService", () => ({
  authenticatedGet: vi.fn(),
}));

// Partial mock (keep real implementation, override specific exports)
vi.mock("../services/apiService", async () => {
  const actual = await vi.importActual("../services/apiService");
  return { ...actual, authenticatedGet: vi.fn() };
});
```

### Mocking fetch

The global `fetch` mock is in `setupTests.ts`. To override per-test:

```typescript
vi.mocked(global.fetch).mockResolvedValueOnce({
  ok: true,
  json: async () => ({ data: "test" }),
} as Response);
```

### Type-safe mock access

```typescript
// Access mock calls/results
vi.mocked(global.fetch).mock.calls        // all call arguments
vi.mocked(global.fetch).mockClear()       // clear call history
vi.mocked(global.fetch).mockResolvedValueOnce(...)  // next return value
vi.mocked(global.fetch).mockRejectedValueOnce(...)  // next error
vi.mocked(global.fetch).mockImplementation(...)      // custom implementation
```

### vi.mock scope — critical limitation

`vi.mock()` is hoisted to the top of **the file it appears in**. It does NOT intercept transitive dependencies in `node_modules`.

```typescript
// This mocks '@chakra-ui/react' for THIS test file's imports
vi.mock('@chakra-ui/react', () => ({ Box: ({ children }) => <div>{children}</div> }));

// But if a component you import uses @chakra-ui/react internally,
// that component still gets the REAL @chakra-ui/react
```

For transitive mocks, use `resolve.alias` in `vite.config.ts` instead.

## Chakra UI Testing

### Approach 1: Real Chakra (preferred for simple components)

Use `test-utils.tsx` which wraps with `ChakraProvider`:

```typescript
import { render, screen } from "../test-utils";
```

Works for most components. Fails for components using Chakra's `Checkbox`, `Radio`, or other components that trigger `@zag-js/focus-visible` (see Known Issues below).

### Approach 2: Mocked Chakra (required for complex components)

For components using Checkbox, Accordion with checkboxes, or other `@zag-js`-dependent components, mock Chakra entirely using the centralized mock:

```typescript
import { vi } from "vitest";

vi.mock("@chakra-ui/react", async () => {
  const { chakraMock } =
    await import("../components/TenantAdmin/TemplateManagement/chakraMock");
  return chakraMock;
});
vi.mock("@chakra-ui/icons", async () => {
  const { iconsMock } =
    await import("../components/TenantAdmin/TemplateManagement/chakraMock");
  return iconsMock;
});

import { render, screen } from "@testing-library/react"; // NOT test-utils
```

When using mocked Chakra, be aware:

- `Modal` renders as `<div role="dialog">` when open, `null` when closed
- `AlertDialog` renders as `<div role="alertdialog">`
- `Button` with `isLoading` shows `loadingText` content
- `Collapse` removes children from DOM when closed (not just hidden)
- `Accordion` renders all items expanded (no collapse logic)
- Style-based assertions (`toHaveStyle`) don't work — check element existence instead
- `ModalCloseButton` renders as `<button>×</button>` — may conflict with footer "Close" button

### The chakraMock.tsx file

Located at `src/components/TenantAdmin/TemplateManagement/chakraMock.tsx`. Contains mock implementations for all commonly used Chakra components. When adding new Chakra components to the app, add corresponding mocks here if tests need them.

## Property-Based Testing (fast-check)

```typescript
import fc from "fast-check";

it("property holds for all inputs", { timeout: 30000 }, () => {
  fc.assert(
    fc.property(fc.string(), fc.integer(), (str, num) => {
      // property assertion
      expect(myFunction(str, num)).toBeDefined();
    }),
    { numRuns: 100 },
  );
});
```

Note the `{ timeout: 30000 }` — property tests with 100+ iterations often exceed the default 5000ms timeout.

For async rendering tests (React hooks), use `fc.sample` + loop instead of `fc.assert`:

```typescript
const inputs = fc.sample(fc.record({ ... }), 100);
for (const input of inputs) {
  const { result } = renderHook(() => useMyHook(input));
  expect(result.current).toBeDefined();
  cleanup();
}
```

## Known Issues & Workarounds

### @zag-js/focus-visible crash in jsdom

**Problem:** Chakra UI v2's checkbox/radio hooks use `@zag-js/focus-visible` which monkey-patches `HTMLElement.prototype.focus`. In jsdom 29+, this crashes with "Cannot set property focus of HTMLElement which has only a getter".

**Solution:** Mock `@chakra-ui/react` entirely in test files that render Checkbox, Radio, or Accordion with checkboxes. Use the centralized `chakraMock.tsx`.

**Why vi.mock doesn't work for this:** `vi.mock('@zag-js/focus-visible')` in a test file only intercepts direct imports, not transitive imports from `@chakra-ui/react` internals.

### React 19 "not wrapped in act()" warnings

Suppressed globally in `setupTests.ts`. React 19 warns aggressively about state updates outside `act()` even when React Testing Library handles them correctly.

### AWS Amplify auth mock

Mocked globally in `setupTests.ts` to prevent real AWS calls. Override per-test:

```typescript
const { fetchAuthSession } = await import("aws-amplify/auth");
vi.mocked(fetchAuthSession).mockResolvedValueOnce({
  tokens: { accessToken: { toString: () => "mock-token" } },
});
```

## File Organization

```
frontend/
├── src/
│   ├── __tests__/           # Service and integration tests
│   ├── components/
│   │   └── MyComponent.test.tsx   # Co-located component tests
│   ├── hooks/__tests__/     # Hook tests (unit + property)
│   ├── services/__tests__/  # Service layer tests
│   ├── tests/               # Cross-cutting integration tests
│   ├── utils/               # Utility tests (co-located)
│   ├── setupTests.ts        # Global test setup
│   └── test-utils.tsx       # Custom render with providers
├── tests/
│   └── unit/                # Additional unit tests outside src/
└── vite.config.ts           # Vitest config in test block
```

## Writing New Tests — Checklist

1. Import `render` from `test-utils` (or `@testing-library/react` if mocking Chakra)
2. Use `vi.fn()` for mock functions, `vi.mock()` for module mocks
3. Use `vi.clearAllMocks()` in `beforeEach`
4. Use `screen.getByRole` / `screen.getByText` for queries (prefer accessible queries)
5. Use `waitFor` for async assertions
6. Use `userEvent.setup()` for user interactions (not `fireEvent` unless necessary)
7. Add `{ timeout: 30000 }` for property-based tests with 100+ iterations
8. Use `vi.mocked(x)` instead of `(x as any)` for type-safe mock access

## Best Practices — Do's and Don'ts

### DO ✅

**Test behavior, not markup.** Query by role, text, or label — not by CSS class or internal structure.

```typescript
// Good — tests what the user sees
await user.click(screen.getByRole("button", { name: /open/i }));
expect(screen.getByRole("dialog")).toBeVisible();

// Bad — tests implementation details
expect(container.firstChild).toMatchSnapshot();
```

**Test accessibility.** Chakra is strong on a11y — take advantage of it.

```typescript
expect(button).toHaveAccessibleName("Opslaan");
expect(screen.getByRole("alert")).toBeInTheDocument();
```

**Use `userEvent` over `fireEvent`.** `userEvent` simulates real user behavior (focus, blur, keyboard events). Use `fireEvent` only when `userEvent` can't handle it (e.g., typing `{` in JSON fields).

```typescript
const user = userEvent.setup();
await user.click(button);
await user.type(input, "hello");
```

**Test your business logic, not Chakra's.** Don't verify that `<Button>` renders a button — verify that clicking it triggers your handler, opens your modal, or submits your form.

**Use Vitest + Playwright together.** Vitest for fast unit/integration tests, Playwright for real browser flows. They complement each other.

### DON'T ❌

**Don't test on Chakra classnames.** They change between versions.

```typescript
// Bad — breaks on Chakra updates
expect(el).toHaveClass("css-abc123");

// Good — stable
expect(el).toBeVisible();
expect(el).toHaveTextContent("Expected text");
```

**Don't test pixel-perfect layout in jsdom.** jsdom has no layout engine — no widths, no animations, no responsive behavior. Use Playwright for visual testing.

**Don't forget portals.** Modal, Drawer, Menu render via portals to `document.body`. Always use `screen.getByRole('dialog')` — never search within `container`.

**Don't overuse snapshots.** They grow into archaeological layers that nobody reviews. Prefer explicit assertions.

**Don't blindly upgrade Chakra.** Lock versions, upgrade deliberately, let CI catch breakage first.

## Browser API Mocks (setupTests.ts)

jsdom doesn't implement several browser APIs that Chakra components use. These are mocked globally in `setupTests.ts`:

| API                           | Why needed              | Mock location   |
| ----------------------------- | ----------------------- | --------------- |
| `TextEncoder` / `TextDecoder` | MSW                     | `setupTests.ts` |
| `BroadcastChannel`            | MSW                     | `setupTests.ts` |
| `fetch`                       | API calls               | `setupTests.ts` |
| `aws-amplify/auth`            | Prevents real AWS calls | `setupTests.ts` |

If you encounter missing browser APIs in new tests, add mocks to `setupTests.ts` rather than per-test. Common ones to watch for:

- `ResizeObserver` — used by some Chakra layout components
- `matchMedia` — used by responsive/color mode features
- `IntersectionObserver` — used by lazy loading
- `scrollIntoView` — used by focus management

## Testing Strategy

```
┌─────────────────────────────────────────────┐
│  Playwright (e2e)                           │
│  Real browser, real backend, slow           │
│  → Auth flows, critical paths, visual       │
├─────────────────────────────────────────────┤
│  Vitest + RTL (integration)                 │
│  jsdom, mocked services, medium speed       │
│  → Component interactions, form flows       │
├─────────────────────────────────────────────┤
│  Vitest (unit)                              │
│  No DOM, fast                               │
│  → Utils, services, hooks, pure functions   │
├─────────────────────────────────────────────┤
│  fast-check (property-based)                │
│  Generated inputs, 100+ iterations          │
│  → Invariants, edge cases, sorting, filters │
└─────────────────────────────────────────────┘
```
