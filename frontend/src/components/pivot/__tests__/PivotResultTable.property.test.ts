/**
 * Property-based tests for Dynamic Pivot Views frontend utilities.
 *
 * Validates correctness properties 9–12 from the design document:
 *   Property 9:  Number format toggle correctness
 *   Property 10: CSV export structure
 *   Property 11: Hierarchical tree nesting
 *   Property 12: Parent row aggregates equal rollup of children
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * @see .kiro/specs/dynamic-pivot-views/design.md — Properties 9, 10, 11, 12
 * Validates: Requirements 3.6, 3.7, 7.2, 7.3, 8.2, 8.3
 */

import fc from 'fast-check';
import { formatPivotNumber } from '../../../utils/pivotFormatting';
import { generateCsv } from '../../../utils/csvExport';
import { buildHierarchicalTree } from '../../../utils/pivotTreeBuilder';
import type { PivotTreeNode } from '../../../utils/pivotTreeBuilder';
import type { NumberFormat } from '../../../types/pivot';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a number format mode. */
const numberFormatArbitrary: fc.Arbitrary<NumberFormat> = fc.constantFrom(
  'decimal' as const,
  'whole' as const,
  'k-notation' as const,
);

/** Generate a locale string. */
const localeArbitrary = fc.constantFrom('nl-NL', 'en-US', 'de-DE');

/**
 * Generate a finite numeric value across a wide range.
 * Excludes NaN and Infinity to test meaningful formatting.
 */
const finiteNumberArbitrary = fc.double({
  min: -1e9,
  max: 1e9,
  noNaN: true,
  noDefaultInfinity: true,
});

/** Generate a short alpha column header. */
const headerArbitrary = fc.stringMatching(/^[A-Za-z_][A-Za-z0-9_]{0,15}$/);

/**
 * Generate a CSV cell value: string, number, null, or undefined.
 * Includes edge cases like commas, quotes, and newlines in strings.
 */
const cellValueArbitrary = fc.oneof(
  { weight: 3, arbitrary: fc.double({ min: -1e6, max: 1e6, noNaN: true }) },
  { weight: 3, arbitrary: fc.string({ minLength: 0, maxLength: 20 }) },
  { weight: 1, arbitrary: fc.constant(null) },
  { weight: 1, arbitrary: fc.constant(undefined) },
);

/** Generate a group column name. */
const groupColumnArbitrary = fc.stringMatching(/^[a-z]{2,8}$/);

/** Generate an aggregate column name prefixed with SUM_ or COUNT_. */
const aggColumnArbitrary = fc.constantFrom(
  'SUM_Amount',
  'COUNT_rows',
  'AVG_price',
  'MIN_value',
  'MAX_total',
);

/**
 * Generate a flat pivot result row with the given group and aggregate columns.
 * Group values are short strings; aggregate values are finite numbers.
 */
function rowArbitrary(
  groupColumns: string[],
  aggregateColumns: string[],
): fc.Arbitrary<Record<string, any>> {
  const entries: Record<string, fc.Arbitrary<any>> = {};
  for (const col of groupColumns) {
    entries[col] = fc.constantFrom('Alpha', 'Beta', 'Gamma', 'Delta');
  }
  for (const col of aggregateColumns) {
    entries[col] = fc.double({ min: 0, max: 100000, noNaN: true, noDefaultInfinity: true });
  }
  return fc.record(entries);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Detect the decimal separator for a given locale by formatting a known value.
 * For nl-NL the decimal separator is ',', for en-US it is '.'.
 */
function getDecimalSeparator(locale: string): string {
  const parts = new Intl.NumberFormat(locale).formatToParts(1.1);
  const decPart = parts.find((p) => p.type === 'decimal');
  return decPart?.value ?? '.';
}

/**
 * Count decimal places in a formatted number string for a given locale.
 * Uses the locale's actual decimal separator to avoid confusing
 * thousand separators with decimal marks.
 */
function countDecimalPlaces(formatted: string, locale: string): number {
  const decSep = getDecimalSeparator(locale);
  const lastIdx = formatted.lastIndexOf(decSep);
  if (lastIdx === -1) return 0;

  // Count digits after the decimal separator (ignore any trailing non-digit chars like suffixes)
  const afterDecimal = formatted.slice(lastIdx + 1);
  const digitMatch = afterDecimal.match(/^\d+/);
  return digitMatch ? digitMatch[0].length : 0;
}

/** Check if a string ends with a k-notation suffix. */
function hasAbbreviationSuffix(formatted: string): boolean {
  return formatted.endsWith('K') || formatted.endsWith('M');
}

/** Recursively collect all nodes from a tree. */
function collectAllNodes(nodes: PivotTreeNode[]): PivotTreeNode[] {
  const result: PivotTreeNode[] = [];
  for (const node of nodes) {
    result.push(node);
    if (node.children.length > 0) {
      result.push(...collectAllNodes(node.children));
    }
  }
  return result;
}

/** Parse a CSV string into rows of fields. */
function parseCsvRows(csv: string, lineSeparator = '\n'): string[][] {
  const lines = csv.split(lineSeparator);
  return lines.map((line) => parseCsvLine(line));
}

/**
 * Simple CSV line parser that handles quoted fields.
 * Handles RFC 4180 quoting: fields wrapped in double quotes,
 * with internal double quotes escaped as "".
 */
function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let current = '';
  let inQuotes = false;
  let i = 0;

  while (i < line.length) {
    const char = line[i];

    if (inQuotes) {
      if (char === '"') {
        if (i + 1 < line.length && line[i + 1] === '"') {
          // Escaped double quote
          current += '"';
          i += 2;
        } else {
          // End of quoted field
          inQuotes = false;
          i++;
        }
      } else {
        current += char;
        i++;
      }
    } else {
      if (char === '"') {
        inQuotes = true;
        i++;
      } else if (char === ',') {
        fields.push(current);
        current = '';
        i++;
      } else {
        current += char;
        i++;
      }
    }
  }

  fields.push(current);
  return fields;
}

// ---------------------------------------------------------------------------
// Property 9: Number format toggle correctness
// ---------------------------------------------------------------------------

describe('Property 9: Number format toggle correctness', () => {
  /**
   * Validates: Requirements 3.6, 3.7
   *
   * For any numeric value and display mode, formatting produces correct output:
   * - decimal: 2 decimal places
   * - whole: 0 decimal places
   * - k-notation: abbreviated with K/M suffix for values >= 1000
   */
  it('decimal mode always produces exactly 2 decimal places', () => {
    fc.assert(
      fc.property(finiteNumberArbitrary, localeArbitrary, (value, locale) => {
        const result = formatPivotNumber(value, 'decimal', locale);

        expect(result).not.toBe('');
        expect(countDecimalPlaces(result, locale)).toBe(2);
      }),
      { numRuns: 100 },
    );
  });

  it('whole mode always produces 0 decimal places', () => {
    fc.assert(
      fc.property(finiteNumberArbitrary, localeArbitrary, (value, locale) => {
        const result = formatPivotNumber(value, 'whole', locale);

        expect(result).not.toBe('');
        // Whole mode should have no decimal separator in the final position
        expect(countDecimalPlaces(result, locale)).toBe(0);
      }),
      { numRuns: 100 },
    );
  });

  it('k-notation uses K suffix for values >= 1000 and M suffix for values >= 1,000,000', () => {
    fc.assert(
      fc.property(finiteNumberArbitrary, localeArbitrary, (value, locale) => {
        const result = formatPivotNumber(value, 'k-notation', locale);
        const absValue = Math.abs(value);

        expect(result).not.toBe('');

        if (absValue >= 1_000_000) {
          expect(result).toContain('M');
        } else if (absValue >= 1_000) {
          expect(result).toContain('K');
        } else {
          // Below 1000: no suffix
          expect(hasAbbreviationSuffix(result)).toBe(false);
        }
      }),
      { numRuns: 100 },
    );
  });

  it('null, undefined, and NaN return empty string for all formats', () => {
    fc.assert(
      fc.property(numberFormatArbitrary, localeArbitrary, (format, locale) => {
        expect(formatPivotNumber(null, format, locale)).toBe('');
        expect(formatPivotNumber(undefined, format, locale)).toBe('');
        expect(formatPivotNumber(NaN, format, locale)).toBe('');
      }),
      { numRuns: 100 },
    );
  });

  it('all three formats produce non-empty output for any finite number', () => {
    fc.assert(
      fc.property(finiteNumberArbitrary, localeArbitrary, (value, locale) => {
        const decimal = formatPivotNumber(value, 'decimal', locale);
        const whole = formatPivotNumber(value, 'whole', locale);
        const kNotation = formatPivotNumber(value, 'k-notation', locale);

        expect(decimal.length).toBeGreaterThan(0);
        expect(whole.length).toBeGreaterThan(0);
        expect(kNotation.length).toBeGreaterThan(0);
      }),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 10: CSV export structure
// ---------------------------------------------------------------------------

describe('Property 10: CSV export structure', () => {
  /**
   * Validates: Requirements 7.2, 7.3
   *
   * For any non-empty result data, the exported CSV has:
   * - A header row matching the column labels
   * - The same number of data rows as the input array
   * - Each row has the same number of fields as the header
   */
  it('CSV has header row + same number of data rows as input', () => {
    fc.assert(
      fc.property(
        fc
          .integer({ min: 1, max: 8 })
          .chain((numCols) =>
            fc.tuple(
              fc.constant(numCols),
              fc.array(headerArbitrary, { minLength: numCols, maxLength: numCols }),
              fc.integer({ min: 1, max: 20 }),
            ),
          )
          .chain(([numCols, headers, numRows]) =>
            fc.tuple(
              fc.constant(headers),
              fc.array(
                fc.array(cellValueArbitrary, { minLength: numCols, maxLength: numCols }),
                { minLength: numRows, maxLength: numRows },
              ),
            ),
          ),
        ([headers, rows]) => {
          const csv = generateCsv(headers, rows);
          const parsedRows = parseCsvRows(csv);

          // First row is headers, rest are data
          expect(parsedRows.length).toBe(rows.length + 1);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('every CSV row has the same number of fields as the header', () => {
    fc.assert(
      fc.property(
        fc
          .integer({ min: 1, max: 8 })
          .chain((numCols) =>
            fc.tuple(
              fc.constant(numCols),
              fc.array(headerArbitrary, { minLength: numCols, maxLength: numCols }),
              fc.integer({ min: 1, max: 15 }),
            ),
          )
          .chain(([numCols, headers, numRows]) =>
            fc.tuple(
              fc.constant(headers),
              fc.array(
                fc.array(cellValueArbitrary, { minLength: numCols, maxLength: numCols }),
                { minLength: numRows, maxLength: numRows },
              ),
            ),
          ),
        ([headers, rows]) => {
          const csv = generateCsv(headers, rows);
          const parsedRows = parseCsvRows(csv);
          const headerFieldCount = parsedRows[0].length;

          expect(headerFieldCount).toBe(headers.length);

          for (let i = 1; i < parsedRows.length; i++) {
            expect(parsedRows[i].length).toBe(headerFieldCount);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('header row matches the provided column labels', () => {
    fc.assert(
      fc.property(
        fc.array(headerArbitrary, { minLength: 1, maxLength: 8 }).chain((headers) =>
          fc.tuple(
            fc.constant(headers),
            fc.array(
              fc.array(cellValueArbitrary, {
                minLength: headers.length,
                maxLength: headers.length,
              }),
              { minLength: 1, maxLength: 10 },
            ),
          ),
        ),
        ([headers, rows]) => {
          const csv = generateCsv(headers, rows);
          const parsedRows = parseCsvRows(csv);
          const parsedHeaders = parsedRows[0];

          for (let i = 0; i < headers.length; i++) {
            expect(parsedHeaders[i]).toBe(headers[i]);
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 11: Hierarchical tree nesting
// ---------------------------------------------------------------------------

describe('Property 11: Hierarchical tree nesting', () => {
  /**
   * Validates: Requirements 8.2
   *
   * For any flat result with 2+ group columns, the tree has:
   * - Top-level nodes keyed by the first group column's distinct values
   * - Each subsequent group column creates a nested child level
   * - Correct depth at each level
   */
  it('top-level nodes correspond to distinct values of the first group column', () => {
    fc.assert(
      fc.property(
        fc
          .array(groupColumnArbitrary, { minLength: 2, maxLength: 4 })
          .filter((cols) => new Set(cols).size === cols.length)
          .chain((groupCols) =>
            fc.tuple(
              fc.constant(groupCols),
              fc.constant(['SUM_Amount'] as string[]),
              fc.array(rowArbitrary(groupCols, ['SUM_Amount']), {
                minLength: 2,
                maxLength: 30,
              }),
            ),
          ),
        ([groupCols, aggCols, rows]) => {
          const tree = buildHierarchicalTree(rows, groupCols, aggCols);

          // Top-level node values should be a subset of distinct values
          // from the first group column
          const firstColValues = new Set(
            rows.map((r) => r[groupCols[0]]).filter((v) => v != null),
          );
          const topLevelValues = new Set(tree.map((n) => n.value));

          for (const val of topLevelValues) {
            expect(firstColValues.has(val as string)).toBe(true);
          }

          // All top-level nodes should reference the first group column
          for (const node of tree) {
            expect(node.groupColumn).toBe(groupCols[0]);
            expect(node.depth).toBe(0);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('child nodes at depth d reference the (d+1)th group column', () => {
    fc.assert(
      fc.property(
        fc
          .array(groupColumnArbitrary, { minLength: 2, maxLength: 4 })
          .filter((cols) => new Set(cols).size === cols.length)
          .chain((groupCols) =>
            fc.tuple(
              fc.constant(groupCols),
              fc.constant(['SUM_Amount'] as string[]),
              fc.array(rowArbitrary(groupCols, ['SUM_Amount']), {
                minLength: 2,
                maxLength: 30,
              }),
            ),
          ),
        ([groupCols, aggCols, rows]) => {
          const tree = buildHierarchicalTree(rows, groupCols, aggCols);
          const allNodes = collectAllNodes(tree);

          for (const node of allNodes) {
            // Each node's groupColumn should match the group column at its depth
            expect(node.groupColumn).toBe(groupCols[node.depth]);

            // Children should be one level deeper
            for (const child of node.children) {
              expect(child.depth).toBe(node.depth + 1);
            }
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('leaf nodes have no children and are at the deepest group level', () => {
    fc.assert(
      fc.property(
        fc
          .array(groupColumnArbitrary, { minLength: 2, maxLength: 4 })
          .filter((cols) => new Set(cols).size === cols.length)
          .chain((groupCols) =>
            fc.tuple(
              fc.constant(groupCols),
              fc.constant(['SUM_Amount'] as string[]),
              fc.array(rowArbitrary(groupCols, ['SUM_Amount']), {
                minLength: 2,
                maxLength: 30,
              }),
            ),
          ),
        ([groupCols, aggCols, rows]) => {
          const tree = buildHierarchicalTree(rows, groupCols, aggCols);
          const allNodes = collectAllNodes(tree);
          const maxDepth = groupCols.length - 1;

          for (const node of allNodes) {
            if (node.children.length === 0) {
              // Leaf nodes should be at the deepest level
              expect(node.depth).toBe(maxDepth);
            }
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 12: Parent row aggregates equal rollup of children
// ---------------------------------------------------------------------------

describe('Property 12: Parent row aggregates equal rollup of children', () => {
  /**
   * Validates: Requirements 8.3
   *
   * For any hierarchical tree, each parent node's aggregate values
   * equal the SUM across its direct children's aggregate values
   * (using SUM as the default aggregation function).
   */
  it('parent SUM aggregates equal sum of children aggregates', () => {
    fc.assert(
      fc.property(
        fc
          .array(groupColumnArbitrary, { minLength: 2, maxLength: 4 })
          .filter((cols) => new Set(cols).size === cols.length)
          .chain((groupCols) => {
            const aggCols = ['SUM_Amount', 'COUNT_rows'];
            return fc.tuple(
              fc.constant(groupCols),
              fc.constant(aggCols),
              fc.array(rowArbitrary(groupCols, aggCols), {
                minLength: 2,
                maxLength: 30,
              }),
            );
          }),
        ([groupCols, aggCols, rows]) => {
          const tree = buildHierarchicalTree(rows, groupCols, aggCols);

          // Recursively verify parent aggregates
          function verifyNode(node: PivotTreeNode): void {
            if (node.children.length === 0) return;

            for (const aggCol of aggCols) {
              const childSum = node.children.reduce((sum, child) => {
                const childVal = child.aggregates[aggCol];
                return sum + (childVal ?? 0);
              }, 0);

              const parentVal = node.aggregates[aggCol];

              // Parent aggregate should equal sum of children
              // Use approximate equality for floating point
              if (parentVal != null) {
                expect(parentVal).toBeCloseTo(childSum, 5);
              }
            }

            // Recurse into children
            for (const child of node.children) {
              verifyNode(child);
            }
          }

          for (const topNode of tree) {
            verifyNode(topNode);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('parent AVG aggregates equal average of children when using AVG function', () => {
    fc.assert(
      fc.property(
        fc
          .array(groupColumnArbitrary, { minLength: 2, maxLength: 3 })
          .filter((cols) => new Set(cols).size === cols.length)
          .chain((groupCols) => {
            const aggCols = ['AVG_price'];
            return fc.tuple(
              fc.constant(groupCols),
              fc.constant(aggCols),
              fc.array(rowArbitrary(groupCols, aggCols), {
                minLength: 2,
                maxLength: 20,
              }),
            );
          }),
        ([groupCols, aggCols, rows]) => {
          const options = {
            aggregateFunctions: { AVG_price: 'AVG' as const },
          };
          const tree = buildHierarchicalTree(rows, groupCols, aggCols, options);

          function verifyAvgNode(node: PivotTreeNode): void {
            if (node.children.length === 0) return;

            for (const aggCol of aggCols) {
              const childValues = node.children
                .map((c) => c.aggregates[aggCol])
                .filter((v): v is number => v != null);

              if (childValues.length > 0) {
                const expectedAvg =
                  childValues.reduce((a, b) => a + b, 0) / childValues.length;
                const parentVal = node.aggregates[aggCol];

                if (parentVal != null) {
                  expect(parentVal).toBeCloseTo(expectedAvg, 5);
                }
              }
            }

            for (const child of node.children) {
              verifyAvgNode(child);
            }
          }

          for (const topNode of tree) {
            verifyAvgNode(topNode);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('parent MIN/MAX aggregates equal min/max of children', () => {
    fc.assert(
      fc.property(
        fc
          .array(groupColumnArbitrary, { minLength: 2, maxLength: 3 })
          .filter((cols) => new Set(cols).size === cols.length)
          .chain((groupCols) => {
            const aggCols = ['MIN_value', 'MAX_total'];
            return fc.tuple(
              fc.constant(groupCols),
              fc.constant(aggCols),
              fc.array(rowArbitrary(groupCols, aggCols), {
                minLength: 2,
                maxLength: 20,
              }),
            );
          }),
        ([groupCols, aggCols, rows]) => {
          const options = {
            aggregateFunctions: {
              MIN_value: 'MIN' as const,
              MAX_total: 'MAX' as const,
            },
          };
          const tree = buildHierarchicalTree(rows, groupCols, aggCols, options);

          function verifyMinMaxNode(node: PivotTreeNode): void {
            if (node.children.length === 0) return;

            // MIN_value: parent should equal min of children
            const minChildValues = node.children
              .map((c) => c.aggregates['MIN_value'])
              .filter((v): v is number => v != null);
            if (minChildValues.length > 0) {
              const expectedMin = Math.min(...minChildValues);
              const parentMin = node.aggregates['MIN_value'];
              if (parentMin != null) {
                expect(parentMin).toBeCloseTo(expectedMin, 5);
              }
            }

            // MAX_total: parent should equal max of children
            const maxChildValues = node.children
              .map((c) => c.aggregates['MAX_total'])
              .filter((v): v is number => v != null);
            if (maxChildValues.length > 0) {
              const expectedMax = Math.max(...maxChildValues);
              const parentMax = node.aggregates['MAX_total'];
              if (parentMax != null) {
                expect(parentMax).toBeCloseTo(expectedMax, 5);
              }
            }

            for (const child of node.children) {
              verifyMinMaxNode(child);
            }
          }

          for (const topNode of tree) {
            verifyMinMaxNode(topNode);
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
