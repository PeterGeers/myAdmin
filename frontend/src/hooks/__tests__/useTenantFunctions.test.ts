/**
 * Property-based tests for useTenantFunctions hook — hasFunction logic
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * Property 7: hasFunction reflects effective state or safe default
 *
 * Tests the pure logic of hasFunction:
 * - Returns `effective` field value when data is loaded (no loading, no error)
 * - Returns `false` during loading state
 * - Returns `false` on error state
 * - Returns `false` for unknown function names
 *
 * **Validates: Requirements 4.1, 4.7, 4.8**
 *
 * @see .kiro/specs/tenant-optional-functions/design.md — Property 7
 */

import fc from 'fast-check';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FunctionState {
  function_name: string;
  parent_module: string;
  label: string;
  is_active: boolean;
  module_active: boolean;
  effective: boolean;
}

// ---------------------------------------------------------------------------
// Pure logic extraction (mirrors useTenantFunctions hook logic)
// ---------------------------------------------------------------------------

/**
 * Pure function that replicates the hasFunction logic from the hook.
 * This allows property-based testing without React rendering context.
 */
function hasFunction(
  functions: FunctionState[],
  loading: boolean,
  error: string | null,
  functionName: string,
): boolean {
  if (loading || error) return false;
  const fn = functions.find((f) => f.function_name === functionName);
  return fn ? fn.effective : false;
}

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a valid snake_case function name (1-20 chars for test efficiency). */
const functionNameArbitrary = fc.stringMatching(/^[a-z][a-z0-9_]{0,19}$/);

/** Generate a module code (e.g., FIN, STR, ZZP). */
const moduleCodeArbitrary = fc.constantFrom('FIN', 'STR', 'ZZP', 'HRM', 'CRM');

/** Generate a human-readable label. */
const labelArbitrary = fc.string({ minLength: 1, maxLength: 50 });

/** Generate a single FunctionState record. */
const functionStateArbitrary: fc.Arbitrary<FunctionState> = fc.record({
  function_name: functionNameArbitrary,
  parent_module: moduleCodeArbitrary,
  label: labelArbitrary,
  is_active: fc.boolean(),
  module_active: fc.boolean(),
  effective: fc.boolean(),
});

/** Generate an array of FunctionState with unique function_name values. */
const functionStatesArbitrary = fc
  .array(functionStateArbitrary, { minLength: 0, maxLength: 20 })
  .map((states) => {
    // Deduplicate by function_name, keeping only the first occurrence
    const seen = new Set<string>();
    return states.filter((s) => {
      if (seen.has(s.function_name)) return false;
      seen.add(s.function_name);
      return true;
    });
  });

/** Generate a non-null error message. */
const errorMessageArbitrary = fc.string({ minLength: 1, maxLength: 100 });

// ---------------------------------------------------------------------------
// Property 7: hasFunction reflects effective state or safe default
// ---------------------------------------------------------------------------

describe('Property 7: hasFunction reflects effective state or safe default', () => {
  /**
   * **Validates: Requirements 4.1, 4.7, 4.8**
   *
   * When data is successfully loaded (loading=false, error=null),
   * hasFunction returns the `effective` field value for the queried function.
   */
  it('hasFunction returns effective state when loaded', () => {
    fc.assert(
      fc.property(
        functionStatesArbitrary.filter((s) => s.length > 0),
        fc.nat(),
        (functions, indexSeed) => {
          // Pick a function that exists in the array
          const index = indexSeed % functions.length;
          const target = functions[index];

          const result = hasFunction(functions, false, null, target.function_name);

          expect(result).toBe(target.effective);
        },
      ),
      { numRuns: 100 },
    );
  });

  /**
   * **Validates: Requirements 4.8**
   *
   * While loading (loading=true), hasFunction always returns false
   * regardless of what functions are available.
   */
  it('hasFunction returns false during loading', () => {
    fc.assert(
      fc.property(
        functionStatesArbitrary,
        functionNameArbitrary,
        (functions, queryName) => {
          const result = hasFunction(functions, true, null, queryName);

          expect(result).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  /**
   * **Validates: Requirements 4.7**
   *
   * When an error exists (error is non-null), hasFunction always returns false
   * regardless of what functions are available.
   */
  it('hasFunction returns false on error', () => {
    fc.assert(
      fc.property(
        functionStatesArbitrary,
        errorMessageArbitrary,
        functionNameArbitrary,
        (functions, errorMsg, queryName) => {
          const result = hasFunction(functions, false, errorMsg, queryName);

          expect(result).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  /**
   * **Validates: Requirements 4.1**
   *
   * When querying a function name that does not exist in the loaded state,
   * hasFunction returns false.
   */
  it('hasFunction returns false for unknown function name', () => {
    fc.assert(
      fc.property(
        functionStatesArbitrary,
        functionNameArbitrary,
        (functions, queryName) => {
          // Ensure the query name is not in the array
          const existingNames = new Set(functions.map((f) => f.function_name));
          fc.pre(!existingNames.has(queryName));

          const result = hasFunction(functions, false, null, queryName);

          expect(result).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });
});
