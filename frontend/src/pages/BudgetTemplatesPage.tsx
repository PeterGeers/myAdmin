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
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter,
  Input, Select, Checkbox, IconButton, useDisclosure,
  FormControl, FormLabel, FormErrorMessage,
  Badge, Collapse,
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon } from '@chakra-ui/icons';
import { Formik, Form, Field, FieldArray } from 'formik';
import * as Yup from 'yup';
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

/** Local form state for a template line */
interface LineFormState {
  account_code: string;
  period_mode: PeriodMode;
  has_detail_dimension: boolean;
  dimension_type: DimensionType | null;
}

const EMPTY_LINE: LineFormState = {
  account_code: '',
  period_mode: 'Monthly',
  has_detail_dimension: false,
  dimension_type: null,
};

/** Initial filters for useFilterableTable */
const INITIAL_FILTERS: Record<string, string> = {
  name: '',
  line_count: '',
  created_at: '',
};

/** Yup schema for template form validation */
const templateSchema = Yup.object({
  name: Yup.string().required('Name is required').max(100),
  lines: Yup.array().of(
    Yup.object({
      account_code: Yup.string().required('Account code is required'),
      period_mode: Yup.string().oneOf(['Monthly', 'Annual']).required(),
      has_detail_dimension: Yup.boolean(),
      dimension_type: Yup.string().nullable().when('has_detail_dimension', {
        is: true,
        then: (schema) => schema.required('Dimension type is required'),
      }),
    })
  ).min(1, 'At least one line is required'),
});

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

      {/* Modal — Formik + Yup */}
      <Modal isOpen={isOpen} onClose={onClose} size="xl" scrollBehavior="inside" closeOnOverlayClick={false}>
        <ModalOverlay />
        <ModalContent maxW="700px" bg="gray.800" color="white">
          <ModalHeader>{editingId ? t('buttons.createTemplate').replace('Create', 'Edit') : t('buttons.createTemplate')}</ModalHeader>
          <ModalCloseButton />
          <Formik
            initialValues={initialFormValues}
            validationSchema={templateSchema}
            onSubmit={handleSave}
            enableReinitialize
          >
            {({ values, isSubmitting, errors, touched }) => (
              <Form>
                <ModalBody>
                  <VStack spacing={4} align="stretch">
                    {/* Name */}
                    <Field name="name">
                      {({ field, meta }: any) => (
                        <FormControl isInvalid={!!(meta.touched && meta.error)}>
                          <FormLabel color="white">{t('labels.templateName')}</FormLabel>
                          <Input
                            {...field}
                            maxLength={100}
                            placeholder={t('labels.templateName')}
                            bg="gray.700"
                            color="white"
                          />
                          <FormErrorMessage>{meta.error}</FormErrorMessage>
                        </FormControl>
                      )}
                    </Field>

                    {/* Lines */}
                    <Box>
                      <Text fontWeight="semibold" mb={2} color="white">{t('columns.lines')}</Text>
                      {typeof errors.lines === 'string' && touched.lines && (
                        <Text color="red.300" fontSize="sm" mb={2}>{errors.lines}</Text>
                      )}
                      <FieldArray name="lines">
                        {({ push, remove }) => (
                          <VStack spacing={3} align="stretch">
                            {values.lines.map((_line, idx) => (
                              <Box key={idx} p={3} borderWidth="1px" borderRadius="md" bg="gray.700">
                                <HStack spacing={2} mb={2} align="flex-end">
                                  <FormControl flex="3">
                                    <FormLabel fontSize="xs" color="gray.300">{t('labels.accountCode')}</FormLabel>
                                    <Field name={`lines.${idx}.account_code`}>
                                      {({ field, meta }: any) => (
                                        <>
                                          <Select
                                            {...field}
                                            size="sm"
                                            placeholder={t('labels.accountCode')}
                                            bg="gray.600"
                                            color="white"
                                          >
                                            {accounts.map((acc) => (
                                              <option key={acc.Account} value={acc.Account}>
                                                {acc.Account} — {acc.AccountName}
                                              </option>
                                            ))}
                                          </Select>
                                          {meta.touched && meta.error && (
                                            <Text color="red.300" fontSize="xs">{meta.error}</Text>
                                          )}
                                        </>
                                      )}
                                    </Field>
                                  </FormControl>
                                  <FormControl flex="2">
                                    <FormLabel fontSize="xs" color="gray.300">{t('labels.periodMode')}</FormLabel>
                                    <Field name={`lines.${idx}.period_mode`}>
                                      {({ field }: any) => (
                                        <Select {...field} size="sm" bg="gray.600" color="white">
                                          <option value="Monthly">{t('labels.monthly')}</option>
                                          <option value="Annual">{t('labels.annual')}</option>
                                        </Select>
                                      )}
                                    </Field>
                                  </FormControl>
                                  <IconButton
                                    aria-label={tc('buttons.remove')}
                                    icon={<DeleteIcon />}
                                    size="sm"
                                    colorScheme="red"
                                    variant="ghost"
                                    onClick={() => remove(idx)}
                                    isDisabled={values.lines.length <= 1}
                                  />
                                </HStack>
                                <HStack spacing={4}>
                                  <Field name={`lines.${idx}.has_detail_dimension`}>
                                    {({ field, form }: any) => (
                                      <Checkbox
                                        size="sm"
                                        isChecked={field.value}
                                        onChange={(e) => {
                                          form.setFieldValue(`lines.${idx}.has_detail_dimension`, e.target.checked);
                                          form.setFieldValue(`lines.${idx}.dimension_type`, e.target.checked ? 'platform' : null);
                                        }}
                                        color="white"
                                      >
                                        {t('labels.detailDimension')}
                                      </Checkbox>
                                    )}
                                  </Field>
                                  {values.lines[idx]?.has_detail_dimension && (
                                    <Field name={`lines.${idx}.dimension_type`}>
                                      {({ field, meta }: any) => (
                                        <>
                                          <Select {...field} size="sm" w="180px" bg="gray.600" color="white">
                                            <option value="platform">Platform</option>
                                            <option value="ReferenceNumber">{t('labels.referenceNumber')}</option>
                                          </Select>
                                          {meta.touched && meta.error && (
                                            <Text color="red.300" fontSize="xs">{meta.error}</Text>
                                          )}
                                        </>
                                      )}
                                    </Field>
                                  )}
                                </HStack>
                              </Box>
                            ))}
                            <Button
                              size="sm"
                              leftIcon={<AddIcon />}
                              variant="outline"
                              onClick={() => push({ ...EMPTY_LINE })}
                              color="white"
                            >
                              {t('buttons.addTemplateLine')}
                            </Button>
                          </VStack>
                        )}
                      </FieldArray>
                    </Box>
                  </VStack>
                </ModalBody>

                <ModalFooter>
                  <HStack spacing={2}>
                    {editingId && (
                      <Button
                        colorScheme="red"
                        variant="outline"
                        onClick={handleDelete}
                        isLoading={isSubmitting}
                      >
                        {tc('buttons.delete')}
                      </Button>
                    )}
                    <Button variant="ghost" onClick={onClose} color="white">
                      {tc('buttons.cancel')}
                    </Button>
                    <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                      {tc('buttons.save')}
                    </Button>
                  </HStack>
                </ModalFooter>
              </Form>
            )}
          </Formik>
        </ModalContent>
      </Modal>
    </Box>
  );
};

export default BudgetTemplatesPage;
