/**
 * Property-based test for the picker-helper filter round-trip.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 9: Filter round-trip
 * preserves field/op/value.
 *
 * Targets the pure helpers `fromFilterDrafts` / `toFilterDrafts` in
 * `../components/members/analytics/memberFieldPicker.helpers`. For any editor
 * filter rows, composing them with `fromFilterDrafts(drafts)` and then reading
 * back with `toFilterDrafts(result)` yields rows equivalent on `(field, op,
 * value)` for EVERY kept row — where "kept" is governed by `fromFilterDrafts`'s
 * compose rules:
 *   - a row with an empty field key is dropped;
 *   - a value-taking row (any op except `empty` / `notEmpty`) with a blank value
 *     (after trim) is dropped;
 *   - a valueless `empty` / `notEmpty` row is kept;
 *   - the composed map emits the object form `{ op, value? }` with `value`
 *     present ONLY for value-taking operators;
 *   - the last row wins on a duplicate field key.
 * Year keys (`years_member` / `joined_after_year`) are ordinary rows with no
 * special carry-through, so they are generated in the field pool to assert the
 * reserved-key concept is gone.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 8.4, 8.5, 8.6, 8.7
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

import {
  fromFilterDrafts,
  toFilterDrafts,
  nextFilterId,
  type FilterDraft,
} from '../components/members/analytics/memberFieldPicker.helpers';
import { operatorTakesNoValue } from '../components/members/analytics/analyticsConfig';
import type { FilterOperator } from '../types/pivot';

/** All twelve operators — the full editor operator space. */
const ALL_OPERATORS: readonly FilterOperator[] = [
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

/**
 * A pool of candidate field keys. Includes the former "reserved" year keys to
 * prove they round-trip as ordinary rows (no carve-out), plus the empty-string
 * sentinel for an unset row that `fromFilterDrafts` must drop. The pool is small
 * so duplicate-key rows (last-wins) are exercised frequently.
 */
const fieldArb: fc.Arbitrary<string> = fc.constantFrom(
  '',
  'clubblad',
  'achternaam',
  'years_member',
  'joined_after_year',
);

const opArb: fc.Arbitrary<FilterOperator> = fc.constantFrom(...ALL_OPERATORS);

// Values span blank-ish (empty / whitespace-only), surrounding-whitespace, and
// arbitrary strings so the trim-and-drop rule and the trim-preservation on
// read-back are both exercised.
const valueArb: fc.Arbitrary<string> = fc.oneof(
  fc.constant(''),
  fc.constant('   '),
  fc.string({ maxLength: 10 }),
  fc.string({ minLength: 1, maxLength: 8 }).map((s) => `  ${s}  `),
);

const draftArb: fc.Arbitrary<FilterDraft> = fc.record({
  id: fc.constant('').map(() => nextFilterId()),
  field: fieldArb,
  op: opArb,
  value: valueArb,
});

const draftsArb: fc.Arbitrary<FilterDraft[]> = fc.array(draftArb, {
  maxLength: 12,
});

/**
 * The oracle: the set of `(field, op, value)` entries `fromFilterDrafts` KEEPS,
 * expressed as the normalized form a read-back must reproduce. Mirrors the
 * compose rules exactly, including last-wins on a duplicate field key.
 *   - value-taking op: kept iff field non-empty AND trimmed value non-empty;
 *     the retained value is the TRIMMED value.
 *   - empty/notEmpty: kept iff field non-empty; the retained value is '' (the
 *     object form carries no value, which reads back as '').
 */
interface Entry {
  field: string;
  op: FilterOperator;
  value: string;
}

function expectedKept(drafts: FilterDraft[]): Map<string, Entry> {
  const kept = new Map<string, Entry>();
  for (const d of drafts) {
    const field = d.field.trim();
    if (field === '') {
      continue;
    }
    const takesValue = !operatorTakesNoValue(d.op);
    const value = d.value.trim();
    if (takesValue && value === '') {
      continue;
    }
    // Last row wins on a duplicate field key (Map.set overwrites).
    kept.set(field, { field, op: d.op, value: takesValue ? value : '' });
  }
  return kept;
}

describe('Feature: member-analytics-pivot-filter-operators, Property 9: Filter round-trip preserves field/op/value', () => {
  it('fromFilterDrafts -> toFilterDrafts preserves (field, op, value) for every kept row (R8.4, R8.5, R8.7)', () => {
    fc.assert(
      fc.property(draftsArb, (drafts) => {
        const composed = fromFilterDrafts(drafts);
        const readBack = toFilterDrafts(composed);

        const expected = expectedKept(drafts);

        // Same set of kept fields (no key excluded — including year keys).
        const gotByField = new Map(readBack.map((r) => [r.field, r]));
        expect(gotByField.size).toBe(readBack.length); // no duplicate fields
        expect(new Set(gotByField.keys())).toEqual(new Set(expected.keys()));

        // Each kept row is equivalent on (field, op, value).
        for (const [field, exp] of expected) {
          const got = gotByField.get(field);
          expect(got).toBeDefined();
          expect(got!.op).toBe(exp.op);
          expect(got!.value).toBe(exp.value);
        }
      }),
      { numRuns: 200 },
    );
  });

  it('the composed map emits value ONLY for value-taking ops; empty/notEmpty carry none (R8.6)', () => {
    fc.assert(
      fc.property(draftsArb, (drafts) => {
        const composed = fromFilterDrafts(drafts) as Record<
          string,
          { op: FilterOperator; value?: string }
        >;
        for (const clause of Object.values(composed)) {
          if (operatorTakesNoValue(clause.op)) {
            // empty / notEmpty: no `value` property at all.
            expect('value' in clause).toBe(false);
          } else {
            // value-taking: a non-blank trimmed value is present.
            expect(typeof clause.value).toBe('string');
            expect(clause.value!.trim()).not.toBe('');
          }
        }
      }),
      { numRuns: 200 },
    );
  });

  it('drops empty-field and blank value-taking rows; keeps valueless empty/notEmpty rows (R8.6)', () => {
    fc.assert(
      fc.property(draftsArb, (drafts) => {
        const composed = fromFilterDrafts(drafts);
        const keptFields = new Set(Object.keys(composed));
        const expectedFields = new Set(expectedKept(drafts).keys());
        expect(keptFields).toEqual(expectedFields);
        // No empty-string key ever survives compose.
        expect(keptFields.has('')).toBe(false);
      }),
      { numRuns: 200 },
    );
  });

  it('round-trip is idempotent: a second compose+read reproduces the first read-back (R8.7)', () => {
    fc.assert(
      fc.property(draftsArb, (drafts) => {
        const firstRead = toFilterDrafts(fromFilterDrafts(drafts));
        const secondRead = toFilterDrafts(fromFilterDrafts(firstRead));

        const norm = (rows: FilterDraft[]) =>
          rows
            .map((r) => ({ field: r.field, op: r.op, value: r.value }))
            .sort((a, b) => a.field.localeCompare(b.field));

        expect(norm(secondRead)).toEqual(norm(firstRead));
      }),
      { numRuns: 200 },
    );
  });
});
