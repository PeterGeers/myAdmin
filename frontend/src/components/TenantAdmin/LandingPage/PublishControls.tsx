/**
 * PublishControls — Publish/unpublish buttons + version history with rollback.
 *
 * Shows version history table (FilterableHeader + useFilterableTable),
 * row-click opens a modal with: Preview, Rollback, Delete options.
 * Compliant with ui-patterns.md and table-filter-framework-v2.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge,
  Table, Thead, Tbody, Tr, Td,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter,
  ModalCloseButton,
  useToast, Spinner, useDisclosure,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { useFilterableTable } from '../../../hooks/useFilterableTable';
import { FilterableHeader } from '../../filters/FilterableHeader';
import PreviewPanel from './PreviewPanel';
import {
  getVersions,
  getVersionDetail,
  rollbackToVersion,
  deleteVersion,
  VersionEntry,
  Section,
} from '../../../services/landingPageApi';

interface PublishControlsProps {
  onVersionChange: (version: number) => void;
}

/** Extend VersionEntry with formatted fields for filtering */
interface VersionRow extends VersionEntry {
  versionLabel: string;
  publishedAtFormatted: string;
}

export default function PublishControls({
  onVersionChange,
}: PublishControlsProps) {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);

  // Selected version modal
  const [selectedVersion, setSelectedVersion] = useState<VersionRow | null>(null);
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();

  // Preview state
  const [previewSections, setPreviewSections] = useState<Section[] | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const deleteCancelRef = React.useRef<HTMLButtonElement>(null);

  // Rollback confirmation
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);
  const rollbackCancelRef = React.useRef<HTMLButtonElement>(null);

  const formatDate = (isoDate: string): string => {
    try {
      return new Date(isoDate).toLocaleString('nl-NL', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoDate;
    }
  };

  const loadVersions = useCallback(async () => {
    setLoadingVersions(true);
    try {
      const data = await getVersions();
      const rows: VersionRow[] = data.map((v) => ({
        ...v,
        versionLabel: `v${v.version}`,
        publishedAtFormatted: formatDate(v.published_at),
      }));
      setVersions(rows);
    } catch {
      // Silent fail — versions are informational
    } finally {
      setLoadingVersions(false);
    }
  }, []);

  useEffect(() => {
    loadVersions();
  }, [loadVersions]);

  // Table filter + sort via framework
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
    resetFilters,
    hasActiveFilters,
  } = useFilterableTable<VersionRow>(versions, {
    initialFilters: {
      versionLabel: '',
      publishedAtFormatted: '',
      published_by: '',
    },
    defaultSort: { field: 'version', direction: 'desc' },
  });

  // --- Row click: open version detail modal ---

  const handleRowClick = (row: VersionRow) => {
    setSelectedVersion(row);
    setPreviewSections(null);
    onModalOpen();
  };

  // --- Preview ---

  const handlePreview = async () => {
    if (!selectedVersion) return;
    setLoadingPreview(true);
    try {
      const detail = await getVersionDetail(selectedVersion.version);
      setPreviewSections(detail.sections);
    } catch (err) {
      toast({
        title: t('landingPage.versions.previewFailed'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoadingPreview(false);
    }
  };

  // --- Rollback ---

  const handleRollbackConfirm = async () => {
    if (!rollbackTarget) return;
    const target = rollbackTarget;
    setRollingBack(true);
    setRollbackTarget(null);
    onModalClose();

    try {
      const result = await rollbackToVersion(target);
      if (result.success) {
        onVersionChange(result.version);
        toast({
          title: t('landingPage.versions.rollbackSuccess'),
          description: `Restored and published version ${target}`,
          status: 'success',
          duration: 5000,
        });
        loadVersions();
      }
    } catch (err) {
      toast({
        title: t('landingPage.versions.rollbackFailed'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setRollingBack(false);
    }
  };

  // --- Delete ---

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleting(true);
    setDeleteTarget(null);
    onModalClose();

    try {
      const result = await deleteVersion(target);
      if (result.success) {
        toast({
          title: t('landingPage.versions.deleteSuccess'),
          description: result.message,
          status: 'success',
          duration: 3000,
        });
        loadVersions();
      }
    } catch (err) {
      toast({
        title: t('landingPage.versions.deleteFailed'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setDeleting(false);
    }
  };

  // --- Publish / Unpublish ---

  return (
    <Box bg="gray.800" borderRadius="md" p={4}>
      <VStack align="stretch" spacing={4}>
        {/* Header with clear filters (right-aligned) */}
        <HStack justify="flex-end" flexWrap="wrap" gap={2}>
          {hasActiveFilters && (
            <Button size="sm" variant="ghost" color="gray.400" onClick={resetFilters}>
              {t('landingPage.versions.clearFilters')}
            </Button>
          )}
        </HStack>

        {/* Version History Table */}
        {loadingVersions && versions.length === 0 ? (
          <Box textAlign="center" py={4}>
            <Spinner size="sm" color="gray.400" />
          </Box>
        ) : versions.length === 0 ? (
          <Text color="gray.500" fontSize="sm" textAlign="center" py={4}>
            {t('landingPage.versions.noVersions')}
          </Text>
        ) : (
          <Box overflowX="auto">
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <FilterableHeader
                    label={t('landingPage.versions.colVersion')}
                    filterValue={filters.versionLabel}
                    onFilterChange={(v) => setFilter('versionLabel', v)}
                    sortable
                    sortDirection={sortField === 'version' ? sortDirection : null}
                    onSort={() => handleSort('version')}
                    placeholder="v..."
                  />
                  <FilterableHeader
                    label={t('landingPage.versions.colPublishedAt')}
                    filterValue={filters.publishedAtFormatted}
                    onFilterChange={(v) => setFilter('publishedAtFormatted', v)}
                    sortable
                    sortDirection={sortField === 'published_at' ? sortDirection : null}
                    onSort={() => handleSort('published_at')}
                    placeholder="Filter..."
                  />
                  <FilterableHeader
                    label={t('landingPage.versions.colPublishedBy')}
                    filterValue={filters.published_by}
                    onFilterChange={(v) => setFilter('published_by', v)}
                    sortable
                    sortDirection={sortField === 'published_by' ? sortDirection : null}
                    onSort={() => handleSort('published_by')}
                    placeholder="Filter..."
                  />
                </Tr>
              </Thead>
              <Tbody>
                {processedData.map((v) => (
                  <Tr
                    key={v.version}
                    _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                    onClick={() => handleRowClick(v)}
                    opacity={rollingBack || deleting ? 0.5 : 1}
                  >
                    <Td borderColor="gray.600">
                      <Badge colorScheme="orange" fontSize="xs">
                        v{v.version}
                      </Badge>
                    </Td>
                    <Td borderColor="gray.600" color="gray.300" fontSize="xs">
                      {v.publishedAtFormatted}
                    </Td>
                    <Td borderColor="gray.600" color="gray.400" fontSize="xs">
                      {v.published_by || '—'}
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>
        )}
      </VStack>

      {/* Version Detail Modal — Preview / Rollback / Delete */}
      <Modal
        isOpen={isModalOpen}
        onClose={onModalClose}
        size={previewSections ? '6xl' : 'md'}
        closeOnOverlayClick={false}
      >
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>
            {t('landingPage.versions.detailTitle', { version: selectedVersion?.version })}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {selectedVersion && (
              <VStack align="stretch" spacing={3}>
                <HStack spacing={4} fontSize="sm" color="gray.300">
                  <Text>
                    {t('landingPage.versions.colPublishedAt')}: {selectedVersion.publishedAtFormatted}
                  </Text>
                  <Text>
                    {t('landingPage.versions.colPublishedBy')}: {selectedVersion.published_by || '—'}
                  </Text>
                </HStack>

                {/* Preview area */}
                {loadingPreview && (
                  <Box textAlign="center" py={6}>
                    <Spinner size="md" color="orange.400" />
                  </Box>
                )}
                {previewSections && (
                  <Box
                    border="1px solid"
                    borderColor="gray.600"
                    borderRadius="md"
                    maxH="500px"
                    overflowY="auto"
                    bg="white"
                  >
                    <PreviewPanel sections={previewSections} />
                  </Box>
                )}
              </VStack>
            )}
          </ModalBody>
          <ModalFooter>
            <HStack spacing={2} w="full" justify="space-between">
              {/* Destructive action left */}
              <Button
                size="sm"
                colorScheme="red"
                variant="ghost"
                onClick={() => {
                  if (selectedVersion) setDeleteTarget(selectedVersion.version);
                }}
                isLoading={deleting}
              >
                {t('landingPage.versions.delete')}
              </Button>
              {/* Non-destructive actions right */}
              <HStack spacing={2}>
                {!previewSections && (
                  <Button
                    size="sm"
                    variant="outline"
                    colorScheme="orange"
                    onClick={handlePreview}
                    isLoading={loadingPreview}
                  >
                    {t('landingPage.versions.preview')}
                  </Button>
                )}
                <Button
                  size="sm"
                  colorScheme="orange"
                  onClick={() => {
                    if (selectedVersion) setRollbackTarget(selectedVersion.version);
                  }}
                  isLoading={rollingBack}
                >
                  {t('landingPage.versions.rollbackAction')}
                </Button>
                <Button size="sm" variant="ghost" onClick={onModalClose}>
                  {t('landingPage.editor.cancel')}
                </Button>
              </HStack>
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Rollback confirmation dialog */}
      <AlertDialog
        isOpen={rollbackTarget !== null}
        leastDestructiveRef={rollbackCancelRef}
        onClose={() => setRollbackTarget(null)}
        isCentered
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white" borderColor="gray.600">
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              {t('landingPage.versions.rollbackTitle', { version: rollbackTarget })}
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300">
              {t('landingPage.versions.rollbackConfirm', { version: rollbackTarget })}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={rollbackCancelRef}
                onClick={() => setRollbackTarget(null)}
                variant="ghost"
              >
                {t('landingPage.editor.cancel')}
              </Button>
              <Button colorScheme="orange" onClick={handleRollbackConfirm} ml={3}>
                {t('landingPage.versions.rollbackAction')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>

      {/* Delete confirmation dialog */}
      <AlertDialog
        isOpen={deleteTarget !== null}
        leastDestructiveRef={deleteCancelRef}
        onClose={() => setDeleteTarget(null)}
        isCentered
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white" borderColor="gray.600">
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              {t('landingPage.versions.deleteTitle', { version: deleteTarget })}
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300">
              {t('landingPage.versions.deleteConfirm', { version: deleteTarget })}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={deleteCancelRef}
                onClick={() => setDeleteTarget(null)}
                variant="ghost"
              >
                {t('landingPage.editor.cancel')}
              </Button>
              <Button colorScheme="red" onClick={handleDeleteConfirm} ml={3}>
                {t('landingPage.versions.delete')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
