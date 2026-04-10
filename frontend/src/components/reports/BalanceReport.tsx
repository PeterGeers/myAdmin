import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Alert,
  AlertIcon,
  Button,
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
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { useTenant } from '../../context/TenantContext';
import { YearFilter } from '../filters/YearFilter';
import { getClosedYears } from '../../services/yearEndClosureService';
import { formatAmount, invalidateAndFetch } from '../../utils/financialReportUtils';
import type { BalanceReportProps, BalanceYearRecord } from '../../types/financialReports';

const BalanceReport: React.FC<BalanceReportProps> = ({
  selectedYears,
  displayFormat,
  availableYears,
  onYearsChange,
  onDisplayFormatChange,
}) => {
  const { t } = useTypedTranslation('reports');
  const { currentTenant } = useTenant();
  const toast = useToast();

  const [balanceData, setBalanceData] = useState<BalanceYearRecord[]>([]);
  const [closedYears, setClosedYears] = useState<number[]>([]);
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sortedYears = useMemo(
    () => [...selectedYears].sort((a, b) => parseInt(a) - parseInt(b)),
    [selectedYears]
  );

  // --- Data fetching ---

  const fetchBalanceData = useCallback(async () => {
    if (!currentTenant || selectedYears.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        years: selectedYears.join(','),
        administration: currentTenant,
        per_year: 'true',
      });
      const resp = await authenticatedGet(buildEndpoint('/api/reports/actuals-balance', params));
      const result = await resp.json();
      if (result.success) {
        setBalanceData(result.data ?? []);
        setClosedYears(result.closedYears ?? []);
      } else {
        setError(result.error ?? t('actuals.errorLoadingData'));
      }
    } catch {
      setError(t('actuals.errorLoadingData'));
    } finally {
      setLoading(false);
    }
  }, [currentTenant, selectedYears, t]);

  const fetchClosedYears = useCallback(async () => {
    try {
      const years = await getClosedYears();
      setClosedYears(years.map((y) => y.year));
    } catch {
      // Non-critical — fall back to API-provided closedYears
    }
  }, []);

  // Fetch on mount / tenant change
  useEffect(() => {
    if (!currentTenant) return;
    setBalanceData([]);
    setExpandedParents(new Set());
    fetchBalanceData();
    fetchClosedYears();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTenant]);

  // Re-fetch when years change
  useEffect(() => {
    if (currentTenant && selectedYears.length > 0) {
      fetchBalanceData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYears]);

  const handleUpdateData = async () => {
    setLoading(true);
    await invalidateAndFetch(fetchBalanceData);
    toast({ title: t('actuals.dataRefreshed') ?? 'Data refreshed', status: 'success', duration: 2000 });
    setLoading(false);
  };

  // --- Grouped data structure ---

  type GroupedBalance = Record<
    string,
    { ledgers: Record<string, Record<number, number>>; totals: Record<number, number> }
  >;

  const grouped: GroupedBalance = useMemo(() => {
    const g: GroupedBalance = {};
    for (const row of balanceData) {
      if (!g[row.Parent]) g[row.Parent] = { ledgers: {}, totals: {} };
      const ledgerKey = `${row.Reknum} ${row.AccountName}`.trim();
      if (!g[row.Parent].ledgers[ledgerKey]) g[row.Parent].ledgers[ledgerKey] = {};
      g[row.Parent].ledgers[ledgerKey][row.jaar] =
        (g[row.Parent].ledgers[ledgerKey][row.jaar] ?? 0) + (Number(row.Amount) || 0);
      g[row.Parent].totals[row.jaar] =
        (g[row.Parent].totals[row.jaar] ?? 0) + (Number(row.Amount) || 0);
    }
    return g;
  }, [balanceData]);

  const grandTotals: Record<number, number> = useMemo(() => {
    const totals: Record<number, number> = {};
    for (const group of Object.values(grouped)) {
      for (const [yr, amt] of Object.entries(group.totals)) {
        totals[Number(yr)] = (totals[Number(yr)] ?? 0) + amt;
      }
    }
    return totals;
  }, [grouped]);

  // --- Pie chart data ---

  const pieData = useMemo(() => {
    const hasExpanded = Array.from(expandedParents).length > 0;
    if (hasExpanded) {
      const items: { name: string; value: number }[] = [];
      for (const row of balanceData) {
        if (!expandedParents.has(row.Parent)) continue;
        const name = `${row.Reknum} ${row.AccountName}`.trim();
        const existing = items.find((i) => i.name === name);
        const val = Math.abs(Number(row.Amount) || 0);
        if (existing) existing.value += val;
        else items.push({ name, value: val });
      }
      return items.filter((i) => i.value > 0);
    }
    return Object.entries(grouped)
      .map(([parent, g]) => {
        const total = Object.values(g.totals).reduce((s, v) => s + v, 0);
        return { name: parent, value: Math.abs(total) };
      })
      .filter((i) => i.value > 0);
  }, [balanceData, grouped, expandedParents]);

  const toggleParent = (parent: string) => {
    setExpandedParents((prev) => {
      const next = new Set(prev);
      if (next.has(parent)) next.delete(parent);
      else next.add(parent);
      return next;
    });
  };

  // --- Render ---

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
              <Button colorScheme="orange" onClick={handleUpdateData} isLoading={loading} size="sm">
                {t('actuals.refresh') ?? 'Refresh'}
              </Button>
            </GridItem>
          </Grid>
        </CardBody>
      </Card>

      {/* Table + Pie Chart */}
      <Grid templateColumns={{ base: '1fr', xl: '1fr 400px' }} gap={4}>
        <GridItem minW={0}>
          <Card bg="gray.700">
            <CardHeader pb={2}>
              <Heading size="md" color="white">{t('actuals.balanceVwN')}</Heading>
            </CardHeader>
            <CardBody pt={0}>
              <TableContainer>
                <Table size="sm" variant="simple" style={{ borderCollapse: 'collapse' }}>
                  <Thead>
                    <Tr>
                      <Th color="white" width="180px" border="none">{t('actuals.account')}</Th>
                      {sortedYears.map((yr) => (
                        <Th key={yr} color="white" textAlign="right" border="none">
                          {yr} {closedYears.includes(Number(yr)) ? '🔒' : '🔓'}
                        </Th>
                      ))}
                    </Tr>
                  </Thead>
                  <Tbody>
                    {Object.entries(grouped).map(([parent, group]) => {
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
                            {sortedYears.map((yr) => (
                              <Td key={yr} color="white" fontSize="sm" textAlign="right" fontWeight="bold" border="none" py={1}>
                                {formatAmount(group.totals[Number(yr)] ?? 0, displayFormat)}
                              </Td>
                            ))}
                          </Tr>
                          {isExpanded &&
                            Object.entries(group.ledgers).map(([ledger, amounts]) => (
                              <Tr key={`${parent}-${ledger}`}>
                                <Td color="white" fontSize="sm" pl="32px" border="none" py={1}>{ledger}</Td>
                                {sortedYears.map((yr) => (
                                  <Td key={yr} color="white" fontSize="sm" textAlign="right" border="none" py={1}>
                                    {formatAmount(amounts[Number(yr)] ?? 0, displayFormat)}
                                  </Td>
                                ))}
                              </Tr>
                            ))}
                        </React.Fragment>
                      );
                    })}
                    {/* Grand total */}
                    <Tr bg="orange.600">
                      <Td color="white" fontSize="sm" fontWeight="bold" border="none" py={1}>
                        {t('actuals.total')}
                      </Td>
                      {sortedYears.map((yr) => (
                        <Td key={yr} color="white" fontSize="sm" textAlign="right" fontWeight="bold" border="none" py={1}>
                          {formatAmount(grandTotals[Number(yr)] ?? 0, displayFormat)}
                        </Td>
                      ))}
                    </Tr>
                  </Tbody>
                </Table>
              </TableContainer>
            </CardBody>
          </Card>
        </GridItem>

        {/* Pie chart */}
        <GridItem>
          <Card bg="gray.700">
            <CardHeader pb={2}>
              <Heading size="md" color="white">{t('actuals.balanceDistribution')}</Heading>
            </CardHeader>
            <CardBody pt={0}>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                    label={(entry) => entry.name}
                  >
                    {pieData.map((_entry, index) => (
                      <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => formatAmount(Number(value), displayFormat)} />
                </PieChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>
    </VStack>
  );
};

export default BalanceReport;
