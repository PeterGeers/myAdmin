/**
 * Members Overview — client-side prev/next pager footer (mirrors the ZZPTrips
 * footer pattern). Extracted from `pages/MembersPage.tsx` during the file-length
 * split (code-quality-fixes 2026-10-15, task 6) with ZERO behaviour change: the
 * visibility gate (`!loading && pageSize > 0 && pageCount > 1`), the status
 * label, and the prev/next buttons are moved verbatim. All navigates in-memory
 * pages of the filtered/sorted set the page already loaded.
 */

import React from 'react';
import { Flex, Text, HStack, Button } from '@chakra-ui/react';

export interface MembersPaginationBarProps {
  loading: boolean;
  pageSize: number;
  pageIndex: number;
  pageCount: number;
  setPageIndex: React.Dispatch<React.SetStateAction<number>>;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

export const MembersPaginationBar: React.FC<MembersPaginationBarProps> = ({
  loading,
  pageSize,
  pageIndex,
  pageCount,
  setPageIndex,
  t,
}) => {
  if (loading || pageSize <= 0 || pageCount <= 1) return null;

  return (
    <Flex justify="space-between" align="center" mt={4} wrap="wrap" gap={2}>
      <Text color="gray.400" fontSize="sm" data-testid="members-pagination-status">
        {t('pagination.pageOf', { page: pageIndex + 1, total: pageCount })}
      </Text>
      <HStack spacing={2}>
        <Button
          size="sm"
          variant="ghost"
          colorScheme="orange"
          onClick={() => setPageIndex(i => Math.max(0, i - 1))}
          isDisabled={pageIndex <= 0}
          data-testid="members-pagination-prev"
        >
          {t('pagination.previous')}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          colorScheme="orange"
          onClick={() => setPageIndex(i => Math.min(pageCount - 1, i + 1))}
          isDisabled={pageIndex >= pageCount - 1}
          data-testid="members-pagination-next"
        >
          {t('pagination.next')}
        </Button>
      </HStack>
    </Flex>
  );
};
