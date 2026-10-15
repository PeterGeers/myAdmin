/**
 * Property-based test for the `empty` / `notEmpty` operators of
 * `applyDefinitionFilters`.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 4: empty / notEmpty
 * partition rows by presence.
 *
 * Targets the pure engine `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig`. For any field key, every
 * row is matched by EXACTLY ONE of `empty` / `notEmpty` for that key, where a
 * row is "present" iff its trimmed string value for the key is non-empty (an
 * absent cell counts as NOT present). Neither operator consumes a value input,
 * so a `value` on the clause is ignored and the clause is active regardless of
 * whether a value is supplied (unlike the value-taking operators, which are
 * inactive when blank).
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 4.1, 5.7, 5.8
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

// The single filtered field key. It carries no storage group in the config, so
// `valueFor` reads it as a flat `row[KEY]`.
const KEY = 'clubblad';

/** A field config with one plain (flat, untyped) field under `KEY`. */
const FIELD_CONFIG: FieldConfig = {
  fields: [{ key: KEY } as FieldConfigField],
} as FieldConfig;

/**
 * The oracle for presence — the exact rule the engine uses in `matchesClause`:
 * a cell is present iff it is non-null, non-undefined, and non-blank after
 * trimming its stringified form.
 */
function isPresent(cell: unknown): boolean {
  return cell !== null && cell !== undefined && String(cell).trim() !== '';
}

// A cell is either absent (the key omitted entirely) or an arbitrary string —
// including blank-ish strings (empty, whitespace-only) so the trim rule is
// genuinely exercised on the boundary between "present" and "empty".
const ABSENT = Symbol('absent');
const cellArb: fc.Arbitrary<string | typeof ABSENT> = fc.oneof(
  fc.constant<string | typeof ABSENT>(ABSENT),
  fc.constant(''),
  fc.constant('   '),
  fc.string({ maxLength: 12 }),
  fc.string({ minLength: 1, maxLength: 8 }).map((s) => `  ${s}  `),
);

/** Build a one-field member row carrying `cell`, omitting the key when absent. */
function makeRow(id: string, cell: string | typeof ABSENT): MemberRow {
  const row: Record<string, unknown> = { member_id: id };
  if (cell !== ABSENT) {
    row[KEY] = cell;
  }
  return row as unknown as MemberRow;
}

/** The surviving member_ids after applying a single clause on `KEY`. */
function survivingIds(
  rows: MemberRow[],
  clause: { op: 'empty' | 'notEmpty'; value?: string },
): Set<string> {
  const result = applyDefinitionFilters(rows, { [KEY]: clause }, FIELD_CONFIG);
  return new Set(
    result.map((r) => String((r as Record<string, unknown>).member_id)),
  );
}

describe('Feature: member-analytics-pivot-filter-operators, Property 4: empty / notEmpty partition rows by presence', () => {
  it('partitions every row: each is matched by EXACTLY ONE of empty / notEmpty (R5.7, R5.8)', () => {
    fc.assert(
      fc.property(
        fc.array(cellArb, { minLength: 1, maxLength: 20 }),
        (cells) => {
          const rows = cells.map((c, i) => makeRow(String(i), c));

          const emptyIds = survivingIds(rows, { op: 'empty' });
          const notEmptyIds = survivingIds(rows, { op: 'notEmpty' });

          cells.forEach((cell, i) => {
            const id = String(i);
            const present = isPresent(cell === ABSENT ? undefined : cell);
            // notEmpty matches present rows (R5.8); empty matches the rest (R5.7).
            expect(notEmptyIds.has(id)).toBe(present);
            expect(emptyIds.has(id)).toBe(!present);
            // Exactly one of the two matches each row (a true partition).
            expect(emptyIds.has(id) !== notEmptyIds.has(id)).toBe(true);
          });

          // The two kept sets are disjoint and together cover every row.
          const allIds = rows.map((_, i) => String(i));
          expect(emptyIds.size + notEmptyIds.size).toBe(allIds.length);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('consumes NO value: a supplied clause value does not change the result (R4.1)', () => {
    fc.assert(
      fc.property(
        fc.array(cellArb, { minLength: 1, maxLength: 20 }),
        // An arbitrary value, including blank — it must be ignored entirely.
        fc.option(fc.string({ maxLength: 10 }), { nil: undefined }),
        (cells, spuriousValue) => {
          const rows = cells.map((c, i) => makeRow(String(i), c));

          // With no value vs with an arbitrary value: identical results, so the
          // operator is active regardless of value (not inactivated-when-blank
          // like the value-taking operators).
          const emptyNoVal = survivingIds(rows, { op: 'empty' });
          const emptyWithVal = survivingIds(rows, {
            op: 'empty',
            value: spuriousValue,
          });
          const notEmptyNoVal = survivingIds(rows, { op: 'notEmpty' });
          const notEmptyWithVal = survivingIds(rows, {
            op: 'notEmpty',
            value: spuriousValue,
          });

          expect([...emptyWithVal].sort()).toEqual([...emptyNoVal].sort());
          expect([...notEmptyWithVal].sort()).toEqual(
            [...notEmptyNoVal].sort(),
          );
        },
      ),
      { numRuns: 200 },
    );
  });

  it('counts an ABSENT cell as empty (not present)', () => {
    const rows = [makeRow('0', ABSENT), makeRow('1', 'x')];
    expect(survivingIds(rows, { op: 'empty' })).toEqual(new Set(['0']));
    expect(survivingIds(rows, { op: 'notEmpty' })).toEqual(new Set(['1']));
  });

  it('counts a whitespace-only cell as empty (trimmed to blank)', () => {
    const rows = [makeRow('0', '   '), makeRow('1', ' a ')];
    expect(survivingIds(rows, { op: 'empty' })).toEqual(new Set(['0']));
    expect(survivingIds(rows, { op: 'notEmpty' })).toEqual(new Set(['1']));
  });
});
