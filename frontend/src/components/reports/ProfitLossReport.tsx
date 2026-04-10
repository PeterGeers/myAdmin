import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Alert,
  AlertIcon,
  Button,
  ButtonGroup,
  Card,
  CardBody,
  CardHeader,
  Grid,
  GridItem,
  HStack,
  Heading,
  Select,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
  useToast,
} from '@chakra-ui/react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { useTenant } from '../../context/TenantContext';
import { YearFilter } from '../filters/YearFilter';
import {
  formatAmount,
  generateColumnKeys,
  invalidateAndFetch,
  splitChartData,
} from '../../utils/financialReportUtils';
import type {
  ProfitLossReportProps,
  PLRecord,
  DrillDownLevel,
  ViewMode,
} from '../../types/financialReports';

// --- Helpers ---

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function periodKey(row: PLRecord, level: DrillDownLevel): string {
  if (level === 'quarter') return `${row.jaar}-Q${row.kwartaal ?? 1}`;
  if (level === 'month') return `${row.jaar}-${MONTH_NAMES[(row.maand ?? 1) - 1]}`;
  return String(row.jaar);
}

// --- Component ---

const ProfitLossReport: React.FC<ProfitLossReportProps> = ({
  selectedYears,
  displayFormat,
  availableYears,
  onYearsChange,
  onDisplayFormatChange,
}) => {
  const { t } = useTypedTranslation('reports');
  const { currentTenant } = useTenant();
  const toast = useToast();

  const [plData, setPlData] = useState<PLRecord[]>([]);
  const [refData, setRefData] = useState<PLRecord[]>([]);
  const [drillDownLevel, setDrillDownLevel] = useState<DrillDownLevel>('year');
  const [viewMode, setViewMode] = useState<ViewMode>('standard');
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());
  const [expandedLedgers, setExpandedLedgers] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const columnKeys = useMemo(
    () => generateColumnKeys(selectedYears, drillDownLevel),
    [selectedYears, drillDownLevel]
  );
  const sortedYears = useMemo(
    () => [...selectedYears].sort((a, b) => parseInt(a) - parseInt(b)),
    [selectedYears]
  );

  // --- Fetch ---

  const fetchPLData = useCallback(async () => {
    if (!currentTenant || selectedYears.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        years: selectedYears.join(','),
        administration: currentTenant,
        groupBy: drillDownLevel,
      });
      const resp = await authenticatedGet(buildEndpoint('/api/reports/actuals-profitloss', params));
      const result = await resp.json();
      if (result.success) {
        setPlData(result.data ?? []);
      } else {
        setError(result.error ?? t('actuals.errorLoadingData'));
      }
    } catch {
      setError(t('actuals.errorLoadingData'));
    } finally {
      setLoading(false);
    }
  }, [currentTenant, selectedYears, drillDownLevel, t]);

  const fetchRefData = useCallback(
    async (reknum: string) => {
      if (!currentTenant) return;
      try {
        const params = new URLSearchParams({
          years: selectedYears.join(','),
          administration: currentTenant,
          groupBy: drillDownLevel,
          includeRef: 'true',
        });
        const resp = await authenticatedGet(buildEndpoint('/api/reports/actuals-profitloss', params));
        const result = await resp.json();
        if (result.success) {
          setRefData(result.data?.filter((r: PLRecord) => r.Reknum === reknum) ?? []);
        }
      } catch {
        // Non-critical
      }
    },
    [currentTenant, selectedYears, drillDownLevel]
  );

  useEffect(() => {
    if (!currentTenant) return;
    setPlData([]);
    setExpandedParents(new Set());
    setExpandedLedgers(new Set());
    fetchPLData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTenant]);

  useEffect(() => {
    if (currentTenant && selectedYears.length > 0) fetchPLData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYears, drillDownLevel]);

  const handleUpdateData = async () => {
    setLoading(true);
    await invalidateAndFetch(fetchPLData);
    toast({ title: t('actuals.dataRefreshed') ?? 'Data refreshed', status: 'success', duration: 2000 });
    setLoading(false);
  };

  // --- Grouped data ---

  type GroupedPL = Record<
    string,
    { ledgers: Record<string, Record<string, number>>; totals: Record<string, number> }
  >;

  const grouped: GroupedPL = useMemo(() => {
    const g: GroupedPL = {};
    for (const row of plData) {
      if (!g[row.Parent]) g[row.Parent] = { ledgers: {}, totals: {} };
      const lk = `${row.Reknum} ${row.AccountName}`.trim();
      if (!g[row.Parent].ledgers[lk]) g[row.Parent].ledgers[lk] = {};
      const pk = periodKey(row, drillDownLevel);
      g[row.Parent].ledgers[lk][pk] = (g[row.Parent].ledgers[lk][pk] ?? 0) + (Number(row.Amount) || 0);
      g[row.Parent].totals[pk] = (g[row.Parent].totals[pk] ?? 0) + (Number(row.Amount) || 0);
    }
    return g;
  }, [plData, drillDownLevel]);

  const grandTotals: Record<string, number> = useMemo(() => {
    const t: Record<string, number> = {};
    for (const g of Object.values(grouped)) {
      for (const [k, v] of Object.entries(g.totals)) t[k] = (t[k] ?? 0) + v;
    }
    return t;
  }, [grouped]);

  // --- Chart data (split profit / loss) ---

  const { profit: profitChartData, loss: lossChartData } = useMemo(() => {
    const { profit, loss } = splitChartData(plData, '8', '4');
    const build = (records: PLRecord[]) => {
      const map: Record<string, Record<string, number>> = {};
      for (const r of records) {
        const label = expandedParents.has(r.Parent)
          ? `${r.Reknum} ${r.AccountName}`.trim()
          : r.Parent;
        if (!map[label]) {
          map[label] = { name: label } as any;
          sortedYears.forEach((y) => ((map[label] as any)[y] = 0));
        }
        (map[label] as any)[r.jaar] = ((map[label] as any)[r.jaar] ?? 0) + (Number(r.Amount) || 0);
      }
      return Object.values(map).filter((item: any) =>
        sortedYears.some((y) => Math.abs(item[y] ?? 0) > 0)
      );
    };
    return { profit: build(profit), loss: build(loss) };
  }, [plData, expandedParents, sortedYears]);

  // --- Toggles ---

  const toggleParent = (parent: string) =>
    setExpandedParents((prev) => {
      const n = new Set(prev);
      n.has(parent) ? n.delete(parent) : n.add(parent);
      return n;
    });

  const toggleLedger = (key: string, reknum: string) => {
    setExpandedLedgers((prev) => {
      const n = new Set(prev);
      if (n.has(key)) {
        n.delete(key);
      } else {
        n.add(key);
        fetchRefData(reknum);
      }
      return n;
    });
  };

  // --- Pivot view data: rows = time periods, columns = accounts ---

  const pivotData = useMemo(() => {
    if (viewMode !== 'pivot') return { accountCols: [] as { key: string; label: string; isParent: boolean }[], rows: [] as { period: string; isYear: boolean; values: Record<string, number> }[] };

    // Build account columns: Parents always shown, ledgers only when parent is expanded
    const parentNames = Object.keys(grouped).sort();
    const accountCols: { key: string; label: string; isParent: boolean }[] = [];
    for (const p of parentNames) {
      accountCols.push({ key: p, label: p, isParent: true });
      if (expandedParents.has(p)) {
        for (const l of Object.keys(grouped[p].ledgers).sort()) {
          accountCols.push({ key: `${p}::${l}`, label: l, isParent: false });
        }
      }
    }

    // Build rows: one per year, with sub-period rows when drill-down is quarter/month
    const rows: { period: string; isYear: boolean; values: Record<string, number> }[] = [];
    for (const yr of sortedYears) {
      const yearValues: Record<string, number> = {};
      for (const [parent, g] of Object.entries(grouped)) {
        let parentTotal = 0;
        for (const [pk, amt] of Object.entries(g.totals)) {
          if (pk.startsWith(yr)) parentTotal += amt;
        }
        yearValues[parent] = parentTotal;
        for (const [ledger, amounts] of Object.entries(g.ledgers)) {
          let ledgerTotal = 0;
          for (const [pk, amt] of Object.entries(amounts)) {
            if (pk.startsWith(yr)) ledgerTotal += amt;
          }
          yearValues[`${parent}::${ledger}`] = ledgerTotal;
        }
      }
      rows.push({ period: yr, isYear: true, values: yearValues });

      // Sub-period rows (only if drill-down is quarter or month)
      if (drillDownLevel !== 'year') {
        const subKeys = columnKeys.filter((k) => k.startsWith(yr));
        for (const sk of subKeys) {
          const subValues: Record<string, number> = {};
          for (const [parent, g] of Object.entries(grouped)) {
            subValues[parent] = g.totals[sk] ?? 0;
            for (const [ledger, amounts] of Object.entries(g.ledgers)) {
              subValues[`${parent}::${ledger}`] = amounts[sk] ?? 0;
            }
          }
          rows.push({ period: sk, isYear: false, values: subValues });
        }
      }
    }
    return { accountCols, rows };
  }, [grouped, viewMode, expandedParents, sortedYears, columnKeys, drillDownLevel]);

  // --- Render ---

  const renderBarChart = (data: Record<string, number>[], title: string) => (
    <Card bg="gray.700" mb={4}>
      <CardHeader pb={2}>
        <Heading size="sm" color="white">{title}</Heading>
      </CardHeader>
      <CardBody pt={0}>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data} margin={{ top: 0, right: 15, left: 15, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} fontSize={10} tick={{ fill: 'white' }} />
            <YAxis tick={{ fill: 'white' }} />
            <Tooltip formatter={(value) => formatAmount(Number(value), displayFormat)} />
            <Legend wrapperStyle={{ color: 'white', paddingTop: '5px' }} />
            {sortedYears.map((year, i) => (
              <Bar key={year} dataKey={year} fill={`hsl(${i * 60}, 70%, 60%)`} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </CardBody>
    </Card>
  );

  return (
    <VStack spacing={4} align="stretch">
      {error && (
        <Alert status="error"><AlertIcon />{error}</Alert>
      )}
      {!currentTenant && (
        <Alert status="warning"><AlertIcon />{t('actuals.noTenantSelected')}</Alert>
      )}

      {/* Filters */}
      <Card bg="gray.700">
        <CardBody>
          <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
            <GridItem colSpan={{ base: 1, md: 2 }}>
              <YearFilter
                values={selectedYears}
                onChange={onYearsChange}
                availableOptions={availableYears}
                multiSelect
                size="sm"
                isLoading={loading}
                labelColor="white"
                bg="gray.600"
                color="white"
              />
            </GridItem>
            <GridItem>
              <Text color="white" mb={2}>{t('actuals.displayFormat')}</Text>
              <Select
                value={displayFormat}
                onChange={(e) => onDisplayFormatChange(e.target.value as any)}
                bg="gray.600"
                color="white"
                size="sm"
              >
                <option value="2dec">{t('actuals.twoDecimals')}</option>
                <option value="0dec">{t('actuals.wholeNumbers')}</option>
                <option value="k">{t('actuals.thousands')}</option>
                <option value="m">{t('actuals.millions')}</option>
              </Select>
            </GridItem>
            <GridItem>
              <Text color="white" mb={2}>{t('actuals.drillDownLevel')}</Text>
              <HStack>
                {(['year', 'quarter', 'month'] as DrillDownLevel[]).map((lvl) => (
                  <Button
                    key={lvl}
                    size="sm"
                    colorScheme={drillDownLevel === lvl ? 'orange' : 'gray'}
                    onClick={() => { setDrillDownLevel(lvl); setExpandedParents(new Set()); setExpandedLedgers(new Set()); }}
                    isLoading={loading && drillDownLevel !== lvl}
                  >
                    {lvl === 'year' ? '📅' : lvl === 'quarter' ? '📊' : '📈'} {t(`actuals.${lvl}`)}
                  </Button>
                ))}
              </HStack>
            </GridItem>
            <GridItem>
              <HStack spacing={3}>
                <Button colorScheme="orange" onClick={handleUpdateData} isLoading={loading} size="md">
                  {t('actuals.refresh') ?? 'Refresh'}
                </Button>
                <ButtonGroup size="md" isAttached>
                  <Button
                    colorScheme={viewMode === 'standard' ? 'orange' : 'gray'}
                    variant={viewMode === 'standard' ? 'solid' : 'outline'}
                    color="white"
                    onClick={() => setViewMode('standard')}
                  >
                    {t('actuals.standardView') ?? 'Standard'}
                  </Button>
                  <Button
                    colorScheme={viewMode === 'pivot' ? 'orange' : 'gray'}
                    variant={viewMode === 'pivot' ? 'solid' : 'outline'}
                    color="white"
                    onClick={() => setViewMode('pivot')}
                  >
                    {t('actuals.pivotView') ?? 'Pivot'}
                  </Button>
                </ButtonGroup>
              </HStack>
            </GridItem>
          </Grid>
        </CardBody>
      </Card>

      {/* Table + Charts */}
      <Grid templateColumns={{ base: '1fr', xl: '1fr 1fr' }} gap={4}>
        <GridItem minW={0}>
          <Card bg="gray.700">
            <CardHeader pb={2}>
              <Heading size="md" color="white">{t('actuals.profitLossVwY')}</Heading>
            </CardHeader>
            <CardBody pt={0}>
              <TableContainer>
                <Table size="sm" variant="simple" style={{ borderCollapse: 'collapse' }}>
                  <Thead>
                    {viewMode === 'standard' ? (
                      <Tr>
                        <Th color="white" width="180px" border="none">{t('actuals.account')}</Th>
                        {columnKeys.map((k) => (
                          <Th key={k} color="white" textAlign="right" border="none">{k}</Th>
                        ))}
                      </Tr>
                    ) : (
                      <Tr>
                        <Th color="white" width="120px" border="none">{t('actuals.period') ?? 'Period'}</Th>
                        {pivotData.accountCols.map((col) => (
                          <Th
                            key={col.key}
                            color="white"
                            textAlign="right"
                            border="none"
                            fontSize="xs"
                            maxW="120px"
                            isTruncated
                            cursor={col.isParent ? 'pointer' : undefined}
                            onClick={col.isParent ? () => toggleParent(col.key) : undefined}
                            fontWeight={col.isParent ? 'bold' : 'normal'}
                            bg={col.isParent ? 'gray.600' : undefined}
                          >
                            {col.isParent ? `${expandedParents.has(col.key) ? '−' : '+'} ` : '  '}{col.label}
                          </Th>
                        ))}
                      </Tr>
                    )}
                  </Thead>
                  <Tbody>
                    {viewMode === 'standard'
                      ? /* --- Standard hierarchical view --- */
                        Object.entries(grouped).map(([parent, group]) => {
                          const isExpanded = expandedParents.has(parent);
                          return (
                            <React.Fragment key={parent}>
                              <Tr bg="gray.600">
                                <Td color="white" fontSize="sm" fontWeight="bold" border="none" py={1}>
                                  <HStack>
                                    <Button size="xs" variant="ghost" color="white" onClick={() => toggleParent(parent)}>
                                      {isExpanded ? '−' : '+'}
                                    </Button>
                                    <Text>{parent}</Text>
                                  </HStack>
                                </Td>
                                {columnKeys.map((k) => (
                                  <Td key={k} color="white" fontSize="sm" textAlign="right" fontWeight="bold" border="none" py={1}>
                                    {formatAmount(group.totals[k] ?? 0, displayFormat)}
                                  </Td>
                                ))}
                              </Tr>
                              {isExpanded &&
                                Object.entries(group.ledgers).map(([ledger, amounts]) => {
                                  const ledgerKey = `${parent}::${ledger}`;
                                  const reknum = ledger.split(' ')[0];
                                  const isLedgerExpanded = expandedLedgers.has(ledgerKey);
                                  return (
                                    <React.Fragment key={ledgerKey}>
                                      <Tr>
                                        <Td color="white" fontSize="sm" pl="32px" border="none" py={1}>
                                          <HStack>
                                            <Button size="xs" variant="ghost" color="white" onClick={() => toggleLedger(ledgerKey, reknum)}>
                                              {isLedgerExpanded ? '−' : '+'}
                                            </Button>
                                            <Text>{ledger}</Text>
                                          </HStack>
                                        </Td>
                                        {columnKeys.map((k) => (
                                          <Td key={k} color="white" fontSize="sm" textAlign="right" border="none" py={1}>
                                            {formatAmount(amounts[k] ?? 0, displayFormat)}
                                          </Td>
                                        ))}
                                      </Tr>
                                      {isLedgerExpanded &&
                                        (() => {
                                          // Group ref data by ReferenceNumber so each ref shows amounts across all year columns
                                          const refsForLedger = refData.filter((r) => r.Reknum === reknum);
                                          const refGrouped: Record<string, Record<string, number>> = {};
                                          for (const r of refsForLedger) {
                                            const ref = (r.ReferenceNumber ?? '—').trim();
                                            if (!refGrouped[ref]) refGrouped[ref] = {};
                                            const pk = periodKey(r, drillDownLevel);
                                            refGrouped[ref][pk] = (refGrouped[ref][pk] ?? 0) + (Number(r.Amount) || 0);
                                          }
                                          return Object.entries(refGrouped)
                                            .sort(([a], [b]) => a.localeCompare(b))
                                            .map(([ref, amounts], i) => (
                                            <Tr key={`ref-${i}`} bg={i % 2 === 0 ? 'gray.600' : 'gray.700'}>
                                              <Td color="gray.300" fontSize="xs" pl="56px" border="none" py={0}>
                                                {ref}
                                              </Td>
                                              {columnKeys.map((k) => (
                                                <Td key={k} color="gray.300" fontSize="xs" textAlign="right" border="none" py={0}>
                                                  {amounts[k] ? formatAmount(amounts[k], displayFormat) : ''}
                                                </Td>
                                              ))}
                                            </Tr>
                                          ));
                                        })()}
                                    </React.Fragment>
                                  );
                                })}
                            </React.Fragment>
                          );
                        })
                      : /* --- Pivot view: rows = periods, columns = accounts --- */
                        pivotData.rows.map((row, i) => (
                          <Tr key={i} bg={row.isYear ? 'gray.600' : i % 2 === 0 ? 'gray.700' : undefined}>
                            <Td
                              color="white"
                              fontSize="sm"
                              fontWeight={row.isYear ? 'bold' : 'normal'}
                              pl={row.isYear ? undefined : '24px'}
                              border="none"
                              py={1}
                            >
                              {row.period}
                            </Td>
                            {pivotData.accountCols.map((col) => (
                              <Td key={col.key} color="white" fontSize="sm" textAlign="right" fontWeight={row.isYear && col.isParent ? 'bold' : 'normal'} border="none" py={1}>
                                {formatAmount(row.values[col.key] ?? 0, displayFormat)}
                              </Td>
                            ))}
                          </Tr>
                        ))}
                    {/* Grand total */}
                    <Tr bg="orange.600">
                      <Td color="white" fontSize="sm" fontWeight="bold" border="none" py={1}>
                        {t('actuals.total')}
                      </Td>
                      {viewMode === 'standard'
                        ? columnKeys.map((k) => (
                            <Td key={k} color="white" fontSize="sm" textAlign="right" fontWeight="bold" border="none" py={1}>
                              {formatAmount(grandTotals[k] ?? 0, displayFormat)}
                            </Td>
                          ))
                        : pivotData.accountCols.map((col) => {
                            const total = pivotData.rows
                              .filter((r) => r.isYear)
                              .reduce((s, r) => s + (r.values[col.key] ?? 0), 0);
                            return (
                              <Td key={col.key} color="white" fontSize="sm" textAlign="right" fontWeight="bold" border="none" py={1}>
                                {formatAmount(total, displayFormat)}
                              </Td>
                            );
                          })}
                    </Tr>
                  </Tbody>
                </Table>
              </TableContainer>
            </CardBody>
          </Card>
        </GridItem>

        {/* Split charts */}
        <GridItem>
          {renderBarChart(profitChartData as any, t('actuals.revenueChart') ?? 'Revenue (8000)')}
          {renderBarChart(lossChartData as any, t('actuals.costChart') ?? 'Costs (4000)')}
        </GridItem>
      </Grid>
    </VStack>
  );
};

export default ProfitLossReport;
