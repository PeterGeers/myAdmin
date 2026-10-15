/**
 * Property-based test for the `regex` operator of `applyDefinitionFilters`.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 7: Regex is total
 * (valid matches; invalid matches nothing, never throws).
 *
 * Targets the pure engine `applyDefinitionFilters` in
 * `../components/members/analytics/analyticsConfig`. For any string pattern
 * (valid or invalid) and any rows, a `regex` clause either matches by the
 * compiled case-insensitive RegExp (`new RegExp(pattern, 'i')`, present cell
 * only — a value-taking op never matches an absent cell) or — when the pattern
 * is invalid — matches NO row, and `applyDefinitionFilters` always returns
 * without throwing.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 7.1, 7.2
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it } from 'vitest';
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

/** Build a flat member row carrying `cell` under `KEY`. */
function rowWith(cell: string): MemberRow {
  return { [KEY]: cell } as unknown as MemberRow;
}

/** Is a raw cell value "present" (non-null, non-blank after trim)? */
function isPresent(cell: unknown): boolean {
  return cell !== null && cell !== undefined && String(cell).trim() !== '';
}

/**
 * The oracle: compile the pattern exactly as the engine does
 * (`new RegExp(pattern, 'i')`); a present cell matches iff `re.test(cell)`. An
 * absent/blank cell is excluded (a value-taking op never matches an absent
 * cell). This mirrors `tryCompileRegex` + the `regex` branch of `matchesClause`.
 */
function regexOracle(cell: unknown, re: RegExp | null): boolean {
  if (!isPresent(cell)) {
    return false;
  }
  return re !== null && re.test(String(cell));
}

/**
 * Compile a pattern the way the engine does: the clause value is TRIMMED before
 * `tryCompileRegex` (`value = (clause.value ?? '').trim()`), then compiled
 * case-insensitively — `null` when invalid. The oracle must trim too so it
 * mirrors the engine exactly (e.g. a pattern `", "` compiles as `","`).
 */
function safeCompile(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern.trim(), 'i');
  } catch {
    return null;
  }
}

describe('Feature: member-analytics-pivot-filter-operators, Property 7: Regex is total (valid matches; invalid matches nothing, never throws)', () => {
  it('matches a present row iff the case-insensitive compiled RegExp matches, for ANY pattern (valid or invalid) (R7.1, R7.2)', () => {
    fc.assert(
      fc.property(
        // Any non-blank pattern string — fast-check's full string generator
        // naturally produces both valid patterns and invalid ones (unbalanced
        // brackets, dangling quantifiers, etc.).
        fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        // Candidate cell values exercised against the pattern.
        fc.array(fc.string(), { minLength: 1, maxLength: 20 }),
        (pattern, cells) => {
          const rows = cells.map(rowWith);
          const filters = { [KEY]: { op: 'regex', value: pattern } };

          // Must never throw regardless of pattern validity.
          const result = applyDefinitionFilters(rows, filters, FIELD_CONFIG);

          const re = safeCompile(pattern);
          const expected = rows.filter((row) =>
            regexOracle((row as Record<string, unknown>)[KEY], re),
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

  it('an invalid pattern matches NO row and never throws (R7.2)', () => {
    // A small catalogue of patterns that `new RegExp(...)` rejects.
    const invalidPatterns = fc.constantFrom(
      '([',
      '(',
      ')',
      '[',
      '\\',
      '*',
      '+',
      '?',
      'a{2,1}',
      '(?<',
    );
    fc.assert(
      fc.property(
        invalidPatterns,
        fc.array(fc.string(), { minLength: 1, maxLength: 20 }),
        (pattern, cells) => {
          // Precondition: the pattern really is invalid under 'i'.
          fc.pre(safeCompile(pattern) === null);

          const rows = cells.map(rowWith);
          const result = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'regex', value: pattern } },
            FIELD_CONFIG,
          );
          // Invalid pattern → never-match sentinel → no row matches.
          return result.length === 0;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('a valid pattern matches case-insensitively by the compiled RegExp (R7.1)', () => {
    fc.assert(
      fc.property(
        // A literal needle with at least one cased letter so the
        // case-insensitive flag is observable, escaped so it is a VALID literal
        // pattern.
        fc
          .string({ minLength: 1, maxLength: 8 })
          .filter((s) => s.trim() !== '' && /[a-zA-Z]/.test(s)),
        fc.string({ maxLength: 6 }),
        fc.string({ maxLength: 6 }),
        (needle, prefix, suffix) => {
          const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

          // Cell embeds an upper-cased needle; query uses a lower-cased literal
          // pattern (and vice-versa) — the 'i' flag must match both.
          const cellUpper = `${prefix}${needle.toUpperCase()}${suffix}`;
          const cellLower = `${prefix}${needle.toLowerCase()}${suffix}`;

          const upperCellLowerPat = applyDefinitionFilters(
            [rowWith(cellUpper)],
            { [KEY]: { op: 'regex', value: escaped.toLowerCase() } },
            FIELD_CONFIG,
          );
          const lowerCellUpperPat = applyDefinitionFilters(
            [rowWith(cellLower)],
            { [KEY]: { op: 'regex', value: escaped.toUpperCase() } },
            FIELD_CONFIG,
          );

          return (
            upperCellLowerPat.length === 1 && lowerCellUpperPat.length === 1
          );
        },
      ),
      { numRuns: 100 },
    );
  });

  it('excludes an absent cell (a value-taking regex op never matches an absent value)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        (pattern) => {
          const rows = [{} as unknown as MemberRow];
          const result = applyDefinitionFilters(
            rows,
            { [KEY]: { op: 'regex', value: pattern } },
            FIELD_CONFIG,
          );
          return result.length === 0;
        },
      ),
      { numRuns: 100 },
    );
  });
});
