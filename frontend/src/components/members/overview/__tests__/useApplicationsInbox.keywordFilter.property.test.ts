/**
 * Property-based test for the applications-inbox keyword quick-filter
 * (members-overview-tweaks, task 8.4, Req 6.4).
 *
 * The applications inbox is NOT a new grid — it is the existing member overview
 * grid viewed through the Table Filter Framework v2 (`useFilterableTable` →
 * `useColumnFilters`). `useApplicationsInbox.filterKeyword('DUP' | 'NO_NOTIFY')`
 * drives that framework with TWO filters at once:
 *   - the `status = application` pin (the inbox view), and
 *   - the `additional_info` column filter set to the stable keyword token the
 *     SAM create/notify path wrote into `overlay.additional_info`.
 *
 * The framework's `additional_info` column is the overlay note field flattened
 * to a top-level, filterable column; the column filter is a case-insensitive
 * substring match (see `useColumnFilters.applyFilters`). This test drives the
 * framework with the exact filter config the hook sets — rather than rendering
 * the full page — and asserts the narrowing invariant across randomized rows.
 *
 * Uses fast-check with a minimum of 100 iterations.
 *
 * Feature: members-overview-tweaks, Property 7: Keyword filter narrows the inbox to matching notes
 * Validates: Requirements 6.4
 */

import { vi, describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import fc from 'fast-check';
import { useFilterableTable } from '../../../../hooks/useFilterableTable';
import {
  APPLICATION_STATUS,
  ADDITIONAL_INFO_KEY,
  DUP_KEYWORD,
  NO_NOTIFY_KEYWORD,
  type InboxKeyword,
} from '../useApplicationsInbox';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Varied lifecycle statuses — some pinned (`application`), some not. */
const statusArbitrary = fc.constantFrom(
  'application',
  'active',
  'inactive',
  'pending',
  'archived',
  'cancelled',
);

/** The keyword a reviewer quick-filters by (the SAM-side tokens). */
const keywordArbitrary = fc.constantFrom<InboxKeyword>(DUP_KEYWORD, NO_NOTIFY_KEYWORD);

/**
 * Build an `additional_info` note that may or may not carry a keyword token,
 * in varied case, surrounded by varied free text — mirroring the space-separated
 * note the create/notify path appends the token to. This exercises:
 *  - notes containing DUP, containing NO_NOTIFY, containing both, or neither;
 *  - varied casing of the token (the match is case-insensitive);
 *  - the substring nature of the match (token embedded in surrounding text).
 */
const additionalInfoArbitrary = fc
  .record({
    prefix: fc.string({ minLength: 0, maxLength: 10 }),
    token: fc.constantFrom('DUP', 'dup', 'Dup', 'NO_NOTIFY', 'no_notify', 'No_Notify', '', 'OTHER'),
    suffix: fc.string({ minLength: 0, maxLength: 10 }),
  })
  .map(({ prefix, token, suffix }) => `${prefix} ${token} ${suffix}`.trim());

/**
 * A member row as the inbox grid sees it: the overlay `additional_info` note is
 * flattened to a top-level, filterable `additional_info` column (the column the
 * framework filters on), while the original nested `overlay.additional_info`
 * stays on the row (what the invariant reads). Both carry the SAME note so the
 * flattened column the hook filters is the overlay note the design pins.
 */
const rowArbitrary = fc
  .record({
    member_id: fc.stringMatching(/^[a-z0-9]{1,8}$/),
    status: statusArbitrary,
    note: additionalInfoArbitrary,
  })
  .map(({ member_id, status, note }) => ({
    member_id,
    status,
    // Flattened filterable column the framework's `additional_info` filter reads.
    [ADDITIONAL_INFO_KEY]: note,
    // The original nested overlay the invariant asserts over.
    overlay: { additional_info: note },
  }));

const rowsArbitrary = fc.array(rowArbitrary, { minLength: 0, maxLength: 25 });

// ---------------------------------------------------------------------------
// Property 7: Keyword filter narrows the inbox to matching notes
// ---------------------------------------------------------------------------

describe('Feature: members-overview-tweaks, Property 7: Keyword filter narrows the inbox to matching notes', () => {
  /**
   * Feature: members-overview-tweaks, Property 7: Keyword filter narrows the inbox to matching notes
   * Validates: Requirements 6.4
   *
   * For any set of member rows and any keyword in {DUP, NO_NOTIFY}, after the
   * inbox keyword filter is applied (status pinned to `application` AND the
   * `additional_info` column filtered to the keyword, exactly as
   * `useApplicationsInbox.filterKeyword` drives the framework), every displayed
   * row's `overlay.additional_info` contains the keyword (case-insensitive,
   * matching the framework's case handling) AND every displayed row still has
   * `status === 'application'` (the pin holds).
   */
  it('every displayed row matches the keyword and keeps the status=application pin', () => {
    fc.assert(
      fc.property(rowsArbitrary, keywordArbitrary, (rows, keyword) => {
        vi.useFakeTimers();

        try {
          // The inbox filters on the pinned `status` column AND the flattened
          // `additional_info` note column — the two-filter config the hook sets.
          const initialFilters = { status: '', [ADDITIONAL_INFO_KEY]: '' };

          const { result } = renderHook(() =>
            useFilterableTable(rows, { initialFilters }),
          );

          // Drive the framework the way `filterKeyword` does: pin the status to
          // `application` AND narrow `additional_info` to the keyword token.
          act(() => {
            result.current.setFilter('status', APPLICATION_STATUS);
            result.current.setFilter(ADDITIONAL_INFO_KEY, keyword);
          });
          act(() => {
            vi.advanceTimersByTime(300); // flush the framework's debounce
          });

          const displayed = result.current.processedData;

          for (const row of displayed) {
            // Invariant part 1: the status=application pin holds for every row.
            expect(row.status).toBe(APPLICATION_STATUS);

            // Invariant part 2: the displayed row's overlay note contains the
            // keyword, matching the framework's case-insensitive substring match.
            const note = String(row.overlay?.additional_info ?? '').toLowerCase();
            expect(note).toContain(keyword.toLowerCase());
          }
        } finally {
          vi.useRealTimers();
        }
      }),
      { numRuns: 100 },
    );
  });
});
