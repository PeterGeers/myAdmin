# Bugfix Requirements Document

## Introduction

After upgrading TypeScript from ~5.6/5.7 to 5.9.3, `tsc --noEmit` reports 153 type errors across 28 frontend files. The application works at runtime (Vite uses esbuild which skips type-checking) and CI passes because `build:ci` only runs `vite build`. However, the standard `build` script (`tsc -b && vite build`) fails, and type safety is degraded. The errors stem from TypeScript 5.9's stricter type narrowing, inference, and union type handling.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN running `tsc --noEmit` with TypeScript 5.9.3 on the frontend codebase THEN the system reports 153 type errors across 28 files and exits with a non-zero status code

1.2 WHEN test files access service response `.data` properties on union types (e.g., `r.data.total_outstanding`) THEN the compiler emits TS18048 ('x' is possibly 'undefined') because TS 5.9 applies stricter nullability checks on union types

1.3 WHEN test files access specific properties on response data typed as `Record<string, unknown> | Record<string, unknown>[]` THEN the compiler emits TS2339 (Property does not exist on type) because TS 5.9 no longer auto-narrows these union types

1.4 WHEN mock functions (Vitest `Mock<Procedure>`) are passed to components expecting specific signatures (e.g., Chakra `useToast`) or when `string | number` values are passed to parameters typed as `number` THEN the compiler emits TS2345 (type not assignable) due to stricter inference

1.5 WHEN object literals in test files or components include properties not defined on the target interface (e.g., `pattern_filled` on `Transaction`) THEN the compiler emits TS2353 (unknown properties in object literals) because the interfaces were not updated to match actual usage

1.6 WHEN `@ts-expect-error` directives exist for issues that TypeScript 5.9 has resolved THEN the compiler emits TS2578 (Unused '@ts-expect-error' directive) because the underlying error no longer occurs

1.7 WHEN object literals in tests are missing required properties of their target type THEN the compiler emits TS2739 (missing properties) due to stricter completeness checking

### Expected Behavior (Correct)

2.1 WHEN running `tsc --noEmit` with TypeScript 5.9.3 on the frontend codebase THEN the system SHALL report zero type errors and exit with status code 0

2.2 WHEN test files access service response `.data` properties THEN the system SHALL use proper null checks or type assertions to satisfy the compiler (e.g., guard with `if (r.data)` or use non-null assertion where response is guaranteed)

2.3 WHEN test files access specific properties on response data typed as a union THEN the system SHALL use type narrowing (type guards, `as` assertions, or refined type definitions) so the compiler can verify property access is valid

2.4 WHEN mock functions are passed to components expecting specific signatures THEN the system SHALL cast mocks to the expected type (e.g., `vi.fn() as unknown as UseToastReturn`) or use properly typed mock factories; WHEN `string | number` is passed where `number` is expected THEN the system SHALL use explicit `Number()` conversion or narrow the type

2.5 WHEN object literals include properties that exist at runtime but are not in the interface THEN the system SHALL extend the TypeScript interface to include those properties with correct types

2.6 WHEN `@ts-expect-error` directives suppress errors that no longer exist in TS 5.9 THEN the system SHALL remove those directives

2.7 WHEN object literals in tests represent domain types THEN the system SHALL include all required properties (using realistic defaults or partial type helpers like `Partial<T>` where appropriate)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the frontend application is built with `vite build` THEN the system SHALL CONTINUE TO produce a working production bundle without errors

3.2 WHEN existing unit and integration tests are run with `vitest run` THEN the system SHALL CONTINUE TO pass with the same outcomes as before the type fixes

3.3 WHEN runtime behavior of components is exercised (form submissions, API calls, data rendering) THEN the system SHALL CONTINUE TO function identically since only type annotations are being corrected

3.4 WHEN non-affected TypeScript files (files not in the 28-file error list) are type-checked THEN the system SHALL CONTINUE TO compile without errors

3.5 WHEN the `strict` mode TypeScript configuration is used THEN the system SHALL CONTINUE TO enforce all strict checks without needing to relax any compiler options

3.6 WHEN CI runs `build:ci` (vite build only) THEN the system SHALL CONTINUE TO pass, and additionally the full `build` script (`tsc -b && vite build`) SHALL now also pass
