import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Heading, Select, Button, Text,
  Card, CardBody, CardHeader, Grid, GridItem, Input,
  Table, Thead, Tbody, Tr, Th, Td, TableContainer,
  Tabs, TabList, TabPanels, Tab, TabPanel, Badge, Stack,
  Menu, MenuButton, MenuList, MenuItem, Checkbox
} from '@chakra-ui/react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, PieChart, Pie, Sector } from 'recharts';
// @ts-ignore
import GridLayout from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

interface MutatiesRecord {
  TransactionDate: string;
  TransactionDescription: string;
  Amount: number;
  Reknum: string;
  AccountName: string;
  Administration: string;
  ReferenceNumber: string;
}

interface BnbRecord {
  checkinDate: string;
  checkoutDate: string;
  channel: string;
  listing: string;
  nights: number;
  amountGross: number;
  amountNett: number;
  guestName: string;
  guests: number;
  reservationCode: string;
}

interface BalanceRecord {
  Parent: string;
  ledger: string;
  total_amount: number;
  [key: string]: any;
}

const MyAdminReports: React.FC = () => {
  const [mutatiesData, setMutatiesData] = useState<MutatiesRecord[]>([]);
  const [bnbData, setBnbData] = useState<BnbRecord[]>([]);
  const [balanceData, setBalanceData] = useState<BalanceRecord[]>([]);
  const [profitLossData, setProfitLossData] = useState<BalanceRecord[]>([]);
  const [trendsData, setTrendsData] = useState<any[]>([]);
  const [checkRefData, setCheckRefData] = useState<any[]>([]);
  const [refSummaryData, setRefSummaryData] = useState<any[]>([]);
  const [filterCombinations, setFilterCombinations] = useState<any[]>([]);
  const [selectedReference, setSelectedReference] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sortField, setSortField] = useState<string>('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [bnbSortField, setBnbSortField] = useState<string>('');
  const [bnbSortDirection, setBnbSortDirection] = useState<'asc' | 'desc'>('desc');
  const [searchFilters, setSearchFilters] = useState({
    TransactionDescription: '',
    Reknum: '',
    AccountName: '',
    Administration: '',
    ReferenceNumber: ''
  });
  const [bnbSearchFilters, setBnbSearchFilters] = useState({
    channel: '',
    listing: '',
    guestName: '',
    reservationCode: ''
  });
  
  // Mutaties Filters
  const [mutatiesFilters, setMutatiesFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    administration: 'all',
    profitLoss: 'all'
  });

  // BNB Filters  
  const [bnbFilters, setBnbFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    channel: 'all',
    listing: 'all'
  });

  // Balance Filters
  const [balanceFilters, setBalanceFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    administration: 'all',
    profitLoss: 'all'
  });

  // Profit/Loss Filters
  const [profitLossFilters, setProfitLossFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    administration: 'all',
    profitLoss: 'all'
  });

  // P&L Trends Filters
  const [trendsFilters, setTrendsFilters] = useState({
    administration: 'all',
    years: [new Date().getFullYear().toString()],
    vwAccount: 'Y',
    displayFormat: '2decimals'
  });

  // Check Reference Filters
  const [checkRefFilters, setCheckRefFilters] = useState({
    referenceNumber: 'all',
    ledger: 'all',
    administration: 'all'
  });

  // Check Reference Search Filters
  const [checkRefSearchFilters, setCheckRefSearchFilters] = useState({
    referenceNumber: '',
    ledger: ''
  });

  // Actuals Dashboard State
  const [actualsFilters, setActualsFilters] = useState({
    years: ['2024'],
    administration: 'all',
    displayFormat: '2dec'
  });
  const [availableYears, setAvailableYears] = useState<string[]>([]);

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
  const renderHierarchicalData = (data: any[], years: string[], displayFormat: string) => {
    const sortedYears = [...years].sort((a, b) => parseInt(a) - parseInt(b));
    const grouped = data.reduce((acc, row) => {
      if (!acc[row.Parent]) {
        acc[row.Parent] = { parent: row.Parent, ledgers: {}, totals: {} };
      }
      
      // Group ledgers by name and accumulate amounts by year
      if (!acc[row.Parent].ledgers[row.ledger]) {
        acc[row.Parent].ledgers[row.ledger] = {};
        years.forEach(year => {
          acc[row.Parent].ledgers[row.ledger][year] = 0;
        });
      }
      
      acc[row.Parent].ledgers[row.ledger][row.jaar] = (acc[row.Parent].ledgers[row.ledger][row.jaar] || 0) + (Number(row.Amount) || 0);
      
      // Calculate parent totals
      years.forEach(year => {
        const key = `amount_${year}`;
        if (!acc[row.Parent].totals[key]) acc[row.Parent].totals[key] = 0;
        if (row.jaar == year) {
          acc[row.Parent].totals[key] += Number(row.Amount) || 0;
        }
      });
      
      return acc;
    }, {} as any);

    const rows: React.ReactElement[] = [];
    let totalIndex = 0;
    const grandTotals: { [key: string]: number } = {};

    // Initialize grand totals
    years.forEach(year => {
      grandTotals[`amount_${year}`] = 0;
    });

    Object.values(grouped).forEach((group: any) => {
      // Add to grand totals
      sortedYears.forEach(year => {
        grandTotals[`amount_${year}`] += group.totals[`amount_${year}`] || 0;
      });
      
      // Parent row with totals
      rows.push(
        <Tr key={`parent-${totalIndex}`} bg="gray.600">
          <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
            {group.parent}
          </Td>
          {sortedYears.map(year => (
            <Td key={year} color="white" fontSize="sm" width="60px" textAlign="right" fontWeight="bold" border="none" py={1}>
              {formatAmount(group.totals[`amount_${year}`] || 0, displayFormat)}
            </Td>
          ))}
        </Tr>
      );
      
      // Ledger rows consolidated by ledger name with 2-character indent
      Object.entries(group.ledgers).forEach(([ledgerName, ledgerAmounts]: [string, any], ledgerIndex: number) => {
        rows.push(
          <Tr key={`ledger-${totalIndex}-${ledgerIndex}`}>
            <Td color="white" fontSize="sm" width="120px" paddingLeft="16px" border="none" py={1}>
              {ledgerName}
            </Td>
            {sortedYears.map(year => (
              <Td key={year} color="white" fontSize="sm" width="60px" textAlign="right" border="none" py={1}>
                {formatAmount(ledgerAmounts[year] || 0, displayFormat)}
              </Td>
            ))}
          </Tr>
        );
      });
      
      totalIndex++;
    });

    // Add grand total row
    rows.push(
      <Tr key="grand-total" bg="orange.600">
        <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
          TOTAL
        </Td>
        {sortedYears.map(year => (
          <Td key={year} color="white" fontSize="sm" width="60px" textAlign="right" fontWeight="bold" border="none" py={1}>
            {formatAmount(grandTotals[`amount_${year}`] || 0, displayFormat)}
          </Td>
        ))}
      </Tr>
    );

    return rows;
  };

  // Render Balance data (aggregated across all years)
  const renderBalanceData = (data: any[], displayFormat: string) => {
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
      
      // Parent row with total
      rows.push(
        <Tr key={`parent-${totalIndex}`} bg="gray.600">
          <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
            {group.parent}
          </Td>
          <Td color="white" fontSize="sm" width="100px" textAlign="right" fontWeight="bold" border="none" py={1}>
            {formatAmount(group.total, displayFormat)}
          </Td>
        </Tr>
      );
      
      // Ledger rows indented under parent with 2-character indent
      group.ledgers.forEach((ledger: any, ledgerIndex: number) => {
        rows.push(
          <Tr key={`ledger-${totalIndex}-${ledgerIndex}`}>
            <Td color="white" fontSize="sm" width="120px" paddingLeft="16px" border="none" py={1}>
              {ledger.ledger}
            </Td>
            <Td color="white" fontSize="sm" width="100px" textAlign="right" border="none" py={1}>
              {formatAmount(Number(ledger.Amount) || 0, displayFormat)}
            </Td>
          </Tr>
        );
      });
      
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

  const handleBnbSort = (field: string) => {
    const newDirection = bnbSortField === field && bnbSortDirection === 'asc' ? 'desc' : 'asc';
    setBnbSortField(field);
    setBnbSortDirection(newDirection);
    
    const sortedData = [...bnbData].sort((a, b) => {
      let aVal = a[field as keyof BnbRecord];
      let bVal = b[field as keyof BnbRecord];
      
      if (field === 'checkinDate' || field === 'checkoutDate') {
        aVal = new Date(aVal as string).getTime();
        bVal = new Date(bVal as string).getTime();
      } else if (field === 'nights' || field === 'guests' || field === 'amountGross' || field === 'amountNett') {
        aVal = Number(aVal) || 0;
        bVal = Number(bVal) || 0;
      }
      
      if (aVal < bVal) return newDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return newDirection === 'asc' ? 1 : -1;
      return 0;
    });
    
    setBnbData(sortedData);
  };

  const filteredMutatiesData = mutatiesData.filter(row => {
    return Object.entries(searchFilters).every(([key, value]) => {
      if (!value) return true;
      const fieldValue = row[key as keyof MutatiesRecord]?.toString().toLowerCase() || '';
      return fieldValue.includes(value.toLowerCase());
    });
  });

  const filteredBnbData = bnbData.filter(row => {
    return Object.entries(bnbSearchFilters).every(([key, value]) => {
      if (!value) return true;
      const fieldValue = row[key as keyof BnbRecord]?.toString().toLowerCase() || '';
      return fieldValue.includes(value.toLowerCase());
    });
  });

  const fetchMutatiesData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        dateFrom: mutatiesFilters.dateFrom,
        dateTo: mutatiesFilters.dateTo,
        administration: mutatiesFilters.administration,
        profitLoss: mutatiesFilters.profitLoss
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/mutaties-table?${params}`);
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

  const fetchBalanceData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        dateTo: balanceFilters.dateTo,
        administration: balanceFilters.administration,
        profitLoss: balanceFilters.profitLoss
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/balance-data?${params}`);
      const data = await response.json();
      
      if (data.success) {
        const filteredData = data.data.filter((row: BalanceRecord) => 
          Math.abs(Number(row.total_amount || 0)) > 0.01
        );
        setBalanceData(filteredData);
      }
    } catch (err) {
      console.error('Error fetching balance data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchProfitLossData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        dateFrom: profitLossFilters.dateFrom,
        dateTo: profitLossFilters.dateTo,
        administration: profitLossFilters.administration,
        profitLoss: profitLossFilters.profitLoss
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/balance-data?${params}`);
      const data = await response.json();
      
      if (data.success) {
        const filteredData = data.data.filter((row: BalanceRecord) => 
          Math.abs(Number(row.total_amount || 0)) > 0.01
        );
        setProfitLossData(filteredData);
      }
    } catch (err) {
      console.error('Error fetching profit/loss data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTrendsData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        years: trendsFilters.years.join(','),
        administration: trendsFilters.administration,
        profitLoss: trendsFilters.vwAccount
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/trends-data?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setTrendsData(data.data);
      }
    } catch (err) {
      console.error('Error fetching trends data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchFilterOptions = async () => {
    try {
      const response = await fetch(`http://localhost:5000/api/reports/filter-options`);
      const data = await response.json();
      
      if (data.success) {
        setFilterCombinations(data.combinations);
      }
    } catch (err) {
      console.error('Error fetching filter options:', err);
    }
  };

  const fetchCheckRefData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        referenceNumber: checkRefFilters.referenceNumber,
        ledger: checkRefFilters.ledger,
        administration: checkRefFilters.administration
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/check-reference?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setCheckRefData(data.transactions);
        const filteredSummary = data.summary.filter((row: any) => {
          const amount = parseFloat(row.total_amount || 0);
          const isZero = amount === 0 || Math.abs(amount) < 0.01;
          const ledgerMatch = checkRefFilters.ledger === 'all' || row.ledger === checkRefFilters.ledger;
          return !isZero && ledgerMatch;
        });
        setRefSummaryData(filteredSummary);
      }
    } catch (err) {
      console.error('Error fetching check reference data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchBnbData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        dateFrom: bnbFilters.dateFrom,
        dateTo: bnbFilters.dateTo,
        channel: bnbFilters.channel,
        listing: bnbFilters.listing
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/bnb-table?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setBnbData(data.data);
      }
    } catch (err) {
      console.error('Error fetching BNB data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAvailableYears = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/reports/available-years');
      const data = await response.json();
      if (data.success) {
        setAvailableYears(data.years);
      }
    } catch (err) {
      console.error('Error fetching available years:', err);
    }
  };

  const fetchActualsData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        years: actualsFilters.years.join(','),
        administration: actualsFilters.administration
      });
      
      // Balance data (VW = N)
      const balanceResponse = await fetch(`http://localhost:5000/api/reports/actuals-balance?${params}`);
      const balanceResult = await balanceResponse.json();
      if (balanceResult.success) {
        setBalanceData(balanceResult.data);
      }

      // Profit/Loss data (VW = Y)
      const profitLossResponse = await fetch(`http://localhost:5000/api/reports/actuals-profitloss?${params}`);
      const profitLossResult = await profitLossResponse.json();
      if (profitLossResult.success) {
        setProfitLossData(profitLossResult.data);
      }
    } catch (err) {
      console.error('Error fetching actuals data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMutatiesData();
    fetchBnbData();
    fetchBalanceData();
    fetchProfitLossData();
    fetchFilterOptions();
    fetchAvailableYears();
    fetchActualsData();
  }, []);

  const exportMutatiesCsv = () => {
    const csvContent = [
      ['Date', 'Reference', 'Description', 'Amount', 'Debet', 'Credit', 'Administration'],
      ...mutatiesData.map(row => [
        row.TransactionDate,
        row.ReferenceNumber,
        row.TransactionDescription,
        row.Amount,
        row.Reknum,
        row.AccountName,
        row.Administration
      ])
    ].map(row => row.join(',')).join('\\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mutaties-${mutatiesFilters.dateFrom}-${mutatiesFilters.dateTo}.csv`;
    a.click();
  };

  const exportBnbCsv = () => {
    const csvContent = [
      ['Check-in Date', 'Check-out Date', 'Channel', 'Listing', 'Nights', 'Guests', 'Gross Amount', 'Net Amount', 'Guest Name', 'Reservation Code'],
      ...bnbData.map(row => [
        row.checkinDate,
        row.checkoutDate,
        row.channel,
        row.listing,
        row.nights,
        row.guests,
        row.amountGross,
        row.amountNett,
        row.guestName,
        row.reservationCode
      ])
    ].map(row => row.join(',')).join('\\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bnb-${bnbFilters.dateFrom}-${bnbFilters.dateTo}.csv`;
    a.click();
  };

  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        <Tabs variant="enclosed" colorScheme="orange">
          <TabList>
            <Tab color="white">💰 Mutaties (P&L)</Tab>
            <Tab color="white">🏠 BNB Revenue</Tab>
            <Tab color="white">📊 Actuals</Tab>
            <Tab color="white">📈 P&L Trends</Tab>
            <Tab color="white">🔍 Check Reference</Tab>
          </TabList>

          <TabPanels>
            {/* Mutaties Tab */}
            <TabPanel>
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
                            <Th color="white" cursor="pointer" onClick={() => handleSort('TransactionDate')}>
                              Date {sortField === 'TransactionDate' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('TransactionDescription')}>
                              Description {sortField === 'TransactionDescription' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('Amount')}>
                              Amount {sortField === 'Amount' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('AccountName')}>
                              Account {sortField === 'AccountName' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('ReferenceNumber')}>
                              Reference {sortField === 'ReferenceNumber' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {filteredMutatiesData.slice(0, 100).map((row, index) => (
                            <Tr key={index}>
                              <Td color="white" fontSize="sm">{new Date(row.TransactionDate).toLocaleDateString('nl-NL')}</Td>
                              <Td color="white" fontSize="sm">{row.TransactionDescription}</Td>
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
            </TabPanel>

            {/* BNB Revenue Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                <Card bg="gray.700">
                  <CardBody>
                    <HStack spacing={4} wrap="wrap">
                      <VStack spacing={1}>
                        <Text color="white" fontSize="sm">Date From</Text>
                        <Input
                          type="date"
                          value={bnbFilters.dateFrom}
                          onChange={(e) => setBnbFilters(prev => ({...prev, dateFrom: e.target.value}))}
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
                          value={bnbFilters.dateTo}
                          onChange={(e) => setBnbFilters(prev => ({...prev, dateTo: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                          w="150px"
                        />
                      </VStack>
                      <Button colorScheme="orange" onClick={fetchBnbData} isLoading={loading} size="sm">
                        Update BNB Data
                      </Button>
                      <Button variant="outline" onClick={exportBnbCsv} size="sm">
                        Export CSV
                      </Button>
                    </HStack>
                  </CardBody>
                </Card>

                <Card bg="gray.700">
                  <CardBody>
                    <HStack spacing={2} mb={4} wrap="wrap">
                      <Input
                        placeholder="Search Channel"
                        value={bnbSearchFilters.channel}
                        onChange={(e) => setBnbSearchFilters(prev => ({...prev, channel: e.target.value}))}
                        bg="gray.600"
                        color="white"
                        size="sm"
                        w="150px"
                      />
                      <Input
                        placeholder="Search Listing"
                        value={bnbSearchFilters.listing}
                        onChange={(e) => setBnbSearchFilters(prev => ({...prev, listing: e.target.value}))}
                        bg="gray.600"
                        color="white"
                        size="sm"
                        w="150px"
                      />
                      <Input
                        placeholder="Search Guest"
                        value={bnbSearchFilters.guestName}
                        onChange={(e) => setBnbSearchFilters(prev => ({...prev, guestName: e.target.value}))}
                        bg="gray.600"
                        color="white"
                        size="sm"
                        w="150px"
                      />
                    </HStack>
                    <TableContainer>
                      <Table size="sm" variant="simple">
                        <Thead>
                          <Tr>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('checkinDate')}>
                              Check-in {bnbSortField === 'checkinDate' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('checkoutDate')}>
                              Check-out {bnbSortField === 'checkoutDate' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('channel')}>
                              Channel {bnbSortField === 'channel' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('listing')}>
                              Listing {bnbSortField === 'listing' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('nights')}>
                              Nights {bnbSortField === 'nights' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountGross')}>
                              Gross {bnbSortField === 'amountGross' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountNett')}>
                              Net {bnbSortField === 'amountNett' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('guestName')}>
                              Guest {bnbSortField === 'guestName' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                            </Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {filteredBnbData.slice(0, 100).map((row, index) => (
                            <Tr key={index}>
                              <Td color="white" fontSize="sm">{new Date(row.checkinDate).toLocaleDateString('nl-NL')}</Td>
                              <Td color="white" fontSize="sm">{new Date(row.checkoutDate).toLocaleDateString('nl-NL')}</Td>
                              <Td color="white" fontSize="sm">{row.channel}</Td>
                              <Td color="white" fontSize="sm">{row.listing}</Td>
                              <Td color="white" fontSize="sm">{row.nights}</Td>
                              <Td color="white" fontSize="sm">€{Number(row.amountGross).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                              <Td color="white" fontSize="sm">€{Number(row.amountNett).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                              <Td color="white" fontSize="sm">{row.guestName}</Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </TableContainer>
                  </CardBody>
                </Card>
              </VStack>
            </TabPanel>

            {/* Actuals Dashboard Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                <Card bg="gray.700">
                  <CardBody>
                    <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
                      <GridItem>
                        <Text color="white" mb={2}>Select Years</Text>
                        <Menu closeOnSelect={false}>
                          <MenuButton
                            as={Button}
                            bg="orange.500"
                            color="white"
                            size="sm"
                            width="100%"
                            textAlign="left"
                            rightIcon={<span>▼</span>}
                            _hover={{ bg: "orange.600" }}
                            _active={{ bg: "orange.600" }}
                          >
                            {actualsFilters.years.length > 0 ? actualsFilters.years.join(', ') : 'Select years...'}
                          </MenuButton>
                          <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
                            {availableYears.map(year => (
                              <MenuItem key={year} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
                                <Checkbox
                                  isChecked={actualsFilters.years.includes(year)}
                                  onChange={(e) => {
                                    const isChecked = e.target.checked;
                                    setActualsFilters(prev => ({
                                      ...prev,
                                      years: isChecked 
                                        ? [...prev.years, year]
                                        : prev.years.filter(y => y !== year)
                                    }));
                                  }}
                                  colorScheme="orange"
                                >
                                  <Text color="white" ml={2}>{year}</Text>
                                </Checkbox>
                              </MenuItem>
                            ))}
                          </MenuList>
                        </Menu>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Administration</Text>
                        <Select
                          value={actualsFilters.administration}
                          onChange={(e) => setActualsFilters(prev => ({...prev, administration: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                        >
                          <option value="all">All</option>
                          <option value="GoodwinSolutions">GoodwinSolutions</option>
                          <option value="PeterPrive">PeterPrive</option>
                        </Select>
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
                        <Button colorScheme="orange" onClick={fetchActualsData} isLoading={loading} size="sm">
                          Update Data
                        </Button>
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
                              data={balanceData.reduce((acc, row) => {
                                const existing = acc.find(item => item.name === row.ledger);
                                const value = Math.abs(Number(row.Amount) || 0);
                                if (existing) {
                                  existing.value += value;
                                } else {
                                  acc.push({ name: row.ledger, value });
                                }
                                return acc;
                              }, [] as any[]).filter(item => item.value > 0)}
                              cx="50%"
                              cy="50%"
                              labelLine={false}
                              outerRadius={80}
                              fill="#8884d8"
                              dataKey="value"
                              label={(entry) => entry.name}
                            >
                              {balanceData.reduce((acc, row) => {
                                const existing = acc.find(item => item.name === row.ledger);
                                const value = Math.abs(Number(row.Amount) || 0);
                                if (existing) {
                                  existing.value += value;
                                } else {
                                  acc.push({ name: row.ledger, value });
                                }
                                return acc;
                              }, [] as any[]).filter(item => item.value > 0).map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                              ))}
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
                                {[...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map(year => (
                                  <Th key={year} color="white" width="60px" textAlign="right" border="none">{year}</Th>
                                ))}
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
                        <ResponsiveContainer width="100%" height={300}>
                          <BarChart
                            data={profitLossData
                              .filter(row => row.ledger !== '8099')
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
                              .filter(item => actualsFilters.years.some(year => Math.abs(item[year] || 0) > 0))}
                            margin={{ top: 20, right: 30, left: 20, bottom: 80 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} fontSize={10} tick={{fill: 'white'}} />
                            <YAxis tick={{fill: 'white'}} />
                            <Tooltip formatter={(value) => formatAmount(Number(value), actualsFilters.displayFormat)} />
                            {[...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map((year, index) => (
                              <Bar key={year} dataKey={year} fill={`hsl(${index * 60}, 70%, 60%)`} />
                            ))}
                          </BarChart>
                        </ResponsiveContainer>
                      </CardBody>
                    </Card>
                  </GridItem>
                </Grid>
              </VStack>
            </TabPanel>

            {/* P&L Trends Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                <Card bg="gray.700">
                  <CardBody>
                    <HStack spacing={4} wrap="wrap">
                      <Button colorScheme="orange" onClick={fetchTrendsData} isLoading={loading} size="sm">
                        Update Trends
                      </Button>
                    </HStack>
                  </CardBody>
                </Card>

                <Card bg="gray.700">
                  <CardHeader>
                    <Heading size="md" color="white">P&L Trends</Heading>
                  </CardHeader>
                  <CardBody>
                    <ResponsiveContainer width="100%" height={400}>
                      <LineChart data={trendsData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="month" />
                        <YAxis />
                        <Tooltip />
                        <Line type="monotone" dataKey="amount" stroke="#8884d8" />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardBody>
                </Card>
              </VStack>
            </TabPanel>

            {/* Check Reference Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                <Card bg="gray.700">
                  <CardBody>
                    <HStack spacing={4} wrap="wrap">
                      <VStack spacing={1}>
                        <Text color="white" fontSize="sm">Reference Number</Text>
                        <Select
                          value={checkRefFilters.referenceNumber}
                          onChange={(e) => setCheckRefFilters(prev => ({...prev, referenceNumber: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                          w="200px"
                        >
                          <option value="all">All References</option>
                          {filterCombinations.map((combo, index) => (
                            <option key={index} value={combo.ReferenceNumber}>{combo.ReferenceNumber}</option>
                          ))}
                        </Select>
                      </VStack>
                      <VStack spacing={1}>
                        <Text color="white" fontSize="sm">Ledger</Text>
                        <Select
                          value={checkRefFilters.ledger}
                          onChange={(e) => setCheckRefFilters(prev => ({...prev, ledger: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                          w="200px"
                        >
                          <option value="all">All Ledgers</option>
                          {filterCombinations.map((combo, index) => (
                            <option key={index} value={combo.ledger}>{combo.ledger}</option>
                          ))}
                        </Select>
                      </VStack>
                      <Button colorScheme="orange" onClick={fetchCheckRefData} isLoading={loading} size="sm">
                        Check References
                      </Button>
                    </HStack>
                  </CardBody>
                </Card>

                <Card bg="gray.700">
                  <CardHeader>
                    <Heading size="md" color="white">Reference Summary</Heading>
                  </CardHeader>
                  <CardBody>
                    <TableContainer>
                      <Table size="sm" variant="simple">
                        <Thead>
                          <Tr>
                            <Th color="white">Reference</Th>
                            <Th color="white">Ledger</Th>
                            <Th color="white">Amount</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {refSummaryData.slice(0, 100).map((row, index) => (
                            <Tr key={index}>
                              <Td color="white" fontSize="sm">{row.referenceNumber}</Td>
                              <Td color="white" fontSize="sm">{row.ledger}</Td>
                              <Td color="white" fontSize="sm">€{Number(row.total_amount).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </TableContainer>
                  </CardBody>
                </Card>
              </VStack>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
};

export default MyAdminReports;