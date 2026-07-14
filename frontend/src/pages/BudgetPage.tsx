/**
 * BudgetPage — Single page for budget preparation.
 *
 * Replaces BudgetVersionsPage + BudgetTemplatesPage + BudgetLinesPage.
 * Features:
 * - Version dropdown (all versions) + New Version button
 * - Status bar with contextual actions (Approve, Activate, Delete)
 * - Budget lines table with FilterableHeader
 * - Row-click opens edit modal, Add Line button, AI Suggestions
 * - Read-only for non-Draft versions
 *
 * UI patterns: dark theme, useFilterableTable, Formik+Yup modals, i18n
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner, Badge, Select,
  Table, Thead, Tbody, Tr, Td, HStack, IconButton,
  useDisclosure,
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import BudgetLineModal from './BudgetLineModal';
import BudgetNewVersionModal from './BudgetNewVersionModal';
import { BudgetVersion, BudgetLine, PeriodMode, DimensionType } from '../types/budget';
import {
  listVersions,
  listLines,
  createLine,
  updateLine,
  deleteLine,
  transitionVersionStatus,
  activateVersion,
  deleteVersion,
  copyBudget,
} from '../services/budgetService';

/** Compute total from a BudgetLine's 12 monthly amounts */
const lineTotal = (line: BudgetLine): number =>
  (Number(line.month_01) || 0) + (Number(line.month_02) || 0) +
  (Number(line.month_03) || 0) + (Number(line.month_04) || 0) +
  (Number(line.month_05) || 0) + (Number(line.month_06) || 0) +
  (Number(line.month_07) || 0) + (Number(line.month_08) || 0) +
  (Number(line.month_09) || 0) + (Number(line.month_10) || 0) +
  (Number(line.month_11) || 0) + (Number(line.month_12) || 0);

/** Format dimension display */
const formatDimension = (line: BudgetLine): string => {
  if (!line.detail_dimension_type) return '—';
  return `${line.detail_dimension_type}: ${line.detail_dimension_value || ''}`;
};

const INITIAL_FILTERS: Record<string, string> = {
  account_code: '',
  dimension: '',
  period_mode: '',
  total: '',
};

const BudgetPage: React.FC = () => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');
  const toast = useToast();

  // State
  const [versions, setVersions] = useState<BudgetVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [lines, setLines] = useState<BudgetLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [linesLoading, setLinesLoading] = useState(false);

  // Modals
  const { isOpen: isLineOpen, onOpen: onLineOpen, onClose: onLineClose } = useDisclosure();
  const { isOpen: isNewVersionOpen, onOpen: onNewVersionOpen, onClose: onNewVersionClose } = useDisclosure();
  const [editingLine, setEditingLine] = useState<BudgetLine | null>(null);

  // Derived
  const selectedVersion = versions.find((v) => v.id === selectedVersionId) || null;
  const isDraft = selectedVersion?.status === 'Draft';

  // Enrich lines for filtering
  const enrichedLines = lines.map((line) => ({
    ...line,
    dimension: formatDimension(line),
    total: lineTotal(line).toFixed(2),
  }));

  const {
    filters, setFilter, handleSort, sortField, sortDirection, processedData,
  } = useFilterableTable(enrichedLines, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'account_code', direction: 'asc' },
  });

  // ─── Load versions ──────────────────────────────────────────────────────────

  const loadVersions = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await listVersions();
      if (resp.success) {
        setVersions(resp.data);
        // Auto-select first version if none selected
        if (!selectedVersionId && resp.data.length > 0) {
          setSelectedVersionId(resp.data[0].id);
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setLoading(false);
    }
  }, [toast, t, selectedVersionId]);

  const loadLines = useCallback(async (versionId: number) => {
    try {
      setLinesLoading(true);
      const resp = await listLines(versionId);
      if (resp.success) setLines(resp.data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setLinesLoading(false);
    }
  }, [toast, t]);

  useEffect(() => { loadVersions(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selectedVersionId) {
      loadLines(selectedVersionId);
    } else {
      setLines([]);
    }
  }, [selectedVersionId, loadLines]);

  // ─── Version Actions ────────────────────────────────────────────────────────

  const handleApprove = async () => {
    if (!selectedVersionId) return;
    try {
      await transitionVersionStatus(selectedVersionId, { action: 'approve' });
      toast({ title: t('messages.versionApproved'), status: 'success', duration: 3000 });
      loadVersions();
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    }
  };

  const handleRevise = async () => {
    if (!selectedVersionId) return;
    try {
      await transitionVersionStatus(selectedVersionId, { action: 'revise' });
      toast({ title: t('messages.versionRevised'), status: 'success', duration: 3000 });
      loadVersions();
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    }
  };

  const handleActivate = async () => {
    if (!selectedVersionId) return;
    try {
      await activateVersion(selectedVersionId);
      toast({ title: t('messages.versionActivated'), status: 'success', duration: 3000 });
      loadVersions();
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    }
  };

  const handleDeleteVersion = async () => {
    if (!selectedVersionId) return;
    try {
      await deleteVersion(selectedVersionId);
      toast({ title: t('messages.versionDeleted'), status: 'success', duration: 3000 });
      setSelectedVersionId(null);
      setLines([]);
      loadVersions();
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    }
  };

  // ─── Line Actions ───────────────────────────────────────────────────────────

  const handleRowClick = (line: BudgetLine) => {
    setEditingLine(line);
    onLineOpen();
  };

  const handleAddLine = () => {
    setEditingLine(null);
    onLineOpen();
  };

  const handleSaveLine = async (values: {
    account_code: string;
    period_mode: PeriodMode;
    amounts: number[];
    annual_amount: number;
    dimension_type: string;
    dimension_value: string;
  }) => {
    if (!selectedVersionId) return;
    try {
      if (editingLine) {
        // Update existing line
        const data = values.period_mode === 'Monthly'
          ? { amounts: values.amounts }
          : { annual_amount: values.annual_amount };
        await updateLine(editingLine.id, data);
        toast({ title: t('messages.lineUpdated'), status: 'success', duration: 3000 });
      } else {
        // Create new line
        const data = values.period_mode === 'Monthly'
          ? {
              account_code: values.account_code,
              period_mode: 'Monthly' as const,
              amounts: values.amounts as [number, number, number, number, number, number, number, number, number, number, number, number],
              detail_dimension_type: (values.dimension_type || null) as DimensionType | null,
              detail_dimension_value: values.dimension_value || null,
            }
          : {
              account_code: values.account_code,
              period_mode: 'Annual' as const,
              annual_amount: values.annual_amount,
              detail_dimension_type: (values.dimension_type || null) as DimensionType | null,
              detail_dimension_value: values.dimension_value || null,
            };
        await createLine(selectedVersionId, data);
        toast({ title: t('messages.lineCreated'), status: 'success', duration: 3000 });
      }
      onLineClose();
      loadLines(selectedVersionId);
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    }
  };

  const handleDeleteLine = async (lineId: number) => {
    try {
      await deleteLine(lineId);
      toast({ title: t('messages.lineDeleted'), status: 'success', duration: 3000 });
      if (selectedVersionId) loadLines(selectedVersionId);
      onLineClose();
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    }
  };

  // ─── New Version Created ────────────────────────────────────────────────────

  const handleVersionCreated = (newVersionId: number) => {
    onNewVersionClose();
    loadVersions();
    setSelectedVersionId(newVersionId);
  };

  // ─── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <Flex justify="center" align="center" minH="200px">
        <Spinner size="xl" color="orange.300" />
      </Flex>
    );
  }

  const lineInitialValues = editingLine
    ? {
        account_code: editingLine.account_code,
        period_mode: editingLine.period_mode,
        amounts: [
          editingLine.month_01, editingLine.month_02, editingLine.month_03,
          editingLine.month_04, editingLine.month_05, editingLine.month_06,
          editingLine.month_07, editingLine.month_08, editingLine.month_09,
          editingLine.month_10, editingLine.month_11, editingLine.month_12,
        ].map(Number),
        annual_amount: lineTotal(editingLine),
        dimension_type: editingLine.detail_dimension_type || '',
        dimension_value: editingLine.detail_dimension_value || '',
      }
    : {
        account_code: '',
        period_mode: 'Monthly' as PeriodMode,
        amounts: Array(12).fill(0),
        annual_amount: 0,
        dimension_type: '',
        dimension_value: '',
      };

  return (
    <Box p={4}>
      {/* Header: Version selector + New Version */}
      <Flex wrap="wrap" gap={3} mb={4} align="center">
        <Select
          w={{ base: '100%', md: '350px' }}
          bg="gray.700"
          color="white"
          value={selectedVersionId || ''}
          onChange={(e) => setSelectedVersionId(Number(e.target.value) || null)}
          placeholder={t('messages.noVersions')}
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} ({v.fiscal_year}) — {v.status}{v.is_active ? ' ✓' : ''}
            </option>
          ))}
        </Select>

        <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={onNewVersionOpen}>
          {t('buttons.createVersion')}
        </Button>
      </Flex>

      {/* Status bar */}
      {selectedVersion && (
        <Flex wrap="wrap" gap={3} mb={4} align="center" bg="gray.750" p={3} borderRadius="md">
          <Badge colorScheme={selectedVersion.status === 'Draft' ? 'yellow' : selectedVersion.status === 'Approved' ? 'green' : 'blue'}>
            {selectedVersion.status}
          </Badge>
          <Text fontSize="sm" color="gray.300">
            {t('labels.fiscalYear')}: {selectedVersion.fiscal_year}
          </Text>
          {selectedVersion.is_active && (
            <Badge colorScheme="orange">{t('messages.activeVersion')}</Badge>
          )}

          {/* Contextual actions */}
          <HStack ml="auto" spacing={2}>
            {isDraft && (
              <Button size="xs" colorScheme="green" onClick={handleApprove}>
                {t('buttons.approve')}
              </Button>
            )}
            {selectedVersion.status === 'Approved' && (
              <Button size="xs" colorScheme="blue" onClick={handleRevise}>
                {t('buttons.revise')}
              </Button>
            )}
            {(selectedVersion.status === 'Approved' || selectedVersion.status === 'Revised') && !selectedVersion.is_active && (
              <Button size="xs" colorScheme="orange" onClick={handleActivate}>
                {t('buttons.activate')}
              </Button>
            )}
            {isDraft && (
              <Button size="xs" colorScheme="red" variant="outline" onClick={handleDeleteVersion}>
                {tc('buttons.delete')}
              </Button>
            )}
          </HStack>
        </Flex>
      )}

      {/* Lines table */}
      {selectedVersionId && (
        <>
          {linesLoading ? (
            <Flex justify="center" py={8}><Spinner color="orange.300" /></Flex>
          ) : (
            <Box overflowX="auto">
              <Table size="sm" variant="simple" bg="gray.800" color="white">
                <Thead>
                  <Tr>
                    <FilterableHeader
                      label={t('columns.accountCode')}
                      filterValue={filters.account_code}
                      onFilterChange={(v) => setFilter('account_code', v)}
                      sortable
                      sortDirection={sortField === 'account_code' ? sortDirection : null}
                      onSort={() => handleSort('account_code')}
                    />
                    <FilterableHeader
                      label={t('columns.dimension')}
                      filterValue={filters.dimension}
                      onFilterChange={(v) => setFilter('dimension', v)}
                      sortable
                      sortDirection={sortField === 'dimension' ? sortDirection : null}
                      onSort={() => handleSort('dimension')}
                    />
                    <FilterableHeader
                      label={t('labels.periodMode')}
                      filterValue={filters.period_mode}
                      onFilterChange={(v) => setFilter('period_mode', v)}
                      sortable
                      sortDirection={sortField === 'period_mode' ? sortDirection : null}
                      onSort={() => handleSort('period_mode')}
                    />
                    <FilterableHeader
                      label={t('columns.total')}
                      filterValue={filters.total}
                      onFilterChange={(v) => setFilter('total', v)}
                      sortable
                      sortDirection={sortField === 'total' ? sortDirection : null}
                      onSort={() => handleSort('total')}
                      isNumeric
                    />
                    {isDraft && <Td bg="gray.700" w="40px" />}
                  </Tr>
                </Thead>
                <Tbody>
                  {processedData.length === 0 ? (
                    <Tr>
                      <Td colSpan={isDraft ? 5 : 4} textAlign="center" color="gray.400">
                        {t('messages.noLines')}
                      </Td>
                    </Tr>
                  ) : (
                    processedData.map((line) => (
                      <Tr
                        key={line.id}
                        _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                        onClick={() => handleRowClick(line)}
                      >
                        <Td>{line.account_code}</Td>
                        <Td>{line.dimension}</Td>
                        <Td>{line.period_mode}</Td>
                        <Td isNumeric>{Number(line.total).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}</Td>
                        {isDraft && (
                          <Td onClick={(e) => e.stopPropagation()}>
                            <IconButton
                              aria-label="Delete line"
                              icon={<DeleteIcon />}
                              size="xs"
                              colorScheme="red"
                              variant="ghost"
                              onClick={() => handleDeleteLine(line.id)}
                            />
                          </Td>
                        )}
                      </Tr>
                    ))
                  )}
                </Tbody>
              </Table>
            </Box>
          )}

          {/* Action buttons below table */}
          {isDraft && (
            <HStack mt={4} spacing={3}>
              <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleAddLine}>
                {t('buttons.addLine')}
              </Button>
            </HStack>
          )}
        </>
      )}

      {/* Line Edit Modal */}
      <BudgetLineModal
        isOpen={isLineOpen}
        onClose={onLineClose}
        editingLine={editingLine}
        initialValues={lineInitialValues}
        onSave={handleSaveLine}
        onDelete={async () => { if (editingLine) await handleDeleteLine(editingLine.id); }}
      />

      {/* New Version Modal */}
      <BudgetNewVersionModal
        isOpen={isNewVersionOpen}
        onClose={onNewVersionClose}
        versions={versions}
        onCreated={handleVersionCreated}
      />
    </Box>
  );
};

export default BudgetPage;
