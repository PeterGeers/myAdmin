/**
 * Unit tests for the applications-inbox preset hook (Member Application Form,
 * task 7.2, R8b.4/R8b.5/F3).
 *
 * The hook owns ONLY the preset wiring over the Table Filter Framework v2 — it
 * introduces no grid. These tests pin that wiring:
 * - activating the inbox pins the `status` column filter to `application` (the
 *   inbox is a view over the one member grid — R8b.4/F3);
 * - activating / keyword-filtering surfaces the `overlay.additional_info` column
 *   so its keyword filter slot exists (R8b.5);
 * - `DUP` / `NO_NOTIFY` quick filters set the `additional_info` column filter to
 *   the stable keyword the SAM plane wrote (R8b.5);
 * - clearing drops both filters back to the full overview.
 *
 * **Validates: Requirements 8b.4, 8b.5**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useApplicationsInbox,
  APPLICATION_STATUS,
  ADDITIONAL_INFO_KEY,
  DUP_KEYWORD,
  NO_NOTIFY_KEYWORD,
} from '../useApplicationsInbox';

describe('useApplicationsInbox (task 7.2)', () => {
  let setFilter: ReturnType<typeof vi.fn>;
  let onColumnsChange: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setFilter = vi.fn();
    onColumnsChange = vi.fn();
  });

  const renderInbox = (chosenKeys: string[]) =>
    renderHook(() =>
      useApplicationsInbox({ setFilter, chosenKeys, onColumnsChange }),
    );

  it('keeps the SAM keyword tokens in lockstep (DUP / NO_NOTIFY)', () => {
    // These MUST match sam/members/domain/application_notification.py exactly,
    // else the inbox filter would miss the rows the create/notify path flagged.
    expect(DUP_KEYWORD).toBe('DUP');
    expect(NO_NOTIFY_KEYWORD).toBe('NO_NOTIFY');
    expect(APPLICATION_STATUS).toBe('application');
    expect(ADDITIONAL_INFO_KEY).toBe('additional_info');
  });

  it('activateInbox pins status=application (the inbox view over the one grid)', () => {
    const { result } = renderInbox(['name', 'email']);
    act(() => result.current.activateInbox());

    // The inbox is the existing grid with status pinned — NOT a new table.
    expect(setFilter).toHaveBeenCalledWith('status', APPLICATION_STATUS);
  });

  it('activateInbox surfaces the additional_info column when it is not already chosen', () => {
    const { result } = renderInbox(['name', 'email']);
    act(() => result.current.activateInbox());

    // The note column must be present so its keyword FilterableHeader renders
    // (R8b.5). The user's existing columns are preserved; the note column is ADDED.
    expect(onColumnsChange).toHaveBeenCalledWith(['name', 'email', ADDITIONAL_INFO_KEY]);
  });

  it('does NOT re-add the additional_info column when it is already chosen', () => {
    const { result } = renderInbox(['name', ADDITIONAL_INFO_KEY]);
    act(() => result.current.activateInbox());

    expect(onColumnsChange).not.toHaveBeenCalled();
    expect(setFilter).toHaveBeenCalledWith('status', APPLICATION_STATUS);
  });

  it('filterKeyword(DUP) narrows the inbox to the DUP note (status stays pinned)', () => {
    const { result } = renderInbox([ADDITIONAL_INFO_KEY]);
    act(() => result.current.filterKeyword(DUP_KEYWORD));

    expect(setFilter).toHaveBeenCalledWith('status', APPLICATION_STATUS);
    expect(setFilter).toHaveBeenCalledWith(ADDITIONAL_INFO_KEY, DUP_KEYWORD);
  });

  it('filterKeyword(NO_NOTIFY) narrows the inbox to the NO_NOTIFY note', () => {
    const { result } = renderInbox([ADDITIONAL_INFO_KEY]);
    act(() => result.current.filterKeyword(NO_NOTIFY_KEYWORD));

    expect(setFilter).toHaveBeenCalledWith(ADDITIONAL_INFO_KEY, NO_NOTIFY_KEYWORD);
  });

  it('clearInbox drops both the status and additional_info filters', () => {
    const { result } = renderInbox([ADDITIONAL_INFO_KEY]);
    act(() => result.current.clearInbox());

    expect(setFilter).toHaveBeenCalledWith('status', '');
    expect(setFilter).toHaveBeenCalledWith(ADDITIONAL_INFO_KEY, '');
  });
});
