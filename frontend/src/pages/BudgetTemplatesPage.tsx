/**
 * BudgetTemplatesPage — Manages budget template CRUD with line configuration.
 * Follows BankingProcessor pattern: row-click opens modal, primary actions in header.
 *
 * Uses table-filter-framework-v2 hybrid approach:
 * - useFilterableTable + FilterableHeader for inline column text filters + sort
 * - Dark theme: gray.800/gray.700/white
 * - i18n: useTypedTranslation('budget') + common namespace
 * - Formik + Yup for modal validation
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner,
  Table, Thead, Tbody, Tr, Td, HStack, VStack,
  Badge, Collapse, useDisclosure,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';
import {
  BudgetTemplate,
  BudgetTemplateWithLines,
  PeriodMode,
  DimensionType,
  TemplateLineRequest,
  AITemplateRecommendation,
} from '../types/budget';
import {
  listTemplates,
  getTemplate,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  getTemplateRecommendations,
} from '../services/budgetService';
import { listAccounts } from '../services/chartOfAccountsService';
import { Account } from '../types/chartOfAccounts';
import { BudgetTemplateFormModal, LineFormState, EMPTY_LINE } from './BudgetTemplateFormModal';

/** Initial filters for useFilterableTable */
const INITIAL_FILTERS: Record<string, string> = {
  name: '',
  line_count: '',
  created_at: '',
};

const BudgetTemplatesPage: React.FC = () => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const [templates, setTemplates] = useState<BudgetTemplate[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);

  // Form state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [initialFormValues, setInitialFormValues] = useState<{ name: string; lines: LineFormState[] }>({
    name: '',
    lines: [{ ...EMPTY_LINE }],
  });

  // AI recommendation state
  const [recommendations, setRecommendations] = useState<AITemplateRecommendation[]>([]);
  const [recommendationsLoading, setRecommendationsLoading] = useState(false);
  const [showRecommendations, setShowRecommendations] = useState(false);
  // Accumulated lines from AI recommendations (before modal is opened)
  const [accumulatedLines, setAccumulatedLines] = useState<LineFormState[]>([]);

  // FilterableHeader integration
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<BudgetTemplate>(templates, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'name', direction: 'asc' },
  });

  const loadTemplates = useCallback(async () => {
    try {
      setLoading(true);
      const [templatesResp, accountsResp] = await Promise.all([
        listTemplates(),
        listAccounts(),
      ]);
      if (templatesResp.success) setTemplates(templatesResp.data);
      if (accountsResp.success) setAccounts(accountsResp.accounts || []);
    } catch {
      toast({ title: t('messages.loadError'), status: 'error' });
    } finally {
      setLoading(false);
    }
  }, [toast, t]);

  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  const handleCreate = () => {
    setEditingId(null);
    // Use accumulated lines from AI recommendations if available
    const linesToUse = accumulatedLines.length > 0 ? accumulatedLines : [{ ...EMPTY_LINE }];
    setInitialFormValues({ name: '', lines: linesToUse });
    onOpen();
  };

  const handleRowClick = async (template: BudgetTemplate) => {
    try {
      const resp = await getTemplate(template.id);
      if (resp.success) {
        const data = resp.data as BudgetTemplateWithLines;
        setEditingId(data.id);
        setInitialFormValues({
          name: data.name,
          lines: data.lines.map((l) => ({
            account_code: l.account_code,
            period_mode: l.period_mode,
            has_detail_dimension: l.has_detail_dimension,
            dimension_type: l.dimension_type,
          })),
        });
        onOpen();
      }
    } catch {
      toast({ title: t('messages.loadError'), status: 'error' });
    }
  };

  const handleSave = async (values: { name: string; lines: LineFormState[] }) => {
    const payload = {
      name: values.name.trim(),
      lines: values.lines.map((l): TemplateLineRequest => ({
        account_code: l.account_code.trim(),
        period_mode: l.period_mode,
        has_detail_dimension: l.has_detail_dimension,
        dimension_type: l.has_detail_dimension ? l.dimension_type : null,
        annualization_method: 'equal-spread',
      })),
    };

    try {
      if (editingId) {
        await updateTemplate(editingId, payload);
        toast({ title: t('messages.templateUpdated'), status: 'success' });
      } else {
        await createTemplate(payload);
        toast({ title: t('messages.templateCreated'), status: 'success' });
      }
      onClose();
      setAccumulatedLines([]);
      loadTemplates();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.saveError');
      toast({ title: message, status: 'error' });
    }
  };

  const handleDelete = async () => {
    if (!editingId) return;
    try {
      await deleteTemplate(editingId);
      toast({ title: t('messages.templateDeleted'), status: 'success' });
      onClose();
      loadTemplates();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.saveError');
      toast({ title: message, status: 'error' });
    }
  };

  // AI Recommendations
  const handleRecommend = async () => {
    try {
      setRecommendationsLoading(true);
      setShowRecommendations(true);
      const currentYear = new Date().getFullYear();
      const resp = await getTemplateRecommendations({ fiscal_year: currentYear });
      if (resp.success) {
        setRecommendations(resp.data.recommendations);
      } else {
        toast({ title: (resp as { error?: string }).error || t('messages.noRecommendations'), status: 'warning' });
        setRecommendations([]);
      }
    } catch {
      toast({ title: t('messages.loadError'), status: 'error' });
      setRecommendations([]);
    } finally {
      setRecommendationsLoading(false);
    }
  };

  const handleAddRecommendation = (rec: AITemplateRecommendation) => {
    const newLine: LineFormState = {
      account_code: rec.account_code,
      period_mode: rec.period_mode,
      has_detail_dimension: rec.has_detail_dimension,
      dimension_type: rec.dimension_type,
    };
    setAccumulatedLines((prev) => {
      if (prev.length === 0) return [newLine];
      if (prev.some(l => l.account_code === rec.account_code)) return prev;
      return [...prev, newLine];
    });
    toast({ title: `${rec.account_code} (${rec.account_name})`, status: 'info', duration: 2000 });
  };

  const confidenceColor = (level: string): string => {
    switch (level) {
      case 'high': return 'green';
      case 'medium': return 'yellow';
      default: return 'gray';
    }
  };

  if (loading) {
    return (
      <Flex justify="center" align="center" h="200px">
        <Spinner size="lg" />
      </Flex>
    );
  }

  return (
    <Box p={4}>
      {/* Header */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('titles.templates')}</Text>
        <HStack spacing={2}>
          <Button
            colorScheme="orange"
            variant="outline"
            onClick={handleRecommend}
            isLoading={recommendationsLoading}
            loadingText={tc('status.processing')}
            size={{ base: 'sm', md: 'sm' }}
          >
            {t('buttons.aiRecommend')}
          </Button>
          {accumulatedLines.length > 0 && (
            <Button colorScheme="orange" onClick={handleCreate} size={{ base: 'sm', md: 'sm' }}>
              {t('buttons.createTemplate')} ({accumulatedLines.length} {t('messages.accountsSelected')})
            </Button>
          )}
          {accumulatedLines.length === 0 && (
            <Button leftIcon={<AddIcon />} colorScheme="orange" onClick={handleCreate} size={{ base: 'sm', md: 'sm' }}>
              {t('buttons.createTemplate')}
            </Button>
          )}
        </HStack>
      </Flex>

      {/* AI Recommendations Panel */}
      <Collapse in={showRecommendations} animateOpacity>
        <Box mb={4} p={4} borderWidth="1px" borderRadius="md" bg="gray.700">
          <Flex justify="space-between" align="center" mb={3}>
            <Text fontWeight="semibold" color="white">{t('buttons.aiRecommend')}</Text>
            <Button size="xs" variant="ghost" color="white" onClick={() => setShowRecommendations(false)}>
              {tc('buttons.close')}
            </Button>
          </Flex>
          {recommendationsLoading ? (
            <Flex justify="center" py={4}><Spinner size="sm" /></Flex>
          ) : recommendations.length === 0 ? (
            <Text fontSize="sm" color="gray.300">{t('messages.noRecommendations')}</Text>
          ) : (
            <VStack spacing={2} align="stretch">
              <HStack spacing={2} mb={1}>
                <Button
                  size="xs"
                  colorScheme="orange"
                  onClick={() => recommendations.forEach(rec => handleAddRecommendation(rec))}
                >
                  {t('buttons.addAll')}
                </Button>
                <Text fontSize="xs" color="gray.300">
                  {accumulatedLines.length} {t('messages.accountsSelected')}
                </Text>
              </HStack>
              {recommendations.map((rec) => {
                const isAdded = accumulatedLines.some(l => l.account_code === rec.account_code);
                return (
                  <Flex
                    key={`${rec.account_code}-${rec.dimension_type}`}
                    p={3}
                    bg={isAdded ? 'whiteAlpha.100' : 'gray.600'}
                    borderWidth="1px"
                    borderColor={isAdded ? 'green.400' : 'gray.500'}
                    borderRadius="md"
                    align="center"
                    justify="space-between"
                  >
                    <Box flex="1">
                      <HStack spacing={2} mb={1}>
                        <Text fontWeight="medium" fontSize="sm" color="white">
                          {rec.account_code} — {rec.account_name}
                        </Text>
                        <Badge colorScheme={confidenceColor(rec.confidence)} fontSize="xs">
                          {rec.confidence}
                        </Badge>
                        <Badge variant="outline" fontSize="xs">{rec.period_mode}</Badge>
                        {rec.has_detail_dimension && (
                          <Badge variant="outline" colorScheme="blue" fontSize="xs">
                            {rec.dimension_type}
                          </Badge>
                        )}
                      </HStack>
                      <Text fontSize="xs" color="gray.300">{rec.reason}</Text>
                    </Box>
                    <Button
                      size="xs"
                      colorScheme="orange"
                      ml={3}
                      onClick={() => handleAddRecommendation(rec)}
                    >
                      {t('buttons.addToTemplate')}
                    </Button>
                  </Flex>
                );
              })}
            </VStack>
          )}
        </Box>
      </Collapse>

      {/* Table */}
      <Box overflowX="auto">
        <Table variant="simple" size="sm" bg="gray.800" color="white">
          <Thead>
            <Tr>
              <FilterableHeader
                label={t('columns.name')}
                filterValue={filters.name}
                onFilterChange={(v) => setFilter('name', v)}
                sortable
                sortDirection={sortField === 'name' ? sortDirection : null}
                onSort={() => handleSort('name')}
              />
              <FilterableHeader
                label={t('columns.lines')}
                filterValue={filters.line_count}
                onFilterChange={(v) => setFilter('line_count', v)}
                sortable
                sortDirection={sortField === 'line_count' ? sortDirection : null}
                onSort={() => handleSort('line_count')}
                isNumeric
              />
              <FilterableHeader
                label={t('columns.created')}
                filterValue={filters.created_at}
                onFilterChange={(v) => setFilter('created_at', v)}
                sortable
                sortDirection={sortField === 'created_at' ? sortDirection : null}
                onSort={() => handleSort('created_at')}
              />
            </Tr>
          </Thead>
          <Tbody>
            {processedData.map((tmpl) => (
              <Tr
                key={tmpl.id}
                _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                onClick={() => handleRowClick(tmpl)}
              >
                <Td color="white">{tmpl.name}</Td>
                <Td isNumeric color="white">{tmpl.line_count}</Td>
                <Td display={{ base: 'none', md: 'table-cell' }} color="white">
                  {new Date(tmpl.created_at).toLocaleDateString()}
                </Td>
              </Tr>
            ))}
            {processedData.length === 0 && (
              <Tr>
                <Td colSpan={3} textAlign="center" color="gray.400">
                  {t('messages.noTemplates')}
                </Td>
              </Tr>
            )}
          </Tbody>
        </Table>
      </Box>

      {/* Template Form Modal */}
      <BudgetTemplateFormModal
        isOpen={isOpen}
        onClose={onClose}
        editingId={editingId}
        initialFormValues={initialFormValues}
        accounts={accounts}
        onSave={handleSave}
        onDelete={handleDelete}
      />
    </Box>
  );
};

export default BudgetTemplatesPage;
