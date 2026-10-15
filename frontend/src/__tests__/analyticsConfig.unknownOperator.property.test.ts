/**
 * Property-based test for the unknown-operator clamp of the Member Analytics
 * filter engine (`applyDefinitionFilters`), exercised via `normalizeClause`.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 10: Unknown
 * operator clamps to eq.
 *
 * For any stored clause whose `op` is OUTSIDE the `FilterOperator` set,
 * `normalizeClause` interprets it as `eq`, so `applyDefinitionFilters` narrows
 * rows exactly as the same clause rewritten with `op: 'eq'` would. This keeps a
 * hand-edited / legacy / forward-incompatible stored op from crashing or
 * silently dropping all rows — it degrades to the legacy equality semantics.
 *
 * Targets the pure engine `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig` and the pure reader
 * `normalizeClause` in `../types/pivot`.
 *
 * Uses fast-check with a minimum of 100 iterations per property.
 *
 * **Validates: Requirements 8.3**
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

import { applyDefinitionFilters } from '../components/members/analytics/analyticsConfig';
import { normalizeClause } from '../types/pivot';
import type { FieldConfig, MemberRow } from '../types/members';

// The single field key every generated row/clause is built around. It carries
// no storage group in the config, so `valueFor` reads it as a flat `row[key]`.
const KEY = 'clubblad';

/** A field config with one plain (untyped, flat) field under `KEY`. */
const FIELD_CONFIG: FieldConfig = {
  fields: [{ key: KEY }],
} as FieldConfig;

/** The known operators the engine recognizes — anything else must clamp to eq. */
const KNOWN_OPERATORS = [
  'eq',
  'ne',
  'gt',
  'gte',
  'lt',
  'lte',
  'contains',
  'notContains',
  'regex',
  'notRegex',
  'empty',
  'notEmpty',
];

/** Build a flat member row carrying `cell` under `KEY`. */
function rowWith(cell: string): MemberRow {
  return { [KEY]: cell } as unknown as MemberRow;
}

// An operator string that is NOT one of the known operators — including the
// empty string, mixed case, and arbitrary junk — so the clamp branch is
// genuinely exercised across the "unknown" input space.
const unknownOpArb: fc.Arbitrary<string> = fc
  .oneof(
    fc.string({ maxLength: 10 }),
    // Case variants of real ops (e.g. 'EQ', 'Contains') are also "unknown"
    // since the set is exact-case.
    fc.constantFrom(...KNOWN_OPERATORS).map((op) => op.toUpperCase()),
    fc.constantFrom('equals', 'matches', 'in', 'between', '==', 'startsWith', ''),
  )
  .filter((op) => !KNOWN_OPERATORS.includes(op));

// A non-blank clause value (a blank value-taking clause is inactive — a
// different property); eq is value-taking so the clamp must honour this.
const nonBlankValueArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 12 })
  .filter((s) => s.trim() !== '');

// Candidate cell values, some re-cased / padded to probe the eq trim +
// case-insensitive semantics the clamp degrades to.
const cellArb: fc.Arbitrary<string> = fc.oneof(
  fc.string({ maxLength: 12 }),
  fc.string({ minLength: 1, maxLength: 8 }).map((s) => `  ${s.toUpperCase()}  `),
);

describe('Feature: member-analytics-pivot-filter-operators, Property 10: Unknown operator clamps to eq', () => {
  it('normalizeClause maps any unknown op to eq (preserving the value) (R8.3)', () => {
    fc.assert(
      fc.property(unknownOpArb, nonBlankValueArb, (unknownOp, value) => {
        const clause = normalizeClause({ op: unknownOp, value });
        expect(clause).not.toBeNull();
        expect(clause?.op).toBe('eq');
        expect(clause?.value).toBe(value);
      }),
      { numRuns: 200 },
    );
  });

  it('applyDefinitionFilters narrows an unknown-op clause identically to an eq clause (R8.3)', () => {
    fc.assert(
      fc.property(
        unknownOpArb,
        nonBlankValueArb,
        fc.array(cellArb, { maxLength: 20 }),
        (unknownOp, value, cells) => {
          const rows = cells.map(rowWith);

          const unknownResult = applyDefinitionFilters(
            rows,
            { [KEY]: { op: unknownOp, value } as never },
            FIELD_CONFIG,
          );
          const eqResult = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'eq', value } },
            FIELD_CONFIG,
          );

          // Same rows, same order, same identities — the unknown op behaves
          // exactly as eq.
          return (
            unknownResult.length === eqResult.length &&
            unknownResult.every((row, i) => row === eqResult[i])
          );
        },
      ),
      { numRuns: 200 },
    );
  });
});
