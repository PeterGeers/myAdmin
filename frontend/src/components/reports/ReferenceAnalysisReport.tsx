import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
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
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { FilterPanel } from '../filters/FilterPanel';
import { useTenant } from '../../context/TenantContext';
import { formatCurrency, formatDate } from '../../utils/formatting';

interface ReferenceAnalysisTransaction {
  TransactionDate: string;
  TransactionDescription: string;
  Amount: number;
  Reknum: string;
  AccountName: string;
  ReferenceNumber: string;
  Administration: string;
}

interface TrendDataPoint {
  jaar: number;
  kwartaal: number;
  total_amount: number;
}

interface AccountOption {
  Reknum: string;
  AccountName: string;
}

const ReferenceAnalysisReport: React.FC = () => {
  const { t, i18n } = useTypedTranslation('reports');
  const { currentTenant } = useTenant();
  
  // Separate state for each filter
  const [selectedYears, setSelectedYears] = useState<string[]>([new Date().getFullYear().toString()]);
  const [referenceNumber, setReferenceNumber] = useState<string>('');
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
  
  const [refAnalysisData, setRefAnalysisData] = useState<ReferenceAnalysisTransaction[]>([]);
  const [refTrendData, setRefTrendData] = useState<TrendDataPoint[]>([]);
  const [availableRefAccounts, setAvailableRefAccounts] = useState<AccountOption[]>([]);
  const [refAnalysisLoading, setRefAnalysisLoading] = useState(false);
  const [availableYears] = useState<string[]>(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: 10 }, (_, i) => (currentYear - i).toString());
  });

  // Auto-refresh on tenant change
  useEffect(() => {
    if (currentTenant) {
      // Clear previous tenant data
      setRefAnalysisData([]);
      setRefTrendData([]);
      setAvailableRefAccounts([]);
    }
  }, [currentTenant]);

  const fetchReferenceAnalysis = async () => {
    // Validate tenant selection before processing
    if (!currentTenant) {
      console.error('No tenant selected for reference analysis');
      return;
    }

    // Validate reference number is provided
    if (!referenceNumber || referenceNumber.trim() === '') {
      console.warn('No reference number provided');
      // Clear previous results
      setRefAnalysisData([]);
      setRefTrendData([]);
      return;
    }

    setRefAnalysisLoading(true);
    try {
      const params = new URLSearchParams({
        years: selectedYears.join(','),
        administration: currentTenant, // Use current tenant instead of filter value
        reference_number: referenceNumber,
        accounts: selectedAccounts.join(',')
      });
      
      console.log('Reference Analysis Request:', {
        years: selectedYears,
        administration: currentTenant,
        reference_number: referenceNumber,
        accounts: selectedAccounts,
        url: buildEndpoint('/api/reports/reference-analysis', params)
      });
      
      const response = await authenticatedGet(buildEndpoint('/api/reports/reference-analysis', params));
      const data = await response.json();
      
      console.log('Reference Analysis Response:', data);
      
      if (data.success) {
        setRefAnalysisData(data.transactions);
        setRefTrendData(data.trend_data);
        setAvailableRefAccounts(data.available_accounts);
      } else {
        console.error('Reference Analysis failed:', data);
      }
    } catch (err) {
      console.error('Error fetching reference analysis:', err);
    } finally {
      setRefAnalysisLoading(false);
    }
  };

  return (
    <VStack spacing={4} align="stretch">
      {/* Tenant validation alert */}
      {!currentTenant && (
        <Alert status="warning" data-testid="no-tenant-alert">
          <AlertIcon />
          {t('common:messages.noTenantSelected')}
        </Alert>
      )}

      <Card bg="gray.700">
        <CardBody>
          <VStack spacing={4} align="stretch">
            {/* All filters on one line */}
            <HStack spacing={3} wrap="wrap" align="end">
              <FilterPanel
                layout="horizontal"
                size="sm"
                spacing={3}
                filters={[
                  {
                    type: 'multi',
                    label: t('filters.year'),
                    options: availableYears,
                    value: selectedYears,
                    onChange: setSelectedYears,
                    placeholder: t('filters.selectYear')
                  },
                  {
                    type: 'search',
                    label: t('tables.reference'),
                    value: referenceNumber,
                    onChange: setReferenceNumber,
                    placeholder: t('common:placeholders.searchReference')
                  },
                  {
                    type: 'multi',
                    label: t('filters.account'),
                    options: availableRefAccounts,
                    value: availableRefAccounts.filter(acc => selectedAccounts.includes(acc.Reknum)),
                    onChange: (accounts: AccountOption[]) => setSelectedAccounts(accounts.map(acc => acc.Reknum)),
                    placeholder: t('filters.selectAccount'),
                    getOptionLabel: (account) => `${account.Reknum} - ${account.AccountName}`,
                    getOptionValue: (account) => account.Reknum,
                    treatEmptyAsSelected: false
                  }
                ]}
              />
              <Box>
                <Button 
                  colorScheme="orange" 
                  onClick={fetchReferenceAnalysis} 
                  isLoading={refAnalysisLoading}
                  isDisabled={!currentTenant}
                  size="sm"
                  mt={6}
                  data-testid="analyze-button"
                >
                  {t('common:buttons.analyze')}
                </Button>
              </Box>
            </HStack>
          </VStack>
        </CardBody>
      </Card>

      {/* Trend Chart */}
      {refTrendData.length > 0 && (
        <Card bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">{t('charts.trend')}</Heading>
          </CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart
                data={refTrendData.map(item => ({
                  period: `${item.jaar}-Q${item.kwartaal}`,
                  amount: Math.abs(Number(item.total_amount)),
                  label: `€${Math.abs(Number(item.total_amount)).toLocaleString('nl-NL', {minimumFractionDigits: 0})}`
                }))}
                margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period" tick={{fill: 'white'}} />
                <YAxis tick={{fill: 'white'}} />
                <Tooltip formatter={(value) => [`€${Number(value).toLocaleString('nl-NL')}`, 'Amount']} />
                <Line 
                  type="monotone" 
                  dataKey="amount" 
                  stroke="#f56500" 
                  strokeWidth={3}
                  dot={{ fill: '#f56500', strokeWidth: 2, r: 6 }}
                />
                {/* Add labels on top of each point */}
                {refTrendData.map((item, index) => {
                  const x = (index / (refTrendData.length - 1)) * 100;
                  return (
                    <text
                      key={index}
                      x={`${x}%`}
                      y="15"
                      textAnchor="middle"
                      fill="white"
                      fontSize="12"
                    >
                      €{Math.abs(Number(item.total_amount)).toLocaleString('nl-NL', {minimumFractionDigits: 0})}
                    </text>
                  );
                })}
              </LineChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      )}

      {/* Transactions Table */}
      {refAnalysisData.length > 0 && (
        <Card bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">{t('titles.mutaties')} ({refAnalysisData.length})</Heading>
          </CardHeader>
          <CardBody>
            <TableContainer maxH="600px" overflowY="auto">
              <Table size="sm" variant="simple">
                <Thead position="sticky" top={0} bg="gray.700" zIndex={1}>
                  <Tr>
                    <Th color="white">{t('tables.date')}</Th>
                    <Th color="white">{t('tables.description')}</Th>
                    <Th color="white" isNumeric>{t('tables.amount')}</Th>
                    <Th color="white">{t('tables.account')}</Th>
                    <Th color="white">{t('tables.reference')}</Th>
                    <Th color="white">{t('filters.administration')}</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {refAnalysisData.map((row, index) => (
                    <Tr key={index}>
                      <Td color="white" fontSize="sm">
                        {formatDate(new Date(row.TransactionDate), i18n.language)}
                      </Td>
                      <Td color="white" fontSize="sm" maxW="300px" isTruncated title={row.TransactionDescription}>
                        {row.TransactionDescription}
                      </Td>
                      <Td color="white" fontSize="sm" isNumeric>
                        {formatCurrency(Number(row.Amount), i18n.language)}
                      </Td>
                      <Td color="white" fontSize="sm">
                        {row.Reknum} - {row.AccountName}
                      </Td>
                      <Td color="white" fontSize="sm" maxW="150px" isTruncated title={row.ReferenceNumber}>
                        {row.ReferenceNumber}
                      </Td>
                      <Td color="white" fontSize="sm">
                        {row.Administration}
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </TableContainer>
            
            {/* Summary */}
            <Box mt={4} p={3} bg="gray.600" borderRadius="md">
              <Text color="white" fontWeight="bold">
                {t('tables.total')}: {formatCurrency(refAnalysisData.reduce((sum, row) => sum + Math.abs(Number(row.Amount)), 0), i18n.language)}
              </Text>
            </Box>
          </CardBody>
        </Card>
      )}

      {/* Instructions */}
      {refAnalysisData.length === 0 && !refAnalysisLoading && (
        <Card bg="gray.700">
          <CardBody>
            <VStack spacing={3} align="start">
              <Heading size="md" color="white">
                {referenceNumber ? 'No Results Found' : 'Reference Number Analysis Instructions'}
              </Heading>
              {referenceNumber ? (
                <>
                  <Text color="white" fontSize="sm">
                    No transactions found matching the reference pattern: <strong>{referenceNumber}</strong>
                  </Text>
                  <Text color="gray.400" fontSize="xs">
                    Tips:
                  </Text>
                  <Text color="gray.400" fontSize="xs">
                    • Check your regex pattern syntax
                  </Text>
                  <Text color="gray.400" fontSize="xs">
                    • Try a simpler pattern (e.g., just "AMZN" instead of ".*AMZN.*")
                  </Text>
                  <Text color="gray.400" fontSize="xs">
                    • Verify the reference number exists in the selected years
                  </Text>
                  <Text color="gray.400" fontSize="xs">
                    • Check if account filters are too restrictive
                  </Text>
                </>
              ) : (
                <>
                  <Text color="white" fontSize="sm">
                    1. Choose one or more years to include in the analysis
                  </Text>
                  <Text color="white" fontSize="sm">
                    2. Enter a reference number or regex pattern (e.g., "AMZN" or ".*Amazon.*")
                  </Text>
                  <Text color="white" fontSize="sm">
                    3. Optionally filter by specific accounts
                  </Text>
                  <Text color="white" fontSize="sm">
                    4. Click "Analyze" to view trends and transactions
                  </Text>
                  <Text color="gray.400" fontSize="xs">
                    The trend chart shows quarterly spending patterns with amounts displayed above each data point.
                  </Text>
                </>
              )}
            </VStack>
          </CardBody>
        </Card>
      )}
    </VStack>
  );
};

export default ReferenceAnalysisReport;
