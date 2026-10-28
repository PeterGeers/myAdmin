/**
 * Tests for the Members Overview row-selection hook (useMembersSelection.ts).
 *
 * Covers the bulk-actions selection branch logic (R8.6):
 *  - toggleRow add/remove
 *  - toggleSelectAll over the VISIBLE rows (select-all then clear-all branch)
 *  - allVisibleSelected / someVisibleSelected derivation (incl. empty view)
 *  - clearSelection
 *  - selection persisting across a visible-data (filter/sort) change
 *
 * Pure state hook — no network, no mocks.
 */

import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { MemberRow } from '../../../types/members';
import { useMembersSelection } from './useMembersSelection';

const row = (id: string): MemberRow => ({ member_id: id });

const rows = (...ids: string[]): MemberRow[] => ids.map(row);

describe('useMembersSelection', () => {
  it('starts with an empty selection', () => {
    const { result } = renderHook(() => useMembersSelection(rows('a', 'b')));

    expect(result.current.selectedIds.size).toBe(0);
    expect(result.current.selectedIdList).toEqual([]);
    expect(result.current.visibleIds).toEqual(['a', 'b']);
    expect(result.current.allVisibleSelected).toBe(false);
    expect(result.current.someVisibleSelected).toBe(false);
  });

  it('toggleRow adds then removes a single id', () => {
    const { result } = renderHook(() => useMembersSelection(rows('a', 'b')));

    act(() => result.current.toggleRow('a'));
    expect(result.current.selectedIds.has('a')).toBe(true);
    expect(result.current.selectedIdList).toEqual(['a']);
    expect(result.current.someVisibleSelected).toBe(true);
    expect(result.current.allVisibleSelected).toBe(false);

    act(() => result.current.toggleRow('a'));
    expect(result.current.selectedIds.has('a')).toBe(false);
    expect(result.current.someVisibleSelected).toBe(false);
  });

  it('toggleSelectAll selects every visible row, then clears them on the second call', () => {
    const { result } = renderHook(() => useMembersSelection(rows('a', 'b', 'c')));

    act(() => result.current.toggleSelectAll());
    expect(result.current.allVisibleSelected).toBe(true);
    expect(result.current.someVisibleSelected).toBe(false);
    expect(new Set(result.current.selectedIdList)).toEqual(new Set(['a', 'b', 'c']));

    act(() => result.current.toggleSelectAll());
    expect(result.current.allVisibleSelected).toBe(false);
    expect(result.current.selectedIds.size).toBe(0);
  });

  it('someVisibleSelected is true only for a partial selection', () => {
    const { result } = renderHook(() => useMembersSelection(rows('a', 'b')));

    act(() => result.current.toggleRow('a'));
    expect(result.current.someVisibleSelected).toBe(true);
    expect(result.current.allVisibleSelected).toBe(false);

    act(() => result.current.toggleRow('b'));
    expect(result.current.someVisibleSelected).toBe(false);
    expect(result.current.allVisibleSelected).toBe(true);
  });

  it('allVisibleSelected stays false when there are no visible rows', () => {
    const { result } = renderHook(() => useMembersSelection([]));

    expect(result.current.allVisibleSelected).toBe(false);
    // toggleSelectAll on an empty view is a no-op
    act(() => result.current.toggleSelectAll());
    expect(result.current.selectedIds.size).toBe(0);
  });

  it('clearSelection empties a non-empty selection', () => {
    const { result } = renderHook(() => useMembersSelection(rows('a', 'b')));

    act(() => result.current.toggleSelectAll());
    expect(result.current.selectedIds.size).toBe(2);

    act(() => result.current.clearSelection());
    expect(result.current.selectedIds.size).toBe(0);
    expect(result.current.selectedIdList).toEqual([]);
  });

  it('keeps selected ids when the visible data changes (filter/sort), updating derived view state', () => {
    const { result, rerender } = renderHook(
      ({ data }) => useMembersSelection(data),
      { initialProps: { data: rows('a', 'b') } },
    );

    act(() => result.current.toggleRow('a'));
    expect(result.current.allVisibleSelected).toBe(false);

    // Re-filter so only 'a' is visible — the selection is unchanged but now
    // every VISIBLE row is selected.
    rerender({ data: rows('a') });

    expect(result.current.selectedIds.has('a')).toBe(true);
    expect(result.current.visibleIds).toEqual(['a']);
    expect(result.current.allVisibleSelected).toBe(true);
    expect(result.current.someVisibleSelected).toBe(false);
  });
});
