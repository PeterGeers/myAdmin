/**
 * Property-based test for typed-ordering comparison in the member-analytics
 * filter engine.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 3: Typed ordering
 * comparison.
 *
 * Targets `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig` for the ordering operators
 * (`gt` / `gte` / `lt` / `lte`). The design's typed-ordering rule (R5.4–5.6):
 *   - a `number`-typed field with both values finite-numeric → NUMERIC compare
 *     (so `'9' lt '10'` is true, not the string `'9' > '10'`);
 *   - a `date`-typed field with both values valid dates → compare by DATE;
 *   - otherwise (unparseable, or any other/absent field type) → the trimmed
 *     values compare as LOCALE STRINGS.
 *
 * The engine narrows a single-clause filter, so for one ordering clause on key
 * `f` the surviving rows are exactly the rows whose value for `f` satisfies the
 * typed comparison against the clause value (an absent cell is always excluded
 * — a value-taking op never matches an absent cell). We assert the engine's
 * membership agrees with an independent oracle that encodes the typed rule.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 5.4, 5.5, 5.6
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { applyDefinitionFilters } from '../components/members/analytics/analyticsConfig';
import type {
  FieldConfig,
  FieldConfigField,
  MemberRow,
} from '../types/members';
import type { FilterOperator } from '../types/pivot';

const ORDERING_OPS: readonly FilterOperator[] = ['gt', 'gte', 'lt', 'lte'];

/** Build a flat MemberRow carrying `value` under the single filter key `f`. */
function row(id: string, value: string | undefined): MemberRow {
  const r: Record<string, unknown> = { member_id: id };
  if (value !== undefined) {
    r.f = value;
  }
  return r as unknown as MemberRow;
}

/** A single-field config with the given declared `type` for key `f`. */
function configWithType(type: string | undefined): FieldConfig {
  return { fields: [{ key: 'f', type } as FieldConfigField] };
}

/** Does `cmp` (sign of a comparison) satisfy the ordering `op`? */
function satisfies(op: FilterOperator, cmp: number): boolean {
  switch (op) {
    case 'gt':
      return cmp > 0;
    case 'gte':
      return cmp >= 0;
    case 'lt':
      return cmp < 0;
    case 'lte':
      return cmp <= 0;
    default:
      return false;
  }
}

/**
 * Independent oracle: should a present cell value `cell` match the ordering
 * clause `{op, value: expected}` for a field of resolved `fieldType`, per the
 * typed-ordering rule (R5.4–5.6)?
 */
function oracleMatch(
  op: FilterOperator,
  cell: string,
  expected: string,
  fieldType: string | undefined,
): boolean {
  const cellTrim = cell.trim();
  const expTrim = expected.trim();

  if (fieldType === 'number') {
    const a = Number(cellTrim);
    const b = Number(expTrim);
    if (cellTrim !== '' && expTrim !== '' && Number.isFinite(a) && Number.isFinite(b)) {
      return satisfies(op, a - b);
    }
    return satisfies(op, cellTrim.localeCompare(expTrim));
  }

  if (fieldType === 'date') {
    const a = new Date(cellTrim).getTime();
    const b = new Date(expTrim).getTime();
    if (!Number.isNaN(a) && !Number.isNaN(b)) {
      return satisfies(op, a - b);
    }
    return satisfies(op, cellTrim.localeCompare(expTrim));
  }

  return satisfies(op, cellTrim.localeCompare(expTrim));
}

/** The surviving member_ids after a single ordering clause on key `f`. */
function survivingIds(
  rows: MemberRow[],
  op: FilterOperator,
  expected: string,
  fieldType: string | undefined,
): string[] {
  const result = applyDefinitionFilters(
    rows,
    { f: { op, value: expected } },
    configWithType(fieldType),
  );
  return result.map((r) => String((r as Record<string, unknown>).member_id));
}

/**
 * The oracle-predicted surviving ids: a PRESENT cell matching the typed rule,
 * an ABSENT cell always excluded (a value-taking op never matches an absent
 * cell), and a blank clause value never narrows (handled by the caller — we
 * only generate non-blank clause values here).
 */
function oracleIds(
  cells: (string | undefined)[],
  op: FilterOperator,
  expected: string,
  fieldType: string | undefined,
): string[] {
  const ids: string[] = [];
  cells.forEach((cell, i) => {
    const id = String(i);
    const present = cell !== undefined && cell.trim() !== '';
    if (present && oracleMatch(op, cell as string, expected, fieldType)) {
      ids.push(id);
    }
  });
  return ids;
}

describe('Feature: member-analytics-pivot-filter-operators, Property 3: Typed ordering comparison', () => {
  it('compares a number-typed field NUMERICALLY when both values are finite (R5.4)', () => {
    // Numeric-string cells + a numeric clause value, on a `number` field.
    const numericString = fc
      .integer({ min: -1000, max: 1000 })
      .map((n) => String(n));
    fc.assert(
      fc.property(
        fc.array(fc.option(numericString, { nil: undefined }), {
          minLength: 1,
          maxLength: 8,
        }),
        fc.constantFrom(...ORDERING_OPS),
        numericString,
        (cells, op, expected) => {
          const rows = cells.map((c, i) => row(String(i), c));
          const got = survivingIds(rows, op, expected, 'number');
          const want = oracleIds(cells, op, expected, 'number');
          expect(got).toEqual(want);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("'9' lt '10' is true on a number field (numeric, not lexical)", () => {
    // The canonical worked example from the design.
    const rows = [row('0', '9'), row('1', '10'), row('2', '100')];
    const got = survivingIds(rows, 'lt', '10', 'number');
    // 9 < 10 only; 10 and 100 are not < 10.
    expect(got).toEqual(['0']);
  });

  it('compares a date-typed field BY DATE when both values are valid dates (R5.5)', () => {
    // ISO date-string cells + an ISO date clause value, on a `date` field.
    const isoDate = fc
      .date({
        min: new Date('2000-01-01T00:00:00.000Z'),
        max: new Date('2030-12-31T00:00:00.000Z'),
        noInvalidDate: true,
      })
      .map((d) => d.toISOString().slice(0, 10));
    fc.assert(
      fc.property(
        fc.array(fc.option(isoDate, { nil: undefined }), {
          minLength: 1,
          maxLength: 8,
        }),
        fc.constantFrom(...ORDERING_OPS),
        isoDate,
        (cells, op, expected) => {
          const rows = cells.map((c, i) => row(String(i), c));
          const got = survivingIds(rows, op, expected, 'date');
          const want = oracleIds(cells, op, expected, 'date');
          expect(got).toEqual(want);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('orders ISO dates chronologically on a date field (not purely lexically for same-length ISO)', () => {
    const rows = [
      row('0', '2024-01-05'),
      row('1', '2024-02-01'),
      row('2', '2023-12-31'),
    ];
    // gt 2024-01-05 → only 2024-02-01.
    expect(survivingIds(rows, 'gt', '2024-01-05', 'date')).toEqual(['1']);
  });

  it('falls back to LOCALE STRING compare for an absent/other field type (R5.6)', () => {
    // Arbitrary short strings, absent OR non-numeric/non-date field type, so the
    // typed branches never apply and the engine must compare as locale strings.
    const cellStr = fc.string({ minLength: 1, maxLength: 6 });
    // The CLAUSE value must be non-blank after trimming — a blank clause value
    // is inactive (no narrowing, Property 6's concern), out of scope here.
    const clauseStr = cellStr.filter((s) => s.trim() !== '');
    const otherType = fc.oneof(
      fc.constant(undefined),
      fc.constantFrom<string>('string', 'enum', 'reference', 'email'),
    );
    fc.assert(
      fc.property(
        fc.array(fc.option(cellStr, { nil: undefined }), {
          minLength: 1,
          maxLength: 8,
        }),
        fc.constantFrom(...ORDERING_OPS),
        clauseStr,
        otherType,
        (cells, op, expected, fieldType) => {
          const rows = cells.map((c, i) => row(String(i), c));
          const got = survivingIds(rows, op, expected, fieldType);
          const want = oracleIds(cells, op, expected, fieldType);
          expect(got).toEqual(want);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('falls back to STRING compare on a number field when a value is NOT finite-numeric (R5.6)', () => {
    // Mixed cells: some numeric, some non-numeric, on a `number` field. Where
    // either side is non-finite the comparison degrades to locale-string compare.
    const mixed = fc.oneof(
      fc.integer({ min: -500, max: 500 }).map((n) => String(n)),
      fc.string({ minLength: 1, maxLength: 5 }).filter((s) => !Number.isFinite(Number(s.trim())) || s.trim() === ''),
    );
    const expectedVal = fc.oneof(
      fc.integer({ min: -500, max: 500 }).map((n) => String(n)),
      fc.constantFrom('abc', 'x1', 'n/a'),
    );
    fc.assert(
      fc.property(
        fc.array(fc.option(mixed, { nil: undefined }), {
          minLength: 1,
          maxLength: 8,
        }),
        fc.constantFrom(...ORDERING_OPS),
        expectedVal,
        (cells, op, expected) => {
          const rows = cells.map((c, i) => row(String(i), c));
          const got = survivingIds(rows, op, expected, 'number');
          const want = oracleIds(cells, op, expected, 'number');
          expect(got).toEqual(want);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('excludes an absent cell for every ordering operator (value-taking op never matches absent)', () => {
    const rows = [row('0', undefined), row('1', '5')];
    for (const op of ORDERING_OPS) {
      const got = survivingIds(rows, op, '5', 'number');
      // The absent row ('0') is never present in the result regardless of op.
      expect(got).not.toContain('0');
    }
  });
});
