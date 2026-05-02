---
inclusion: fileMatch
fileMatchPattern: "frontend/src/**/*.test.{ts,tsx},frontend/tests/**/*.test.{ts,tsx}"
---

# Frontend Testing

This project uses **Vitest 4.x** with **jsdom**, **React Testing Library**, and **fast-check** for property-based tests.

## Key Rules

- Use `vi.fn()`, `vi.mock()`, `vi.spyOn()` — never `jest.*`
- Import `render` from `src/test-utils` (wraps with ChakraProvider) unless mocking Chakra entirely
- Use `vi.mocked(x)` for type-safe mock access instead of `(x as any)`
- Use `vi.clearAllMocks()` in `beforeEach`
- Add `{ timeout: 30000 }` on property-based tests with 100+ iterations
- `vi.importActual()` is async (unlike Jest's `requireActual`)

## Chakra UI Components

- Simple components: use real Chakra via `test-utils`
- Components with Checkbox/Radio/Accordion: mock `@chakra-ui/react` using `chakraMock.tsx` and import from `@testing-library/react` directly
- `vi.mock()` does NOT intercept transitive node_modules deps — mock the top-level package instead

## Compliance (enforced by frontend scanner)

The test maintenance framework's frontend scanner (`python -m backend.scripts.test_maintenance.scanner --frontend-only`) checks for:

- **Missing MSW handlers** — `fetch()` or `axios` calls without `setupServer` are flagged
- **Missing provider wrappers** — importing `render` from `@testing-library/react` instead of `src/test-utils` is flagged
- **Stale imports** — imports from paths that don't exist in the source tree are flagged

## Full Guide

#[[file:.kiro/specs/Common/Test approach/frontend/vitest-guide.md]]
