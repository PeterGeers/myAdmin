/**
 * Members Overview — live statistics strip (task 4.3, design C-SURFACE; R5.4).
 * Extracted from `pages/MembersPage.tsx` during the file-length split
 * (code-quality-fixes 2026-10-15, task 6) with ZERO behaviour change: the markup
 * (including the deliberate `Box`/`Text` `StatCard` — Chakra's `Stat*` family is
 * `undefined` under the test runner's ESM interop) is moved verbatim.
 */

import React from 'react';
import { Box, Flex, Text } from '@chakra-ui/react';

export interface MembersStats {
  total: number;
  filtered: number;
  active: number;
  regions: number;
}

/**
 * One card in the live statistics strip (task 4.3). Deliberately built from
 * `Box`/`Text` (not Chakra `Stat`/`StatLabel`/`StatNumber`, which are `undefined`
 * under the test runner's ESM interop) while keeping the same visual shape as the
 * shared stats-strip pattern: a `gray.800` card with a muted label over a large
 * colored number. `testId` is placed on the number node so tests read the figure.
 */
const StatCard: React.FC<{
  label: string;
  value: number;
  valueColor: string;
  testId: string;
}> = ({ label, value, valueColor, testId }) => (
  <Box bg="gray.800" borderRadius="md" p={4} minW="140px" flex="1">
    <Text color="gray.400" fontSize="sm">{label}</Text>
    <Text color={valueColor} fontSize="2xl" fontWeight="bold" data-testid={testId}>
      {value}
    </Text>
  </Box>
);

export interface MembersStatsStripProps {
  stats: MembersStats;
  t: (key: string) => string;
}

/**
 * The stats strip reuses the shared Chakra stats-strip convention
 * (`bg="gray.800"` cards). Every figure is recomputed by the page from
 * `processedData` (the filtered+sorted rows), so the strip follows every column
 * filter, sort, and search.
 */
export const MembersStatsStrip: React.FC<MembersStatsStripProps> = ({ stats, t }) => (
  <Flex
    mb={4}
    gap={4}
    wrap="wrap"
    data-testid="members-stats-strip"
  >
    <StatCard
      label={t('stats.total')}
      value={stats.total}
      valueColor="white"
      testId="stat-total"
    />
    <StatCard
      label={t('stats.filtered')}
      value={stats.filtered}
      valueColor="orange.300"
      testId="stat-filtered"
    />
    <StatCard
      label={t('stats.active')}
      value={stats.active}
      valueColor="green.400"
      testId="stat-active"
    />
    <StatCard
      label={t('stats.regions')}
      value={stats.regions}
      valueColor="purple.300"
      testId="stat-regions"
    />
  </Flex>
);
