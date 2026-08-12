/**
 * Media Asset Administration Page
 *
 * Tenant admin dashboard for managing media assets (images, documents, etc.)
 * stored in S3. Provides summary stats, scan controls, deletion workflow,
 * retention settings, and duplicate management.
 *
 * Permission gate: storage_manage (Tenant_Admin role)
 * Route: /admin/assets
 *
 * @module pages/MediaAssetAdminPage
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  VStack,
  HStack,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  SimpleGrid,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Text,
  Spinner,
  Alert,
  AlertIcon,
  Badge,
} from '@chakra-ui/react';
import { fetchAssetDashboard } from '@/services/mediaAssetService';
import type { AssetDashboardData } from '@/types/mediaAsset';
import ScanTab from '@/components/MediaAssetAdmin/ScanTab';
import DeletionTab from '@/components/MediaAssetAdmin/DeletionTab';
import UnregisteredTab from '@/components/MediaAssetAdmin/UnregisteredTab';
import RetentionTab from '@/components/MediaAssetAdmin/RetentionTab';
import DuplicatesTab from '@/components/MediaAssetAdmin/DuplicatesTab';
import StorageSummaryTab from '@/components/MediaAssetAdmin/StorageSummaryTab';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Format bytes into human-readable string (KB, MB, GB) */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(1)} ${units[i]}`;
}

/** Format ISO date string to readable local format */
function formatDate(isoDate: string | null): string {
  if (!isoDate) return 'Never';
  return new Date(isoDate).toLocaleString();
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function MediaAssetAdminPage() {
  const [dashboard, setDashboard] = useState<AssetDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tabIndex, setTabIndex] = useState(0);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAssetDashboard();
      setDashboard(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  };

  // Refresh dashboard data when switching to Dashboard or Storage tabs
  const handleTabChange = (index: number) => {
    setTabIndex(index);
    if (index === 0 || index === 6) {
      loadDashboard();
    }
  };

  return (
    <Box p={6}>
      <Tabs variant="enclosed" colorScheme="orange" index={tabIndex} onChange={handleTabChange}>
        <TabList>
          <Tab color="gray.300" _selected={{ color: 'orange.300', bg: 'gray.800' }}>
            Dashboard
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.300', bg: 'gray.800' }}>
            Scan
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.300', bg: 'gray.800' }}>
            Deletion
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.300', bg: 'gray.800' }}>
            Unregistered
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.300', bg: 'gray.800' }}>
            Retention
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.300', bg: 'gray.800' }}>
            Duplicates
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.300', bg: 'gray.800' }}>
            Storage
          </Tab>
        </TabList>

        <TabPanels>
          {/* ── Dashboard Tab ─────────────────────────────────────── */}
          <TabPanel p={4}>
            <DashboardTab
              dashboard={dashboard}
              loading={loading}
              error={error}
            />
          </TabPanel>

          {/* ── Placeholder Tabs ──────────────────────────────────── */}
          <TabPanel p={4}><ScanTab /></TabPanel>
          <TabPanel p={4}><DeletionTab /></TabPanel>
          <TabPanel p={4}><UnregisteredTab /></TabPanel>
          <TabPanel p={4}><RetentionTab /></TabPanel>
          <TabPanel p={4}><DuplicatesTab /></TabPanel>
          <TabPanel p={4}><StorageSummaryTab /></TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}

// ─── Dashboard Tab ────────────────────────────────────────────────────────────

interface DashboardTabProps {
  dashboard: AssetDashboardData | null;
  loading: boolean;
  error: string | null;
}

function DashboardTab({ dashboard, loading, error }: DashboardTabProps) {
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" py={12}>
        <Spinner size="xl" color="orange.400" thickness="4px" />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert status="error" bg="red.900" borderRadius="md">
        <AlertIcon />
        {error}
      </Alert>
    );
  }

  if (!dashboard) return null;

  return (
    <VStack spacing={6} align="stretch">
      {/* ── Summary Stats ─────────────────────────────────────── */}
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
        <StatCard label="Total Assets" value={dashboard.total_assets} />
        <StatCard label="Active" value={dashboard.active_assets} color="green.300" />
        <StatCard
          label="Orphaned"
          value={dashboard.orphaned_assets}
          color="orange.300"
        />
        <StatCard
          label="Deletion Eligible"
          value={dashboard.deletion_eligible}
          color="red.300"
        />
      </SimpleGrid>

      {/* ── Last Scan ─────────────────────────────────────────── */}
      <Box bg="gray.800" p={4} borderRadius="md">
        <HStack>
          <Text color="gray.400" fontSize="sm">Last reconciliation scan:</Text>
          <Text color="gray.200" fontSize="sm" fontWeight="medium">
            {formatDate(dashboard.last_scan_at)}
          </Text>
        </HStack>
      </Box>

      {/* ── Storage by Category ───────────────────────────────── */}
      <Box bg="gray.800" p={4} borderRadius="md">
        <Text color="gray.200" fontWeight="bold" mb={3}>
          Storage by Category
        </Text>
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th color="gray.400">Category</Th>
              <Th color="gray.400" isNumeric>Count</Th>
              <Th color="gray.400" isNumeric>Size</Th>
            </Tr>
          </Thead>
          <Tbody>
            {Object.entries(dashboard.storage_by_category).map(([category, info]) => (
              <Tr key={category}>
                <Td color="gray.200">
                  <Badge colorScheme="orange" variant="subtle">
                    {category}
                  </Badge>
                </Td>
                <Td color="gray.300" isNumeric>{info.count}</Td>
                <Td color="gray.300" isNumeric>{formatBytes(info.bytes)}</Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </Box>

      {/* ── Top Orphans ───────────────────────────────────────── */}
      {dashboard.top_orphans.length > 0 && (
        <Box bg="gray.800" p={4} borderRadius="md">
          <Text color="gray.200" fontWeight="bold" mb={3}>
            Top Orphaned Assets
          </Text>
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <Th color="gray.400">Filename</Th>
                <Th color="gray.400" isNumeric>Size</Th>
                <Th color="gray.400" isNumeric>Days Orphaned</Th>
              </Tr>
            </Thead>
            <Tbody>
              {dashboard.top_orphans.map((orphan) => (
                <Tr key={orphan.id}>
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
    </VStack>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: number;
  color?: string;
}

function StatCard({ label, value, color = 'gray.100' }: StatCardProps) {
  return (
    <Box bg="gray.800" p={4} borderRadius="md">
      <Stat>
        <StatLabel color="gray.400">{label}</StatLabel>
        <StatNumber color={color} fontSize="2xl">
          {value.toLocaleString()}
        </StatNumber>
      </Stat>
    </Box>
  );
}

// ─── Placeholder Tab ──────────────────────────────────────────────────────────

function PlaceholderTab({ name }: { name: string }) {
  return (
    <Box py={12} textAlign="center">
      <Text color="gray.500" fontSize="lg">
        {name} — Coming soon
      </Text>
      {/* TODO: Implement in tasks 9.2-9.7 */}
    </Box>
  );
}
