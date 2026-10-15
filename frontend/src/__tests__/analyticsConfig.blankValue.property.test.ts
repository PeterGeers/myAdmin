/**
 * Property-based test for the "blank value never narrows" contract of
 * `applyDefinitionFilters`.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 6: Blank value
 * never narrows.
 *
 * Targets the pure engine `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig`. For any value-taking
 * operator and any filters map where a clause has a blank value (`''`, a
 * whitespace-only string, `null`, or `undefined`) — or where a filters ENTRY is
 * itself `null`/`undefined` — the engine returns the same rows as if that clause
 * were absent entirely. A blank value-taking clause is inactive and applies no
 * narrowing, so an unfinished filter row never hides every member.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 6.1, 6.3
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

import { applyDefinitionFilters } from '../components/members/analytics/analyticsConfig';
import type { FieldConfig, FieldConfigField, MemberRow } from '../types/members';
import type { FilterOperator } from '../types/pivot';

// The field a blank clause targets, plus a second field carrying a genuine
// (non-blank) active clause so a map can mix an active clause with a blank one.
const BLANK_KEY = 'clubblad';
const ACTIVE_KEY = 'status';

/** A field config with two plain `string` fields (flat keys, no storage group). */
const FIELD_CONFIG: FieldConfig = {
  fields: [
    { key: BLANK_KEY, type: 'string' } as FieldConfigField,
    { key: ACTIVE_KEY, type: 'string' } as FieldConfigField,
  ],
} as FieldConfig;

/**
 * The value-taking operators. A blank value for ANY of these must leave the
 * clause inactive. (`empty`/`notEmpty` are presence checks that take no value
 * and are a different property — Property 4 — so they are excluded here.)
 */
const VALUE_TAKING_OPS: readonly FilterOperator[] = [
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
];

/** A blank "value" in any of the forms the engine must treat as inactive. */
const blankValueArb: fc.Arbitrary<string | null | undefined> = fc.oneof(
  fc.constant<string | null | undefined>(''),
  fc.constant<string | null | undefined>('   '),
  fc.constant<string | null | undefined>('\t \n'),
  fc.constant<string | null | undefined>(null),
  fc.constant<string | null | undefined>(undefined),
);

/** Build a two-field member row. */
function makeRow(id: number, blankCell: string, activeCell: string): MemberRow {
  return {
    member_id: String(id),
    [BLANK_KEY]: blankCell,
    [ACTIVE_KEY]: activeCell,
  } as unknown as MemberRow;
}

/** The ordered member_id list a result narrows to (order-preserving check). */
function ids(rows: MemberRow[]): string[] {
  return rows.map((r) => (r as Record<string, unknown>).member_id as string);
}

const cellArb = fc.string({ maxLength: 10 });
const rowsArb = fc.array(fc.tuple(cellArb, cellArb), { maxLength: 20 });

describe('Feature: member-analytics-pivot-filter-operators, Property 6: Blank value never narrows', () => {
  it('a blank-value clause for a value-taking operator returns the same rows as if the clause were absent (R6.1)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALUE_TAKING_OPS),
        blankValueArb,
        rowsArb,
        (op, blankValue, cells) => {
          const rows = cells.map(([b, a], i) => makeRow(i, b, a));

          // The filters map carries ONLY the blank clause.
          const withBlank = { [BLANK_KEY]: { op, value: blankValue } };
          // The "absent" baseline: the clause is simply not present.
          const withoutClause = {};

          const got = applyDefinitionFilters(rows, withBlank, FIELD_CONFIG);
          const baseline = applyDefinitionFilters(
            rows,
            withoutClause,
            FIELD_CONFIG,
          );

          // Same rows, same order — the blank clause narrowed nothing.
          expect(ids(got)).toEqual(ids(baseline));
          // And since there is no other clause, it is the full set.
          expect(ids(got)).toEqual(ids(rows));
        },
      ),
      { numRuns: 100 },
    );
  });

  it('a blank clause alongside an active clause narrows exactly as the active clause alone does (R6.1)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALUE_TAKING_OPS),
        blankValueArb,
        // A non-blank value for the genuinely active eq clause on ACTIVE_KEY.
        fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        rowsArb,
        (blankOp, blankValue, activeValue, cells) => {
          const rows = cells.map(([b, a], i) => makeRow(i, b, a));

          const activeClause = { [ACTIVE_KEY]: { op: 'eq', value: activeValue } };

          // Blank clause on BLANK_KEY + the active eq clause on ACTIVE_KEY.
          const withBlankPlusActive = {
            [BLANK_KEY]: { op: blankOp, value: blankValue },
            ...activeClause,
          };

          const withBoth = applyDefinitionFilters(
            rows,
            withBlankPlusActive,
            FIELD_CONFIG,
          );
          const withActiveOnly = applyDefinitionFilters(
            rows,
            activeClause,
            FIELD_CONFIG,
          );

          // The blank clause is inert: adding it changes nothing.
          expect(ids(withBoth)).toEqual(ids(withActiveOnly));
        },
      ),
      { numRuns: 100 },
    );
  });

  it('a null/undefined filters ENTRY applies no narrowing, same as an absent clause (R6.3)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<null | undefined>(null, undefined),
        rowsArb,
        (nullish, cells) => {
          const rows = cells.map(([b, a], i) => makeRow(i, b, a));

          const withNullEntry = { [BLANK_KEY]: nullish };
          const got = applyDefinitionFilters(rows, withNullEntry, FIELD_CONFIG);

          // A null/undefined entry is treated as "no narrowing" → full set.
          expect(ids(got)).toEqual(ids(rows));
        },
      ),
      { numRuns: 100 },
    );
  });
});
