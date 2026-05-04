---
inclusion: fileMatch
fileMatchPattern: "frontend/src/**/*.test.{ts,tsx},frontend/tests/**/*.test.{ts,tsx}"
---

# Frontend Testing

This project uses **Vitest 4.x** with **jsdom**, **React Testing Library**, and **fast-check** for property-based tests.

## Key Rules

- Use `vi.fn()`, `vi.mock()`, `vi.spyOn()` — never `jest.*`
- Import `render` from `@/test-utils` (wraps with mock ChakraProvider automatically via resolve alias) — never from `@testing-library/react` directly
- Use `vi.mocked(x)` for type-safe mock access instead of `(x as any)`
- Use `vi.clearAllMocks()` in `beforeEach`
- Add `{ timeout: 30000 }` on property-based tests with 100+ iterations
- `vi.importActual()` is async (unlike Jest's `requireActual`)

## Chakra UI Components

Chakra UI is automatically mocked via `test.alias` in `vite.config.ts`. All imports of `@chakra-ui/react` and `@chakra-ui/icons` — including transitive imports from source components — resolve to centralized mock modules during test runs.

- **No mock setup needed**: just write your test and import `render` from `@/test-utils`
- **Mock modules**: `frontend/src/__mocks__/chakra-ui-react.tsx` and `frontend/src/__mocks__/chakra-ui-icons.tsx`
- **Prop filtering**: Chakra style props are automatically stripped to prevent React DOM warnings
- **Interactive behavior preserved**: `Modal`/`Drawer`/`AlertDialog` respect `isOpen`, `Button` maps `isDisabled`/`isLoading` to `disabled`, `Collapse` respects `in`
- **Adding new mocks**: if a Chakra component is missing from the mock module, add it to `chakra-ui-react.tsx` following the existing patterns (Pattern A–D in the design doc)
- **Known limitations**: no style assertions (`toHaveStyle`), fixed color mode (`"light"`), instant animations, no internal state management (Tabs/Accordion/Menu) — use Playwright for those

Design reference: `.kiro\specs\Common\Frameworks\chakra-test-mock-framework\design.md`

## Compliance (enforced by frontend scanner)

The test maintenance framework's frontend scanner (`python -m backend.scripts.test_maintenance.scanner --frontend-only`) checks for:

- **Missing MSW handlers** — `fetch()` or `axios` calls without `setupServer` are flagged
- **Missing provider wrappers** — importing `render` from `@testing-library/react` instead of `src/test-utils` is flagged
- **Stale imports** — imports from paths that don't exist in the source tree are flagged

## Full Guide

#[[file:.kiro/specs/Common/Test approach/frontend/vitest-guide.md]]
