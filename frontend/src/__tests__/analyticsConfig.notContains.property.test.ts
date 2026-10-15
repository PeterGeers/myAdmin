/**
 * Property-based test for the `notContains` operator of `applyDefinitionFilters`.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 15: notContains is
 * the exact complement of contains for present values.
 *
 * Targets the pure engine `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig`. For any field key and any
 * non-blank clause value, a `notContains` clause matches a PRESENT row value iff
 * the corresponding `contains` clause does NOT (exact boolean negation on a
 * present value). An ABSENT cell is excluded by BOTH operators (a value-taking op
 * never matches an absent cell), so `contains` / `notContains` partition exactly
 * the present-valued rows. (Sibling of Property 2.)
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 5.12, 5.13
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

import { applyDefinitionFilters } from '../components/members/analytics/analyticsConfig';
import type { FieldConfig, MemberRow } from '../types/members';

// The single field key every generated row/clause is built around. It carries
// no storage group in the config, so `valueFor` reads it as a flat `row[key]`.
const KEY = 'clubblad';

/** A field config with one typed-`string` field under `KEY` and no group. */
const FIELD_CONFIG: FieldConfig = {
  fields: [{ key: KEY, type: 'string' }],
} as FieldConfig;

/**
 * The `contains` oracle: the exact case-insensitive-substring predicate from the
 * design's `contains` semantics — `cell.toLowerCase().includes(value.trim().toLowerCase())`
 * — for a PRESENT cell. An absent/blank cell is excluded (a value-taking op never
 * matches an absent cell), so the oracle requires presence first.
 */
function containsOracle(cell: unknown, clauseValue: string): boolean {
  const present =
    cell !== null && cell !== undefined && String(cell).trim() !== '';
  if (!present) {
    return false;
  }
  return String(cell)
    .toLowerCase()
    .includes(clauseValue.trim().toLowerCase());
}

/** Build a flat member row carrying `cell` under `KEY`. */
function rowWith(cell: string): MemberRow {
  return { [KEY]: cell } as unknown as MemberRow;
}

describe('Feature: member-analytics-pivot-filter-operators, Property 15: notContains is the exact complement of contains for present values', () => {
  it('matches a present value iff contains does NOT (exact boolean negation) (R5.12)', () => {
    fc.assert(
      fc.property(
        // A non-blank clause value (a blank value-taking clause is inactive,
        // which is a different property).
        fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        // Candidate PRESENT cell values. Each is forced non-blank so presence is
        // guaranteed and the test isolates the comparison branch; absent/blank
        // handling is covered separately below.
        fc.array(fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''), {
          minLength: 1,
          maxLength: 20,
        }),
        (clauseValue, cells) => {
          const rows = cells.map(rowWith);

          const kept = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'notContains', value: clauseValue } },
            FIELD_CONFIG,
          );

          // The engine's notContains set must equal the exact negation of the
          // contains oracle over the (all present) rows.
          const expected = rows.filter(
            (row) =>
              !containsOracle(
                (row as Record<string, unknown>)[KEY],
                clauseValue,
              ),
          );
          return (
            kept.length === expected.length &&
            kept.every((row, i) => row === expected[i])
          );
        },
      ),
      { numRuns: 100 },
    );
  });

  it('partitions present-valued rows: contains ∪ notContains = all present, and the two are disjoint (R5.12)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        fc.array(fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''), {
          minLength: 1,
          maxLength: 20,
        }),
        (clauseValue, cells) => {
          const rows = cells.map(rowWith);

          const containsKept = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'contains', value: clauseValue } },
            FIELD_CONFIG,
          );
          const notContainsKept = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'notContains', value: clauseValue } },
            FIELD_CONFIG,
          );

          // Disjoint: no present row is in both sets.
          const disjoint = containsKept.every(
            (row) => !notContainsKept.includes(row),
          );
          // Cover: together they account for every present row exactly once.
          const covers =
            containsKept.length + notContainsKept.length === rows.length;

          return disjoint && covers;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('excludes an absent cell (both contains and notContains never match an absent value) (R5.13)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        (clauseValue) => {
          const rows = [{} as unknown as MemberRow];

          const notContainsKept = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'notContains', value: clauseValue } },
            FIELD_CONFIG,
          );
          const containsKept = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'contains', value: clauseValue } },
            FIELD_CONFIG,
          );

          // The absent cell is excluded by BOTH operators — the negation applies
          // to the comparison of a present value, not to presence.
          return notContainsKept.length === 0 && containsKept.length === 0;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('is case-insensitive: a present cell containing a re-cased needle is excluded by notContains', () => {
    fc.assert(
      fc.property(
        // A non-blank substring with at least one cased letter so flipping case
        // is observable.
        fc
          .string({ minLength: 1 })
          .filter((s) => s.trim() !== '' && /[a-zA-Z]/.test(s)),
        fc.string(),
        fc.string(),
        (needle, prefix, suffix) => {
          // Cell embeds an upper-cased needle; query with the lower-cased needle
          // (and vice-versa) — notContains must EXCLUDE both (empty result).
          const cellUpper = `${prefix}${needle.toUpperCase()}${suffix}`;
          const cellLower = `${prefix}${needle.toLowerCase()}${suffix}`;

          const upperCellLowerQuery = applyDefinitionFilters(
            [rowWith(cellUpper)],
            { [KEY]: { op: 'notContains', value: needle.toLowerCase() } },
            FIELD_CONFIG,
          );
          const lowerCellUpperQuery = applyDefinitionFilters(
            [rowWith(cellLower)],
            { [KEY]: { op: 'notContains', value: needle.toUpperCase() } },
            FIELD_CONFIG,
          );

          return (
            upperCellLowerQuery.length === 0 &&
            lowerCellUpperQuery.length === 0
          );
        },
      ),
      { numRuns: 100 },
    );
  });
});
