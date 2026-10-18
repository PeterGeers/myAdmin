/**
 * Members Overview — "Applications inbox" preset (Member Application Form, task 7.2).
 *
 * R8b.4 / R8b.5 / F3: the staff-facing applications inbox is NOT a new grid — it
 * is the EXISTING authenticated member overview grid, viewed through the standard
 * Table Filter Framework v2 with the `status` column pinned to `application`. On
 * top of that, the possible-duplicate (`DUP`) and un-notifiable (`NO_NOTIFY`)
 * keyword tokens the SAM create/notify path writes to `overlay.additional_info`
 * (tasks 2.5 / 6.4) must be keyword-FILTERABLE in that same grid, so a reviewer
 * can narrow the inbox to just the possible-duplicate or un-notified applications.
 *
 * This hook owns ONLY the preset wiring — it composes the framework, it does not
 * rebuild it:
 *   - `activateInbox()` pins the `status` filter to `application` (the inbox view)
 *     and ensures the `overlay.additional_info` column is surfaced so its
 *     FilterableHeader keyword slot exists;
 *   - `filterKeyword('DUP' | 'NO_NOTIFY')` sets the `additional_info` column filter
 *     to the stable keyword (substring match via the framework);
 *   - `clearInbox()` drops both filters back to the full, unfiltered overview.
 *
 * The `status` column is an existing compact column (always filterable); the
 * `additional_info` column is an overlay field promoted to a flat, filterable
 * column by the unified column model's on-the-fly flatten once it is chosen — so
 * both filters resolve entirely through the generic framework, no bespoke grid.
 *
 * Keywords are kept in lockstep with the SAM-side constants
 * (`sam/members/domain/application_notification.py`:
 * `_DUP_KEYWORD = "DUP"`, `NO_NOTIFY_KEYWORD = "NO_NOTIFY"`).
 *
 * _Requirements: R8b.4, R8b.5, F3_
 */

import { useCallback } from 'react';

/** The lifecycle status that the applications inbox pins the `status` filter to. */
export const APPLICATION_STATUS = 'application';

/** The overlay free-text column the `DUP` / `NO_NOTIFY` keyword notes ride on. */
export const ADDITIONAL_INFO_KEY = 'additional_info';

/**
 * The stable keyword tokens the SAM plane appends to `overlay.additional_info`
 * (tasks 2.5 / 6.4). MUST match the SAM constants exactly so the inbox filter
 * matches the rows the create/notify path flagged.
 */
export const DUP_KEYWORD = 'DUP';
export const NO_NOTIFY_KEYWORD = 'NO_NOTIFY';

/** The keyword tokens a reviewer can quick-filter the inbox by (R8b.5). */
export type InboxKeyword = typeof DUP_KEYWORD | typeof NO_NOTIFY_KEYWORD;

export interface UseApplicationsInboxParams {
  /**
   * The framework's single-filter setter (`useFilterableTable().setFilter`). Pins
   * the `status` / `additional_info` column filters — the inbox is a view over the
   * one grid, never a new table.
   */
  setFilter: (key: string, value: string) => void;
  /**
   * The user's current chosen column keys (the overview column model). The inbox
   * ensures `additional_info` is among them so its keyword filter slot exists.
   */
  chosenKeys: string[];
  /**
   * The overview column-preference setter (`useMembersData().handleColumnsChange`).
   * Used only to ADD the `additional_info` column when activating the inbox; the
   * user's other columns are preserved.
   */
  onColumnsChange: (keys: string[]) => void;
}

export interface UseApplicationsInboxReturn {
  /** Pin the grid to the `status = application` inbox view + surface the note column. */
  activateInbox: () => void;
  /** Quick-filter the inbox to rows carrying a keyword note (`DUP` / `NO_NOTIFY`). */
  filterKeyword: (keyword: InboxKeyword) => void;
  /** Clear the inbox view: drop the `status` and `additional_info` column filters. */
  clearInbox: () => void;
}

/**
 * Compose the Table Filter Framework v2 into the applications-inbox preset
 * (task 7.2). Pure wiring over the framework's `setFilter` + the overview column
 * model — introduces NO grid and NO filtering engine of its own.
 */
export function useApplicationsInbox({
  setFilter,
  chosenKeys,
  onColumnsChange,
}: UseApplicationsInboxParams): UseApplicationsInboxReturn {
  // Surface the `additional_info` column (if not already chosen) so its
  // FilterableHeader — and thus its keyword filter slot — renders. Preserve the
  // user's existing columns; only ADD the note column.
  const ensureNoteColumn = useCallback(() => {
    if (!chosenKeys.includes(ADDITIONAL_INFO_KEY)) {
      onColumnsChange([...chosenKeys, ADDITIONAL_INFO_KEY]);
    }
  }, [chosenKeys, onColumnsChange]);

  const activateInbox = useCallback(() => {
    ensureNoteColumn();
    setFilter('status', APPLICATION_STATUS);
  }, [ensureNoteColumn, setFilter]);

  const filterKeyword = useCallback(
    (keyword: InboxKeyword) => {
      ensureNoteColumn();
      // Stay in the inbox view AND narrow to the keyword note. `setFilter` on the
      // `additional_info` column is a case-insensitive substring match, so the
      // stable `DUP` / `NO_NOTIFY` token matches wherever it sits in the
      // space-separated note field.
      setFilter('status', APPLICATION_STATUS);
      setFilter(ADDITIONAL_INFO_KEY, keyword);
    },
    [ensureNoteColumn, setFilter],
  );

  const clearInbox = useCallback(() => {
    setFilter('status', '');
    setFilter(ADDITIONAL_INFO_KEY, '');
  }, [setFilter]);

  return { activateInbox, filterKeyword, clearInbox };
}
