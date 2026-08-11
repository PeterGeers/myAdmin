/**
 * Deletion Tab — Deletion Approval Workflow
 *
 * Displays DELETION_ELIGIBLE assets in a selectable table.
 * Provides bulk actions: Approve Deletion, Extend Retention, Re-attach.
 * Shows a confirmation dialog with extra warning for compliance-sensitive
 * categories (invoices).
 *
 * @module components/MediaAssetAdmin/DeletionTab
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
  Checkbox,
  Button,
  Badge,
  Spinner,
  Alert,
  AlertIcon,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  useDisclosure,
  useToast,
  Icon,
} from '@chakra-ui/react';
import { MdDelete, MdSchedule, MdLink } from 'react-icons/md';
import { fetchDeletionEligible, approveDeletion } from '@/services/mediaAssetService';
import type { MediaAsset } from '@/types/mediaAsset';

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

/** Calculate days since a given date */
function daysOrphaned(createdAt: string): number {
  const created = new Date(createdAt).getTime();
  const now = Date.now();
  return Math.floor((now - created) / (1000 * 60 * 60 * 24));
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DeletionTab() {
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const { isOpen, onOpen, onClose } = useDisclosure();
  const toast = useToast();

  // ── Data fetching ───────────────────────────────────────────────────────────

  const loadAssets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchDeletionEligible(1, 100);
      setAssets(result.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load deletion-eligible assets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAssets();
  }, [loadAssets]);

  // ── Selection logic ─────────────────────────────────────────────────────────

  const allSelected = assets.length > 0 && selectedIds.size === assets.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < assets.length;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(assets.map((a) => a.id)));
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // ── Deletion logic ──────────────────────────────────────────────────────────

  const selectedAssets = assets.filter((a) => selectedIds.has(a.id));
  const hasInvoices = selectedAssets.some((a) => a.category === 'invoices');

  const handleApproveClick = () => {
    if (selectedIds.size === 0) return;
    onOpen();
  };

  const handleConfirmDelete = async () => {
    onClose();
    setDeleting(true);
    try {
      const result = await approveDeletion(Array.from(selectedIds));
      toast({
        title: 'Deletion complete',
        description: `${result.deleted} deleted, ${result.skipped} skipped`,
        status: result.deleted > 0 ? 'success' : 'info',
        duration: 5000,
        isClosable: true,
      });
      // Clear selection and reload
      setSelectedIds(new Set());
      await loadAssets();
    } catch (err) {
      toast({
        title: 'Deletion failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setDeleting(false);
    }
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

  if (assets.length === 0) {
    return (
      <Box py={12} textAlign="center">
        <Text color="gray.500" fontSize="lg">
          No deletion-eligible assets found
        </Text>
        <Text color="gray.600" fontSize="sm" mt={2}>
          Assets become eligible after their retention period elapses.
        </Text>
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      {/* ── Action Bar ────────────────────────────────────────── */}
      {selectedIds.size > 0 && (
        <HStack
          bg="gray.700"
          p={3}
          borderRadius="md"
          justifyContent="space-between"
          flexWrap="wrap"
          gap={2}
        >
          <Text color="gray.300" fontSize="sm">
            {selectedIds.size} asset{selectedIds.size > 1 ? 's' : ''} selected
          </Text>
          <HStack spacing={2} flexWrap="wrap">
            <Button
              size="sm"
              colorScheme="red"
              leftIcon={<Icon as={MdDelete} />}
              onClick={handleApproveClick}
              isLoading={deleting}
              loadingText="Deleting..."
            >
              Approve Deletion
            </Button>
            <Button
              size="sm"
              colorScheme="orange"
              variant="outline"
              leftIcon={<Icon as={MdSchedule} />}
              isDisabled
              title="Coming soon"
            >
              Extend Retention
            </Button>
            <Button
              size="sm"
              colorScheme="blue"
              variant="outline"
              leftIcon={<Icon as={MdLink} />}
              isDisabled
              title="Coming soon"
            >
              Re-attach
            </Button>
          </HStack>
        </HStack>
      )}

      {/* ── Asset Table ───────────────────────────────────────── */}
      <Box bg="gray.800" borderRadius="md" overflowX="auto">
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th px={3} w="40px">
                <Checkbox
                  colorScheme="orange"
                  isChecked={allSelected}
                  isIndeterminate={someSelected}
                  onChange={toggleSelectAll}
                  aria-label="Select all assets"
                />
              </Th>
              <Th color="gray.400">Filename</Th>
              <Th color="gray.400">Category</Th>
              <Th color="gray.400" isNumeric>Size</Th>
              <Th color="gray.400" isNumeric>Days Orphaned</Th>
              <Th color="gray.400">Created</Th>
            </Tr>
          </Thead>
          <Tbody>
            {assets.map((asset) => (
              <Tr
                key={asset.id}
                _hover={{ bg: 'gray.700' }}
                bg={selectedIds.has(asset.id) ? 'gray.700' : undefined}
              >
                <Td px={3}>
                  <Checkbox
                    colorScheme="orange"
                    isChecked={selectedIds.has(asset.id)}
                    onChange={() => toggleSelect(asset.id)}
                    aria-label={`Select ${asset.original_filename}`}
                  />
                </Td>
                <Td color="gray.200" maxW="250px" isTruncated title={asset.original_filename}>
                  {asset.original_filename}
                </Td>
                <Td>
                  <Badge
                    colorScheme={asset.category === 'invoices' ? 'red' : 'orange'}
                    variant="subtle"
                  >
                    {asset.category}
                  </Badge>
                </Td>
                <Td color="gray.300" isNumeric>{formatBytes(asset.file_size)}</Td>
                <Td color="orange.300" isNumeric>{daysOrphaned(asset.created_at)}</Td>
                <Td color="gray.400" fontSize="xs">{formatDate(asset.created_at)}</Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </Box>

      {/* ── Confirmation Modal ────────────────────────────────── */}
      <ConfirmDeleteModal
        isOpen={isOpen}
        onClose={onClose}
        onConfirm={handleConfirmDelete}
        count={selectedIds.size}
        hasInvoices={hasInvoices}
      />
    </VStack>
  );
}

// ─── Confirmation Modal ───────────────────────────────────────────────────────

interface ConfirmDeleteModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  count: number;
  hasInvoices: boolean;
}

function ConfirmDeleteModal({
  isOpen,
  onClose,
  onConfirm,
  count,
  hasInvoices,
}: ConfirmDeleteModalProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} isCentered>
      <ModalOverlay />
      <ModalContent bg="gray.800" borderColor="gray.600" borderWidth="1px">
        <ModalHeader color="gray.100">Confirm Deletion</ModalHeader>
        <ModalCloseButton color="gray.400" />
        <ModalBody>
          <VStack spacing={3} align="stretch">
            <Text color="gray.300">
              Are you sure you want to permanently delete{' '}
              <Text as="span" fontWeight="bold" color="red.300">
                {count}
              </Text>{' '}
              asset{count > 1 ? 's' : ''}? This action cannot be undone.
            </Text>

            {hasInvoices && (
              <Alert status="warning" bg="yellow.900" borderRadius="md">
                <AlertIcon />
                <Text fontSize="sm" color="yellow.200">
                  ⚠️ These include compliance-sensitive invoice documents. Verify that
                  retention requirements have been met before proceeding.
                </Text>
              </Alert>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          <HStack spacing={3}>
            <Button variant="ghost" color="gray.300" onClick={onClose}>
              Cancel
            </Button>
            <Button colorScheme="red" onClick={onConfirm}>
              Delete Permanently
            </Button>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
