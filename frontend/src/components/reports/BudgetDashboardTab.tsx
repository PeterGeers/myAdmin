/**
 * BudgetDashboardTab — Budget vs Actuals comparison for FIN Reports.
 *
 * Replaces the standalone BudgetDashboard page. Key difference:
 * - Version dropdown (active versions) instead of year selector
 * - Year is implied by the selected version
 * - Drill-down: Parent → SubParent → Account with breadcrumbs
 * - Period filter, variance color coding, AI narrative + query
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, Flex, Text, Spinner, useToast,
  Table, Thead, Tbody, Tr, Td,
  Select, Input, HStack, Button, Alert, AlertIcon,
  Collapse, IconButton,
} from '@chakra-ui/react';
import { ChevronDownIcon, ChevronUpIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { BudgetVersion, DashboardData, DashboardLevel, DashboardPeriod, DashboardRow } from '../../types/budget';
import { listVersions, getDashboard, generateNarrative, queryBudget } from '../../services/budgetService';

/** Format a number to 2 decimal places using Dutch locale */
const formatAmount = (value: number): string =>
  new Intl.NumberFormat('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);

/** Period options */
const PERIOD_OPTIONS: { value: DashboardPeriod; label: string }[] = [
  { value: 'ytd', label: 'Year to Date' },
  { value: 'full', label: 'Full Year' },
  { value: 'q1', label: 'Q1' }, { value: 'q2', label: 'Q2' },
  { value: 'q3', label: 'Q3' }, { value: 'q4', label: 'Q4' },
  { value: 'month-1', label: 'Jan' }, { value: 'month-2', label: 'Feb' },
  { value: 'month-3', label: 'Mar' }, { value: 'month-4', label: 'Apr' },
  { value: 'month-5', label: 'May' }, { value: 'month-6', label: 'Jun' },
  { value: 'month-7', label: 'Jul' }, { value: 'month-8', label: 'Aug' },
  { value: 'month-9', label: 'Sep' }, { value: 'month-10', label: 'Oct' },
  { value: 'month-11', label: 'Nov' }, { value: 'month-12', label: 'Dec' },
];

const INITIAL_FILTERS: Record<string, string> = {
  code: '', name: '', budget: '', actual: '', variance: '',
};

const BudgetDashboardTab: React.FC = () => {
  const { t } = useTypedTranslation('budget');
  const toast = useToast();

  // Version state
  const [activeVersions, setActiveVersions] = useState<BudgetVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(true);

  // Dashboard state
  const [period, setPeriod] = useState<DashboardPeriod>('ytd');
  const [level, setLevel] = useState<DashboardLevel>('parent');
  const [parentCode, setParentCode] = useState<string | null>(null);
  const [subparentCode, setSubparentCode] = useState<string | null>(null);
  const [referenceNumber, setReferenceNumber] = useState('');
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);

  // AI state
  const [narrativeText, setNarrativeText] = useState('');
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [showNarrative, setShowNarrative] = useState(false);
  const [queryQuestion, setQueryQuestion] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);

  // FilterableTable
  const rows: DashboardRow[] = useMemo(() => dashboardData?.rows || [], [dashboardData]);
  const { filters, setFilter, handleSort, sortField, sortDirection, processedData } =
    useFilterableTable<DashboardRow>(rows, {
      initialFilters: INITIAL_FILTERS,
      defaultSort: { field: 'code', direction: 'asc' },
    });

  // ─── Load active versions ─────────────────────────────────────────────────

  useEffect(() => {
    const loadActiveVersions = async () => {
      try {
        setVersionsLoading(true);
        const resp = await listVersions();
        if (resp.success) {
          const active = resp.data.filter((v) => v.is_active);
          setActiveVersions(active);
          if (active.length > 0 && !selectedVersionId) {
            setSelectedVersionId(active[0].id);
          }
        }
      } catch {
        // Non-critical
      } finally {
        setVersionsLoading(false);
      }
    };
    loadActiveVersions();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Fetch dashboard ──────────────────────────────────────────────────────

  const fetchDashboard = useCallback(async () => {
    if (!selectedVersionId) return;
    try {
      setLoading(true);
      const params: any = { version_id: selectedVersionId, level, period };
      if (parentCode) params.parent_code = parentCode;
      if (subparentCode) params.subparent_code = subparentCode;
      if (referenceNumber.trim()) params.reference_number = referenceNumber.trim();

      const resp = await getDashboard(params);
      if (resp.success) setDashboardData(resp.data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('messages.loadError');
      toast({ title: message, status: 'error', duration: 4000 });
    } finally {
      setLoading(false);
    }
  }, [selectedVersionId, level, period, parentCode, subparentCode, referenceNumber, toast, t]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  // ─── Drill-down ───────────────────────────────────────────────────────────

  const handleRowClick = (row: DashboardRow) => {
    if (level === 'parent') { setParentCode(row.code); setLevel('subparent'); }
    else if (level === 'subparent') { setSubparentCode(row.code); setLevel('account'); }
  };

  const navigateToParent = () => { setLevel('parent'); setParentCode(null); setSubparentCode(null); };
  const navigateToSubparent = () => { setLevel('subparent'); setSubparentCode(null); };

  // ─── AI handlers ──────────────────────────────────────────────────────────

  const selectedVersion = activeVersions.find((v) => v.id === selectedVersionId);
  const year = selectedVersion?.fiscal_year || new Date().getFullYear();

  const handleGenerateNarrative = async () => {
    try {
      setNarrativeLoading(true);
      const resp = await generateNarrative({ year, level, period });
      if (resp.success) { setNarrativeText(resp.data.narrative); setShowNarrative(true); }
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    } finally { setNarrativeLoading(false); }
  };

  const handleQuery = async () => {
    if (!queryQuestion.trim()) return;
    try {
      setQueryLoading(true);
      const resp = await queryBudget({ question: queryQuestion.trim(), year });
      if (resp.success) {
        const { interpreted_params } = resp.data;
        if (interpreted_params.level) setLevel(interpreted_params.level);
        if (interpreted_params.period) setPeriod(interpreted_params.period);
        setParentCode(interpreted_params.parent_code || null);
        setSubparentCode(interpreted_params.subparent_code || null);
        if (interpreted_params.reference_number) setReferenceNumber(interpreted_params.reference_number);
      }
    } catch (err: any) {
      toast({ title: err.message, status: 'warning', duration: 5000 });
    } finally { setQueryLoading(false); }
  };

  // ─── Render ───────────────────────────────────────────────────────────────

  if (versionsLoading) {
    return <Flex justify="center" py={8}><Spinner color="orange.300" /></Flex>;
  }

  if (activeVersions.length === 0) {
    return (
      <Alert status="info" bg="gray.700" color="white" borderRadius="md">
        <AlertIcon />
        <Text>No active budget versions available. Activate a budget version in Budget Preparation to see comparisons here.</Text>
      </Alert>
    );
  }

  return (
    <Box>
      {/* Controls: Version + Period + Reference */}
      <Flex wrap="wrap" gap={3} mb={4} align="center">
        <Select
          w={{ base: '100%', md: '280px' }}
          bg="gray.700" color="white" size="sm"
          value={selectedVersionId || ''}
          onChange={(e) => { setSelectedVersionId(Number(e.target.value) || null); navigateToParent(); }}
        >
          {activeVersions.map((v) => (
            <option key={v.id} value={v.id}>{v.name} ({v.fiscal_year})</option>
          ))}
        </Select>

        <Select
          w="150px" bg="gray.700" color="white" size="sm"
          value={period}
          onChange={(e) => setPeriod(e.target.value as DashboardPeriod)}
        >
          {PERIOD_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </Select>

        <Input
          w="160px" bg="gray.700" color="white" size="sm"
          placeholder={t('labels.referenceNumber')}
          value={referenceNumber}
          onChange={(e) => setReferenceNumber(e.target.value)}
        />

        <Button size="sm" colorScheme="orange" variant="outline"
          onClick={handleGenerateNarrative} isLoading={narrativeLoading}>
          {t('buttons.generateSummary')}
        </Button>
      </Flex>

      {/* AI Narrative */}
      <Collapse in={showNarrative} animateOpacity>
        <Box bg="gray.700" p={3} mb={4} borderRadius="md" position="relative">
          <IconButton
            aria-label="Close narrative"
            icon={<ChevronUpIcon />}
            size="xs" position="absolute" top={2} right={2}
            onClick={() => setShowNarrative(false)}
          />
          <Text fontSize="sm" whiteSpace="pre-wrap">{narrativeText}</Text>
        </Box>
      </Collapse>

      {/* AI Query */}
      <HStack mb={4} spacing={2}>
        <Input
          bg="gray.700" color="white" size="sm" flex="1"
          placeholder="Stel een vraag over je budget..."
          value={queryQuestion}
          onChange={(e) => setQueryQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
        />
        <Button size="sm" colorScheme="orange" onClick={handleQuery} isLoading={queryLoading}>
          {t('buttons.ask')}
        </Button>
      </HStack>

      {/* Navigation breadcrumb */}
      {level !== 'parent' && (
        <HStack spacing={2} mb={3} fontSize="sm">
          <Button variant="link" color="orange.300" size="sm" onClick={navigateToParent}>
            Parent
          </Button>
          <Text color="gray.400">›</Text>
          {level === 'subparent' && parentCode && (
            <Text color="white" fontWeight="semibold">{parentCode}</Text>
          )}
          {level === 'account' && (
            <>
              <Button variant="link" color="orange.300" size="sm" onClick={navigateToSubparent}>
                {parentCode}
              </Button>
              <Text color="gray.400">›</Text>
              <Text color="white" fontWeight="semibold">{subparentCode}</Text>
            </>
          )}
        </HStack>
      )}

      {/* Data table */}
      {loading ? (
        <Flex justify="center" py={8}><Spinner color="orange.300" /></Flex>
      ) : (
        <Box overflowX="auto">
          <Table size="sm" variant="simple" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <FilterableHeader label={t('columns.code')} filterValue={filters.code}
                  onFilterChange={(v) => setFilter('code', v)} sortable
                  sortDirection={sortField === 'code' ? sortDirection : null}
                  onSort={() => handleSort('code')} />
                <FilterableHeader label={t('columns.name')} filterValue={filters.name}
                  onFilterChange={(v) => setFilter('name', v)} sortable
                  sortDirection={sortField === 'name' ? sortDirection : null}
                  onSort={() => handleSort('name')} />
                <FilterableHeader label={t('columns.budget')} filterValue={filters.budget}
                  onFilterChange={(v) => setFilter('budget', v)} sortable
                  sortDirection={sortField === 'budget' ? sortDirection : null}
                  onSort={() => handleSort('budget')} isNumeric />
                <FilterableHeader label={t('columns.actual')} filterValue={filters.actual}
                  onFilterChange={(v) => setFilter('actual', v)} sortable
                  sortDirection={sortField === 'actual' ? sortDirection : null}
                  onSort={() => handleSort('actual')} isNumeric />
                <FilterableHeader label={t('columns.variance')} filterValue={filters.variance}
                  onFilterChange={(v) => setFilter('variance', v)} sortable
                  sortDirection={sortField === 'variance' ? sortDirection : null}
                  onSort={() => handleSort('variance')} isNumeric />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.length === 0 ? (
                <Tr><Td colSpan={5} textAlign="center" color="gray.400">{t('messages.noData')}</Td></Tr>
              ) : (
                processedData.map((row) => (
                  <Tr key={row.code}
                    _hover={level !== 'account' ? { bg: 'gray.700', cursor: 'pointer' } : undefined}
                    onClick={() => handleRowClick(row)}>
                    <Td>{row.code}</Td>
                    <Td>{row.name}</Td>
                    <Td isNumeric>{formatAmount(row.budget)}</Td>
                    <Td isNumeric>{formatAmount(row.actual)}</Td>
                    <Td isNumeric color={row.variance > 0 ? 'red.300' : row.variance < 0 ? 'green.300' : 'white'}>
                      {formatAmount(row.variance)}
                    </Td>
                  </Tr>
                ))
              )}
            </Tbody>
          </Table>
        </Box>
      )}
    </Box>
  );
};

export default BudgetDashboardTab;
