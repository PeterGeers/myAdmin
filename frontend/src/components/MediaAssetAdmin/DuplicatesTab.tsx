/**
 * Duplicates Tab — Duplicate Asset Management
 *
 * Displays groups of assets sharing the same content_hash (identical files).
 * Allows the tenant admin to select which asset to keep and merge duplicates,
 * re-attaching references from deleted copies to the kept asset.
 *
 * @module components/MediaAssetAdmin/DuplicatesTab
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Text,
  Button,
  Spinner,
  Alert,
  AlertIcon,
  Badge,
  Radio,
  RadioGroup,
  useToast,
  Icon,
} from '@chakra-ui/react';
import { MdCallMerge, MdCheckCircle } from 'react-icons/md';
import { fetchDuplicates, mergeDuplicates } from '@/services/mediaAssetService';
import { useTypedTranslation } from '@/hooks/useTypedTranslation';
import type { DuplicateGroup } from '@/types/mediaAsset';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Format bytes into human-readable string */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(1)} ${units[i]}`;
}

/** Format ISO date to short readable format */
function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString();
}

/** Truncate a hash for display */
function truncateHash(hash: string): string {
  if (hash.length <= 16) return hash;
  return `${hash.slice(0, 8)}…${hash.slice(-8)}`;
}

/**
 * Pick the default "keep" asset — the one with the most references.
 * Ties broken by earliest created_at.
 */
function pickDefaultKeep(group: DuplicateGroup): string {
  const sorted = [...group.assets].sort((a, b) => {
    if (b.reference_count !== a.reference_count) return b.reference_count - a.reference_count;
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
  return sorted[0]?.id ?? '';
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DuplicatesTab() {
  const { t } = useTypedTranslation('admin');
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keepSelections, setKeepSelections] = useState<Record<string, string>>({});
  const [mergingHash, setMergingHash] = useState<string | null>(null);

  const toast = useToast();

  // ── Data fetching ───────────────────────────────────────────────────────────

  const loadGroups = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDuplicates();
      setGroups(data);
      // Set default keep selections for each group
      const defaults: Record<string, string> = {};
      for (const group of data) {
        defaults[group.content_hash] = pickDefaultKeep(group);
      }
      setKeepSelections(defaults);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load duplicates');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  // ── Merge logic ─────────────────────────────────────────────────────────────

  const handleMerge = async (group: DuplicateGroup) => {
    const keepId = keepSelections[group.content_hash];
    if (!keepId) return;

    const duplicateIds = group.assets
      .filter((a) => a.id !== keepId)
      .map((a) => a.id);

    if (duplicateIds.length === 0) return;

    setMergingHash(group.content_hash);
    try {
      const result = await mergeDuplicates(keepId, duplicateIds);
      toast({
        title: t('mediaAssets.duplicates.messages.mergeSuccess'),
        description: `${result.duplicates_deleted} duplicate${result.duplicates_deleted !== 1 ? 's' : ''} removed, ${result.references_moved} reference${result.references_moved !== 1 ? 's' : ''} moved`,
        status: 'success',
        duration: 5000,
        isClosable: true,
      });
      await loadGroups();
    } catch (err) {
      toast({
        title: t('mediaAssets.duplicates.messages.mergeFailed'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setMergingHash(null);
    }
  };

  // ── Selection handler ───────────────────────────────────────────────────────

  const handleKeepChange = (contentHash: string, assetId: string) => {
    setKeepSelections((prev) => ({ ...prev, [contentHash]: assetId }));
  };

  // ── Render states ───────────────────────────────────────────────────────────

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

  if (groups.length === 0) {
    return (
      <Box py={12} textAlign="center">
        <Icon as={MdCheckCircle} boxSize={10} color="green.400" mb={3} />
        <Text color="green.300" fontSize="lg" fontWeight="medium">
          {t('mediaAssets.duplicates.noDuplicates')}
        </Text>
        <Text color="gray.500" fontSize="sm" mt={2}>
          {t('mediaAssets.duplicates.noDuplicatesHint')}
        </Text>
      </Box>
    );
  }

  return (
    <VStack spacing={6} align="stretch">
      <Text color="gray.400" fontSize="sm">
        {groups.length} duplicate group{groups.length !== 1 ? 's' : ''} found.
        Select which asset to keep in each group, then merge to consolidate references.
      </Text>

      {groups.map((group) => (
        <DuplicateGroupCard
          key={group.content_hash}
          group={group}
          keepId={keepSelections[group.content_hash] ?? ''}
          onKeepChange={(id) => handleKeepChange(group.content_hash, id)}
          onMerge={() => handleMerge(group)}
          isMerging={mergingHash === group.content_hash}
        />
      ))}
    </VStack>
  );
}

// ─── Duplicate Group Card ─────────────────────────────────────────────────────

interface DuplicateGroupCardProps {
  group: DuplicateGroup;
  keepId: string;
  onKeepChange: (assetId: string) => void;
  onMerge: () => void;
  isMerging: boolean;
}

function DuplicateGroupCard({
  group,
  keepId,
  onKeepChange,
  onMerge,
  isMerging,
}: DuplicateGroupCardProps) {
  const { t } = useTypedTranslation('admin');
  const duplicateCount = group.assets.length - 1;

  return (
    <Box bg="gray.800" borderRadius="md" p={4}>
      {/* ── Header ──────────────────────────────────────────── */}
      <HStack justifyContent="space-between" mb={3} flexWrap="wrap" gap={2}>
        <HStack spacing={3}>
          <Text color="gray.300" fontSize="sm" fontFamily="mono">
            Hash: {truncateHash(group.content_hash)}
          </Text>
          <Badge colorScheme="orange" variant="subtle">
            {group.assets.length} copies
          </Badge>
        </HStack>
        <Button
          size="sm"
          colorScheme="orange"
          leftIcon={<Icon as={MdCallMerge} />}
          onClick={onMerge}
          isLoading={isMerging}
          loadingText="Merging..."
          isDisabled={!keepId || duplicateCount === 0}
        >
          {t('mediaAssets.duplicates.merge')} ({duplicateCount} duplicate{duplicateCount !== 1 ? 's' : ''})
        </Button>
      </HStack>

      {/* ── Assets Table ────────────────────────────────────── */}
      <Box overflowX="auto">
        <RadioGroup value={keepId} onChange={onKeepChange}>
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <Th color="gray.400" w="60px">Keep</Th>
                <Th color="gray.400">Filename</Th>
                <Th color="gray.400">Category</Th>
                <Th color="gray.400" isNumeric>References</Th>
                <Th color="gray.400" isNumeric>Size</Th>
                <Th color="gray.400">Created</Th>
              </Tr>
            </Thead>
            <Tbody>
              {group.assets.map((asset) => (
                <Tr
                  key={asset.id}
                  _hover={{ bg: 'gray.700' }}
                  bg={asset.id === keepId ? 'gray.700' : undefined}
                >
                  <Td px={3}>
                    <Radio
                      value={asset.id}
                      colorScheme="orange"
                      aria-label={`Keep ${asset.original_filename}`}
                    />
                  </Td>
                  <Td color="gray.200" maxW="250px" isTruncated title={asset.original_filename}>
                    {asset.original_filename}
                  </Td>
                  <Td>
                    <Badge colorScheme="purple" variant="subtle" fontSize="xs">
                      {asset.category}
                    </Badge>
                  </Td>
                  <Td isNumeric>
                    <Text
                      color={asset.reference_count > 0 ? 'green.300' : 'gray.500'}
                      fontWeight={asset.reference_count > 0 ? 'medium' : 'normal'}
                    >
                      {asset.reference_count}
                    </Text>
                  </Td>
                  <Td color="gray.300" isNumeric>{formatBytes(asset.file_size)}</Td>
                  <Td color="gray.400" fontSize="xs">{formatDate(asset.created_at)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </RadioGroup>
      </Box>
    </Box>
  );
}
