/**
 * Members Overview — rows-per-page selector + cursor prev/next footer
 * (spec 02, Task 1.17 / Requirement 25).
 *
 * REPLACES the former client-side pageIndex/pageCount pager with a
 * Rows_Per_Page_Selector (50/100/250/500/Max) + DynamoDB cursor prev/next,
 * mirroring the FIN/SysAdmin rows-per-page dropdown pattern
 * (`SysAdmin/TenantTable.tsx`) adapted for cursor paging (no jump-to-page).
 *
 * The control is purely presentational: the fetch + cursor walk live in
 * `useMembersCursorPaging`. Next is disabled when no next-page cursor was
 * returned (final page, R25.5); Prev is disabled on the first page (R25.6).
 */

import React from 'react';
import { Flex, Text, HStack, Button, Select } from '@chakra-ui/react';
import {
  MEMBERS_FIXED_PAGE_SIZES,
  MEMBERS_PAGE_SIZE_MAX,
} from '../../../services/members/membersPageSize';
import type { MembersPageSize } from '../../../services/members/membersPageSize';

export interface MembersPaginationBarProps {
  loading: boolean;
  /** The selected rows-per-page option (a fixed size or `'max'`). */
  pageSize: MembersPageSize;
  /** Select a new rows-per-page option. */
  onPageSizeChange: (next: MembersPageSize) => void;
  /** True when a next page exists (R25.5). */
  canNext: boolean;
  /** True when a previous page exists (R25.6). */
  canPrev: boolean;
  onNext: () => void;
  onPrev: () => void;
  /** The number of rows on the CURRENT page (for the status label). */
  pageItemCount: number;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

/** Parse the `<Select>` value back to a `MembersPageSize` (the `'max'` sentinel or an int). */
function toPageSize(raw: string): MembersPageSize {
  return raw === MEMBERS_PAGE_SIZE_MAX
    ? MEMBERS_PAGE_SIZE_MAX
    : (Number(raw) as MembersPageSize);
}

export const MembersPaginationBar: React.FC<MembersPaginationBarProps> = ({
  loading,
  pageSize,
  onPageSizeChange,
  canNext,
  canPrev,
  onNext,
  onPrev,
  pageItemCount,
  t,
}) => {
  if (loading) return null;

  return (
    <Flex justify="space-between" align="center" mt={4} wrap="wrap" gap={2}>
      {/* Rows_Per_Page_Selector (R25.1) — 50/100/250/500/Max. */}
      <HStack spacing={2}>
        <Text color="gray.400" fontSize="sm">{t('pagination.rowsPerPage')}:</Text>
        <Select
          value={String(pageSize)}
          onChange={e => onPageSizeChange(toPageSize(e.target.value))}
          bg="gray.600"
          color="white"
          borderColor="gray.500"
          size="sm"
          maxW="100px"
          data-testid="members-page-size-select"
          aria-label={t('pagination.rowsPerPage')}
        >
          {MEMBERS_FIXED_PAGE_SIZES.map(size => (
            <option
              key={String(size)}
              style={{ background: '#2D3748', color: 'white' }}
              value={String(size)}
            >
              {size}
            </option>
          ))}
          <option
            style={{ background: '#2D3748', color: 'white' }}
            value={MEMBERS_PAGE_SIZE_MAX}
          >
            {t('pagination.max')}
          </option>
        </Select>
        <Text color="gray.500" fontSize="sm" data-testid="members-pagination-status">
          {t('pagination.showing', { count: pageItemCount })}
        </Text>
      </HStack>

      {/* Cursor prev/next (R25.4) — no jump-to-page, no SQL-style offset. */}
      <HStack spacing={2}>
        <Button
          size="sm"
          variant="ghost"
          colorScheme="orange"
          onClick={onPrev}
          isDisabled={!canPrev}
          data-testid="members-pagination-prev"
        >
          {t('pagination.previous')}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          colorScheme="orange"
          onClick={onNext}
          isDisabled={!canNext}
          data-testid="members-pagination-next"
        >
          {t('pagination.next')}
        </Button>
      </HStack>
    </Flex>
  );
};
