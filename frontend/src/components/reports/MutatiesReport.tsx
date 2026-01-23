import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Button,
  Card,
  CardBody,
  HStack,
  Input,
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
import { authenticatedGet } from '../../services/apiService';

interface MutatiesRecord {
  TransactionDate: string;
  TransactionDescription: string;
  Amount: number;
  Reknum: string;
  AccountName: string;
  Administration: string;
  ReferenceNumber: string;
}

const MutatiesReport: React.FC = () => {
  const [mutatiesData, setMutatiesData] = useState<MutatiesRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [sortField, setSortField] = useState<string>('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [searchFilters, setSearchFilters] = useState({
    TransactionDescription: '',
    Reknum: '',
    AccountName: '',
    Administration: '',
    ReferenceNumber: ''
  });
  
  const [mutatiesFilters, setMutatiesFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    administration: 'all',
    profitLoss: 'all'
  });

  const handleSort = (field: string) => {
    const newDirection = sortField === field && sortDirection === 'asc' ? 'desc' : 'asc';
    setSortField(field);
    setSortDirection(newDirection);
    
    const sortedData = [...mutatiesData].sort((a, b) => {
      let aVal = a[field as keyof MutatiesRecord];
      let bVal = b[field as keyof MutatiesRecord];
      
      if (field === 'Amount') {
        aVal = Number(aVal) || 0;
        bVal = Number(bVal) || 0;
      }
      
      if (aVal < bVal) return newDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return newDirection === 'asc' ? 1 : -1;
      return 0;
    });
    
    setMutatiesData(sortedData);
  };

  const filteredMutatiesData = useMemo(() => {
    return mutatiesData.filter(row => {
      return Object.entries(searchFilters).every(([key, value]) => {
        if (!value) return true;
        const fieldValue = row[key as keyof MutatiesRecord]?.toString().toLowerCase() || '';
        return fieldValue.includes(value.toLowerCase());
      });
    });
  }, [mutatiesData, searchFilters]);

  const fetchMutatiesData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        dateFrom: mutatiesFilters.dateFrom,
        dateTo: mutatiesFilters.dateTo,
        administration: mutatiesFilters.administration,
        profitLoss: mutatiesFilters.profitLoss
      });
      
      const response = await authenticatedGet(buildApiUrl('/api/reports/mutaties-table', params));
      const data = await response.json();
      
      if (data.success) {
        setMutatiesData(data.data);
      }
    } catch (err) {
      console.error('Error fetching mutaties data:', err);
    } finally {
      setLoading(false);
    }
  };

  const exportMutatiesCsv = useCallback(() => {
    const csvContent = [
      ['Date', 'Reference', 'Description', 'Amount', 'Debet', 'Credit', 'Administration'],
      ...filteredMutatiesData.map(row => [
        row.TransactionDate,
        row.ReferenceNumber,
        row.TransactionDescription,
        row.Amount,
        row.Reknum,
        row.AccountName,
        row.Administration
      ])
    ].map(row => row.join(',')).join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mutaties-${mutatiesFilters.dateFrom}-${mutatiesFilters.dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filteredMutatiesData, mutatiesFilters.dateFrom, mutatiesFilters.dateTo]);

  useEffect(() => {
    fetchMutatiesData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardBody>
          <HStack spacing={4} wrap="wrap">
            <VStack spacing={1}>
              <Text color="white" fontSize="sm">Date From</Text>
              <Input
                type="date"
                value={mutatiesFilters.dateFrom}
                onChange={(e) => setMutatiesFilters(prev => ({...prev, dateFrom: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
                w="150px"
              />
            </VStack>
            <VStack spacing={1}>
              <Text color="white" fontSize="sm">Date To</Text>
              <Input
                type="date"
                value={mutatiesFilters.dateTo}
                onChange={(e) => setMutatiesFilters(prev => ({...prev, dateTo: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
                w="150px"
              />
            </VStack>
            <Button colorScheme="orange" onClick={fetchMutatiesData} isLoading={loading} size="sm">
              Update Data
            </Button>
            <Button variant="outline" onClick={exportMutatiesCsv} size="sm">
              Export CSV
            </Button>
          </HStack>
        </CardBody>
      </Card>

      <Card bg="gray.700">
        <CardBody>
          <HStack spacing={2} mb={4} wrap="wrap">
            <Input
              placeholder="Search Description"
              value={searchFilters.TransactionDescription}
              onChange={(e) => setSearchFilters(prev => ({...prev, TransactionDescription: e.target.value}))}
              bg="gray.600"
              color="white"
              size="sm"
              w="200px"
            />
            <Input
              placeholder="Search Account"
              value={searchFilters.AccountName}
              onChange={(e) => setSearchFilters(prev => ({...prev, AccountName: e.target.value}))}
              bg="gray.600"
              color="white"
              size="sm"
              w="200px"
            />
            <Input
              placeholder="Search Reference"
              value={searchFilters.ReferenceNumber}
              onChange={(e) => setSearchFilters(prev => ({...prev, ReferenceNumber: e.target.value}))}
              bg="gray.600"
              color="white"
              size="sm"
              w="200px"
            />
          </HStack>
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="white" cursor="pointer" onClick={() => handleSort('TransactionDate')} style={{color: 'white !important'}}>
                    Date {sortField === 'TransactionDate' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </Th>
                  <Th color="white" cursor="pointer" onClick={() => handleSort('TransactionDescription')} style={{color: 'white !important'}}>
                    Description {sortField === 'TransactionDescription' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </Th>
                  <Th color="white" cursor="pointer" onClick={() => handleSort('Amount')} style={{color: 'white !important'}}>
                    Amount {sortField === 'Amount' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </Th>
                  <Th color="white" cursor="pointer" onClick={() => handleSort('AccountName')} style={{color: 'white !important'}}>
                    Account {sortField === 'AccountName' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </Th>
                  <Th color="white" cursor="pointer" onClick={() => handleSort('ReferenceNumber')} style={{color: 'white !important'}}>
                    Reference {sortField === 'ReferenceNumber' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </Th>
                </Tr>
              </Thead>
              <Tbody>
                {filteredMutatiesData.slice(0, 100).map((row, index) => (
                  <Tr key={index}>
                    <Td color="white" fontSize="sm">{new Date(row.TransactionDate).toLocaleDateString('nl-NL')}</Td>
                    <Td color="white" fontSize="sm" maxW="300px" isTruncated title={row.TransactionDescription}>{row.TransactionDescription}</Td>
                    <Td color="white" fontSize="sm">€{Number(row.Amount).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                    <Td color="white" fontSize="sm">{row.AccountName}</Td>
                    <Td color="white" fontSize="sm">{row.ReferenceNumber}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
        </CardBody>
      </Card>
    </VStack>
  );
};

export default MutatiesReport;
