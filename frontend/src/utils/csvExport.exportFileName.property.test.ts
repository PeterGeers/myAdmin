/**
 * Property-based test for the shared pivot-export filename rule.
 *
 * Feature: members-overview-tweaks, Property 3: Frontend download filename follows the tenant-pivot rule
 *
 * Targets the pure helper `exportFileName(tenantName, pivotName)` in
 * `./csvExport` (the single frontend naming rule mirrored on the SAM worker
 * plane). For any tenant name and pivot name the downloaded CSV filename equals
 * `sanitize(tenantName) + "-" + sanitize(pivotName) + ".csv"`, always ends in
 * `.csv`, is deterministic, and is never the fixed `members.csv`.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 5.1, 5.4
 * Spec: `.kiro/specs/members-overview-tweaks` (design Property 3).
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { exportFileName, sanitize } from './csvExport';

/**
 * A generator for realistic-but-adversarial tenant/pivot name parts. It mixes
 * plain words, spaces, ASCII punctuation, unicode (accented letters, CJK,
 * emoji), filesystem-hostile characters (path separators, control chars,
 * newlines/tabs), and empty parts — covering the full input space the design
 * calls out (spaces, punctuation, unicode, empty parts).
 */
const namePart = fc.oneof(
  // Empty / whitespace-only parts.
  fc.constantFrom('', '   ', '\t', '\n', '  \t\n  '),
  // Plain words with internal spaces.
  fc.constantFrom('Acme', 'Big Charity Foundation', 'Members by city', 'Donors'),
  // Punctuation-heavy names.
  fc.constantFrom('A.B,C;D', "O'Brien & Sons", '(2026) Q1 — report', '100% match!'),
  // Unicode: accents, CJK, emoji.
  fc.constantFrom('Stichting Café', '日本語ピボット', 'naïve résumé', 'donors 🎉'),
  // Filesystem-hostile: path separators and control chars.
  fc.constantFrom('a/b\\c', 'x\u0000y', 'line1\r\nline2', 'tab\there'),
  // Fully arbitrary strings. In fast-check 4.x `fc.string()` draws from the
  // full unicode range by default (control chars, surrogate pairs, etc.).
  fc.string(),
  fc.string({ unit: 'grapheme' }),
);

describe('Feature: members-overview-tweaks, Property 3: Frontend download filename follows the tenant-pivot rule', () => {
  it('equals sanitize(tenant) + "-" + sanitize(pivot) + ".csv" for any name pair (R5.1)', () => {
    fc.assert(
      fc.property(namePart, namePart, (tenantName, pivotName) => {
        const expected = `${sanitize(tenantName)}-${sanitize(pivotName)}.csv`;
        expect(exportFileName(tenantName, pivotName)).toBe(expected);
      }),
      { numRuns: 100 },
    );
  });

  it('always ends in .csv (R5.1, R5.4)', () => {
    fc.assert(
      fc.property(namePart, namePart, (tenantName, pivotName) => {
        expect(exportFileName(tenantName, pivotName).endsWith('.csv')).toBe(true);
      }),
      { numRuns: 100 },
    );
  });

  it('is deterministic — same inputs produce the same output (R5.1)', () => {
    fc.assert(
      fc.property(namePart, namePart, (tenantName, pivotName) => {
        expect(exportFileName(tenantName, pivotName)).toBe(
          exportFileName(tenantName, pivotName),
        );
      }),
      { numRuns: 100 },
    );
  });

  it('is never the fixed members.csv (R5.4)', () => {
    fc.assert(
      fc.property(namePart, namePart, (tenantName, pivotName) => {
        // The rule always embeds the "-" separator before ".csv", so a bare
        // "members.csv" (no separator) can never be produced for any input.
        expect(exportFileName(tenantName, pivotName)).not.toBe('members.csv');
      }),
      { numRuns: 100 },
    );
  });
});
