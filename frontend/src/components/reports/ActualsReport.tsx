import React, { useEffect, useState, useCallback } from 'react';
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
  VStack
} from '@chakra-ui/react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import { authenticatedGet, authenticatedPost, buildEndpoint } from '../../services/apiService';
import { useTenant } from '../../context/TenantContext';
import UnifiedAdminYearFilter from '../UnifiedAdminYearFilter';
import { createActualsFilterAdapter } from '../UnifiedAdminYearFilterAdapters';

interface BalanceRecord {
  Parent: string;
  ledger: string;
  Amount: number;
  jaar: number;
  kwartaal?: number;
  maand?: number;
  [key: string]: any;
}

interface ActualsFilters {
  years: string[];
  administration: string;
  displayFormat: string;
}

const ActualsReport: React.FC = () => {
  const { currentTenant } = useTenant();
  const [balanceData, setBalanceData] = useState<BalanceRecord[]>([]);
  const [profitLossData, setProfitLossData] = useState<BalanceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [tenantSwitching, setTenantSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());
  const [drillDownLevel, setDrillDownLevel] = useState<'year' | 'quarter' | 'month'>('year');
  const [availableYears, setAvailableYears] = useState<string[]>([]);
  
  const [actualsFilters, setActualsFilters] = useState<ActualsFilters>({
    years: [new Date().getFullYear().toString()],
    administration: currentTenant || 'all',
    displayFormat: '2dec'
  });

  // Format amount based on display format
  const formatAmount = (amount: number, format: string): string => {
    const num = Number(amount) || 0;
    
    switch (format) {
      case '2dec':
        return `€${num.toLocaleString('nl-NL', {minimumFractionDigits: 2})}`;
      case '0dec':
        return `€${Math.round(num).toLocaleString('nl-NL')}`;
      case 'k':
        return `€${(num / 1000).toFixed(1)}K`;
      case 'm':
        return `€${(num / 1000000).toFixed(1)}M`;
      default:
        return `€${num.toLocaleString('nl-NL', {minimumFractionDigits: 2})}`;
    }
  };

  // Render hierarchical data with Parent totals and indented ledgers
  const renderHierarchicalData = (data: BalanceRecord[], years: string[], displayFormat: string) => {
    const sortedYears = [...years].sort((a, b) => parseInt(a) - parseInt(b));
    
    // Generate column keys based on drill-down level
    const getColumnKeys = () => {
      if (drillDownLevel === 'year') {
        return sortedYears;
      } else if (drillDownLevel === 'quarter') {
        return sortedYears.flatMap(year => ['Q1', 'Q2', 'Q3', 'Q4'].map(q => `${year}-${q}`));
      } else {
        return sortedYears.flatMap(year => 
          ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            .map(m => `${year}-${m}`)
        );
      }
    };
    
    const columnKeys = getColumnKeys();
    
    const grouped = data.reduce((acc, row) => {
      if (!acc[row.Parent]) {
        acc[row.Parent] = { parent: row.Parent, ledgers: {}, totals: {} };
      }
      
      // Group ledgers by name and accumulate amounts by period
      // Use ledger field, or fallback to Reknum + AccountName if ledger is missing
      const ledgerKey = row.ledger || `${row.Reknum || ''} ${row.AccountName || ''}`.trim() || 'Unknown';
      
      if (!acc[row.Parent].ledgers[ledgerKey]) {
        acc[row.Parent].ledgers[ledgerKey] = {};
        columnKeys.forEach(key => {
          acc[row.Parent].ledgers[ledgerKey][key] = 0;
        });
      }
      
      // Determine the key based on drill-down level
      let periodKey = '';
      if (drillDownLevel === 'year') {
        periodKey = String(row.jaar);
      } else if (drillDownLevel === 'quarter') {
        const quarter = row.kwartaal || 1;
        periodKey = `${row.jaar}-Q${quarter}`;
      } else {
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const month = row.maand || 1;
        periodKey = `${row.jaar}-${monthNames[month - 1]}`;
      }
      
      if (columnKeys.includes(periodKey)) {
        acc[row.Parent].ledgers[ledgerKey][periodKey] = (acc[row.Parent].ledgers[ledgerKey][periodKey] || 0) + (Number(row.Amount) || 0);
      }
      
      // Calculate parent totals
      columnKeys.forEach(key => {
        if (!acc[row.Parent].totals[key]) acc[row.Parent].totals[key] = 0;
        if (key === periodKey) {
          acc[row.Parent].totals[key] += Number(row.Amount) || 0;
        }
      });
      
      return acc;
    }, {} as any);

    const rows: React.ReactElement[] = [];
    let totalIndex = 0;
    const grandTotals: { [key: string]: number } = {};

    // Initialize grand totals
    columnKeys.forEach(key => {
      grandTotals[key] = 0;
    });

    Object.values(grouped).forEach((group: any) => {
      // Add to grand totals
      columnKeys.forEach(key => {
        grandTotals[key] = (grandTotals[key] || 0) + (group.totals[key] || 0);
      });
      
      const isExpanded = expandedParents.has(`profitloss-${group.parent}`);
      
      // Parent row with totals and expand/collapse button
      rows.push(
        <Tr key={`parent-${totalIndex}`} bg="gray.600">
          <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
            <HStack>
              <Button
                size="xs"
                variant="ghost"
                color="white"
                onClick={() => {
                  const newExpanded = new Set(expandedParents);
                  const key = `profitloss-${group.parent}`;
                  if (isExpanded) {
                    newExpanded.delete(key);
                  } else {
                    newExpanded.add(key);
                  }
                  setExpandedParents(newExpanded);
                }}
              >
                {isExpanded ? '−' : '+'}
              </Button>
              <Text>{group.parent}</Text>
            </HStack>
          </Td>
          {columnKeys.map(key => (
            <Td key={key} color="white" fontSize="sm" width="60px" textAlign="right" fontWeight="bold" border="none" py={1}>
              {formatAmount(Math.round((group.totals[key] || 0) * 100) / 100, displayFormat)}
            </Td>
          ))}
        </Tr>
      );
      
      // Ledger rows consolidated by ledger name (only if expanded)
      if (isExpanded) {
        Object.entries(group.ledgers).forEach(([ledgerName, ledgerAmounts]: [string, any], ledgerIndex: number) => {
          rows.push(
            <Tr key={`ledger-${totalIndex}-${ledgerIndex}`}>
              <Td color="white" fontSize="sm" width="120px" paddingLeft="32px" border="none" py={1}>
                {ledgerName}
              </Td>
              {columnKeys.map(key => (
                <Td key={key} color="white" fontSize="sm" width="60px" textAlign="right" border="none" py={1}>
                  {formatAmount(Math.round((ledgerAmounts[key] || 0) * 100) / 100, displayFormat)}
                </Td>
              ))}
            </Tr>
          );
        });
      }
      
      totalIndex++;
    });

    // Add grand total row
    rows.push(
      <Tr key="grand-total" bg="orange.600">
        <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
          TOTAL
        </Td>
        {columnKeys.map(key => (
          <Td key={key} color="white" fontSize="sm" width="60px" textAlign="right" fontWeight="bold" border="none" py={1}>
            {formatAmount(Math.round((grandTotals[key] || 0) * 100) / 100, displayFormat)}
          </Td>
        ))}
      </Tr>
    );

    return rows;
  };


  // Render Balance data (aggregated across all years)
  const renderBalanceData = (data: BalanceRecord[], displayFormat: string) => {
    const grouped = data.reduce((acc, row) => {
      if (!acc[row.Parent]) {
        acc[row.Parent] = { parent: row.Parent, ledgers: [], total: 0 };
      }
      acc[row.Parent].ledgers.push(row);
      acc[row.Parent].total += Number(row.Amount) || 0;
      return acc;
    }, {} as any);

    const rows: React.ReactElement[] = [];
    let totalIndex = 0;
    let grandTotal = 0;

    Object.values(grouped).forEach((group: any) => {
      grandTotal += group.total;
      const isExpanded = expandedParents.has(`balance-${group.parent}`);
      
      // Parent row with total and expand/collapse button
      rows.push(
        <Tr key={`parent-${totalIndex}`} bg="gray.600">
          <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
            <HStack>
              <Button
                size="xs"
                variant="ghost"
                color="white"
                onClick={() => {
                  const newExpanded = new Set(expandedParents);
                  const key = `balance-${group.parent}`;
                  if (isExpanded) {
                    newExpanded.delete(key);
                  } else {
                    newExpanded.add(key);
                  }
                  setExpandedParents(newExpanded);
                }}
              >
                {isExpanded ? '−' : '+'}
              </Button>
              <Text>{group.parent}</Text>
            </HStack>
          </Td>
          <Td color="white" fontSize="sm" width="100px" textAlign="right" fontWeight="bold" border="none" py={1}>
            {formatAmount(group.total, displayFormat)}
          </Td>
        </Tr>
      );
      
      // Ledger rows indented under parent (only if expanded)
      if (isExpanded) {
        group.ledgers.forEach((ledger: any, ledgerIndex: number) => {
          rows.push(
            <Tr key={`ledger-${totalIndex}-${ledgerIndex}`}>
              <Td color="white" fontSize="sm" width="120px" paddingLeft="32px" border="none" py={1}>
                {ledger.ledger}
              </Td>
              <Td color="white" fontSize="sm" width="100px" textAlign="right" border="none" py={1}>
                {formatAmount(Number(ledger.Amount) || 0, displayFormat)}
              </Td>
            </Tr>
          );
        });
      }
      
      totalIndex++;
    });

    // Add grand total row
    rows.push(
      <Tr key="grand-total" bg="orange.600">
        <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
          TOTAL
        </Td>
        <Td color="white" fontSize="sm" width="100px" textAlign="right" fontWeight="bold" border="none" py={1}>
          {formatAmount(grandTotal, displayFormat)}
        </Td>
      </Tr>
    );

    return rows;
  };

  const fetchActualsData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Validate tenant before making API call
      if (!currentTenant) {
        console.warn('[SECURITY] Attempted to fetch actuals data without tenant selection');
        setError('No tenant selected. Please select a tenant to view actuals data.');
        return;
      }

      console.log('[TENANT SECURITY] Fetching actuals data for tenant:', currentTenant);

      const params = new URLSearchParams({
        years: actualsFilters.years.join(','),
        administration: currentTenant, // Use current tenant instead of filter
        groupBy: drillDownLevel
      });
      
      // Balance data (VW = N)
      const balanceResponse = await authenticatedGet(buildEndpoint('/api/reports/actuals-balance', params));
      const balanceResult = await balanceResponse.json();
      if (balanceResult.success) {
        console.log('[TENANT SECURITY] Balance data fetched successfully for tenant:', currentTenant);
        // Transform data to add ledger field (Reknum + AccountName)
        const transformedData = balanceResult.data.map((row: any) => ({
          ...row,
          ledger: `${row.Reknum || ''} ${row.AccountName || ''}`.trim()
        }));
        setBalanceData(transformedData);
      } else {
        console.error('[TENANT SECURITY] Failed to fetch balance data for tenant:', currentTenant, balanceResult.message);
        setError(`Failed to fetch balance data: ${balanceResult.message || 'Unknown error'}`);
      }

      // Profit/Loss data (VW = Y)
      const profitLossResponse = await authenticatedGet(buildEndpoint('/api/reports/actuals-profitloss', params));
      const profitLossResult = await profitLossResponse.json();
      if (profitLossResult.success) {
        console.log('[TENANT SECURITY] Profit/Loss data fetched successfully for tenant:', currentTenant);
        console.log('[DEBUG] Sample P&L row before transformation:', profitLossResult.data[0]);
        // Transform data to add ledger field (Reknum + AccountName)
        const transformedData = profitLossResult.data.map((row: any) => ({
          ...row,
          ledger: `${row.Reknum || ''} ${row.AccountName || ''}`.trim()
        }));
        console.log('[DEBUG] Sample P&L row after transformation:', transformedData[0]);
        setProfitLossData(transformedData);
      } else {
        console.error('[TENANT SECURITY] Failed to fetch profit/loss data for tenant:', currentTenant, profitLossResult.message);
        setError(`Failed to fetch profit/loss data: ${profitLossResult.message || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('[TENANT SECURITY] Error fetching actuals data for tenant:', currentTenant, err);
      setError(`Error loading actuals data. Please check your connection and try again.`);
    } finally {
      setLoading(false);
    }
  }, [currentTenant, actualsFilters.years, drillDownLevel]);

  const fetchAvailableYears = useCallback(async () => {
    try {
      // Validate tenant before making API call
      if (!currentTenant) {
        console.warn('[SECURITY] Attempted to fetch available years without tenant selection');
        return;
      }

      console.log('[TENANT SECURITY] Fetching available years for tenant:', currentTenant);

      const params = new URLSearchParams({
        administration: currentTenant
      });
      
      const response = await authenticatedGet(buildEndpoint('/api/reports/available-years', params));
      const data = await response.json();
      if (data.success) {
        console.log('[TENANT SECURITY] Available years fetched successfully for tenant:', currentTenant);
        setAvailableYears(data.years);
      } else {
        console.error('[TENANT SECURITY] Failed to fetch available years for tenant:', currentTenant, data.message);
        setError(`Failed to fetch available years: ${data.message || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('[TENANT SECURITY] Error fetching available years for tenant:', currentTenant, err);
      setError('Error loading available years. Please check your connection and try again.');
    }
  }, [currentTenant]);

  // Initial data fetch
  useEffect(() => {
    if (currentTenant) {
      // Warmup cache on component mount
      authenticatedPost('/api/cache/warmup', {})
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            console.log('[CACHE] Cache warmed up:', data.message);
          }
        })
        .catch(err => {
          console.warn('[CACHE] Cache warmup failed (non-critical):', err);
        });
      
      fetchAvailableYears();
    }
  }, [currentTenant, fetchAvailableYears]);

  // Refetch when drill-down level changes
  useEffect(() => {
    if (actualsFilters.years.length > 0) {
      fetchActualsData();
    }
  }, [drillDownLevel, actualsFilters.years.length, fetchActualsData]);

  // Refetch when filters change
  useEffect(() => {
    if (actualsFilters.years.length > 0) {
      fetchActualsData();
    }
  }, [actualsFilters.years, actualsFilters.years.length, actualsFilters.administration, fetchActualsData, fetchAvailableYears]);

  // Auto-refresh on tenant change
  useEffect(() => {
    if (currentTenant) {
      console.log('[TENANT CHANGE] Tenant changed to:', currentTenant);
      console.log('[TENANT CHANGE] Clearing previous tenant data for security');
      
      setTenantSwitching(true);
      setError(null); // Clear any previous errors
      
      // Update filters with current tenant
      setActualsFilters(prev => ({
        ...prev,
        administration: currentTenant
      }));
      
      // Clear previous tenant data to prevent data leakage
      setBalanceData([]);
      setProfitLossData([]);
      
      // Reset expanded state
      setExpandedParents(new Set());
      
      // Fetch new data for current tenant
      Promise.all([
        fetchAvailableYears(),
        actualsFilters.years.length > 0 ? fetchActualsData() : Promise.resolve()
      ]).catch((err) => {
        console.error('[TENANT CHANGE] Error during tenant switch:', err);
      }).finally(() => {
        setTenantSwitching(false);
        console.log('[TENANT CHANGE] Tenant switch completed for:', currentTenant);
      });
    }
  }, [currentTenant, actualsFilters.years.length, fetchActualsData, fetchAvailableYears]);


  return (
    <VStack spacing={4} align="stretch">
      {/* Error message */}
      {error && (
        <Alert status="error">
          <AlertIcon />
          {error}
        </Alert>
      )}

      {/* Tenant validation - show alert if no tenant selected */}
      {!currentTenant && (
        <Alert status="warning">
          <AlertIcon />
          No tenant selected. Please select a tenant first.
        </Alert>
      )}

      {/* Tenant switching indicator */}
      {tenantSwitching && (
        <Alert status="info" bg="blue.500" color="white" mb={4}>
          <AlertIcon color="white" />
          Switching tenant... Please wait while data is being loaded.
        </Alert>
      )}

      <Card bg="gray.700">
        <CardBody>
          <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
            {/* Unified Year Filter (Administration hidden - using tenant context) */}
            <GridItem colSpan={{ base: 1, md: 2 }}>
              <UnifiedAdminYearFilter
                {...createActualsFilterAdapter(
                  actualsFilters,
                  setActualsFilters,
                  availableYears
                )}
                showAdministration={false}
                size="sm"
                isLoading={loading || tenantSwitching}
              />
            </GridItem>
            <GridItem>
              <Text color="white" mb={2}>Display Format</Text>
              <Select
                value={actualsFilters.displayFormat}
                onChange={(e) => setActualsFilters(prev => ({...prev, displayFormat: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
              >
                <option value="2dec">€1,234.56 (2 decimals)</option>
                <option value="0dec">€1,235 (whole numbers)</option>
                <option value="k">€1.2K (thousands)</option>
                <option value="m">€1.2M (millions)</option>
              </Select>
            </GridItem>
            <GridItem>
              <Text color="white" mb={2}>Drill Down Level</Text>
              <HStack>
                <Button 
                  size="sm" 
                  colorScheme={drillDownLevel === 'year' ? 'orange' : 'gray'}
                  onClick={() => {
                    setDrillDownLevel('year');
                    setExpandedParents(new Set());
                  }}
                  isLoading={(loading && drillDownLevel !== 'year') || tenantSwitching}
                >
                  📅 Year
                </Button>
                <Button 
                  size="sm" 
                  colorScheme={drillDownLevel === 'quarter' ? 'orange' : 'gray'}
                  onClick={() => {
                    setDrillDownLevel('quarter');
                    setExpandedParents(new Set());
                  }}
                  isLoading={(loading && drillDownLevel !== 'quarter') || tenantSwitching}
                >
                  📊 Quarter
                </Button>
                <Button 
                  size="sm" 
                  colorScheme={drillDownLevel === 'month' ? 'orange' : 'gray'}
                  onClick={() => {
                    setDrillDownLevel('month');
                    setExpandedParents(new Set());
                  }}
                  isLoading={(loading && drillDownLevel !== 'month') || tenantSwitching}
                >
                  📈 Month
                </Button>
              </HStack>
            </GridItem>
            <GridItem>
              <Button colorScheme="orange" onClick={fetchActualsData} isLoading={loading || tenantSwitching} size="sm">
                Update Data
              </Button>
            </GridItem>
            <GridItem>
              <VStack align="start" spacing={1}>
                <Text color="gray.400" fontSize="xs">
                  Current View: {drillDownLevel === 'year' ? '📅 Yearly Summary' : drillDownLevel === 'quarter' ? '📊 Quarterly Breakdown' : '📈 Monthly Detail'}
                </Text>
                <Text color="gray.500" fontSize="xs">
                  {drillDownLevel === 'year' ? 'Shows annual totals' : drillDownLevel === 'quarter' ? 'Shows quarterly data' : 'Shows monthly granularity'}
                </Text>
              </VStack>
            </GridItem>
          </Grid>
        </CardBody>
      </Card>


      {/* Balance Table and Pie Chart */}
      <Grid templateColumns={{ base: "1fr", lg: "1fr 400px" }} gap={4}>
        <GridItem>
          <Card bg="gray.700">
            <CardHeader pb={2}>
              <Heading size="md" color="white">Balance (VW = N) - All Years Total</Heading>
            </CardHeader>
            <CardBody pt={0}>
              <TableContainer>
                <Table size="sm" variant="simple" style={{borderCollapse: 'collapse'}}>
                  <Thead>
                    <Tr>
                      <Th color="white" width="120px" border="none">Account</Th>
                      <Th color="white" width="100px" textAlign="right" border="none">Total Amount</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {renderBalanceData(balanceData, actualsFilters.displayFormat)}
                  </Tbody>
                </Table>
              </TableContainer>
            </CardBody>
          </Card>
        </GridItem>
        
        <GridItem>
          <Card bg="gray.700">
            <CardHeader pb={2}>
              <Heading size="md" color="white">Balance Distribution</Heading>
            </CardHeader>
            <CardBody pt={0}>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={(() => {
                      const hasExpandedParents = Array.from(expandedParents).some(key => key.startsWith('balance-'));
                      if (hasExpandedParents) {
                        return balanceData.filter(row => expandedParents.has(`balance-${row.Parent}`)).reduce((acc, row) => {
                          const existing = acc.find(item => item.name === row.ledger);
                          const value = Math.abs(Number(row.Amount) || 0);
                          if (existing) {
                            existing.value += value;
                          } else {
                            acc.push({ name: row.ledger, value });
                          }
                          return acc;
                        }, [] as any[]).filter(item => item.value > 0);
                      } else {
                        const grouped = balanceData.reduce((acc, row) => {
                          if (!acc[row.Parent]) {
                            acc[row.Parent] = { parent: row.Parent, ledgers: [], total: 0 };
                          }
                          acc[row.Parent].ledgers.push(row);
                          acc[row.Parent].total += Number(row.Amount) || 0;
                          return acc;
                        }, {} as any);
                        return Object.values(grouped).map((group: any) => ({
                          name: group.parent,
                          value: Math.abs(group.total)
                        })).filter(item => item.value > 0);
                      }
                    })()}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                    label={(entry) => entry.name}
                  >
                    {(() => {
                      const hasExpandedParents = Array.from(expandedParents).some(key => key.startsWith('balance-'));
                      const data = hasExpandedParents 
                        ? balanceData.filter(row => expandedParents.has(`balance-${row.Parent}`)).reduce((acc, row) => {
                            const existing = acc.find(item => item.name === row.ledger);
                            const value = Math.abs(Number(row.Amount) || 0);
                            if (existing) {
                              existing.value += value;
                            } else {
                              acc.push({ name: row.ledger, value });
                            }
                            return acc;
                          }, [] as any[]).filter(item => item.value > 0)
                        : (() => {
                            const grouped = balanceData.reduce((acc, row) => {
                              if (!acc[row.Parent]) {
                                acc[row.Parent] = { parent: row.Parent, ledgers: [], total: 0 };
                              }
                              acc[row.Parent].ledgers.push(row);
                              acc[row.Parent].total += Number(row.Amount) || 0;
                              return acc;
                            }, {} as any);
                            return Object.values(grouped).map((group: any) => ({
                              name: group.parent,
                              value: Math.abs(group.total)
                            })).filter(item => item.value > 0);
                          })();
                      return data.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                      ));
                    })()}
                  </Pie>
                  <Tooltip formatter={(value) => formatAmount(Number(value), actualsFilters.displayFormat)} />
                </PieChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>


      {/* Profit/Loss Table and Bar Chart */}
      <Grid templateColumns={{ base: "1fr", lg: "1fr 1.5fr" }} gap={4}>
        <GridItem>
          <Card bg="gray.700">
            <CardHeader pb={2}>
              <Heading size="md" color="white">Profit/Loss (VW = Y)</Heading>
            </CardHeader>
            <CardBody pt={0}>
              <TableContainer>
                <Table size="sm" variant="simple" style={{borderCollapse: 'collapse'}}>
                  <Thead>
                    <Tr>
                      <Th color="white" width="120px" border="none">Account</Th>
                      {drillDownLevel === 'year' && [...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map(year => (
                        <Th key={year} color="white" width="60px" textAlign="right" border="none">{year}</Th>
                      ))}
                      {drillDownLevel === 'quarter' && [...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map(year => 
                        ['Q1', 'Q2', 'Q3', 'Q4'].map(quarter => (
                          <Th key={`${year}-${quarter}`} color="white" width="60px" textAlign="right" border="none">
                            {year} {quarter}
                          </Th>
                        ))
                      ).flat()}
                      {drillDownLevel === 'month' && [...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map(year => 
                        ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'].map(month => (
                          <Th key={`${year}-${month}`} color="white" width="60px" textAlign="right" border="none">
                            {year} {month}
                          </Th>
                        ))
                      ).flat()}
                    </Tr>
                  </Thead>
                  <Tbody>
                    {renderHierarchicalData(profitLossData, actualsFilters.years, actualsFilters.displayFormat)}
                  </Tbody>
                </Table>
              </TableContainer>
            </CardBody>
          </Card>
        </GridItem>
        
        <GridItem>
          <Card bg="gray.700">
            <CardHeader pb={2}>
              <Heading size="md" color="white">P&L Distribution</Heading>
            </CardHeader>
            <CardBody pt={0}>
              <ResponsiveContainer width="100%" height={480}>
                <BarChart
                  data={(() => {
                    const hasExpandedParents = Array.from(expandedParents).some(key => key.startsWith('profitloss-'));
                    const filteredData = profitLossData.filter(row => row.ledger !== '8099');
                    
                    if (hasExpandedParents) {
                      return filteredData
                        .filter(row => expandedParents.has(`profitloss-${row.Parent}`))
                        .reduce((acc, row) => {
                          const existing = acc.find(item => item.name === row.ledger);
                          const value = Number(row.Amount) || 0;
                          if (existing) {
                            existing[row.jaar] = (existing[row.jaar] || 0) + value;
                          } else {
                            const newItem: any = { name: row.ledger };
                            actualsFilters.years.forEach(year => {
                              newItem[year] = 0;
                            });
                            newItem[row.jaar] = value;
                            acc.push(newItem);
                          }
                          return acc;
                        }, [] as any[])
                        .filter(item => actualsFilters.years.some(year => Math.abs(item[year] || 0) > 0));
                    } else {
                      return filteredData
                        .reduce((acc, row) => {
                          const existing = acc.find(item => item.name === row.Parent);
                          const value = Number(row.Amount) || 0;
                          if (existing) {
                            existing[row.jaar] = (existing[row.jaar] || 0) + value;
                          } else {
                            const newItem: any = { name: row.Parent };
                            actualsFilters.years.forEach(year => {
                              newItem[year] = 0;
                            });
                            newItem[row.jaar] = value;
                            acc.push(newItem);
                          }
                          return acc;
                        }, [] as any[])
                        .filter(item => actualsFilters.years.some(year => Math.abs(item[year] || 0) > 0));
                    }
                  })()}
                  margin={{ top: 0, right: 15, left: 15, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} fontSize={10} tick={{fill: 'white'}} />
                  <YAxis tick={{fill: 'white'}} />
                  <Tooltip formatter={(value) => formatAmount(Number(value), actualsFilters.displayFormat)} />
                  <Legend wrapperStyle={{color: 'white', paddingTop: '5px'}} />
                  {[...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map((year, index) => (
                    <Bar key={year} dataKey={year} fill={`hsl(${index * 60}, 70%, 60%)`} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
              <Text color="gray.400" fontSize="xs" mt={2} textAlign="center">
                * 8099 Bijzondere baten en lasten not included
              </Text>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>
    </VStack>
  );
};

export default ActualsReport;
