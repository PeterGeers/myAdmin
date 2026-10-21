/**
 * Property-based test for the applications-inbox status pin
 * (members-overview-tweaks, task 8.3).
 *
 * The applications inbox is NOT a new grid: `useApplicationsInbox` pins the
 * `status` column of the shared Table Filter Framework v2 to `application` via
 * `setFilter('status', APPLICATION_STATUS)` (see `useApplicationsInbox.ts`). The
 * actual row narrowing happens in the framework's `useColumnFilters` /
 * `useFilterableTable` (case-insensitive substring match). So this test drives
 * the SAME mechanism the inbox relies on — it pins `status = application` through
 * `useFilterableTable`'s `setFilter` and asserts the resulting `processedData`,
 * rather than reimplementing the predicate or rendering the whole page.
 *
 * Property 6 invariant (both directions):
 *  - soundness:     every displayed row has `status === 'application'`;
 *  - completeness:  no input row whose `status === 'application'` is dropped.
 *
 * Uses fast-check 4.4.0, min 100 iterations.
 *
 * **Feature: members-overview-tweaks, Property 6: Applications inbox shows only status=application rows**
 * **Validates: Requirements 6.3**
 */

import { vi, describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import fc from 'fast-check';
import { useFilterableTable } from '../../../../hooks/useFilterableTable';
import { APPLICATION_STATUS } from '../useApplicationsInbox';

interface MemberRow extends Record<string, any> {
  id: number;
  status: string;
  name: string;
}

/**
 * Varied member lifecycle statuses. `application` is the pinned one; the others
 * are the real non-application statuses. None of the non-application statuses
 * contains the substring "application", so the framework's case-insensitive
 * substring match is equivalent to equality over this domain — exactly what the
 * inbox pin means in practice.
 */
const NON_APPLICATION_STATUSES = [
  'active',
  'lapsed',
  'prospect',
  'resigned',
  'deceased',
  'honorary',
  'pending',
  'suspended',
] as const;

/** A single status: either the pinned `application` or a varied other status. */
const statusArbitrary = fc.oneof(
  { weight: 1, arbitrary: fc.constant(APPLICATION_STATUS) },
  { weight: 2, arbitrary: fc.constantFrom(...NON_APPLICATION_STATUSES) },
);

/** A member row with an index-stamped id so rows stay identity-distinct. */
const rowArbitrary = fc.record({
  status: statusArbitrary,
  name: fc.string({ minLength: 0, maxLength: 8 }),
});

describe('Property 6: Applications inbox shows only status=application rows', () => {
  /**
   * **Feature: members-overview-tweaks, Property 6: Applications inbox shows only status=application rows**
   * **Validates: Requirements 6.3**
   *
   * For any set of member rows with varied statuses, pinning the shared table
   * filter to `status = application` (the exact mechanism `useApplicationsInbox`
   * uses) yields a view where every displayed row is an application AND every
   * application row survives.
   */
  it('status pin keeps exactly the application rows (sound + complete)', () => {
    fc.assert(
      fc.property(
        fc.array(rowArbitrary, { minLength: 0, maxLength: 40 }),
        (rawRows) => {
          vi.useFakeTimers();
          try {
            const rows: MemberRow[] = rawRows.map((r, i) => ({ ...r, id: i }));

            const { result } = renderHook(() =>
              useFilterableTable<MemberRow>(rows, {
                // The inbox surfaces `status` (and `additional_info`) as
                // filterable columns; only `status` is pinned here.
                initialFilters: { status: '', additional_info: '' },
              }),
            );

            // Pin status=application exactly as useApplicationsInbox does.
            act(() => {
              result.current.setFilter('status', APPLICATION_STATUS);
            });
            act(() => {
              vi.advanceTimersByTime(300);
            });

            const displayed = result.current.processedData;

            // Soundness: every displayed row is an application.
            for (const row of displayed) {
              expect(row.status).toBe(APPLICATION_STATUS);
            }

            // Completeness: no application row was dropped. Compare by id set.
            const expectedIds = rows
              .filter((r) => r.status === APPLICATION_STATUS)
              .map((r) => r.id)
              .sort((a, b) => a - b);
            const displayedIds = displayed
              .map((r) => r.id)
              .sort((a, b) => a - b);
            expect(displayedIds).toEqual(expectedIds);
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
