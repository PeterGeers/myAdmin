import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  Heading,
  HStack,
  Input,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
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
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { authenticatedGet } from '../../services/apiService';
import { buildApiUrl } from '../../config';
import UnifiedAdminYearFilter from '../UnifiedAdminYearFilter';
import { createRefAnalysisFilterAdapter } from '../UnifiedAdminYearFilterAdapters';
import { useTenant } from '../../context/TenantContext';

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
  const { currentTenant } = useTenant();
  
  const [refAnalysisFilters, setRefAnalysisFilters] = useState({
    years: [new Date().getFullYear().toString()],
    administration: currentTenant || 'all',
    referenceNumber: '',
    accounts: [] as string[]
  });
  
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
      // Update filters with new tenant
      setRefAnalysisFilters(prev => ({
        ...prev,
        administration: currentTenant
      }));
      
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

    setRefAnalysisLoading(true);
    try {
      const params = new URLSearchParams({
        years: refAnalysisFilters.years.join(','),
        administration: currentTenant, // Use current tenant instead of filter value
        reference_number: refAnalysisFilters.referenceNumber,
        accounts: refAnalysisFilters.accounts.join(',')
      });
      
      const response = await authenticatedGet(buildApiUrl('/api/reports/reference-analysis', params));
      const data = await response.json();
      
      if (data.success) {
        setRefAnalysisData(data.transactions);
        setRefTrendData(data.trend_data);
        setAvailableRefAccounts(data.available_accounts);
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
        <Alert status="warning">
          <AlertIcon />
          No tenant selected. Please select a tenant first to view reference analysis data.
        </Alert>
      )}

      <Card bg="gray.700">
        <CardBody>
          <VStack spacing={4} align="stretch">
            {/* All filters on one line */}
            <HStack spacing={3} wrap="wrap" align="end">
              <Box minW="150px">
                <UnifiedAdminYearFilter
                  {...createRefAnalysisFilterAdapter(refAnalysisFilters, setRefAnalysisFilters, availableYears)}
                  showAdministration={false}
                  size="sm"
                />
              </Box>
              <Box minW="200px">
                <Text color="white" mb={2} fontSize="sm">Reference Number (Regex)</Text>
                <Input
                  value={refAnalysisFilters.referenceNumber}
                  onChange={(e) => setRefAnalysisFilters(prev => ({...prev, referenceNumber: e.target.value}))}
                  placeholder="Enter regex pattern (e.g. AMZN or .*Amazon.*)"
                  bg="gray.600"
                  color="white"
                  size="xs"
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  name="reference-regex-input"
                  id="reference-regex-input"
                />
              </Box>
              <Box minW="150px">
                <Text color="white" mb={2} fontSize="sm">Accounts</Text>
                <Menu closeOnSelect={false}>
                  <MenuButton
                    as={Button}
                    bg="orange.500"
                    color="white"
                    size="xs"
                    width="100%"
                    textAlign="left"
                    rightIcon={<span>▼</span>}
                    _hover={{ bg: "orange.600" }}
                    _active={{ bg: "orange.600" }}
                  >
                    {refAnalysisFilters.accounts.length > 0 ? `${refAnalysisFilters.accounts.length} selected` : 'Select accounts...'}
                  </MenuButton>
                  <MenuList bg="gray.600" border="1px solid" borderColor="gray.500" maxH="400px" overflowY="auto">
                    {availableRefAccounts.map((account, index) => (
                      <MenuItem key={`ref-account-${account.Reknum}-${index}`} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
                        <Checkbox
                          isChecked={refAnalysisFilters.accounts.includes(account.Reknum)}
                          onChange={(e) => {
                            const isChecked = e.target.checked;
                            setRefAnalysisFilters(prev => ({
                              ...prev,
                              accounts: isChecked
                                ? [...prev.accounts, account.Reknum]
                                : prev.accounts.filter(a => a !== account.Reknum)
                            }));
                          }}
                          colorScheme="orange"
                          size="xs"
                        >
                          <Text color="white" ml={2} fontSize="xs">{account.Reknum} - {account.AccountName}</Text>
                        </Checkbox>
                      </MenuItem>
                    ))}
                  </MenuList>
                </Menu>
              </Box>
              <Box>
                <Button 
                  colorScheme="orange" 
                  onClick={fetchReferenceAnalysis} 
                  isLoading={refAnalysisLoading}
                  isDisabled={!currentTenant}
                  size="xs"
                  mt={6}
                >
                  Analyze
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
            <Heading size="md" color="white">Expense Trend by Quarter</Heading>
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
            <Heading size="md" color="white">Transactions ({refAnalysisData.length})</Heading>
          </CardHeader>
          <CardBody>
            <TableContainer maxH="600px" overflowY="auto">
              <Table size="sm" variant="simple">
                <Thead position="sticky" top={0} bg="gray.700" zIndex={1}>
                  <Tr>
                    <Th color="white">Date</Th>
                    <Th color="white">Description</Th>
                    <Th color="white" isNumeric>Amount</Th>
                    <Th color="white">Account</Th>
                    <Th color="white">Reference</Th>
                    <Th color="white">Administration</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {refAnalysisData.map((row, index) => (
                    <Tr key={index}>
                      <Td color="white" fontSize="sm">
                        {new Date(row.TransactionDate).toLocaleDateString('nl-NL')}
                      </Td>
                      <Td color="white" fontSize="sm" maxW="300px" isTruncated title={row.TransactionDescription}>
                        {row.TransactionDescription}
                      </Td>
                      <Td color="white" fontSize="sm" isNumeric>
                        €{Number(row.Amount).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
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
                Total: €{refAnalysisData.reduce((sum, row) => sum + Math.abs(Number(row.Amount)), 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
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
              <Heading size="md" color="white">Reference Number Analysis Instructions</Heading>
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
            </VStack>
          </CardBody>
        </Card>
      )}
    </VStack>
  );
};

export default ReferenceAnalysisReport;
