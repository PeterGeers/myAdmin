/**
 * Unregistered Tab — Unregistered S3 Objects Management
 *
 * Displays S3 objects that exist in buckets but are not tracked in the
 * asset registry. Provides actions to import into registry or permanently
 * delete from S3, with explicit confirmation for destructive operations.
 *
 * @module components/MediaAssetAdmin/UnregisteredTab
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
import { MdDelete, MdFileDownload } from 'react-icons/md';
import { fetchUnregistered, importUnregistered, deleteUnregistered } from '@/services/mediaAssetService';
import type { UnregisteredObject } from '@/types/mediaAsset';

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
function formatDate(isoDate: string | null): string {
  if (!isoDate) return '—';
  return new Date(isoDate).toLocaleDateString();
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function UnregisteredTab() {
  const [objects, setObjects] = useState<UnregisteredObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [actionInProgress, setActionInProgress] = useState(false);

  const { isOpen, onOpen, onClose } = useDisclosure();
  const toast = useToast();

  // ── Data fetching ───────────────────────────────────────────────────────────

  const loadObjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchUnregistered();
      setObjects(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load unregistered objects');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadObjects();
  }, [loadObjects]);

  // ── Selection logic ─────────────────────────────────────────────────────────

  const allSelected = objects.length > 0 && selectedKeys.size === objects.length;
  const someSelected = selectedKeys.size > 0 && selectedKeys.size < objects.length;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedKeys(new Set());
    } else {
      setSelectedKeys(new Set(objects.map((o) => o.s3_key)));
    }
  };

  const toggleSelect = (s3Key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(s3Key)) {
        next.delete(s3Key);
      } else {
        next.add(s3Key);
      }
      return next;
    });
  };

  // ── Import logic ────────────────────────────────────────────────────────────

  const handleImport = async () => {
    if (selectedKeys.size === 0) return;
    setActionInProgress(true);
    try {
      const result = await importUnregistered(Array.from(selectedKeys));
      toast({
        title: 'Import complete',
        description: `${result.imported} imported, ${result.skipped} skipped`,
        status: result.imported > 0 ? 'success' : 'info',
        duration: 5000,
        isClosable: true,
      });
      setSelectedKeys(new Set());
      await loadObjects();
    } catch (err) {
      toast({
        title: 'Import failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setActionInProgress(false);
    }
  };

  // ── Delete logic ────────────────────────────────────────────────────────────

  const handleDeleteClick = () => {
    if (selectedKeys.size === 0) return;
    onOpen();
  };

  const handleConfirmDelete = async () => {
    onClose();
    setActionInProgress(true);
    try {
      const result = await deleteUnregistered(Array.from(selectedKeys));
      toast({
        title: 'Deletion complete',
        description: `${result.deleted} deleted, ${result.skipped} skipped`,
        status: result.deleted > 0 ? 'success' : 'info',
        duration: 5000,
        isClosable: true,
      });
      setSelectedKeys(new Set());
      await loadObjects();
    } catch (err) {
      toast({
        title: 'Deletion failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setActionInProgress(false);
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

  if (objects.length === 0) {
    return (
      <Box py={12} textAlign="center">
        <Text color="gray.500" fontSize="lg">
          No unregistered objects found
        </Text>
        <Text color="gray.600" fontSize="sm" mt={2}>
          Run a scan to check for S3 objects not tracked in the registry.
        </Text>
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      {/* ── Action Bar ────────────────────────────────────────── */}
      {selectedKeys.size > 0 && (
        <HStack
          bg="gray.700"
          p={3}
          borderRadius="md"
          justifyContent="space-between"
          flexWrap="wrap"
          gap={2}
        >
          <Text color="gray.300" fontSize="sm">
            {selectedKeys.size} object{selectedKeys.size > 1 ? 's' : ''} selected
          </Text>
          <HStack spacing={2} flexWrap="wrap">
            <Button
              size="sm"
              colorScheme="orange"
              leftIcon={<Icon as={MdFileDownload} />}
              onClick={handleImport}
              isLoading={actionInProgress}
              loadingText="Importing..."
            >
              Import to Registry
            </Button>
            <Button
              size="sm"
              colorScheme="red"
              leftIcon={<Icon as={MdDelete} />}
              onClick={handleDeleteClick}
              isLoading={actionInProgress}
              loadingText="Deleting..."
            >
              Delete from S3
            </Button>
          </HStack>
        </HStack>
      )}

      {/* ── Objects Table ─────────────────────────────────────── */}
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
                  aria-label="Select all objects"
                />
              </Th>
              <Th color="gray.400">S3 Key</Th>
              <Th color="gray.400">Bucket</Th>
              <Th color="gray.400" isNumeric>Size</Th>
              <Th color="gray.400">Last Modified</Th>
            </Tr>
          </Thead>
          <Tbody>
            {objects.map((obj) => (
              <Tr
                key={obj.s3_key}
                _hover={{ bg: 'gray.700' }}
                bg={selectedKeys.has(obj.s3_key) ? 'gray.700' : undefined}
              >
                <Td px={3}>
                  <Checkbox
                    colorScheme="orange"
                    isChecked={selectedKeys.has(obj.s3_key)}
                    onChange={() => toggleSelect(obj.s3_key)}
                    aria-label={`Select ${obj.s3_key}`}
                  />
                </Td>
                <Td color="gray.200" maxW="350px" isTruncated title={obj.s3_key}>
                  {obj.s3_key}
                </Td>
                <Td color="gray.400" fontSize="xs" maxW="150px" isTruncated title={obj.bucket}>
                  {obj.bucket}
                </Td>
                <Td color="gray.300" isNumeric>{formatBytes(obj.size)}</Td>
                <Td color="gray.400" fontSize="xs">{formatDate(obj.last_modified)}</Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </Box>

      {/* ── Delete Confirmation Modal ─────────────────────────── */}
      <ConfirmDeleteModal
        isOpen={isOpen}
        onClose={onClose}
        onConfirm={handleConfirmDelete}
        count={selectedKeys.size}
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
}

function ConfirmDeleteModal({
  isOpen,
  onClose,
  onConfirm,
  count,
}: ConfirmDeleteModalProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} isCentered>
      <ModalOverlay />
      <ModalContent bg="gray.800" borderColor="gray.600" borderWidth="1px">
        <ModalHeader color="gray.100">Confirm Permanent Deletion</ModalHeader>
        <ModalCloseButton color="gray.400" />
        <ModalBody>
          <VStack spacing={3} align="stretch">
            <Text color="gray.300">
              Are you sure you want to permanently delete{' '}
              <Text as="span" fontWeight="bold" color="red.300">
                {count}
              </Text>{' '}
              S3 object{count > 1 ? 's' : ''}?
            </Text>

            <Alert status="error" bg="red.900" borderRadius="md">
              <AlertIcon />
              <Text fontSize="sm" color="red.200">
                This action is irreversible. These files will be permanently
                removed from S3 storage and cannot be recovered.
              </Text>
            </Alert>
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
