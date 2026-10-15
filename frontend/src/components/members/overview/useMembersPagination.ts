/**
 * Members Overview — client-side pagination hook. Extracted from
 * `pages/MembersPage.tsx` during the file-length split (code-quality-fixes
 * 2026-10-15, task 6) with ZERO behaviour change: the page-size resolution, the
 * page-count derivation, the clamp effect, and the in-memory slice are moved
 * verbatim (same order + dependencies). All scope-authorized rows are already
 * loaded; this is a pure in-memory pager over the filtered/sorted set.
 */

import React, { useState, useEffect, useMemo } from 'react';
import { resolvePageSize } from '../../../pages/membersPagination';
import type { MemberRow, FieldConfig } from '../../../types/members';

export interface UseMembersPaginationReturn {
  pageIndex: number;
  setPageIndex: React.Dispatch<React.SetStateAction<number>>;
  pageSize: number;
  pageCount: number;
  visibleData: MemberRow[];
}

export function useMembersPagination(
  processedData: MemberRow[],
  userPageSize: number | null,
  fieldConfig: FieldConfig | null,
): UseMembersPaginationReturn {
  // Current (zero-based) page index for the client-side prev/next pager. Reset/
  // clamped when the filtered set or page size changes (see the clamp effect).
  const [pageIndex, setPageIndex] = useState(0);

  // ── Rows-per-page precedence (Members config redesign Phase 2, step (a)) ──────
  // Resolve the page size by `userPreference ?? default_page_size ??
  // platformDefault` (the resolver mirrors the backend read-side guard — never
  // 0/blank, Property 1).
  const pageSize = useMemo(
    () => resolvePageSize(userPageSize, fieldConfig?.default_page_size),
    [userPageSize, fieldConfig],
  );
  // Total number of pages for the current filtered/searched set at the resolved
  // page size (at least 1; a non-positive page size means "show all" → 1 page).
  const pageCount = useMemo(
    () => (pageSize > 0 ? Math.max(1, Math.ceil(processedData.length / pageSize)) : 1),
    [processedData.length, pageSize],
  );
  // Keep the current page in range when the data set or page size changes.
  useEffect(() => {
    setPageIndex(i => Math.min(i, pageCount - 1));
  }, [pageCount]);
  const visibleData: MemberRow[] = useMemo(
    () => {
      if (pageSize <= 0) return processedData;
      const start = pageIndex * pageSize;
      return processedData.slice(start, start + pageSize);
    },
    [processedData, pageSize, pageIndex],
  );

  return { pageIndex, setPageIndex, pageSize, pageCount, visibleData };
}
