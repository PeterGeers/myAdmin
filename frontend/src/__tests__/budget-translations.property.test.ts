/**
 * Property-based tests for budget translation file parity and structure.
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * Validates: Requirements 2.3, 2.4, 2.6
 */

import fc from 'fast-check';
import enBudget from '../locales/en/budget.json';
import nlBudget from '../locales/nl/budget.json';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Allowed top-level categories in budget translation files. */
const ALLOWED_CATEGORIES = ['titles', 'columns', 'buttons', 'labels', 'messages'] as const;

/** Extract all key paths from a flat or nested JSON object (max 2 levels deep). */
function getAllKeyPaths(obj: Record<string, unknown>): string[] {
  const paths: string[] = [];
  for (const category of Object.keys(obj)) {
    const value = obj[category];
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const key of Object.keys(value as Record<string, unknown>)) {
        paths.push(`${category}.${key}`);
      }
    }
  }
  return paths;
}

/** Get the value at a dot-separated path in a nested object. */
function getValueAtPath(obj: Record<string, unknown>, path: string): unknown {
  const [category, key] = path.split('.');
  const categoryObj = obj[category];
  if (categoryObj && typeof categoryObj === 'object' && !Array.isArray(categoryObj)) {
    return (categoryObj as Record<string, unknown>)[key];
  }
  return undefined;
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

const enKeyPaths = getAllKeyPaths(enBudget as Record<string, unknown>);
const nlKeyPaths = getAllKeyPaths(nlBudget as Record<string, unknown>);
const allKeyPaths = [...new Set([...enKeyPaths, ...nlKeyPaths])];

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a random key path from the EN budget file. */
const enKeyPathArbitrary = fc.constantFrom(...enKeyPaths);

/** Generate a random key path from all budget translation key paths. */
const anyKeyPathArbitrary = fc.constantFrom(...allKeyPaths);

// ---------------------------------------------------------------------------
// Property 1: Translation key completeness (EN/NL parity)
// ---------------------------------------------------------------------------

describe('Property 1: Translation key completeness (EN/NL parity)', () => {
  /**
   * **Validates: Requirements 2.3, 2.4**
   *
   * For any key present in EN budget.json, the NL budget.json SHALL also
   * contain a corresponding non-empty string value at the same path.
   */
  it('every EN key has a corresponding non-empty NL translation', () => {
    fc.assert(
      fc.property(enKeyPathArbitrary, (keyPath) => {
        const nlValue = getValueAtPath(nlBudget as Record<string, unknown>, keyPath);

        // NL must have the key
        expect(nlValue).toBeDefined();

        // NL value must be a string
        expect(typeof nlValue).toBe('string');

        // NL value must be non-empty
        expect((nlValue as string).trim().length).toBeGreaterThan(0);
      }),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: Translation key structure conformance
// ---------------------------------------------------------------------------

describe('Property 2: Translation key structure conformance', () => {
  /**
   * **Validates: Requirements 2.6**
   *
   * For any key path in the budget translation files, the top-level category
   * SHALL be one of `titles`, `columns`, `buttons`, `labels`, or `messages`,
   * and the key path SHALL have exactly two segments (`{category}.{key}`).
   */
  it('all key paths have exactly two segments with a valid category', () => {
    fc.assert(
      fc.property(anyKeyPathArbitrary, (keyPath) => {
        const segments = keyPath.split('.');

        // Key path must have exactly 2 segments
        expect(segments).toHaveLength(2);

        // Top-level category must be one of the allowed values
        const [category] = segments;
        expect(ALLOWED_CATEGORIES).toContain(category);
      }),
      { numRuns: 100 },
    );
  });
});
