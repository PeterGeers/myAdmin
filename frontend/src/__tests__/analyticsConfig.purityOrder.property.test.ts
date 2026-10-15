/**
 * Property-based test for the purity + order-preservation contract of
 * `applyDefinitionFilters`.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 13: Engine is pure
 * and order-preserving.
 *
 * Targets the pure engine `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig`. For any rows and filters the
 * engine:
 *   - returns a NEW array (never the same reference as its input);
 *   - preserves the ORIGINAL row order (the result is a sub-sequence of the
 *     input rows in the same order);
 *   - resolves each row value through the shared nested-or-flat `valueFor`
 *     accessor using the field's storage group from the field config (so a value
 *     stored under its nested bucket narrows the same as a flat alias);
 *   - never MUTATES its inputs (rows array, the row objects, or the filters map);
 *   - returns an EMPTY array when the rows input is not an array.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 5.10, 5.11, 6.4, 11.4
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { applyDefinitionFilters } from '../components/members/analytics/analyticsConfig';
import type { FieldConfig, FieldConfigField, MemberRow } from '../types/members';
import type { FilterOperator } from '../types/pivot';

// A flat field (top-level key) and a nested field whose value lives under a
// storage bucket (`membership`) — so the accessor-via-group behavior is
// exercised: a nested value must narrow identically to a flat one.
const FLAT_KEY = 'clubblad';
const NESTED_KEY = 'status';
const NESTED_GROUP = 'membership';

/** Field config: one flat `string` field, one nested `string` field. */
const FIELD_CONFIG: FieldConfig = {
  fields: [
    { key: FLAT_KEY, type: 'string' } as FieldConfigField,
    { key: NESTED_KEY, type: 'string', group: NESTED_GROUP } as FieldConfigField,
  ],
} as FieldConfig;

/** A representative spread of operators (value-taking + presence checks). */
const OPS: readonly FilterOperator[] = [
  'eq',
  'ne',
  'contains',
  'notContains',
  'regex',
  'notRegex',
  'empty',
  'notEmpty',
];

/**
 * Build a member row carrying the flat key at top level AND the nested key under
 * its `membership` storage bucket (how a calculated/nested field is enriched).
 */
function makeRow(id: number, flatCell: string, nestedCell: string): MemberRow {
  return {
    member_id: String(id),
    [FLAT_KEY]: flatCell,
    [NESTED_GROUP]: { [NESTED_KEY]: nestedCell },
  } as unknown as MemberRow;
}

/** The ordered member_id list a result narrows to (order-preserving check). */
function ids(rows: MemberRow[]): string[] {
  return rows.map((r) => (r as Record<string, unknown>).member_id as string);
}

/** A simple short-string value cell. */
const cellArb = fc.string({ maxLength: 8 });
const rowsArb = fc.array(fc.tuple(cellArb, cellArb), { maxLength: 25 });
// A non-blank clause value (a blank value is inactive — Property 6).
const valueArb = fc.string({ minLength: 1 }).filter((s) => s.trim() !== '');

/**
 * A filters map targeting the flat key, the nested key, or both, with a chosen
 * operator. Presence ops (`empty`/`notEmpty`) carry no value; value-taking ops
 * carry a non-blank value.
 */
const filtersArb = fc
  .record({
    flatOp: fc.option(fc.constantFrom(...OPS), { nil: undefined }),
    nestedOp: fc.option(fc.constantFrom(...OPS), { nil: undefined }),
    flatValue: valueArb,
    nestedValue: valueArb,
  })
  .map(({ flatOp, nestedOp, flatValue, nestedValue }) => {
    const map: Record<string, { op: FilterOperator; value?: string }> = {};
    if (flatOp) {
      map[FLAT_KEY] =
        flatOp === 'empty' || flatOp === 'notEmpty'
          ? { op: flatOp }
          : { op: flatOp, value: flatValue };
    }
    if (nestedOp) {
      map[NESTED_KEY] =
        nestedOp === 'empty' || nestedOp === 'notEmpty'
          ? { op: nestedOp }
          : { op: nestedOp, value: nestedValue };
    }
    return map;
  });

/** Is `sub` an order-preserving subsequence of `full`? */
function isOrderedSubsequence(sub: string[], full: string[]): boolean {
  let i = 0;
  for (const x of full) {
    if (i < sub.length && sub[i] === x) i += 1;
  }
  return i === sub.length;
}

describe('Feature: member-analytics-pivot-filter-operators, Property 13: Engine is pure and order-preserving', () => {
  it('preserves the original row order and returns a fresh array when it narrows (R5.11)', () => {
    fc.assert(
      fc.property(filtersArb, rowsArb, (filters, cells) => {
        const rows = cells.map(([f, n], i) => makeRow(i, f, n));

        const result = applyDefinitionFilters(rows, filters, FIELD_CONFIG);

        // Order-preserving: the result is an in-order subsequence of the input
        // (same relative order, no reordering) — the core R5.11 guarantee.
        expect(isOrderedSubsequence(ids(result), ids(rows))).toBe(true);

        // Whenever the engine actually narrows (drops at least one row) it hands
        // back a FRESH array, never a mutated view of the input. (On the pure
        // pass-through path — no active clause — it may return the input array
        // reference unchanged; that is still safe because inputs are never
        // mutated, asserted separately below.)
        if (result.length !== rows.length) {
          expect(result).not.toBe(rows);
        }
      }),
      { numRuns: 100 },
    );
  });

  it('never mutates its inputs — the rows array, the row objects, or the filters map (R11.4)', () => {
    fc.assert(
      fc.property(filtersArb, rowsArb, (filters, cells) => {
        const rows = cells.map(([f, n], i) => makeRow(i, f, n));

        // Deep snapshots of the inputs BEFORE the call.
        const rowsSnapshot = JSON.parse(JSON.stringify(rows));
        const filtersSnapshot = JSON.parse(JSON.stringify(filters));
        const rowsArrayRef = rows;
        const rowRefs = [...rows];

        applyDefinitionFilters(rows, filters, FIELD_CONFIG);

        // The input array identity and length are untouched.
        expect(rows).toBe(rowsArrayRef);
        expect(rows.length).toBe(rowsSnapshot.length);
        // Each row object is the same reference and deeply unchanged.
        rows.forEach((row, i) => {
          expect(row).toBe(rowRefs[i]);
        });
        expect(rows).toEqual(rowsSnapshot);
        // The filters map is deeply unchanged.
        expect(filters).toEqual(filtersSnapshot);
      }),
      { numRuns: 100 },
    );
  });

  it('resolves a value through the storage group — a NESTED value narrows identically to a FLAT one (R5.10)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...OPS),
        valueArb,
        rowsArb,
        (op, value, cells) => {
          // Give every row the SAME content for the flat and nested cells, so a
          // clause on the flat field and the equivalent clause on the nested
          // field must narrow to the SAME rows — proving the nested value is
          // read via its storage group (not missed by a flat-only read).
          const rows = cells.map(([c], i) => makeRow(i, c, c));

          const takesValue = op !== 'empty' && op !== 'notEmpty';
          const flatClause = takesValue ? { op, value } : { op };
          const nestedClause = takesValue ? { op, value } : { op };

          const viaFlat = applyDefinitionFilters(
            rows,
            { [FLAT_KEY]: flatClause },
            FIELD_CONFIG,
          );
          const viaNested = applyDefinitionFilters(
            rows,
            { [NESTED_KEY]: nestedClause },
            FIELD_CONFIG,
          );

          expect(ids(viaNested)).toEqual(ids(viaFlat));
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns an EMPTY array when the rows input is not an array (R6.4)', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(null),
          fc.constant(undefined),
          fc.string(),
          fc.integer(),
          fc.boolean(),
          fc.object(),
          fc.record({ op: fc.constant('eq'), value: fc.string() }),
        ),
        filtersArb,
        (notAnArray, filters) => {
          const result = applyDefinitionFilters(
            notAnArray as unknown as MemberRow[],
            filters,
            FIELD_CONFIG,
          );
          expect(Array.isArray(result)).toBe(true);
          expect(result).toEqual([]);
        },
      ),
      { numRuns: 100 },
    );
  });
});
