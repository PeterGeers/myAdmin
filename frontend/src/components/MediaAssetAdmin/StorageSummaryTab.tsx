/**
 * Storage Summary Tab — Storage overview by category + orphan analysis
 *
 * Displays:
 * - Table of asset count + total size per category (with totals row)
 * - Orphan summary: count, total size, oldest orphan
 * - Top 10 largest orphans table
 *
 * Reuses dashboard data from GET /api/assets/dashboard.
 *
 * @module components/MediaAssetAdmin/StorageSummaryTab
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  VStack,
  SimpleGrid,
  Table,
  Thead,
  Tbody,
  Tfoot,
  Tr,
  Th,
  Td,
  Text,
  Badge,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Spinner,
  Alert,
  AlertIcon,
} from '@chakra-ui/react';
import { fetchAssetDashboard } from '@/services/mediaAssetService';
import type { AssetDashboardData } from '@/types/mediaAsset';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Format bytes into human-readable string (KB, MB, GB) */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(1)} ${units[i]}`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function StorageSummaryTab() {
  const [dashboard, setDashboard] = useState<AssetDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAssetDashboard();
      setDashboard(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load storage data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Loading state ───────────────────────────────────────────────────────────

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" py={12}>
        <Spinner size="xl" color="orange.400" thickness="4px" />
      </Box>
    );
  }

  // ── Error state ─────────────────────────────────────────────────────────────

  if (error) {
    return (
      <Alert status="error" bg="red.900" borderRadius="md">
        <AlertIcon />
        {error}
      </Alert>
    );
  }

  if (!dashboard) return null;

  // ── Derived data ────────────────────────────────────────────────────────────

  const categories = Object.entries(dashboard.storage_by_category);
  const totalCount = categories.reduce((sum, [, info]) => sum + info.count, 0);
  const totalBytes = categories.reduce((sum, [, info]) => sum + info.bytes, 0);

  const orphans = dashboard.top_orphans;
  const orphanCount = dashboard.orphaned_assets;
  const orphanTotalSize = orphans.reduce((sum, o) => sum + o.size, 0);
  const oldestOrphan = orphans.length > 0
    ? Math.max(...orphans.map((o) => o.days_orphaned))
    : 0;

  // Show top 10 orphans (API may already limit, but be safe)
  const topOrphans = orphans.slice(0, 10);

  return (
    <VStack spacing={6} align="stretch" p={4}>
      {/* ── Section: Storage by Category ─────────────────────── */}
      <Box>
        <Text color="gray.200" fontWeight="bold" fontSize="lg" mb={3}>
          Storage by Category
        </Text>
        <Box bg="gray.800" borderRadius="md" overflowX="auto">
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <Th color="gray.400">Category</Th>
                <Th color="gray.400" isNumeric>Asset Count</Th>
                <Th color="gray.400" isNumeric>Total Size</Th>
                <Th color="gray.400" isNumeric>% of Total</Th>
              </Tr>
            </Thead>
            <Tbody>
              {categories.map(([category, info]) => {
                const pct = totalBytes > 0 ? (info.bytes / totalBytes) * 100 : 0;
                return (
                  <Tr key={category} _hover={{ bg: 'gray.700' }}>
                    <Td color="gray.200">
                      <Badge colorScheme="orange" variant="subtle">
                        {category}
                      </Badge>
                    </Td>
                    <Td color="gray.300" isNumeric>{info.count.toLocaleString()}</Td>
                    <Td color="gray.300" isNumeric>{formatBytes(info.bytes)}</Td>
                    <Td color="gray.300" isNumeric>{pct.toFixed(1)}%</Td>
                  </Tr>
                );
              })}
            </Tbody>
            <Tfoot>
              <Tr bg="gray.750">
                <Td color="gray.100" fontWeight="bold">Total</Td>
                <Td color="gray.100" fontWeight="bold" isNumeric>
                  {totalCount.toLocaleString()}
                </Td>
                <Td color="gray.100" fontWeight="bold" isNumeric>
                  {formatBytes(totalBytes)}
                </Td>
                <Td color="gray.100" fontWeight="bold" isNumeric>100%</Td>
              </Tr>
            </Tfoot>
          </Table>
        </Box>
      </Box>

      {/* ── Section: Orphan Summary ──────────────────────────── */}
      <Box>
        <Text color="gray.200" fontWeight="bold" fontSize="lg" mb={3}>
          Orphan Summary
        </Text>
        <SimpleGrid columns={{ base: 1, sm: 3 }} spacing={4}>
          <Box bg="gray.800" p={4} borderRadius="md">
            <Stat>
              <StatLabel color="gray.400">Total Orphans</StatLabel>
              <StatNumber color="orange.300" fontSize="2xl">
                {orphanCount.toLocaleString()}
              </StatNumber>
              <StatHelpText color="gray.500">assets without references</StatHelpText>
            </Stat>
          </Box>
          <Box bg="gray.800" p={4} borderRadius="md">
            <Stat>
              <StatLabel color="gray.400">Orphan Storage</StatLabel>
              <StatNumber color="orange.300" fontSize="2xl">
                {formatBytes(orphanTotalSize)}
              </StatNumber>
              <StatHelpText color="gray.500">total size of top orphans</StatHelpText>
            </Stat>
          </Box>
          <Box bg="gray.800" p={4} borderRadius="md">
            <Stat>
              <StatLabel color="gray.400">Oldest Orphan</StatLabel>
              <StatNumber color="orange.300" fontSize="2xl">
                {oldestOrphan > 0 ? `${oldestOrphan} days` : '—'}
              </StatNumber>
              <StatHelpText color="gray.500">longest unreferenced</StatHelpText>
            </Stat>
          </Box>
        </SimpleGrid>
      </Box>

      {/* ── Section: Top 10 Largest Orphans ──────────────────── */}
      <Box>
        <Text color="gray.200" fontWeight="bold" fontSize="lg" mb={3}>
          Top 10 Largest Orphans
        </Text>
        {topOrphans.length === 0 ? (
          <Box bg="gray.800" p={6} borderRadius="md" textAlign="center">
            <Text color="gray.500">No orphaned assets found.</Text>
          </Box>
        ) : (
          <Box bg="gray.800" borderRadius="md" overflowX="auto">
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th color="gray.400">Filename</Th>
                  <Th color="gray.400" isNumeric>Size</Th>
                  <Th color="gray.400" isNumeric>Days Orphaned</Th>
                </Tr>
              </Thead>
              <Tbody>
                {topOrphans.map((orphan) => (
                  <Tr key={orphan.id} _hover={{ bg: 'gray.700' }}>
                    <Td color="gray.200" maxW="300px" isTruncated>
                      {orphan.filename}
                    </Td>
                    <Td color="gray.300" isNumeric>{formatBytes(orphan.size)}</Td>
                    <Td color="orange.300" isNumeric>{orphan.days_orphaned}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>
        )}
      </Box>
    </VStack>
  );
}
