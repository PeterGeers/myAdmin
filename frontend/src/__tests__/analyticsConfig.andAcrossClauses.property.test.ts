/**
 * Property-based test for AND semantics across multiple active clauses in the
 * member-analytics filter engine.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 5: AND across
 * clauses.
 *
 * Targets the pure engine `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig`. For any filters map with
 * multiple active clauses, the engine includes a row iff it matches EVERY active
 * clause (R5.9). We assert this against an independent oracle derived from the
 * engine's own single-clause behavior: applying all clauses at once must equal
 * the intersection of applying each clause on its own (an AND is exactly the
 * intersection of its per-clause results, with input order preserved).
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 5.9
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { applyDefinitionFilters } from '../components/members/analytics/analyticsConfig';
import type { FieldConfig, FieldConfigField, MemberRow } from '../types/members';
import type { FilterClause, FilterOperator } from '../types/pivot';

// Three independent, flat string fields the clauses filter on. None carry a
// storage group, so `valueFor` reads each as a flat `row[key]`.
const KEYS = ['clubblad', 'status', 'city'] as const;

const FIELD_CONFIG: FieldConfig = {
  fields: KEYS.map((key) => ({ key, type: 'string' } as FieldConfigField)),
} as FieldConfig;

/** A value-taking operator generator (presence ops are a separate property). */
const valueOp: fc.Arbitrary<FilterOperator> = fc.constantFrom<FilterOperator>(
  'eq',
  'ne',
  'contains',
  'notContains',
);

/** A non-blank clause value — a blank value-taking clause is inactive (Property 6). */
const clauseValue = fc.string({ minLength: 1 }).filter((s) => s.trim() !== '');

/** A single clause for a given key. */
const clauseFor = (): fc.Arbitrary<FilterClause> =>
  fc.record({ op: valueOp, value: clauseValue });

/**
 * A member row carrying a (possibly absent) cell for each of the three keys,
 * biased so clause values recur across cells (otherwise `eq`/`contains` would
 * almost never match and the AND would trivially empty out).
 */
function rowArb(sharedValues: readonly string[]): fc.Arbitrary<MemberRow> {
  const cell = fc.oneof(
    fc.constantFrom(...sharedValues),
    fc.string(),
    fc.constant(undefined),
  );
  return fc
    .record(
      Object.fromEntries(KEYS.map((k) => [k, cell])) as Record<
        string,
        fc.Arbitrary<string | undefined>
      >,
    )
    .map((obj) => {
      const r: Record<string, unknown> = {};
      for (const k of KEYS) {
        const v = (obj as Record<string, string | undefined>)[k];
        if (v !== undefined) {
          r[k] = v;
        }
      }
      return r as unknown as MemberRow;
    });
}

describe('Feature: member-analytics-pivot-filter-operators, Property 5: AND across clauses', () => {
  it('includes a row iff it matches EVERY active clause (= intersection of per-clause results) (R5.9)', () => {
    // A clause value drawn from a small shared pool so eq/contains clauses can
    // actually match some generated cells (otherwise the AND trivially empties).
    const POOL = ['Papier', 'Digitaal', 'Actief', 'Delft', 'pap'] as const;
    const poolValue = fc.constantFrom(...POOL);
    const poolCell = fc.oneof(
      fc.constantFrom(...POOL),
      fc.string(),
      fc.constant(undefined),
    );

    fc.assert(
      fc.property(
        // One, two, or three clauses, one per distinct key.
        fc.uniqueArray(fc.constantFrom(...KEYS), { minLength: 1, maxLength: 3 }),
        fc.array(fc.record({ op: valueOp, value: poolValue }), {
          minLength: 1,
          maxLength: 3,
        }),
        // A batch of rows, each a flat record over the three keys.
        fc.array(
          fc.record(
            Object.fromEntries(KEYS.map((k) => [k, poolCell])) as Record<
              string,
              fc.Arbitrary<string | undefined>
            >,
          ),
          { minLength: 0, maxLength: 25 },
        ),
        (keys, clauses, rawRows) => {
          const rows = rawRows.map((obj) => {
            const r: Record<string, unknown> = {};
            for (const k of KEYS) {
              const v = (obj as Record<string, string | undefined>)[k];
              if (v !== undefined) {
                r[k] = v;
              }
            }
            return r as unknown as MemberRow;
          });

          const filters: Record<string, FilterClause> = {};
          keys.forEach((key, i) => {
            filters[key] = clauses[i % clauses.length];
          });

          const combined = applyDefinitionFilters(rows, filters, FIELD_CONFIG);

          // Oracle: a row survives the AND iff it survives every single clause
          // applied on its own (an AND is exactly the per-clause intersection).
          const expected = rows.filter((row) =>
            Object.entries(filters).every(
              ([key, clause]) =>
                applyDefinitionFilters([row], { [key]: clause }, FIELD_CONFIG)
                  .length === 1,
            ),
          );

          // Membership AND preserved order must both match.
          expect(combined).toEqual(expected);
          return true;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('is strictly narrowing: adding a clause never grows the result set', () => {
    fc.assert(
      fc.property(
        fc.array(rowArb(['Papier', 'Actief', 'Delft']), {
          minLength: 1,
          maxLength: 25,
        }),
        clauseFor(),
        clauseFor(),
        (rows, c1, c2) => {
          const oneClause = applyDefinitionFilters(
            rows,
            { [KEYS[0]]: c1 },
            FIELD_CONFIG,
          );
          const twoClauses = applyDefinitionFilters(
            rows,
            { [KEYS[0]]: c1, [KEYS[1]]: c2 },
            FIELD_CONFIG,
          );

          // The two-clause result is a subset of the one-clause result, in the
          // same relative order (AND can only remove rows, never add/reorder).
          expect(twoClauses.length).toBeLessThanOrEqual(oneClause.length);
          const oneSet = new Set(oneClause);
          return twoClauses.every((row) => oneSet.has(row));
        },
      ),
      { numRuns: 100 },
    );
  });

  it('a worked example: two eq clauses keep only rows matching BOTH', () => {
    const rows: MemberRow[] = [
      { clubblad: 'Papier', status: 'Actief' } as unknown as MemberRow, // both
      { clubblad: 'Papier', status: 'Inactief' } as unknown as MemberRow, // only clubblad
      { clubblad: 'Digitaal', status: 'Actief' } as unknown as MemberRow, // only status
      { clubblad: 'Digitaal', status: 'Inactief' } as unknown as MemberRow, // neither
    ];
    const result = applyDefinitionFilters(
      rows,
      {
        clubblad: { op: 'eq', value: 'Papier' },
        status: { op: 'eq', value: 'Actief' },
      },
      FIELD_CONFIG,
    );
    expect(result).toEqual([rows[0]]);
  });
});
