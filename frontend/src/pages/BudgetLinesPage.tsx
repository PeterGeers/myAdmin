/**
 * BudgetLinesPage — Budget line entry per version with monthly/annual amounts.
 *
 * Features:
 * - Version selector dropdown
 * - Table showing budget lines (account code, period mode, dimension, total)
 * - Row-click opens edit modal
 * - Line form: account code, period mode toggle, monthly/annual inputs, optional dimension
 * - Generate Draft button: template selection, fiscal year, version name
 * - Copy Budget button: source version, target year, version name
 *
 * UI patterns applied: i18n, FilterableHeader, dark theme, responsive, Formik+Yup modals, button styling.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Box, Flex, Spinner, useToast, useDisclosure } from '@chakra-ui/react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useFilterableTable } from '../hooks/useFilterableTable';
import {
  BudgetLineTable,
  BudgetLineToolbar,
  AISuggestionsModal,
  lineTotal,
  formatDimension,
} from '../components/budget';
import type { BudgetLineFormValues, EnrichedBudgetLine } from '../components/budget';
import BudgetLineModal from './BudgetLineModal';
import GenerateDraftModal from './GenerateDraftModal';
import CopyBudgetModal from './CopyBudgetModal';
import {
  BudgetVersion,
  BudgetLine,
  BudgetTemplate,
  AIDraftSuggestion,
  PeriodMode,
  DimensionType,
} from '../types/budget';
import {
  listVersions,
  listLines,
  createLine,
  updateLine,
  deleteLine,
  generateDraft,
  copyBudget,
  listTemplates,
  getDraftSuggestions,
} from '../services/budgetService';

const INITIAL_FILTERS: Record<string, string> = {
  account_code: '',
  period_mode: '',
  dimension: '',
  total: '',
};

const BudgetLinesPage: React.FC = () => {
  const toast = useToast();
  const { t } = useTypedTranslation('budget');

  // Data state
  const [versions, setVersions] = useState<BudgetVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [lines, setLines] = useState<BudgetLine[]>([]);
  const [templates, setTemplates] = useState<BudgetTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [linesLoading, setLinesLoading] = useState(false);

  // Line modal
  const { isOpen: isLineOpen, onOpen: onLineOpen, onClose: onLineClose } = useDisclosure();
  const [editingLine, setEditingLine] = useState<BudgetLine | null>(null);
  const [lineForm, setLineForm] = useState<BudgetLineFormValues>({
    account_code: '',
    period_mode: 'Monthly' as PeriodMode,
    amounts: Array(12).fill(0) as number[],
    annual_amount: 0,
    dimension_type: '',
    dimension_value: '',
  });

  // Generate Draft modal
  const { isOpen: isDraftOpen, onOpen: onDraftOpen, onClose: onDraftClose } = useDisclosure();
  const [draftForm, setDraftForm] = useState({
    template_id: 0,
    fiscal_year: new Date().getFullYear(),
    version_name: '',
  });

  // Copy Budget modal
  const { isOpen: isCopyOpen, onOpen: onCopyOpen, onClose: onCopyClose } = useDisclosure();
  const [copyForm, setCopyForm] = useState({
    source_version_id: 0,
    target_fiscal_year: new Date().getFullYear() + 1,
    version_name: '',
  });

  // AI Suggestions modal
  const { isOpen: isSuggestionsOpen, onOpen: onSuggestionsOpen, onClose: onSuggestionsClose } = useDisclosure();
  const [contextNotes, setContextNotes] = useState('');
  const [suggestions, setSuggestions] = useState<AIDraftSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  // FilterableTable — enrich lines with computed fields for filtering
  const enrichedLines: EnrichedBudgetLine[] = lines.map((line) => ({
    ...line,
    dimension: formatDimension(line),
    total: lineTotal(line).toFixed(2),
  }));

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
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
        if (resp.data.length > 0 && !selectedVersionId) {
          setSelectedVersionId(resp.data[0].id);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: msg, status: 'error', duration: 4000 });
    } finally {
      setLoading(false);
    }
  }, [toast, selectedVersionId, t]);

  const loadLines = useCallback(async (versionId: number) => {
    try {
      setLinesLoading(true);
      const resp = await listLines(versionId);
      if (resp.success) setLines(resp.data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: msg, status: 'error', duration: 4000 });
    } finally {
      setLinesLoading(false);
    }
  }, [toast, t]);

  useEffect(() => { loadVersions(); }, [loadVersions]);

  useEffect(() => {
    if (selectedVersionId) loadLines(selectedVersionId);
  }, [selectedVersionId, loadLines]);

  // ─── Line form helpers ──────────────────────────────────────────────────────

  const resetLineForm = () => {
    setEditingLine(null);
    setLineForm({
      account_code: '',
      period_mode: 'Monthly',
      amounts: Array(12).fill(0),
      annual_amount: 0,
      dimension_type: '',
      dimension_value: '',
    });
  };

  const handleAddLine = () => {
    resetLineForm();
    onLineOpen();
  };

  const handleRowClick = (line: BudgetLine) => {
    setEditingLine(line);
    setLineForm({
      account_code: line.account_code,
      period_mode: line.period_mode,
      amounts: [
        line.month_01, line.month_02, line.month_03, line.month_04,
        line.month_05, line.month_06, line.month_07, line.month_08,
        line.month_09, line.month_10, line.month_11, line.month_12,
      ],
      annual_amount: lineTotal(line),
      dimension_type: line.detail_dimension_type || '',
      dimension_value: line.detail_dimension_value || '',
    });
    onLineOpen();
  };

  const handleLineSave = async (values: BudgetLineFormValues) => {
    if (!selectedVersionId) return;

    const dimType = values.dimension_type || null;
    const dimValue = values.dimension_value || null;

    if (editingLine) {
      if (values.period_mode === 'Monthly') {
        await updateLine(editingLine.id, {
          account_code: values.account_code.trim(),
          period_mode: 'Monthly',
          amounts: values.amounts as [number, number, number, number, number, number, number, number, number, number, number, number],
          detail_dimension_type: dimType as DimensionType | null,
          detail_dimension_value: dimValue,
        });
      } else {
        await updateLine(editingLine.id, {
          account_code: values.account_code.trim(),
          period_mode: 'Annual',
          annual_amount: values.annual_amount,
          detail_dimension_type: dimType as DimensionType | null,
          detail_dimension_value: dimValue,
        });
      }
      toast({ title: t('messages.lineUpdated'), status: 'success', duration: 3000 });
    } else {
      if (values.period_mode === 'Monthly') {
        await createLine(selectedVersionId, {
          account_code: values.account_code.trim(),
          period_mode: 'Monthly',
          amounts: values.amounts as [number, number, number, number, number, number, number, number, number, number, number, number],
          detail_dimension_type: dimType as DimensionType | null,
          detail_dimension_value: dimValue,
        });
      } else {
        await createLine(selectedVersionId, {
          account_code: values.account_code.trim(),
          period_mode: 'Annual',
          annual_amount: values.annual_amount,
          detail_dimension_type: dimType as DimensionType | null,
          detail_dimension_value: dimValue,
        });
      }
      toast({ title: t('messages.lineCreated'), status: 'success', duration: 3000 });
    }

    onLineClose();
    resetLineForm();
    loadLines(selectedVersionId);
  };

  const handleLineDelete = async () => {
    if (!editingLine || !selectedVersionId) return;
    await deleteLine(editingLine.id);
    toast({ title: t('messages.lineDeleted'), status: 'success', duration: 3000 });
    onLineClose();
    resetLineForm();
    loadLines(selectedVersionId);
  };

  // ─── Generate Draft ─────────────────────────────────────────────────────────

  const handleOpenDraft = async () => {
    try {
      const resp = await listTemplates();
      if (resp.success) setTemplates(resp.data);
    } catch {
      // templates may already be loaded
    }
    setDraftForm({ template_id: 0, fiscal_year: new Date().getFullYear(), version_name: '' });
    onDraftOpen();
  };

  const handleGenerateDraft = async (values: typeof draftForm) => {
    try {
      const resp = await generateDraft({
        template_id: values.template_id,
        fiscal_year: values.fiscal_year,
        version_name: values.version_name.trim(),
      });
      if (resp.success) {
        toast({
          title: t('messages.draftGenerated'),
          status: 'success',
          duration: 4000,
        });
        onDraftClose();
        loadVersions();
      }
    } catch (err: any) {
      toast({
        title: t('messages.error'),
        description: err.message || t('messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    }
  };

  // ─── Copy Budget ────────────────────────────────────────────────────────────

  const handleOpenCopy = () => {
    setCopyForm({
      source_version_id: selectedVersionId || 0,
      target_fiscal_year: new Date().getFullYear() + 1,
      version_name: '',
    });
    onCopyOpen();
  };

  const handleCopyBudget = async (values: typeof copyForm) => {
    const resp = await copyBudget({
      source_version_id: values.source_version_id,
      target_fiscal_year: values.target_fiscal_year,
      version_name: values.version_name.trim(),
    });
    if (resp.success) {
      toast({
        title: t('messages.budgetCopied'),
        status: 'success',
        duration: 4000,
      });
      onCopyClose();
      loadVersions();
    }
  };

  // ─── AI Suggestions ───────────────────────────────────────────────────────

  const selectedVersion = versions.find((v) => v.id === selectedVersionId);
  const isDraftVersion = selectedVersion?.status === 'Draft';

  const handleOpenSuggestions = () => {
    setContextNotes('');
    setSuggestions([]);
    onSuggestionsOpen();
  };

  const handleGetSuggestions = async () => {
    if (!selectedVersionId) return;
    if (!contextNotes.trim()) {
      toast({ title: t('messages.noSuggestions'), status: 'warning', duration: 3000 });
      return;
    }
    try {
      setSuggestionsLoading(true);
      const resp = await getDraftSuggestions({
        version_id: selectedVersionId,
        context_notes: contextNotes.trim(),
      });
      if (resp.success) {
        setSuggestions(resp.data.suggestions);
        if (resp.data.suggestions.length === 0) {
          toast({ title: t('messages.noSuggestions'), status: 'info', duration: 3000 });
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('messages.saveError');
      toast({ title: msg, status: 'error', duration: 4000 });
    } finally {
      setSuggestionsLoading(false);
    }
  };

  const handleAcceptSuggestion = (suggestion: AIDraftSuggestion) => {
    const existingLine = lines.find((l) => l.account_code === suggestion.account_code);
    const amounts = existingLine
      ? [
          existingLine.month_01, existingLine.month_02, existingLine.month_03,
          existingLine.month_04, existingLine.month_05, existingLine.month_06,
          existingLine.month_07, existingLine.month_08, existingLine.month_09,
          existingLine.month_10, existingLine.month_11, existingLine.month_12,
        ]
      : Array(12).fill(0) as number[];

    suggestion.affected_months.forEach((month, idx) => {
      amounts[month - 1] = suggestion.suggested_amounts[idx];
    });

    setEditingLine(existingLine || null);
    setLineForm({
      account_code: suggestion.account_code,
      period_mode: 'Monthly',
      amounts,
      annual_amount: amounts.reduce((sum, a) => sum + a, 0),
      dimension_type: existingLine?.detail_dimension_type || '',
      dimension_value: existingLine?.detail_dimension_value || '',
    });

    onSuggestionsClose();
    onLineOpen();
  };

  const handleRejectSuggestion = (index: number) => {
    setSuggestions((prev) => prev.filter((_, i) => i !== index));
  };

  // ─── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <Flex justify="center" align="center" h="200px">
        <Spinner size="lg" color="orange.300" />
      </Flex>
    );
  }

  return (
    <Box p={6}>
      {/* Toolbar */}
      <BudgetLineToolbar
        versions={versions}
        selectedVersionId={selectedVersionId}
        onVersionChange={setSelectedVersionId}
        isDraftVersion={isDraftVersion ?? false}
        onAddLine={handleAddLine}
        onGenerateDraft={handleOpenDraft}
        onCopyBudget={handleOpenCopy}
        onAISuggestions={handleOpenSuggestions}
      />

      {/* Lines Table */}
      <BudgetLineTable
        processedData={processedData as EnrichedBudgetLine[]}
        loading={linesLoading}
        isEmpty={lines.length === 0}
        filters={filters}
        setFilter={setFilter}
        sortField={sortField}
        sortDirection={sortDirection}
        handleSort={handleSort}
        onRowClick={handleRowClick}
      />

      {/* Line Edit/Create Modal */}
      <BudgetLineModal
        isOpen={isLineOpen}
        onClose={onLineClose}
        editingLine={editingLine}
        initialValues={lineForm}
        onSave={handleLineSave}
        onDelete={handleLineDelete}
      />

      {/* Generate Draft Modal */}
      <GenerateDraftModal
        isOpen={isDraftOpen}
        onClose={onDraftClose}
        templates={templates}
        initialValues={draftForm}
        onGenerate={handleGenerateDraft}
      />

      {/* Copy Budget Modal */}
      <CopyBudgetModal
        isOpen={isCopyOpen}
        onClose={onCopyClose}
        versions={versions}
        initialValues={copyForm}
        onCopy={handleCopyBudget}
      />

      {/* AI Suggestions Modal */}
      <AISuggestionsModal
        isOpen={isSuggestionsOpen}
        onClose={onSuggestionsClose}
        suggestions={suggestions}
        loading={suggestionsLoading}
        contextNotes={contextNotes}
        onContextNotesChange={setContextNotes}
        onGetSuggestions={handleGetSuggestions}
        onAccept={handleAcceptSuggestion}
        onReject={handleRejectSuggestion}
      />
    </Box>
  );
};

export default BudgetLinesPage;
