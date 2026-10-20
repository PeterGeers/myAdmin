/**
 * Members Overview — rows-per-page selector + DynamoDB cursor paging hook
 * (spec 02, Task 1.17 / Requirement 25).
 *
 * REPLACES the former client-side `useMembersPagination` (slice an
 * already-fully-loaded array) with DynamoDB-native CURSOR paging: the page fetches
 * ONE server page at a time via `GET /members?page_size=&cursor=`, and prev/next
 * walk the opaque `LastEvaluatedKey` cursor the read path returns. There is no
 * SQL-style offset / jump-to-page (R25.7).
 *
 * The runtime selector is the per-user rows-per-page control (R25.1): the fixed
 * options (50/100/250/500) apply the value as the Query `Limit`; `'max'` omits the
 * `Limit` so DynamoDB returns one page up to its natural ~1 MB boundary (`Max` is
 * ONE Query page, NOT all rows, R25.3). The initial pre-selected option is a
 * PLATFORM FALLBACK (R25.9 — there is no tenant `default_page_size`, retired).
 *
 * Prev/next semantics (R25.4/R25.5/R25.6):
 * - NEXT is enabled only when the last query returned a cursor (a `LastEvaluated
 *   Key` remained); on the final page the cursor is `null` → Next disabled.
 * - PREV is enabled only when a previous-page cursor exists (we keep the stack of
 *   cursors that STARTED each visited page); on the first page → Prev disabled.
 * - Changing the page size RESETS to the first page (the cursor is page-size
 *   relative, so a stale cursor cannot carry across a size change).
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useToast } from '@chakra-ui/react';
import { listMembersPage } from '../../../services/membersApiService';
import { MEMBERS_DEFAULT_PAGE_SIZE } from '../../../services/members/membersPageSize';
import type { MembersPageSize } from '../../../services/members/membersPageSize';
import type { Member } from '../../../types/members';

export interface UseMembersCursorPagingReturn {
  /** The members on the CURRENT server page (already scope-narrowed server-side). */
  members: Member[];
  loading: boolean;
  /** The selected rows-per-page option (a fixed size or `'max'`). */
  pageSize: MembersPageSize;
  /** Select a new rows-per-page option; resets to the first page. */
  setPageSize: (next: MembersPageSize) => void;
  /** True when a next page exists (the last query returned a cursor, R25.5). */
  canNext: boolean;
  /** True when a previous page exists (not the first page, R25.6). */
  canPrev: boolean;
  /** Advance to the next page (no-op when `canNext` is false). */
  goNext: () => void;
  /** Return to the previous page (no-op when `canPrev` is false). */
  goPrev: () => void;
  /** Re-fetch the CURRENT page from the first page (used after a create/edit/delete). */
  reload: () => void;
}

export function useMembersCursorPaging(
  t: (key: string) => string
): UseMembersCursorPagingReturn {
  const toast = useToast();

  const [pageSize, setPageSizeState] = useState<MembersPageSize>(MEMBERS_DEFAULT_PAGE_SIZE);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);

  // The cursor that STARTS each visited page. `cursorStack[i]` is the cursor used
  // to fetch the page at depth `i` (depth 0 → `null`, the first page). The current
  // depth is `cursorStack.length - 1`. Prev pops; Next pushes the cursor the last
  // query returned. This is the ONLY paging state — no offset/index (R25.7).
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([null]);
  // The cursor the LAST successful query returned (the NEXT-page start), or `null`
  // on the final page (→ Next disabled, R25.5/R25.6).
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  // Guards an out-of-order response from clobbering a newer request's result
  // (fast prev/next clicks or a size change mid-flight).
  const requestSeq = useRef(0);

  const fetchPage = useCallback(
    async (size: MembersPageSize, cursor: string | null) => {
      const seq = ++requestSeq.current;
      try {
        setLoading(true);
        const page = await listMembersPage({ pageSize: size, cursor });
        if (seq !== requestSeq.current) return; // a newer request superseded this one
        setMembers(page.items);
        setNextCursor(page.cursor);
      } catch {
        if (seq !== requestSeq.current) return;
        toast({ title: t('table.empty'), status: 'error' });
        setMembers([]);
        setNextCursor(null);
      } finally {
        if (seq === requestSeq.current) setLoading(false);
      }
    },
    [toast, t]
  );

  // Fetch whenever the page size or the current page's start cursor changes.
  const currentCursor = cursorStack[cursorStack.length - 1] ?? null;
  useEffect(() => {
    void fetchPage(pageSize, currentCursor);
  }, [fetchPage, pageSize, currentCursor]);

  const setPageSize = useCallback((next: MembersPageSize) => {
    // A new size invalidates any accumulated cursor (it is page-size relative).
    setPageSizeState(next);
    setCursorStack([null]);
    setNextCursor(null);
  }, []);

  const canNext = nextCursor !== null;
  const canPrev = cursorStack.length > 1;

  const goNext = useCallback(() => {
    if (nextCursor === null) return;
    setCursorStack(stack => [...stack, nextCursor]);
  }, [nextCursor]);

  const goPrev = useCallback(() => {
    setCursorStack(stack => (stack.length > 1 ? stack.slice(0, -1) : stack));
  }, []);

  const reload = useCallback(() => {
    // Re-fetch from the first page (a create/edit/delete can shift the whole set).
    setCursorStack([null]);
    setNextCursor(null);
  }, []);

  return {
    members,
    loading,
    pageSize,
    setPageSize,
    canNext,
    canPrev,
    goNext,
    goPrev,
    reload,
  };
}
