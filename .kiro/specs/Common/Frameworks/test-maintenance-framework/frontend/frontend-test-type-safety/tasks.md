# Implementation Plan: Frontend Test Type Safety

## Overview

Eliminate all 209 TypeScript compilation errors across 41 frontend test files by applying targeted fixes in three phases: configuration layer (tsconfig + type declarations), shared utilities layer (mockHelpers.ts), and test file migration (grouped by error category). Each phase ends with a `tsc --noEmit` verification to confirm error count reduction.

## Tasks

- [x] 1. Configuration layer — tsconfig and type declarations
  - [x] 1.1 Add `"vitest"` to tsconfig.json types array
    - Open `frontend/tsconfig.json`
    - Add `"vitest"` to the `compilerOptions.types` array alongside existing `"vitest/globals"` and `"node"`
    - Result: `"types": ["vitest/globals", "vitest", "node"]`
    - Run `tsc --noEmit` from `frontend/` and record new error count (expect ~60 fewer errors)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.2 Create PlotlyChart type declaration file
    - Create `frontend/src/types/plotly-dist-min.d.ts`
    - Declare module `"plotly.js-dist-min"` re-exporting types from `plotly.js`
    - Verify `PlotlyChart.tsx` compiles without errors
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 2. Shared utilities layer — mockHelpers.ts
  - [x] 2.1 Create the Response mock factory module
    - Create `frontend/src/test-utils/mockHelpers.ts`
    - Implement `MockResponseOptions` interface with all optional fields
    - Implement `createMockResponse()` function with full `Response` interface compliance
    - Include JSDoc comments with usage examples on all exports
    - Verify the file compiles with `tsc --noEmit`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 8.1, 8.2_

  - [x] 2.2 Write property tests for createMockResponse — Property 1: Response factory completeness
    - Create `frontend/src/test-utils/__tests__/mockHelpers.property.test.ts`
    - **Property 1: Response factory completeness**
    - Generate random `MockResponseOptions` (status 100–599, random ok, random JSON body via `fc.jsonValue()`, random headers)
    - Assert all required Response properties are defined and all methods are callable functions
    - Minimum 100 iterations
    - **Validates: Requirements 3.1, 3.3, 3.4**

  - [x] 2.3 Write property test — Property 2: Response factory json round-trip
    - **Property 2: Response factory json round-trip**
    - Generate random JSON-serializable values via `fc.jsonValue()`
    - Pass as `body` option, call `.json()`, assert deep equality with input
    - Minimum 100 iterations
    - **Validates: Requirements 3.1, 3.5**

  - [x] 2.4 Write property test — Property 3: Response factory defaults preserve override
    - **Property 3: Response factory defaults preserve override**
    - Generate random subsets of `MockResponseOptions` fields
    - Assert provided fields match input values, omitted fields match documented defaults
    - Assert returned object always satisfies Response interface
    - Minimum 100 iterations
    - **Validates: Requirements 3.3, 3.6**

  - [x] 2.5 Write unit tests for createMockResponse
    - Create `frontend/src/test-utils/__tests__/mockHelpers.test.ts`
    - Test default response (no args): `ok: true`, `status: 200`, `statusText: "OK"`
    - Test error response: `ok: false`, `status: 404`
    - Test custom headers
    - Test `textBody` maps to `.text()` return value
    - Test `clone()` returns distinct object with same properties
    - _Requirements: 3.1, 3.3, 3.4_

- [x] 3. Checkpoint — Verify configuration and utilities
  - Run `tsc --noEmit` from `frontend/` and confirm error count is reduced from 209
  - Run `vitest --run` and confirm all 1782+ tests still pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Test file migration — vi.mocked() pattern (Category: MockedFunction casts)
  - [x] 4.1 Migrate auth-related test files to vi.mocked()
    - Find all test files using `as vi.MockedFunction<typeof fn>` in auth/amplify-related tests
    - Replace each cast with `vi.mocked(fn)` — either inline or as a const declaration
    - Remove unused `vi.MockedFunction` type imports if any
    - Run `tsc --noEmit` to verify errors reduced
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 4.2 Migrate services test files to vi.mocked()
    - Find all test files in `src/services/` using `as vi.MockedFunction<typeof fn>`
    - Replace each cast with `vi.mocked(fn)`
    - Run `tsc --noEmit` to verify errors reduced
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 4.3 Migrate remaining test files to vi.mocked()
    - Find all remaining test files using `as vi.MockedFunction<typeof fn>`
    - Replace each cast with `vi.mocked(fn)`
    - Run grep to confirm zero instances of `as vi.MockedFunction<typeof` remain
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 5. Test file migration — Response mock factory (Category: Partial Response objects)
  - [x] 5.1 Migrate services test files to createMockResponse()
    - Find test files in `src/services/` that create partial `Response` objects or use `as Response` casts
    - Add import: `import { createMockResponse } from '@/test-utils/mockHelpers'`
    - Replace inline `{ ok: true, json: async () => ... } as Response` with `createMockResponse({ body: ... })`
    - Run `tsc --noEmit` to verify errors reduced
    - _Requirements: 3.1, 3.2, 3.5_

  - [x] 5.2 Migrate hooks and components test files to createMockResponse()
    - Find test files in `src/hooks/` and `src/components/` with partial Response mocks
    - Replace with `createMockResponse()` calls
    - Run `tsc --noEmit` to verify errors reduced
    - _Requirements: 3.1, 3.2, 3.5_

  - [x] 5.3 Migrate remaining test files to createMockResponse()
    - Find all remaining test files with partial Response objects or `as Response` casts
    - Replace with `createMockResponse()` calls
    - Run grep to confirm zero instances of `as Response` or `as unknown as Response` for fetch mocks remain
    - _Requirements: 3.1, 3.2, 3.5_

- [x] 6. Checkpoint — Verify mock migrations
  - Run `tsc --noEmit` from `frontend/` and confirm significant error reduction
  - Run `vitest --run` and confirm all 1782+ tests still pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Test file migration — mockImplementation and null guards
  - [x] 7.1 Fix mockImplementation() zero-argument calls
    - Find all test files calling `.mockImplementation()` with zero arguments
    - Add explicit `() => {}` argument to each call
    - Typically `vi.spyOn(console, 'error').mockImplementation()` → `vi.spyOn(console, 'error').mockImplementation(() => {})`
    - Run grep to confirm zero instances of `.mockImplementation()` with no arguments remain
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 7.2 Add null guards for strict-null property access
    - Find all test files with `possibly undefined` errors on `.mock.calls` access
    - Add non-null assertions (`!`) to array element access: `calls[0]!`, `call[1]!`
    - Use consistent `!` pattern within each file
    - Run `tsc --noEmit` to verify zero `possibly undefined` errors remain
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 8. Final verification — Zero errors gate
  - [x] 8.1 Verify tsc --noEmit reports zero errors
    - Run `tsc --noEmit` from `frontend/` directory
    - Confirm zero errors across all files
    - _Requirements: 7.1_

  - [x] 8.2 Verify all tests still pass
    - Run `vitest --run` from `frontend/` directory
    - Confirm all 1782+ tests pass with zero failures
    - _Requirements: 7.2_

  - [x] 8.3 Verify build succeeds
    - Run `tsc -b && vite build` from `frontend/` directory
    - Confirm build completes without errors
    - _Requirements: 7.3_

  - [x] 8.4 Verify no pattern regressions
    - Grep for `as vi.MockedFunction<typeof` — expect zero matches
    - Grep for `.mockImplementation()` with no arguments — expect zero matches
    - Confirm `createMockResponse` is importable via `@/test-utils/mockHelpers`
    - _Requirements: 2.4, 4.1, 8.1, 8.3, 8.4_

- [x] 9. Final checkpoint — All gates pass
  - Ensure all tests pass, ask the user if questions arise.
  - Update relevant documentation in .kiro\specs\Common\Frameworks\test-maintenance-framework\frontend\vitest-guide.md

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each phase
- Property tests validate the `createMockResponse()` factory's correctness properties
- All changes are type-level only — zero runtime behavior changes
- Run `tsc --noEmit` after each phase to track error count reduction: 209 → ~149 (after Phase 1) → ~149 (Phase 2 adds no fixes to existing files) → ~0 (after Phases 4–7)
