/**
 * Property-Based Tests — Member Analytics filter engine (`applyDefinitionFilters`).
 *
 * Feature: member-analytics-pivot-filter-operators, Property 1: eq / ne semantics preserved
 *
 * For any field key and any non-blank clause value, an `eq` clause matches a row
 * iff the row's value for that key equals the clause value under trim +
 * case-insensitive compare (the exact legacy semantics), and a `ne` clause
 * matches iff the `eq` clause does NOT — for a PRESENT value. (An absent cell is
 * excluded by both value-taking operators and is not part of the eq/ne
 * complement claim.)
 *
 * **Validates: Requirements 5.1, 5.2**
 */
import fc from 'fast-check';
import { applyDefinitionFilters } from '../components/members/analytics/analyticsConfig';
import type { FieldConfig, FieldConfigField, MemberRow } from '../types/members';

// The single filtered field. A flat key (no storage group) means `valueFor`
// reads `row[FIELD_KEY]` directly, matching how a generic string filter resolves.
const FIELD_KEY = 'clubblad';

/** A FieldConfig with the one filtered field as a plain (untyped, flat) field. */
const fieldConfig: FieldConfig = {
  fields: [{ key: FIELD_KEY } as FieldConfigField],
} as FieldConfig;

/** The oracle for eq: trim + lowercase equality — the exact legacy normalization. */
function norm(value: string): string {
  return value.trim().toLowerCase();
}

/** Is a raw cell value "present" (non-null, non-blank after trim)? */
function isPresent(cell: unknown): boolean {
  return cell !== null && cell !== undefined && String(cell).trim() !== '';
}

/** Build a one-field member row carrying `cell` (omit the key entirely when
 *  `cell` is the absent sentinel so the row has no value for the field). */
const ABSENT = Symbol('absent');
function makeRow(id: string, cell: string | typeof ABSENT): MemberRow {
  const row: Record<string, unknown> = { member_id: id };
  if (cell !== ABSENT) {
    row[FIELD_KEY] = cell;
  }
  return row as unknown as MemberRow;
}

// A cell value is either absent, blank-ish, or an arbitrary string with varied
// casing / surrounding whitespace so the trim + case-insensitive contract is
// genuinely exercised.
const cellArb: fc.Arbitrary<string | typeof ABSENT> = fc.oneof(
  fc.constant<string | typeof ABSENT>(ABSENT),
  fc.string({ maxLength: 12 }),
  // Pad an existing word with whitespace / case flips to probe trim + ci.
  fc.string({ minLength: 1, maxLength: 8 }).map((s) => `  ${s.toUpperCase()}  `),
);

// A clause value constrained to NON-BLANK (Property 1 scopes to non-blank
// values; a blank clause value is Property 6's concern and would be inactive).
const nonBlankValueArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 12 })
  .filter((s) => s.trim() !== '');

describe('Property 1: eq / ne semantics preserved', () => {
  /**
   * Feature: member-analytics-pivot-filter-operators, Property 1: eq / ne semantics preserved
   *
   * An `eq` clause includes a row iff the row's value equals the clause value
   * under trimmed, case-insensitive compare, and an absent cell is never
   * included by a value-taking `eq`.
   *
   * **Validates: Requirements 5.1**
   */
  it('PROPERTY: eq includes exactly the rows equal under trim + case-insensitive compare', () => {
    fc.assert(
      fc.property(
        fc.array(fc.tuple(fc.string({ maxLength: 6 }), cellArb), { maxLength: 20 }),
        nonBlankValueArb,
        (cells, clauseValue) => {
          const rows = cells.map(([, cell], i) => makeRow(String(i), cell));

          const result = applyDefinitionFilters(
            rows,
            { [FIELD_KEY]: { op: 'eq', value: clauseValue } },
            fieldConfig,
          );
          const got = new Set(
            result.map((r) => (r as Record<string, unknown>).member_id),
          );

          // Oracle: a present cell equal under norm(); absent cells excluded.
          cells.forEach(([, cell], i) => {
            const id = String(i);
            const expected =
              cell !== ABSENT && norm(String(cell)) === norm(clauseValue);
            expect(got.has(id)).toBe(expected);
          });
        },
      ),
      { numRuns: 200 },
    );
  });

  /**
   * Feature: member-analytics-pivot-filter-operators, Property 1: eq / ne semantics preserved
   *
   * For every PRESENT cell, `ne` matches iff `eq` does not — the two partition
   * the present-valued rows; an absent cell is excluded by both.
   *
   * **Validates: Requirements 5.2**
   */
  it('PROPERTY: ne is the exact complement of eq on present values (both exclude absent cells)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.tuple(fc.string({ maxLength: 6 }), cellArb), { maxLength: 20 }),
        nonBlankValueArb,
        (cells, clauseValue) => {
          const rows = cells.map(([, cell], i) => makeRow(String(i), cell));

          const eqIds = new Set(
            applyDefinitionFilters(
              rows,
              { [FIELD_KEY]: { op: 'eq', value: clauseValue } },
              fieldConfig,
            ).map((r) => (r as Record<string, unknown>).member_id),
          );
          const neIds = new Set(
            applyDefinitionFilters(
              rows,
              { [FIELD_KEY]: { op: 'ne', value: clauseValue } },
              fieldConfig,
            ).map((r) => (r as Record<string, unknown>).member_id),
          );

          cells.forEach(([, cell], i) => {
            const id = String(i);
            if (!isPresent(cell === ABSENT ? undefined : cell)) {
              // Absent / blank cell: excluded by BOTH eq and ne (value-taking
              // ops never match an absent cell).
              expect(eqIds.has(id)).toBe(false);
              expect(neIds.has(id)).toBe(false);
            } else {
              // Present cell: ne matches iff eq does not (exact complement).
              expect(neIds.has(id)).toBe(!eqIds.has(id));
            }
          });
        },
      ),
      { numRuns: 200 },
    );
  });
});
