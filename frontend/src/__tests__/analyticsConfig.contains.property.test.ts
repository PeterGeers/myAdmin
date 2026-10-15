/**
 * Property-based test for the `contains` operator of `applyDefinitionFilters`.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 2: contains is
 * case-insensitive substring.
 *
 * Targets the pure engine `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig`. For any field key and any
 * non-blank clause value, a `contains` clause matches a row iff the row's value
 * for that key contains the clause value as a case-insensitive substring (and an
 * absent/blank cell is excluded, since a value-taking op never matches an absent
 * cell).
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 5.3
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
 * The oracle: the exact case-insensitive-substring predicate from the design's
 * `contains` semantics — `cell.toLowerCase().includes(value.trim().toLowerCase())`
 * — for a PRESENT cell. An absent/blank cell is excluded (value-taking op never
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

describe('Feature: member-analytics-pivot-filter-operators, Property 2: contains is case-insensitive substring', () => {
  it('includes a row iff its value contains the clause value as a case-insensitive substring (R5.3)', () => {
    fc.assert(
      fc.property(
        // A non-blank clause value (the engine treats a blank value-taking
        // clause as inactive, which is a different property).
        fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        // A set of candidate cell values, including some that embed the clause
        // value in varied case so the substring branch is genuinely exercised.
        fc.array(fc.string(), { minLength: 1, maxLength: 20 }),
        (clauseValue, cells) => {
          const rows = cells.map(rowWith);
          const filters = { [KEY]: { op: 'contains', value: clauseValue } };

          const result = applyDefinitionFilters(rows, filters, FIELD_CONFIG);

          // The engine's kept set must equal the oracle's kept set exactly.
          const expected = rows.filter((row) =>
            containsOracle((row as Record<string, unknown>)[KEY], clauseValue),
          );
          return (
            result.length === expected.length &&
            result.every((row, i) => row === expected[i])
          );
        },
      ),
      { numRuns: 100 },
    );
  });

  it('is case-insensitive: a cell matches regardless of the case of either side', () => {
    fc.assert(
      fc.property(
        // A non-blank substring with at least one cased letter so flipping case
        // is observable.
        fc
          .string({ minLength: 1 })
          .filter((s) => s.trim() !== '' && /[a-zA-Z]/.test(s)),
        // Surrounding text placed around the (re-cased) needle.
        fc.string(),
        fc.string(),
        (needle, prefix, suffix) => {
          // Embed an upper-cased needle inside the cell, query with a
          // lower-cased needle (and vice-versa) — both must match.
          const cellUpper = `${prefix}${needle.toUpperCase()}${suffix}`;
          const cellLower = `${prefix}${needle.toLowerCase()}${suffix}`;

          const matchUpperCellLowerQuery = applyDefinitionFilters(
            [rowWith(cellUpper)],
            { [KEY]: { op: 'contains', value: needle.toLowerCase() } },
            FIELD_CONFIG,
          );
          const matchLowerCellUpperQuery = applyDefinitionFilters(
            [rowWith(cellLower)],
            { [KEY]: { op: 'contains', value: needle.toUpperCase() } },
            FIELD_CONFIG,
          );

          return (
            matchUpperCellLowerQuery.length === 1 &&
            matchLowerCellUpperQuery.length === 1
          );
        },
      ),
      { numRuns: 100 },
    );
  });

  it('excludes an absent cell (a value-taking op never matches an absent value)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        (clauseValue) => {
          const rows = [{} as unknown as MemberRow];
          const result = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'contains', value: clauseValue } },
            FIELD_CONFIG,
          );
          return result.length === 0;
        },
      ),
      { numRuns: 100 },
    );
  });
});
