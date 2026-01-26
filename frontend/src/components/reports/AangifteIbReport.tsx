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
  Progress,
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
import { buildApiUrl } from '../../config';
import { authenticatedGet, authenticatedPost } from '../../services/apiService';
import { tenantAwareGet, tenantAwarePost, requireTenant } from '../../services/tenantApiService';
import { useTenant } from '../../context/TenantContext';
import UnifiedAdminYearFilter from '../UnifiedAdminYearFilter';
import { createAangifteIbFilterAdapter } from '../UnifiedAdminYearFilterAdapters';

interface AangifteIbRecord {
  Parent: string;
  Aangifte: string;
  Amount: number;
}

interface AangifteIbDetail {
  Reknum: string;
  AccountName: string;
  Amount: number;
}

interface XlsxExportProgress {
  current: number;
  total: number;
  status: string;
  fileProgress?: {
    current_file: number;
    total_files: number;
    reference_number: string;
  };
}

const AangifteIbReport: React.FC = () => {
  const { currentTenant } = useTenant();
  const [aangifteIbData, setAangifteIbData] = useState<AangifteIbRecord[]>([]);
  const [aangifteIbDetails, setAangifteIbDetails] = useState<AangifteIbDetail[]>([]);
  const [aangifteIbFilters, setAangifteIbFilters] = useState({
    year: new Date().getFullYear().toString(),
    administration: currentTenant || 'all'
  });
  const [aangifteIbAvailableYears, setAangifteIbAvailableYears] = useState<string[]>([]);
  const [aangifteIbLoading, setAangifteIbLoading] = useState(false);
  const [selectedAangifteRow, setSelectedAangifteRow] = useState<{parent: string, aangifte: string} | null>(null);
  const [expandedAangifteRows, setExpandedAangifteRows] = useState<Set<string>>(new Set());
  const [xlsxExportLoading, setXlsxExportLoading] = useState(false);
  const [xlsxExportProgress, setXlsxExportProgress] = useState<XlsxExportProgress | null>(null);
  const [tenantSwitching, setTenantSwitching] = useState(false);

  const fetchAangifteIbData = async () => {
    setAangifteIbLoading(true);
    try {
      const params = {
        year: aangifteIbFilters.year
      };
      
      const response = await tenantAwareGet('/api/reports/aangifte-ib', params);
      const data = await response.json();
      
      if (data.success) {
        setAangifteIbData(data.data);
        setAangifteIbAvailableYears(data.available_years);
      }
    } catch (err) {
      console.error('Error fetching Aangifte IB data:', err);
    } finally {
      setAangifteIbLoading(false);
    }
  };

  const fetchAangifteIbDetails = async (parent: string, aangifte: string) => {
    try {
      const params = {
        year: aangifteIbFilters.year,
        parent: parent,
        aangifte: aangifte
      };
      
      const response = await tenantAwareGet('/api/reports/aangifte-ib-details', params);
      const data = await response.json();
      
      if (data.success) {
        setAangifteIbDetails(data.data);
        setSelectedAangifteRow({parent, aangifte});
      }
    } catch (err) {
      console.error('Error fetching Aangifte IB details:', err);
    }
  };

  const handleExportHtml = async () => {
    try {
      // Validate tenant selection
      const tenant = requireTenant();
      
      const exportData = {
        year: aangifteIbFilters.year,
        administration: tenant,
        data: aangifteIbData
      };
      
      const response = await tenantAwarePost('/api/reports/aangifte-ib-export', exportData);
      const data = await response.json();
      if (data.success) {
        const blob = new Blob([data.html], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = data.filename;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Export error:', err);
      if (err instanceof Error && err.message.includes('No tenant selected')) {
        alert('Error: No tenant selected. Please select a tenant first.');
      } else {
        alert('Export failed. Please try again.');
      }
    }
  };

  const handleGenerateXlsx = async () => {
    try {
      // Validate tenant selection
      const tenant = requireTenant();
      
      console.log('Starting XLSX export with streaming...');
      setXlsxExportLoading(true);
      setXlsxExportProgress(null);
      
      const response = await tenantAwarePost(
        '/api/reports/aangifte-ib-xlsx-export-stream',
        {
          administrations: [tenant],
          years: [aangifteIbFilters.year]
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        throw new Error('No response body reader available');
      }

      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === 'start') {
                setXlsxExportProgress({
                  current: 0,
                  total: 1,
                  status: 'Starting export...'
                });
              } else if (data.type === 'progress') {
                setXlsxExportProgress({
                  current: data.current_combination || 0,
                  total: data.total_combinations || 1,
                  status: data.status || 'Processing...',
                  fileProgress: data.file_progress
                });
              } else if (data.type === 'complete') {
                console.log('Export completed:', data.message);
                alert(`Export completed! ${data.message}`);
                setXlsxExportProgress(null);
                break;
              } else if (data.type === 'error') {
                console.error('Export error:', data.message);
                alert(`Export error: ${data.message}`);
                setXlsxExportProgress(null);
                break;
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }
    } catch (err) {
      console.error('XLSX export error:', err);
      if (err instanceof Error && err.message.includes('No tenant selected')) {
        alert('Error: No tenant selected. Please select a tenant first.');
      } else {
        alert('Failed to export XLSX files. Check console for details.');
      }
    } finally {
      setXlsxExportLoading(false);
    }
  };

  useEffect(() => {
    if (aangifteIbFilters.year) {
      fetchAangifteIbData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aangifteIbFilters.year, aangifteIbFilters.administration]);

  // Auto-refresh on tenant change
  useEffect(() => {
    if (currentTenant) {
      setTenantSwitching(true);
      
      // Update filters with current tenant
      setAangifteIbFilters(prev => ({
        ...prev,
        administration: currentTenant
      }));
      
      // Clear previous tenant data
      setAangifteIbData([]);
      setAangifteIbDetails([]);
      setSelectedAangifteRow(null);
      setExpandedAangifteRows(new Set());
      setXlsxExportProgress(null);
      
      // Reset tenant switching state after a brief delay
      setTimeout(() => setTenantSwitching(false), 100);
    }
  }, [currentTenant]);

  const renderTableRows = () => {
    const grouped = aangifteIbData.reduce((acc, row) => {
      // Skip rows with zero amounts
      const amount = Number(row.Amount) || 0;
      if (Math.abs(amount) < 0.01) return acc;
      
      if (!acc[row.Parent]) {
        acc[row.Parent] = { parent: row.Parent, items: [], total: 0 };
      }
      acc[row.Parent].items.push(row);
      acc[row.Parent].total += amount;
      return acc;
    }, {} as any);
    
    const rows: React.ReactElement[] = [];
    
    Object.values(grouped).forEach((group: any) => {
      // Skip parent groups with zero total
      if (Math.abs(group.total) < 0.01) return;
      
      const isExpanded = expandedAangifteRows.has(group.parent);
      
      // Parent row
      rows.push(
        <Tr key={group.parent} bg="gray.600">
          <Td color="white" fontSize="sm" w="50px">
            <Button
              size="xs"
              variant="ghost"
              color="white"
              onClick={() => {
                const newExpanded = new Set(expandedAangifteRows);
                if (isExpanded) {
                  newExpanded.delete(group.parent);
                } else {
                  newExpanded.add(group.parent);
                }
                setExpandedAangifteRows(newExpanded);
              }}
            >
              {isExpanded ? '−' : '+'}
            </Button>
          </Td>
          <Td color="white" fontSize="sm" fontWeight="bold">{group.parent}</Td>
          <Td color="white" fontSize="sm"></Td>
          <Td color="white" fontSize="sm" isNumeric fontWeight="bold">
            €{group.total.toLocaleString('nl-NL', {minimumFractionDigits: 2})}
          </Td>
        </Tr>
      );
      
      // Detail rows
      if (isExpanded) {
        group.items.forEach((item: any) => {
          // Skip items with zero amounts
          const itemAmount = Number(item.Amount) || 0;
          if (Math.abs(itemAmount) < 0.01) return;
          
          const rowKey = `${group.parent}-${item.Aangifte}`;
          const isDetailExpanded = selectedAangifteRow?.parent === group.parent && selectedAangifteRow?.aangifte === item.Aangifte;
          
          rows.push(
            <Tr 
              key={rowKey}
              cursor="pointer"
              _hover={{ bg: "gray.500" }}
              bg={isDetailExpanded ? "gray.500" : "transparent"}
              onClick={() => {
                if (isDetailExpanded) {
                  setSelectedAangifteRow(null);
                  setAangifteIbDetails([]);
                } else {
                  fetchAangifteIbDetails(group.parent, item.Aangifte);
                }
              }}
            >
              <Td color="white" fontSize="sm" w="50px" pl={8}>
                <Button size="xs" variant="ghost" color="white">
                  {isDetailExpanded ? '−' : '+'}
                </Button>
              </Td>
              <Td color="white" fontSize="sm" pl={8}></Td>
              <Td color="white" fontSize="sm">{item.Aangifte}</Td>
              <Td color="white" fontSize="sm" isNumeric>
                €{itemAmount.toLocaleString('nl-NL', {minimumFractionDigits: 2})}
              </Td>
            </Tr>
          );
          
          // Account details
          if (isDetailExpanded && aangifteIbDetails.length > 0) {
            // Filter out zero amount details
            const nonZeroDetails = aangifteIbDetails.filter(detail => Math.abs(Number(detail.Amount) || 0) >= 0.01);
            
            if (nonZeroDetails.length > 0) {
              rows.push(
                <Tr key={`${rowKey}-details`}>
                  <Td colSpan={4} p={0}>
                    <Box bg="gray.800" p={4}>
                      <Text color="white" fontWeight="bold" mb={3}>
                        Accounts for {selectedAangifteRow?.parent} - {selectedAangifteRow?.aangifte}
                      </Text>
                      <Table size="sm" variant="simple">
                        <Thead>
                          <Tr>
                            <Th color="white" fontSize="xs">Account</Th>
                            <Th color="white" fontSize="xs">Description</Th>
                            <Th color="white" fontSize="xs" isNumeric>Amount</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {nonZeroDetails.map((detail, detailIndex) => (
                            <Tr key={detailIndex}>
                              <Td color="white" fontSize="xs">{detail.Reknum}</Td>
                              <Td color="white" fontSize="xs">{detail.AccountName}</Td>
                              <Td color="white" fontSize="xs" isNumeric>
                                €{Number(detail.Amount).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                              </Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                      <Box mt={3} p={2} bg="gray.700" borderRadius="md">
                        <Text color="white" fontSize="sm" fontWeight="bold">
                          Total: €{nonZeroDetails.reduce((sum, d) => sum + (Number(d.Amount) || 0), 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                        </Text>
                      </Box>
                    </Box>
                  </Td>
                </Tr>
              );
            }
          }
        });
      }
    });
    
    // Add Resultaat row (Parent 4000 - Parent 8000)
    const parent4000Total = aangifteIbData.filter(row => row.Parent === '4000').reduce((sum, row) => sum + (Number(row.Amount) || 0), 0);
    const parent8000Total = aangifteIbData.filter(row => row.Parent === '8000').reduce((sum, row) => sum + (Number(row.Amount) || 0), 0);
    const resultaat = parent4000Total + parent8000Total;
    
    // Only show Resultaat if non-zero
    if (Math.abs(resultaat) >= 0.01) {
      rows.push(
        <Tr key="resultaat" bg={resultaat >= 0 ? "red.600" : "green.600"}>
          <Td color="white" fontSize="sm" w="50px"></Td>
          <Td color="white" fontSize="sm" fontWeight="bold">RESULTAAT</Td>
          <Td color="white" fontSize="sm"></Td>
          <Td color="white" fontSize="sm" isNumeric fontWeight="bold">
            €{resultaat.toLocaleString('nl-NL', {minimumFractionDigits: 2})}
          </Td>
        </Tr>
      );
    }
    
    // Add grand total row
    const grandTotal = aangifteIbData.reduce((sum, row) => sum + (Number(row.Amount) || 0), 0);
    rows.push(
      <Tr key="grand-total" bg="orange.600">
        <Td color="white" fontSize="sm" w="50px"></Td>
        <Td color="white" fontSize="sm" fontWeight="bold">GRAND TOTAL</Td>
        <Td color="white" fontSize="sm"></Td>
        <Td color="white" fontSize="sm" isNumeric fontWeight="bold">
          €{grandTotal.toLocaleString('nl-NL', {minimumFractionDigits: 2})}
        </Td>
      </Tr>
    );
    
    return rows;
  };

  return (
    <VStack spacing={4} align="stretch">
      {!currentTenant && (
        <Alert status="warning">
          <AlertIcon />
          No tenant selected. Please select a tenant first.
        </Alert>
      )}
      
      <Card bg="gray.700">
        <CardBody>
          <HStack spacing={4} flexWrap="nowrap">
            <UnifiedAdminYearFilter
              {...createAangifteIbFilterAdapter(
                aangifteIbFilters,
                setAangifteIbFilters,
                aangifteIbAvailableYears
              )}
              size="sm"
              isLoading={aangifteIbLoading || tenantSwitching}
            />
            <Button 
              colorScheme="orange"
              onClick={handleExportHtml}
              size="sm"
              isDisabled={aangifteIbData.length === 0 || !currentTenant || tenantSwitching}
            >
              Export HTML
            </Button>
            <Button 
              colorScheme="green" 
              onClick={handleGenerateXlsx}
              isLoading={xlsxExportLoading}
              size="sm"
              isDisabled={!currentTenant || !aangifteIbFilters.year || tenantSwitching}
            >
              Generate XLSX
            </Button>
          </HStack>
          
          {xlsxExportProgress && (
            <VStack spacing={2} align="stretch" mt={4}>
              <VStack spacing={1} align="stretch">
                <Text color="gray.300" fontSize="xs" textAlign="center">
                  Overall Progress: {xlsxExportProgress.current}/{xlsxExportProgress.total}
                </Text>
                <Progress 
                  value={(xlsxExportProgress.current / xlsxExportProgress.total) * 100} 
                  colorScheme="green" 
                  size="sm"
                  bg="gray.600"
                />
              </VStack>
              
              {xlsxExportProgress.fileProgress && (
                <VStack spacing={1} align="stretch">
                  <Text color="gray.300" fontSize="xs" textAlign="center">
                    Files: {xlsxExportProgress.fileProgress.current_file}/{xlsxExportProgress.fileProgress.total_files} ({xlsxExportProgress.fileProgress.reference_number})
                  </Text>
                  <Progress 
                    value={(xlsxExportProgress.fileProgress.current_file / xlsxExportProgress.fileProgress.total_files) * 100} 
                    colorScheme="blue" 
                    size="xs"
                    bg="gray.600"
                  />
                </VStack>
              )}
              
              <Text color="gray.300" fontSize="xs" textAlign="center">
                {xlsxExportProgress.status}
              </Text>
            </VStack>
          )}
        </CardBody>
      </Card>

      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">Aangifte IB Summary</Heading>
        </CardHeader>
        <CardBody>
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="white" w="50px"></Th>
                  <Th color="white">Parent</Th>
                  <Th color="white">Aangifte</Th>
                  <Th color="white" isNumeric>Amount</Th>
                </Tr>
              </Thead>
              <Tbody>
                {renderTableRows()}
              </Tbody>
            </Table>
          </TableContainer>
        </CardBody>
      </Card>
    </VStack>
  );
};

export default AangifteIbReport;
