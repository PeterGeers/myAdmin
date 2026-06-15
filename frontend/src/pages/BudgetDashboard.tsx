/**
 * BudgetDashboard — Budget vs Actuals comparison with drill-down navigation.
 *
 * Features:
 * - Fiscal year selector and period selector (month, quarter, ytd, full)
 * - Optional ReferenceNumber filter
 * - Drill-down: Parent → SubParent → Account
 * - Breadcrumb navigation for drill-down levels
 * - Color-coded variance: green (under-budget), red (over-budget)
 * - Notification when no active version exists
 *
 * UI patterns: FilterableHeader + useFilterableTable, dark theme, i18n, responsive
 * Reference: .kiro/specs/budget-ui-alignment/design.md
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, Flex, Text, Spinner, useToast,
  Table, Thead, Tbody, Tr, Td,
  Select, Input, HStack, Button, Alert, AlertIcon,
  Breadcrumb, BreadcrumbItem, BreadcrumbLink,
  Collapse, IconButton,
} from '@chakra-ui/react';
import { ChevronRightIcon, ChevronDownIcon, ChevronUpIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { DashboardData, DashboardLevel, DashboardPeriod, DashboardRow } from '../types/budget';
import { getDashboard, generateNarrative, queryBudget } from '../services/budgetService';

/** Format a number to 2 decimal places using Dutch locale */
const formatAmount = (value: number): string => {
  return new Intl.NumberFormat('nl-NL', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
};

/** Period options for the select dropdown */
const PERIOD_OPTIONS: { value: DashboardPeriod; label: string }[] = [
  { value: 'ytd', label: 'Year to Date' },
  { value: 'full', label: 'Full Year' },
  { value: 'q1', label: 'Q1' },
  { value: 'q2', label: 'Q2' },
  { value: 'q3', label: 'Q3' },
  { value: 'q4', label: 'Q4' },
  { value: 'month-1', label: 'January' },
  { value: 'month-2', label: 'February' },
  { value: 'month-3', label: 'March' },
  { value: 'month-4', label: 'April' },
  { value: 'month-5', label: 'May' },
  { value: 'month-6', label: 'June' },
  { value: 'month-7', label: 'July' },
  { value: 'month-8', label: 'August' },
  { value: 'month-9', label: 'September' },
  { value: 'month-10', label: 'October' },
  { value: 'month-11', label: 'November' },
  { value: 'month-12', label: 'December' },
];

/** Initial column filters for useFilterableTable */
const INITIAL_FILTERS: Record<string, string> = {
  code: '',
  name: '',
  budget: '',
  actual: '',
  variance: '',
};

const BudgetDashboard: React.FC = () => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');
  const toast = useToast();

  // ─── State ──────────────────────────────────────────────────────────────────
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [period, setPeriod] = useState<DashboardPeriod>('ytd');
  const [level, setLevel] = useState<DashboardLevel>('parent');
  const [parentCode, setParentCode] = useState<string | null>(null);
  const [subparentCode, setSubparentCode] = useState<string | null>(null);
  const [referenceNumber, setReferenceNumber] = useState('');
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  // ─── AI State ─────────────────────────────────────────────────────────────
  const [narrativeText, setNarrativeText] = useState('');
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [showNarrative, setShowNarrative] = useState(false);
  const [queryQuestion, setQueryQuestion] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryDescription, setQueryDescription] = useState('');

  // ─── FilterableTable hook ───────────────────────────────────────────────────
  const rows: DashboardRow[] = useMemo(
    () => dashboardData?.rows || [],
    [dashboardData],
  );

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<DashboardRow>(rows, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'code', direction: 'asc' },
  });

  /** Helper for sortDirection per column */
  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  // ─── Fetch dashboard data ───────────────────────────────────────────────────
  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const params: {
        year: number;
        level: DashboardLevel;
        period: DashboardPeriod;
        parent_code?: string;
        subparent_code?: string;
        reference_number?: string;
      } = { year, level, period };

      if (parentCode) params.parent_code = parentCode;
      if (subparentCode) params.subparent_code = subparentCode;
      if (referenceNumber.trim()) params.reference_number = referenceNumber.trim();

      const resp = await getDashboard(params);
      if (resp.success) {
        setDashboardData(resp.data);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setLoading(false);
    }
  }, [year, level, period, parentCode, subparentCode, referenceNumber, toast, t]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  // ─── Drill-down handlers ────────────────────────────────────────────────────
  const handleRowClick = (row: DashboardRow) => {
    if (level === 'parent') {
      setParentCode(row.code);
      setLevel('subparent');
    } else if (level === 'subparent') {
      setSubparentCode(row.code);
      setLevel('account');
    }
    // Account level rows are not clickable (leaf)
  };

  const navigateToParent = () => {
    setLevel('parent');
    setParentCode(null);
    setSubparentCode(null);
  };

  const navigateToSubparent = () => {
    setLevel('subparent');
    setSubparentCode(null);
  };

  // ─── AI handlers ──────────────────────────────────────────────────────────
  const handleGenerateNarrative = async () => {
    try {
      setNarrativeLoading(true);
      const resp = await generateNarrative({ year, level, period });
      if (resp.success) {
        setNarrativeText(resp.data.narrative);
        setShowNarrative(true);
      } else {
        toast({ title: resp.error || t('messages.loadError'), status: 'error', duration: 4000 });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setNarrativeLoading(false);
    }
  };

  const handleQuerySubmit = async () => {
    if (!queryQuestion.trim()) return;
    try {
      setQueryLoading(true);
      setQueryDescription('');
      const resp = await queryBudget({ question: queryQuestion.trim(), year });
      if (resp.success) {
        const { interpreted_params, filter_description } = resp.data;
        // Apply interpreted filters to the dashboard
        if (interpreted_params.year) setYear(interpreted_params.year);
        if (interpreted_params.level) setLevel(interpreted_params.level);
        if (interpreted_params.period) setPeriod(interpreted_params.period);
        setParentCode(interpreted_params.parent_code || null);
        setSubparentCode(interpreted_params.subparent_code || null);
        if (interpreted_params.reference_number) {
          setReferenceNumber(interpreted_params.reference_number);
        }
        setQueryDescription(`Interpreted: ${filter_description}`);
      } else {
        toast({ title: resp.error || t('messages.loadError'), status: 'warning', duration: 5000 });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: message, status: 'warning', duration: 5000 });
    } finally {
      setQueryLoading(false);
    }
  };

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <Box p={6}>
      {/* Header */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">
          {t('titles.dashboard')}
        </Text>
      </Flex>

      {/* Filters row */}
      <HStack spacing={4} mb={4} flexWrap="wrap">
        <Box>
          <Text fontSize="xs" color="gray.400" mb={1}>{t('labels.year')}</Text>
          <Input
            type="number"
            size="sm"
            width="100px"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            min={2000}
            max={2100}
            bg="whiteAlpha.100"
            color="white"
          />
        </Box>
        <Box>
          <Text fontSize="xs" color="gray.400" mb={1}>{t('labels.period')}</Text>
          <Select
            size="sm"
            width="160px"
            value={period}
            onChange={(e) => setPeriod(e.target.value as DashboardPeriod)}
            bg="whiteAlpha.100"
            color="white"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value} style={{ color: 'black' }}>
                {opt.label}
              </option>
            ))}
          </Select>
        </Box>
        <Box>
          <Text fontSize="xs" color="gray.400" mb={1}>{t('labels.referenceNumber')}</Text>
          <Input
            size="sm"
            width="160px"
            placeholder="Optional filter"
            value={referenceNumber}
            onChange={(e) => setReferenceNumber(e.target.value)}
            bg="whiteAlpha.100"
            color="white"
          />
        </Box>
        <Box alignSelf="flex-end">
          <Button
            size="sm"
            colorScheme="orange"
            variant="outline"
            onClick={handleGenerateNarrative}
            isLoading={narrativeLoading}
            loadingText={tc('status.loading')}
          >
            {t('buttons.generateSummary')}
          </Button>
        </Box>
      </HStack>

      {/* Natural language query */}
      <HStack spacing={2} mb={4}>
        <Input
          size="sm"
          placeholder="Ask a question about your budget (e.g. 'Which accounts are over budget?')"
          value={queryQuestion}
          onChange={(e) => setQueryQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleQuerySubmit()}
          bg="whiteAlpha.100"
          color="white"
          maxW="500px"
        />
        <Button
          size="sm"
          colorScheme="orange"
          onClick={handleQuerySubmit}
          isLoading={queryLoading}
          loadingText={tc('status.loading')}
          isDisabled={!queryQuestion.trim()}
        >
          {t('buttons.ask')}
        </Button>
      </HStack>
      {queryDescription && (
        <Text fontSize="xs" color="gray.400" mb={3} fontStyle="italic">
          {queryDescription}
        </Text>
      )}

      {/* AI Narrative panel */}
      {narrativeText && (
        <Box mb={4}>
          <Flex align="center" mb={1}>
            <Text fontSize="sm" fontWeight="semibold" color="orange.300">
              AI Summary
            </Text>
            <IconButton
              aria-label={showNarrative ? 'Hide summary' : 'Show summary'}
              icon={showNarrative ? <ChevronUpIcon /> : <ChevronDownIcon />}
              size="xs"
              variant="ghost"
              colorScheme="orange"
              ml={2}
              onClick={() => setShowNarrative(!showNarrative)}
            />
          </Flex>
          <Collapse in={showNarrative} animateOpacity>
            <Box
              bg="whiteAlpha.100"
              borderRadius="md"
              p={4}
              borderLeft="3px solid"
              borderColor="orange.300"
            >
              <Text fontSize="sm" color="gray.200" whiteSpace="pre-wrap">
                {narrativeText}
              </Text>
            </Box>
          </Collapse>
        </Box>
      )}

      {/* No-active-version notification */}
      {dashboardData?.notification && (
        <Alert status="warning" mb={4} borderRadius="md" color="gray.800">
          <AlertIcon />
          {dashboardData.notification}
        </Alert>
      )}

      {/* Active version info */}
      {dashboardData?.active_version && (
        <Text fontSize="sm" color="gray.400" mb={2}>
          {t('messages.activeVersion')}: {dashboardData.active_version.name}
        </Text>
      )}

      {/* Breadcrumb */}
      <Flex align="center" mb={4}>
        <Breadcrumb separator={<ChevronRightIcon color="gray.400" />} fontSize="sm">
          <BreadcrumbItem isCurrentPage={level === 'parent'}>
            <BreadcrumbLink
              onClick={navigateToParent}
              color={level === 'parent' ? 'orange.300' : 'gray.400'}
              cursor="pointer"
            >
              Parent
            </BreadcrumbLink>
          </BreadcrumbItem>
          {(level === 'subparent' || level === 'account') && (
            <BreadcrumbItem isCurrentPage={level === 'subparent'}>
              <BreadcrumbLink
                onClick={navigateToSubparent}
                color={level === 'subparent' ? 'orange.300' : 'gray.400'}
                cursor="pointer"
              >
                SubParent: {parentCode}
              </BreadcrumbLink>
            </BreadcrumbItem>
          )}
          {level === 'account' && (
            <BreadcrumbItem isCurrentPage>
              <BreadcrumbLink color="orange.300">
                Account: {subparentCode}
              </BreadcrumbLink>
            </BreadcrumbItem>
          )}
        </Breadcrumb>

        {/* Back button */}
        {level !== 'parent' && (
          <Button
            size="xs"
            variant="ghost"
            colorScheme="orange"
            ml={4}
            onClick={level === 'account' ? navigateToSubparent : navigateToParent}
          >
            ← Back
          </Button>
        )}
      </Flex>

      {/* Table */}
      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner size="lg" color="orange.300" />
        </Flex>
      ) : !dashboardData || processedData.length === 0 ? (
        <Text color="gray.400">{t('messages.noData')}</Text>
      ) : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <FilterableHeader
                  label={t('columns.code')}
                  filterValue={filters.code}
                  onFilterChange={(v) => setFilter('code', v)}
                  sortable
                  sortDirection={columnSortDirection('code')}
                  onSort={() => handleSort('code')}
                />
                <FilterableHeader
                  label={t('columns.name')}
                  filterValue={filters.name}
                  onFilterChange={(v) => setFilter('name', v)}
                  sortable
                  sortDirection={columnSortDirection('name')}
                  onSort={() => handleSort('name')}
                />
                <FilterableHeader
                  label={t('columns.budget')}
                  filterValue={filters.budget}
                  onFilterChange={(v) => setFilter('budget', v)}
                  sortable
                  isNumeric
                  sortDirection={columnSortDirection('budget')}
                  onSort={() => handleSort('budget')}
                />
                <FilterableHeader
                  label={t('columns.actual')}
                  filterValue={filters.actual}
                  onFilterChange={(v) => setFilter('actual', v)}
                  sortable
                  isNumeric
                  sortDirection={columnSortDirection('actual')}
                  onSort={() => handleSort('actual')}
                />
                <FilterableHeader
                  label={t('columns.variance')}
                  filterValue={filters.variance}
                  onFilterChange={(v) => setFilter('variance', v)}
                  sortable
                  isNumeric
                  sortDirection={columnSortDirection('variance')}
                  onSort={() => handleSort('variance')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map((row) => (
                <Tr
                  key={row.code}
                  _hover={level !== 'account' ? { bg: 'gray.700', cursor: 'pointer' } : undefined}
                  onClick={() => level !== 'account' && handleRowClick(row)}
                >
                  <Td color="white">{row.code}</Td>
                  <Td color="white" display={{ base: 'none', md: 'table-cell' }}>{row.name}</Td>
                  <Td color="white" isNumeric>{formatAmount(row.budget)}</Td>
                  <Td color="white" isNumeric>{formatAmount(row.actual)}</Td>
                  <Td
                    isNumeric
                    color={row.variance > 0 ? 'red.400' : row.variance < 0 ? 'green.400' : 'white'}
                    fontWeight={row.variance !== 0 ? 'semibold' : 'normal'}
                  >
                    {formatAmount(row.variance)}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}
    </Box>
  );
};

export default BudgetDashboard;
