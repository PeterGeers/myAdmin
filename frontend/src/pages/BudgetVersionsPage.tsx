/**
 * BudgetVersionsPage — Manages budget versions with status transitions.
 *
 * Follows ZZPInvoices / BankingProcessor pattern:
 * - Dark theme (gray.800/gray.700/white)
 * - useFilterableTable + FilterableHeader for column filtering/sorting
 * - useTypedTranslation('budget') for i18n
 * - Formik + Yup for create modal validation
 * - Responsive: Flex wrap, hidden columns on mobile
 * - Action button styling: orange primary, ghost cancel, red outline delete
 *
 * Reference: .kiro/specs/budget-ui-alignment/design.md
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner,
  Table, Thead, Tbody, Tr, Td, Badge,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, useDisclosure,
  FormControl, FormLabel, Input, VStack, HStack,
  FormErrorMessage,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { Formik, Form, Field } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { BudgetVersion } from '../types/budget';
import {
  listVersions,
  createVersion,
  transitionVersionStatus,
  activateVersion,
  deleteVersion,
} from '../services/budgetService';

const INITIAL_FILTERS: Record<string, string> = {
  name: '',
  fiscal_year: '',
  status: '',
  is_active: '',
};

const BudgetVersionsPage: React.FC = () => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');
  const toast = useToast();

  const [versions, setVersions] = useState<BudgetVersion[]>([]);
  const [loading, setLoading] = useState(true);

  // Detail modal
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const [selectedVersion, setSelectedVersion] = useState<BudgetVersion | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Create modal
  const { isOpen: isCreateOpen, onOpen: onCreateOpen, onClose: onCreateClose } = useDisclosure();

  // Formik validation schema for create modal
  const createVersionSchema = Yup.object({
    name: Yup.string().required(t('messages.nameRequired')).max(100),
    fiscal_year: Yup.number()
      .required(t('messages.yearRequired'))
      .min(2000)
      .max(2100),
  });

  // FilterableTable hook for column filtering + sorting
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<BudgetVersion>(versions, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'fiscal_year', direction: 'desc' },
  });

  const loadVersions = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await listVersions();
      if (resp.success) {
        setVersions(resp.data);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setLoading(false);
    }
  }, [toast, t]);

  useEffect(() => {
    loadVersions();
  }, [loadVersions]);

  // ─── Row click → detail modal ───────────────────────────────────────────────

  const handleRowClick = (version: BudgetVersion) => {
    setSelectedVersion(version);
    onDetailOpen();
  };

  const handleDetailClose = () => {
    onDetailClose();
    setSelectedVersion(null);
  };

  // ─── Create version (Formik onSubmit) ───────────────────────────────────────

  const handleCreate = async (
    values: { name: string; fiscal_year: number },
    { setSubmitting, resetForm }: { setSubmitting: (v: boolean) => void; resetForm: () => void },
  ) => {
    try {
      const resp = await createVersion({ name: values.name.trim(), fiscal_year: values.fiscal_year });
      if (resp.success) {
        toast({ title: t('messages.versionCreated'), status: 'success', duration: 3000 });
        onCreateClose();
        resetForm();
        loadVersions();
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.saveError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setSubmitting(false);
    }
  };

  // ─── Status transitions ─────────────────────────────────────────────────────

  const handleApprove = async () => {
    if (!selectedVersion) return;
    try {
      setActionLoading(true);
      const resp = await transitionVersionStatus(selectedVersion.id, { action: 'approve' });
      if (resp.success) {
        toast({ title: t('messages.versionApproved'), status: 'success', duration: 3000 });
        setSelectedVersion(resp.data);
        loadVersions();
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.saveError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleRevise = async () => {
    if (!selectedVersion) return;
    try {
      setActionLoading(true);
      const resp = await transitionVersionStatus(selectedVersion.id, { action: 'revise' });
      if (resp.success) {
        toast({ title: t('messages.versionRevised'), status: 'success', duration: 3000 });
        setSelectedVersion(resp.data);
        loadVersions();
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.saveError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleActivate = async () => {
    if (!selectedVersion) return;
    try {
      setActionLoading(true);
      const resp = await activateVersion(selectedVersion.id);
      if (resp.success) {
        toast({ title: t('messages.versionActivated'), status: 'success', duration: 3000 });
        setSelectedVersion(resp.data);
        loadVersions();
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.saveError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedVersion) return;
    try {
      setActionLoading(true);
      await deleteVersion(selectedVersion.id);
      toast({ title: t('messages.versionDeleted'), status: 'success', duration: 3000 });
      handleDetailClose();
      loadVersions();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.saveError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setActionLoading(false);
    }
  };

  // ─── Sort direction helper ──────────────────────────────────────────────────

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <Box p={6}>
      {/* Header */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">
          {t('titles.versions')}
        </Text>
        <HStack spacing={2}>
          <Button leftIcon={<AddIcon />} size="sm" colorScheme="orange" onClick={onCreateOpen}>
            {t('buttons.createVersion')}
          </Button>
        </HStack>
      </Flex>

      {/* Table */}
      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner size="lg" color="orange.300" />
        </Flex>
      ) : versions.length === 0 ? (
        <Text color="gray.400">{t('messages.noVersions')}</Text>
      ) : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <FilterableHeader
                  label={t('columns.name')}
                  filterValue={filters.name}
                  onFilterChange={(v) => setFilter('name', v)}
                  sortable
                  sortDirection={columnSortDirection('name')}
                  onSort={() => handleSort('name')}
                />
                <FilterableHeader
                  label={t('columns.fiscalYear')}
                  filterValue={filters.fiscal_year}
                  onFilterChange={(v) => setFilter('fiscal_year', v)}
                  sortable
                  sortDirection={columnSortDirection('fiscal_year')}
                  onSort={() => handleSort('fiscal_year')}
                />
                <FilterableHeader
                  label={t('columns.status')}
                  filterValue={filters.status}
                  onFilterChange={(v) => setFilter('status', v)}
                  sortable
                  sortDirection={columnSortDirection('status')}
                  onSort={() => handleSort('status')}
                />
                <FilterableHeader
                  label={t('columns.active')}
                  filterValue={filters.is_active}
                  onFilterChange={(v) => setFilter('is_active', v)}
                  sortable
                  sortDirection={columnSortDirection('is_active')}
                  onSort={() => handleSort('is_active')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map((v) => (
                <Tr
                  key={v.id}
                  _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(v)}
                >
                  <Td>{v.name}</Td>
                  <Td>{v.fiscal_year}</Td>
                  <Td>
                    <Badge
                      colorScheme={
                        v.status === 'Draft' ? 'gray' :
                        v.status === 'Approved' ? 'blue' : 'purple'
                      }
                    >
                      {v.status}
                    </Badge>
                  </Td>
                  <Td display={{ base: 'none', md: 'table-cell' }}>
                    {v.is_active && (
                      <Badge colorScheme="green">{t('messages.activeVersion')}</Badge>
                    )}
                  </Td>
                </Tr>
              ))}
              {processedData.length === 0 && (
                <Tr><Td colSpan={4}><Text color="gray.500">{tc('messages.noResults')}</Text></Td></Tr>
              )}
            </Tbody>
          </Table>
        </Box>
      )}

      {/* Detail Modal */}
      <Modal isOpen={isDetailOpen} onClose={handleDetailClose} size="md">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>{t('labels.versionName')}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {selectedVersion && (
              <VStack align="stretch" spacing={3}>
                <HStack justify="space-between">
                  <Text fontWeight="bold">{t('columns.name')}:</Text>
                  <Text>{selectedVersion.name}</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text fontWeight="bold">{t('columns.fiscalYear')}:</Text>
                  <Text>{selectedVersion.fiscal_year}</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text fontWeight="bold">{t('columns.status')}:</Text>
                  <Badge
                    colorScheme={
                      selectedVersion.status === 'Draft' ? 'gray' :
                      selectedVersion.status === 'Approved' ? 'blue' : 'purple'
                    }
                  >
                    {selectedVersion.status}
                  </Badge>
                </HStack>
                <HStack justify="space-between">
                  <Text fontWeight="bold">{t('columns.active')}:</Text>
                  {selectedVersion.is_active ? (
                    <Badge colorScheme="green">{t('messages.activeVersion')}</Badge>
                  ) : (
                    <Text color="gray.500">{tc('buttons.no')}</Text>
                  )}
                </HStack>
                {selectedVersion.status_changed_at && (
                  <HStack justify="space-between">
                    <Text fontWeight="bold">{t('columns.status')}:</Text>
                    <Text>{new Date(selectedVersion.status_changed_at).toLocaleString()}</Text>
                  </HStack>
                )}
                <HStack justify="space-between">
                  <Text fontWeight="bold">{t('columns.created')}:</Text>
                  <Text>{new Date(selectedVersion.created_at).toLocaleString()}</Text>
                </HStack>
              </VStack>
            )}
          </ModalBody>
          <ModalFooter>
            {selectedVersion && (
              <HStack spacing={2} wrap="wrap">
                {/* Draft: Approve + Delete */}
                {selectedVersion.status === 'Draft' && (
                  <>
                    <Button
                      size="sm"
                      colorScheme="orange"
                      onClick={handleApprove}
                      isLoading={actionLoading}
                    >
                      {t('buttons.approve')}
                    </Button>
                    <Button
                      size="sm"
                      colorScheme="red"
                      variant="outline"
                      onClick={handleDelete}
                      isLoading={actionLoading}
                    >
                      {tc('buttons.delete')}
                    </Button>
                  </>
                )}

                {/* Approved: Revise + Activate */}
                {selectedVersion.status === 'Approved' && (
                  <>
                    <Button
                      size="sm"
                      colorScheme="orange"
                      variant="outline"
                      onClick={handleRevise}
                      isLoading={actionLoading}
                    >
                      {t('buttons.revise')}
                    </Button>
                    <Button
                      size="sm"
                      colorScheme="orange"
                      onClick={handleActivate}
                      isLoading={actionLoading}
                    >
                      {t('buttons.activate')}
                    </Button>
                  </>
                )}

                {/* Revised: Activate */}
                {selectedVersion.status === 'Revised' && (
                  <Button
                    size="sm"
                    colorScheme="orange"
                    onClick={handleActivate}
                    isLoading={actionLoading}
                  >
                    {t('buttons.activate')}
                  </Button>
                )}
              </HStack>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Create Modal — Formik + Yup */}
      <Modal isOpen={isCreateOpen} onClose={onCreateClose} size="sm" closeOnOverlayClick={false}>
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>{t('buttons.createVersion')}</ModalHeader>
          <ModalCloseButton />
          <Formik
            initialValues={{ name: '', fiscal_year: new Date().getFullYear() }}
            validationSchema={createVersionSchema}
            onSubmit={handleCreate}
          >
            {({ isSubmitting }) => (
              <Form>
                <ModalBody>
                  <VStack spacing={4}>
                    <Field name="name">
                      {({ field, meta }: { field: any; meta: any }) => (
                        <FormControl isInvalid={!!(meta.touched && meta.error)}>
                          <FormLabel>{t('labels.versionName')}</FormLabel>
                          <Input
                            {...field}
                            placeholder="e.g. Budget 2025"
                            maxLength={100}
                          />
                          <FormErrorMessage>{meta.error}</FormErrorMessage>
                        </FormControl>
                      )}
                    </Field>
                    <Field name="fiscal_year">
                      {({ field, meta }: { field: any; meta: any }) => (
                        <FormControl isInvalid={!!(meta.touched && meta.error)}>
                          <FormLabel>{t('labels.fiscalYear')}</FormLabel>
                          <Input
                            {...field}
                            type="number"
                            min={2000}
                            max={2100}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                              field.onChange(e);
                            }}
                          />
                          <FormErrorMessage>{meta.error}</FormErrorMessage>
                        </FormControl>
                      )}
                    </Field>
                  </VStack>
                </ModalBody>
                <ModalFooter>
                  <Button variant="ghost" mr={3} onClick={onCreateClose}>
                    {tc('buttons.cancel')}
                  </Button>
                  <Button
                    colorScheme="orange"
                    type="submit"
                    isLoading={isSubmitting}
                  >
                    {tc('buttons.save')}
                  </Button>
                </ModalFooter>
              </Form>
            )}
          </Formik>
        </ModalContent>
      </Modal>
    </Box>
  );
};

export default BudgetVersionsPage;
