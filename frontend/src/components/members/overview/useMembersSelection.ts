/**
 * Members Overview — row-selection hook for the bulk actions (task 20.4, R8.6).
 * Extracted from `pages/MembersPage.tsx` during the file-length split
 * (code-quality-fixes 2026-10-15, task 6) with ZERO behaviour change: the
 * selection set, the select-all/row toggles, and the derived selection state are
 * moved verbatim. The select-all header toggles every VISIBLE row so the
 * selection tracks the shared filter/sort framework's current view.
 */

import { useState, useMemo, useCallback } from 'react';
import type { MemberRow } from '../../../types/members';

export interface UseMembersSelectionReturn {
  selectedIds: Set<string>;
  selectedIdList: string[];
  visibleIds: string[];
  allVisibleSelected: boolean;
  someVisibleSelected: boolean;
  toggleSelectAll: () => void;
  toggleRow: (id: string) => void;
  clearSelection: () => void;
}

export function useMembersSelection(visibleData: MemberRow[]): UseMembersSelectionReturn {
  // Row selection for bulk actions (task 20.4): the set of selected member_ids.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const visibleIds = useMemo(
    () => visibleData.map(r => r.member_id),
    [visibleData],
  );

  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
  const someVisibleSelected =
    visibleIds.some(id => selectedIds.has(id)) && !allVisibleSelected;

  const toggleSelectAll = useCallback(() => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (visibleIds.every(id => next.has(id))) {
        // All visible already selected → clear them.
        visibleIds.forEach(id => next.delete(id));
      } else {
        visibleIds.forEach(id => next.add(id));
      }
      return next;
    });
  }, [visibleIds]);

  const toggleRow = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const selectedIdList = useMemo(() => Array.from(selectedIds), [selectedIds]);

  return {
    selectedIds,
    selectedIdList,
    visibleIds,
    allVisibleSelected,
    someVisibleSelected,
    toggleSelectAll,
    toggleRow,
    clearSelection,
  };
}
