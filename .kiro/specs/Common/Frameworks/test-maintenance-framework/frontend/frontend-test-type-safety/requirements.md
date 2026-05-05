# Requirements Document

## Introduction

Systematically resolve all 209 TypeScript compilation errors across 41 frontend test files so that `tsc --noEmit` passes with zero errors. All tests currently pass at runtime (1782 passed via `vitest --run`); only the static type checker reports issues. The errors fall into five categories: `vi.MockedFunction` namespace resolution, partial `Response` mock objects, missing mock method types, `mockImplementation()` signature changes in Vitest 4.x, and strict-null property access. The fix strategy uses centralized utilities, consistent patterns, and Vitest-idiomatic APIs to prevent regression.

## Glossary

- **Type_Checker**: The TypeScript compiler invoked via `tsc --noEmit` that performs static type analysis without emitting output files
- **Test_File**: Any `.test.ts`, `.test.tsx`, `.spec.ts`, or `.spec.tsx` file under `frontend/src/` or `frontend/tests/`
- **Mock_Utility_Module**: A shared TypeScript module (e.g. `frontend/src/test-utils/mockHelpers.ts`) that exports reusable, fully-typed mock factories and casting helpers for use across test files
- **Response_Mock_Factory**: A function within the Mock_Utility_Module that produces complete `Response`-compatible objects with all required properties (`ok`, `status`, `statusText`, `headers`, `redirected`, `type`, `url`, `json`, `text`, `blob`, `arrayBuffer`, `formData`, `bytes`, `clone`, `body`, `bodyUsed`)
- **Vitest_Type_Reference**: A TypeScript triple-slash directive (`/// <reference types="vitest" />`) or `tsconfig.json` `types` entry that makes the `vi` namespace and its type utilities available to the Type_Checker
- **vi_mocked_Helper**: The `vi.mocked()` function provided by Vitest that wraps an imported function and returns a properly-typed mock instance with `mockResolvedValue`, `mockImplementation`, and other mock methods
- **Strict_Null_Guard**: A runtime assertion or optional-chaining expression that satisfies TypeScript's `strictNullChecks` when accessing properties that may be `undefined`

## Requirements

### Requirement 1: Vitest Type Reference Configuration

**User Story:** As a developer, I want `tsc --noEmit` to recognize the `vi` namespace and all Vitest type utilities in every test file, so that I do not see `vi.MockedFunction` namespace errors during type checking.

#### Acceptance Criteria

1. THE Type_Checker SHALL resolve the `vi` namespace and all its type exports (including `MockedFunction`, `MockInstance`, `Mock`) in every Test_File without errors
2. WHEN a Test_File imports from `vitest`, THE Type_Checker SHALL recognize all exported type utilities without requiring per-file triple-slash directives
3. THE Vitest_Type_Reference SHALL be configured in exactly one central location (`tsconfig.json` `types` array or a single shared declaration file) to avoid duplication across Test_Files
4. WHEN a new Test_File is created, THE Type_Checker SHALL automatically resolve Vitest types without any additional per-file configuration

### Requirement 2: Replace vi.MockedFunction Type Casts with vi.mocked() Helper

**User Story:** As a developer, I want all mock function type casts to use the Vitest-idiomatic `vi.mocked()` helper instead of `as vi.MockedFunction<typeof fn>` casts, so that mock methods are correctly typed and the codebase follows a single consistent pattern.

#### Acceptance Criteria

1. WHEN a Test_File needs to access mock methods on an imported function, THE Test_File SHALL use `vi.mocked(fn)` instead of casting with `as vi.MockedFunction<typeof fn>`
2. THE Type_Checker SHALL recognize `mockResolvedValue`, `mockRejectedValue`, `mockImplementation`, `mockReturnValue`, and all other mock methods on the return value of `vi.mocked(fn)` without errors
3. WHEN `vi.mocked()` is applied to a function that was set up via `vi.mock()`, THE Type_Checker SHALL infer the correct parameter and return types from the original function signature
4. THE codebase SHALL contain zero remaining instances of `as vi.MockedFunction<typeof` after all Test_Files are updated

### Requirement 3: Typed Response Mock Factory

**User Story:** As a developer, I want a centralized, fully-typed factory for creating mock `Response` objects, so that test files do not trigger type errors from missing `Response` properties.

#### Acceptance Criteria

1. THE Mock_Utility_Module SHALL export a Response_Mock_Factory function that accepts partial response data (`ok`, `status`, `json` body, `headers`) and returns an object satisfying the full `Response` interface
2. WHEN a Test_File creates a mock fetch response, THE Test_File SHALL use the Response_Mock_Factory instead of inline partial object literals
3. THE Response_Mock_Factory SHALL provide sensible defaults for all required `Response` properties: `ok` (true), `status` (200), `statusText` ("OK"), `headers` (empty Headers), `redirected` (false), `type` ("basic"), `url` (""), `body` (null), `bodyUsed` (false)
4. THE Response_Mock_Factory SHALL provide stub implementations for all required `Response` methods: `json()`, `text()`, `blob()`, `arrayBuffer()`, `formData()`, `bytes()`, `clone()`
5. THE Type_Checker SHALL accept the Response_Mock_Factory return value anywhere a `Response` type is expected without requiring `as unknown as Response` casts
6. IF a Test_File passes invalid or mistyped properties to the Response_Mock_Factory, THEN THE Type_Checker SHALL report a compile-time error

### Requirement 4: Fix mockImplementation() Signature Compatibility

**User Story:** As a developer, I want all `mockImplementation()` calls to be compatible with Vitest 4.x type signatures, so that zero-argument calls and no-op mocks do not produce type errors.

#### Acceptance Criteria

1. WHEN a Test_File calls `mockImplementation()` with zero arguments to create a no-op mock, THE Test_File SHALL pass an explicit no-op function (e.g. `() => {}` or `() => undefined`) as the argument
2. THE Type_Checker SHALL accept all `mockImplementation()` calls across the codebase without argument-count errors
3. WHEN `mockImplementation()` is called with a function argument, THE Type_Checker SHALL verify that the function signature matches the original mocked function's parameter and return types

### Requirement 5: Strict Null Safety in Test Assertions

**User Story:** As a developer, I want all test assertions that access potentially undefined properties (like `fetchCall[1].headers`) to use proper null guards, so that `strictNullChecks` does not flag them as errors.

#### Acceptance Criteria

1. WHEN a Test_File accesses an array element or object property that the Type_Checker considers possibly `undefined`, THE Test_File SHALL use a Strict_Null_Guard (non-null assertion `!`, optional chaining `?.`, or an explicit `expect(...).toBeDefined()` assertion preceding the access)
2. THE Type_Checker SHALL report zero `possibly undefined` errors across all Test_Files
3. THE Strict_Null_Guard pattern used SHALL be consistent within each Test_File (prefer one style per file rather than mixing approaches)

### Requirement 6: PlotlyChart Type Declaration

**User Story:** As a developer, I want the PlotlyChart component to compile without type errors, so that the single non-test type error is also resolved.

#### Acceptance Criteria

1. WHEN `plotly.js-dist-min` is imported in `PlotlyChart.tsx`, THE Type_Checker SHALL resolve the module type without errors
2. IF the `plotly.js-dist-min` package lacks a type declaration, THEN THE codebase SHALL include a local declaration file (e.g. `src/types/plotly.d.ts`) that declares the module with the correct type
3. THE Type_Checker SHALL accept the `createPlotlyComponent(Plotly)` call and the resulting `Plot` component without errors

### Requirement 7: Zero TypeScript Errors Gate

**User Story:** As a developer, I want `tsc --noEmit` to report zero errors across the entire frontend codebase, so that type safety is fully enforced and regressions are caught early.

#### Acceptance Criteria

1. WHEN `tsc --noEmit` is run from the `frontend/` directory, THE Type_Checker SHALL report zero errors across all 41 previously-affected Test_Files and all other source files
2. WHEN `vitest --run` is executed, THE test suite SHALL continue to pass all 1782+ tests with zero failures (no behavioral regressions)
3. THE existing `build` script (`tsc -b && vite build`) SHALL complete successfully without type errors

### Requirement 8: Prevent Regression via Consistent Patterns

**User Story:** As a developer, I want documented patterns and shared utilities for test mocking, so that new test files follow type-safe conventions and do not reintroduce the same categories of errors.

#### Acceptance Criteria

1. THE Mock_Utility_Module SHALL be importable via the `@/` path alias (e.g. `@/test-utils/mockHelpers`)
2. THE Mock_Utility_Module SHALL include JSDoc comments on each exported function describing its purpose, parameters, and usage example
3. WHEN a developer creates a new Test_File that mocks `fetch` responses, THE Response_Mock_Factory SHALL be the documented and recommended approach
4. WHEN a developer creates a new Test_File that needs typed mock functions, THE `vi.mocked()` helper SHALL be the documented and recommended approach over type casting
