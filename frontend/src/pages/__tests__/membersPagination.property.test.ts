/**
 * Pagination precedence — Property 1 (Phase 2, task 2.2).
 *
 * **Property 1: Pagination precedence is total and deterministic.**
 * For any combination of (user page-size preference present/absent, tenant `default_page_size`
 * present/absent), the resolved rows-per-page equals the FIRST PRESENT of
 * `userPreference → default_page_size → platformDefault`, and ALWAYS resolves to a positive
 * integer (never blank, never zero, never NaN).
 *
 * **Validates: Requirements 2.2, 2.3, 2.4, 9.4**
 *
 * Targets the single exported resolver `resolvePageSize` (`../membersPagination`) — the SPA
 * read path (task 2.1) consumes the SAME function, so this property locks the real behaviour,
 * not a duplicate. Uses fast-check 4.4.0 for the universal legs and an explicit
 * (present/absent × present/absent) matrix of random positive ints for the precedence legs.
 *
 * @see .kiro/specs/Members/Parameter redesign/phase-2-delete-redundant-surface/requirements.md
 *      — Property 1
 */

import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import {
  resolvePageSize,
  PLATFORM_DEFAULT_PAGE_SIZE,
  type PageSizeCandidate,
} from '../membersPagination';

// A random POSITIVE integer page size (the only values that count as "present").
const positiveIntArbitrary = fc.integer({ min: 1, max: 10_000 });

// The "absent" candidates: null / undefined — the shapes a missing preference or an unset
// tenant default actually take on the field-config / preference read paths.
const absentArbitrary = fc.constantFrom<PageSizeCandidate>(null, undefined);

// A candidate that is EITHER a present positive int OR absent.
const candidateArbitrary = fc.oneof(positiveIntArbitrary, absentArbitrary);

const isPresent = (v: PageSizeCandidate): v is number => typeof v === 'number';

describe('Property 1: pagination precedence is total and deterministic', () => {
  it('resolves to the first present of (userPref, tenantDefault, platformDefault) — full 4-way matrix', () => {
    fc.assert(
      fc.property(
        candidateArbitrary,
        candidateArbitrary,
        positiveIntArbitrary, // platform default is always a positive int by construction
        (userPref, tenantDefault, platformDefault) => {
          const resolved = resolvePageSize(userPref, tenantDefault, platformDefault);

          // Expected = first present of the chain.
          const expected = isPresent(userPref)
            ? userPref
            : isPresent(tenantDefault)
              ? tenantDefault
              : platformDefault;

          expect(resolved).toBe(expected);
          // Totality: always a positive integer, never 0 / NaN / blank.
          expect(Number.isInteger(resolved)).toBe(true);
          expect(resolved).toBeGreaterThan(0);
        },
      ),
      { numRuns: 300 },
    );
  });

  it('always resolves to a positive integer across the default platform fallback', () => {
    fc.assert(
      fc.property(candidateArbitrary, candidateArbitrary, (userPref, tenantDefault) => {
        // No explicit platformDefault → the module's PLATFORM_DEFAULT_PAGE_SIZE applies.
        const resolved = resolvePageSize(userPref, tenantDefault);

        expect(Number.isInteger(resolved)).toBe(true);
        expect(resolved).toBeGreaterThan(0);

        // When BOTH are absent, the platform default is used (R2.4).
        if (!isPresent(userPref) && !isPresent(tenantDefault)) {
          expect(resolved).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
        }
      }),
      { numRuns: 300 },
    );
  });

  it('is deterministic — identical inputs always yield the identical result', () => {
    fc.assert(
      fc.property(candidateArbitrary, candidateArbitrary, positiveIntArbitrary, (u, t, p) => {
        expect(resolvePageSize(u, t, p)).toBe(resolvePageSize(u, t, p));
      }),
      { numRuns: 200 },
    );
  });

  // Explicit 2×2 matrix (present/absent × present/absent) with random positive ints, so the
  // precedence legs are each hit as named cases (not just folded into the universal property).
  describe('explicit (userPref × tenantDefault) presence matrix', () => {
    const rand = (seed: number) => ((seed * 9301 + 49297) % 233280) % 500 + 1; // 1..500

    it('userPref present, tenantDefault present → userPref wins (R2.3)', () => {
      for (let i = 0; i < 50; i++) {
        const u = rand(i + 1);
        const t = rand(i + 999);
        expect(resolvePageSize(u, t, 25)).toBe(u);
      }
    });

    it('userPref absent, tenantDefault present → tenantDefault wins (R2.2)', () => {
      for (let i = 0; i < 50; i++) {
        const t = rand(i + 1);
        expect(resolvePageSize(null, t, 25)).toBe(t);
        expect(resolvePageSize(undefined, t, 25)).toBe(t);
      }
    });

    it('userPref present, tenantDefault absent → userPref wins (R2.3)', () => {
      for (let i = 0; i < 50; i++) {
        const u = rand(i + 7);
        expect(resolvePageSize(u, null, 25)).toBe(u);
        expect(resolvePageSize(u, undefined, 25)).toBe(u);
      }
    });

    it('both absent → platform default (R2.4)', () => {
      expect(resolvePageSize(null, null, 25)).toBe(25);
      expect(resolvePageSize(undefined, undefined, 25)).toBe(25);
      expect(resolvePageSize(null, undefined)).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
    });
  });
});
