import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Heading, Select, Button, Text,
  Card, CardBody, CardHeader, Grid, GridItem, Input,
  Table, Thead, Tbody, Tr, Th, Td, TableContainer,
  Tabs, TabList, TabPanels, Tab, TabPanel, Badge
} from '@chakra-ui/react';
import { Chart } from 'react-google-charts';

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
}

const ProfitLoss: React.FC = () => {
  const [mutatiesData, setMutatiesData] = useState<MutatiesRecord[]>([]);
  const [bnbData, setBnbData] = useState<BnbRecord[]>([]);
  const [balanceData, setBalanceData] = useState<BalanceRecord[]>([]);
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
    profitLoss: 'all' // all, Y, N
  });

  // BNB Filters  
  const [bnbFilters, setBnbFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    channel: 'all',
    listing: 'all'
  });

  // Balance Filters - Added dateFrom
  const [balanceFilters, setBalanceFilters] = useState({
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
        console.log('Mutaties data sample:', data.data[0]);
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
        dateFrom: balanceFilters.dateFrom,
        dateTo: balanceFilters.dateTo,
        administration: balanceFilters.administration,
        profitLoss: balanceFilters.profitLoss
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/balance-data?${params}`);
      const data = await response.json();
      
      if (data.success) {
        // Filter out zero amounts
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
        console.log('BNB data sample:', data.data[0]);
        setBnbData(data.data);
      }
    } catch (err) {
      console.error('Error fetching BNB data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMutatiesData();
    fetchBnbData();
    fetchBalanceData();
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
    ].map(row => row.join(',')).join('\n');
    
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
    ].map(row => row.join(',')).join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bnb-${bnbFilters.dateFrom}-${bnbFilters.dateTo}.csv`;
    a.click();
  };

  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <style>
        {`
          .google-visualization-table-table td:nth-child(3) {
            text-align: right !important;
          }
          .google-visualization-table-table tr:has(td:nth-child(2):contains('TOTAL')) {
            font-weight: bold !important;
          }
          .google-visualization-table-table td[data-parent='true'] {
            font-weight: bold !important;
          }
          .chakra-table {
            border-collapse: collapse !important;
          }
          .chakra-table td, .chakra-table th {
            border: none !important;
            padding: 2px 8px !important;
            line-height: 1.2 !important;
          }
          .google-visualization-tooltip {
            color: #000 !important;
          }
          .google-visualization-tooltip * {
            color: #000 !important;
          }
        `}
      </style>
      <VStack spacing={6} align="stretch">

        <Tabs variant="enclosed" colorScheme="orange">
          <TabList>
            <Tab color="white">💰 Mutaties (P&L)</Tab>
            <Tab color="white">🏠 BNB Revenue</Tab>
            <Tab color="white">📊 Profit/Loss</Tab>
          </TabList>

          <TabPanels>
            {/* Mutaties Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                {/* Mutaties Filters */}
                <Card bg="gray.700">
                  <CardHeader>
                    <Heading size="md" color="white">Mutaties Filters</Heading>
                  </CardHeader>
                  <CardBody>
                    <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
                      <GridItem>
                        <Text color="white" mb={2}>From Date</Text>
                        <Input
                          type="date"
                          value={mutatiesFilters.dateFrom}
                          onChange={(e) => setMutatiesFilters(prev => ({...prev, dateFrom: e.target.value}))}
                          bg="gray.600"
                          color="white"
                        />
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>To Date</Text>
                        <Input
                          type="date"
                          value={mutatiesFilters.dateTo}
                          onChange={(e) => setMutatiesFilters(prev => ({...prev, dateTo: e.target.value}))}
                          bg="gray.600"
                          color="white"
                        />
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Administration</Text>
                        <Select
                          value={mutatiesFilters.administration}
                          onChange={(e) => setMutatiesFilters(prev => ({...prev, administration: e.target.value}))}
                          bg="gray.600"
                          color="white"
                        >
                          <option value="all">All</option>
                          <option value="GoodwinSolutions">GoodwinSolutions</option>
                          <option value="PeterPrive">PeterPrive</option>
                        </Select>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Profit/Loss</Text>
                        <Select
                          value={mutatiesFilters.profitLoss}
                          onChange={(e) => setMutatiesFilters(prev => ({...prev, profitLoss: e.target.value}))}
                          bg="gray.600"
                          color="white"
                        >
                          <option value="all">All</option>
                          <option value="Y">Y</option>
                          <option value="N">N</option>
                        </Select>
                      </GridItem>
                    </Grid>
                    <HStack mt={4}>
                      <Button colorScheme="orange" onClick={fetchMutatiesData} isLoading={loading}>
                        Update Mutaties
                      </Button>
                      <Button variant="outline" onClick={exportMutatiesCsv}>
                        Export CSV
                      </Button>
                      <Badge colorScheme="blue">{filteredMutatiesData.length} / {mutatiesData.length} records</Badge>
                    </HStack>
                  </CardBody>
                </Card>

                {/* Mutaties Table */}
                <Card bg="gray.700">
                  <CardHeader>
                    <Heading size="md" color="white">Mutaties Data</Heading>
                  </CardHeader>
                  <CardBody>
                    <TableContainer maxH="500px" overflowY="auto">
                      <Table size="sm" variant="simple">
                        <Thead position="sticky" top={0} bg="gray.600">
                          <Tr>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('TransactionDate')}>Date {sortField === 'TransactionDate' && (sortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('ReferenceNumber')} maxW="60px" w="60px">Reference {sortField === 'ReferenceNumber' && (sortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('TransactionDescription')}>Description {sortField === 'TransactionDescription' && (sortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('Amount')}>Amount {sortField === 'Amount' && (sortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('Reknum')} w="80px">Account {sortField === 'Reknum' && (sortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('AccountName')} w="150px">Account Name {sortField === 'AccountName' && (sortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleSort('Administration')}>Administration {sortField === 'Administration' && (sortDirection === 'asc' ? '↑' : '↓')}</Th>
                          </Tr>
                          <Tr>
                            <Th></Th>
                            <Th><Input size="xs" placeholder="Search..." value={searchFilters.ReferenceNumber} onChange={(e) => setSearchFilters(prev => ({...prev, ReferenceNumber: e.target.value}))} bg="gray.500" color="white" /></Th>
                            <Th><Input size="xs" placeholder="Search..." value={searchFilters.TransactionDescription} onChange={(e) => setSearchFilters(prev => ({...prev, TransactionDescription: e.target.value}))} bg="gray.500" color="white" /></Th>
                            <Th></Th>
                            <Th><Input size="xs" placeholder="Search..." value={searchFilters.Reknum} onChange={(e) => setSearchFilters(prev => ({...prev, Reknum: e.target.value}))} bg="gray.500" color="white" /></Th>
                            <Th><Input size="xs" placeholder="Search..." value={searchFilters.AccountName} onChange={(e) => setSearchFilters(prev => ({...prev, AccountName: e.target.value}))} bg="gray.500" color="white" /></Th>
                            <Th><Input size="xs" placeholder="Search..." value={searchFilters.Administration} onChange={(e) => setSearchFilters(prev => ({...prev, Administration: e.target.value}))} bg="gray.500" color="white" /></Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {filteredMutatiesData.map((row, index) => (
                            <Tr key={index} bg={index % 2 === 0 ? 'gray.600' : 'gray.700'}>
                              <Td color="white">{new Date(row.TransactionDate).toLocaleDateString('en-GB').replace(/\//g, '-')}</Td>
                              <Td color="white" maxW="60px" w="60px" isTruncated>{row.ReferenceNumber}</Td>
                              <Td color="white" maxW="300px" isTruncated>{row.TransactionDescription}</Td>
                              <Td color="white" isNumeric>€{Number(row.Amount || 0).toFixed(2)}</Td>
                              <Td color="white" w="80px">{row.Reknum}</Td>
                              <Td color="white" w="150px" isTruncated>{row.AccountName}</Td>
                              <Td color="white">{row.Administration}</Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </TableContainer>
                  </CardBody>
                </Card>
              </VStack>
            </TabPanel>

            {/* BNB Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                {/* BNB Filters */}
                <Card bg="gray.700">
                  <CardHeader>
                    <Heading size="md" color="white">BNB Filters</Heading>
                  </CardHeader>
                  <CardBody>
                    <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
                      <GridItem>
                        <Text color="white" mb={2}>From Date</Text>
                        <Input
                          type="date"
                          value={bnbFilters.dateFrom}
                          onChange={(e) => setBnbFilters(prev => ({...prev, dateFrom: e.target.value}))}
                          bg="gray.600"
                          color="white"
                        />
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>To Date</Text>
                        <Input
                          type="date"
                          value={bnbFilters.dateTo}
                          onChange={(e) => setBnbFilters(prev => ({...prev, dateTo: e.target.value}))}
                          bg="gray.600"
                          color="white"
                        />
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Channel</Text>
                        <Select
                          value={bnbFilters.channel}
                          onChange={(e) => setBnbFilters(prev => ({...prev, channel: e.target.value}))}
                          bg="gray.600"
                          color="white"
                        >
                          <option value="all">All Channels</option>
                          <option value="airbnb">Airbnb</option>
                          <option value="booking.com">Booking.com</option>
                          <option value="dfDirect">Direct</option>
                          <option value="VRBO">VRBO</option>
                        </Select>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Listing</Text>
                        <Select
                          value={bnbFilters.listing}
                          onChange={(e) => setBnbFilters(prev => ({...prev, listing: e.target.value}))}
                          bg="gray.600"
                          color="white"
                        >
                          <option value="all">All Listings</option>
                          <option value="Red Studio">Red Studio</option>
                          <option value="Green Studio">Green Studio</option>
                          <option value="Child Friendly">Child Friendly</option>
                        </Select>
                      </GridItem>
                    </Grid>
                    <HStack mt={4}>
                      <Button colorScheme="orange" onClick={fetchBnbData} isLoading={loading}>
                        Update BNB Data
                      </Button>
                      <Button variant="outline" onClick={exportBnbCsv}>
                        Export CSV
                      </Button>
                      <Badge colorScheme="green">{filteredBnbData.length} / {bnbData.length} bookings</Badge>
                    </HStack>
                  </CardBody>
                </Card>

                {/* BNB Table */}
                <Card bg="gray.700">
                  <CardHeader>
                    <Heading size="md" color="white">BNB Revenue Data</Heading>
                  </CardHeader>
                  <CardBody>
                    <TableContainer maxH="500px" overflowY="auto">
                      <Table size="sm" variant="simple">
                        <Thead position="sticky" top={0} bg="gray.600">
                          <Tr>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('checkinDate')}>Check-in {bnbSortField === 'checkinDate' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('checkoutDate')}>Check-out {bnbSortField === 'checkoutDate' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('channel')}>Channel {bnbSortField === 'channel' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('listing')}>Listing {bnbSortField === 'listing' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('nights')} w="60px">Nights {bnbSortField === 'nights' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('guests')} w="60px">Guests {bnbSortField === 'guests' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountGross')} w="80px">Gross {bnbSortField === 'amountGross' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountNett')} w="80px">Net {bnbSortField === 'amountNett' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('guestName')}>Guest {bnbSortField === 'guestName' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                            <Th color="white" cursor="pointer" onClick={() => handleBnbSort('reservationCode')}>Reservation {bnbSortField === 'reservationCode' && (bnbSortDirection === 'asc' ? '↑' : '↓')}</Th>
                          </Tr>
                          <Tr>
                            <Th></Th>
                            <Th></Th>
                            <Th><Input size="xs" placeholder="Search..." value={bnbSearchFilters.channel} onChange={(e) => setBnbSearchFilters(prev => ({...prev, channel: e.target.value}))} bg="gray.500" color="white" /></Th>
                            <Th><Input size="xs" placeholder="Search..." value={bnbSearchFilters.listing} onChange={(e) => setBnbSearchFilters(prev => ({...prev, listing: e.target.value}))} bg="gray.500" color="white" /></Th>
                            <Th></Th>
                            <Th></Th>
                            <Th></Th>
                            <Th></Th>
                            <Th><Input size="xs" placeholder="Search..." value={bnbSearchFilters.guestName} onChange={(e) => setBnbSearchFilters(prev => ({...prev, guestName: e.target.value}))} bg="gray.500" color="white" /></Th>
                            <Th><Input size="xs" placeholder="Search..." value={bnbSearchFilters.reservationCode} onChange={(e) => setBnbSearchFilters(prev => ({...prev, reservationCode: e.target.value}))} bg="gray.500" color="white" /></Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {filteredBnbData.map((row, index) => (
                            <Tr key={index} bg={index % 2 === 0 ? 'gray.600' : 'gray.700'}>
                              <Td color="white">{new Date(row.checkinDate).toLocaleDateString('en-GB').replace(/\//g, '-')}</Td>
                              <Td color="white">{row.checkoutDate ? new Date(row.checkoutDate).toLocaleDateString('en-GB').replace(/\//g, '-') : 'N/A'}</Td>
                              <Td color="white">{row.channel}</Td>
                              <Td color="white">{row.listing}</Td>
                              <Td color="white" isNumeric w="60px">{Number(row.nights || 0)}</Td>
                              <Td color="white" isNumeric w="60px">{Number(row.guests || 0)}</Td>
                              <Td color="white" isNumeric w="80px">€{Number(row.amountGross || 0).toFixed(0)}</Td>
                              <Td color="white" isNumeric w="80px">€{Number(row.amountNett || 0).toFixed(0)}</Td>
                              <Td color="white" maxW="200px" isTruncated>{row.guestName}</Td>
                              <Td color="white">{row.reservationCode}</Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </TableContainer>
                  </CardBody>
                </Card>
              </VStack>
            </TabPanel>

            {/* Profit/Loss Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                {/* Profit/Loss Filters */}
                <Card bg="gray.700">
                  <CardBody>
                    <HStack spacing={4} wrap="wrap">
                      <VStack spacing={1}>
                        <Text color="white" fontSize="sm">Date From</Text>
                        <Input
                          type="date"
                          value={balanceFilters.dateFrom}
                          onChange={(e) => setBalanceFilters(prev => ({...prev, dateFrom: e.target.value}))}
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
                          value={balanceFilters.dateTo}
                          onChange={(e) => setBalanceFilters(prev => ({...prev, dateTo: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                          w="150px"
                        />
                      </VStack>
                      <VStack spacing={1}>
                        <Text color="white" fontSize="sm">Administration</Text>
                        <Select
                          value={balanceFilters.administration}
                          onChange={(e) => setBalanceFilters(prev => ({...prev, administration: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                          w="150px"
                        >
                          <option value="all">All</option>
                          <option value="GoodwinSolutions">GoodwinSolutions</option>
                          <option value="PeterPrive">PeterPrive</option>
                        </Select>
                      </VStack>
                      <VStack spacing={1}>
                        <Text color="white" fontSize="sm">Profit/Loss</Text>
                        <Select
                          value={balanceFilters.profitLoss}
                          onChange={(e) => setBalanceFilters(prev => ({...prev, profitLoss: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                          w="100px"
                        >
                          <option value="all">All</option>
                          <option value="Y">Y</option>
                          <option value="N">N</option>
                        </Select>
                      </VStack>
                      <Button colorScheme="orange" onClick={fetchBalanceData} isLoading={loading} size="sm">
                        Update Profit/Loss
                      </Button>
                      <Badge colorScheme="purple">{balanceData.length} records</Badge>
                    </HStack>
                  </CardBody>
                </Card>

                {/* Profit/Loss Chart and Table */}
                <HStack spacing={4} align="start">
                  <Card bg="gray.700">
                    <CardBody>
                      <Chart
                        chartType="PieChart"
                        data={[
                          ['Ledger', 'Amount'],
                          ...balanceData.map(row => [
                            row.ledger || 'N/A',
                            Math.abs(Number(row.total_amount || 0))
                          ])
                        ]}
                        options={{
                          pieHole: 0.4,
                          backgroundColor: 'transparent',
                          legend: { textStyle: { color: '#fff' } },
                          pieSliceTextStyle: { color: '#000' },
                          tooltip: { textStyle: { color: '#000', fontSize: 12 }, trigger: 'both' },
                          focusTarget: 'category',
                          chartArea: { width: '90%', height: '98%' }
                        }}
                        width="500px"
                        height="400px"
                      />
                    </CardBody>
                  </Card>

                  <Card bg="gray.700">
                    <CardHeader>
                      <Heading size="md" color="white">Profit/Loss Statement</Heading>
                    </CardHeader>
                  <CardBody>
                    <Box maxW="400px">
                      <TableContainer maxH="500px" overflowY="auto">
                      <Table size="sm" variant="simple">
                        <Thead position="sticky" top={0} bg="gray.600">
                          <Tr>
                            <Th color="white">Parent</Th>
                            <Th color="white" textAlign="right">Amount</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {(() => {
                            const groupedData: { [key: string]: BalanceRecord[] } = {};
                            
                            // Group by Parent
                            balanceData.forEach(row => {
                              const parent = row.Parent || 'N/A';
                              if (!groupedData[parent]) {
                                groupedData[parent] = [];
                              }
                              groupedData[parent].push(row);
                            });
                            
                            const tableRows: React.ReactElement[] = [];
                            
                            // Calculate grand total
                            const grandTotal = balanceData.reduce((sum, row) => sum + Number(row.total_amount || 0), 0);
                            
                            // Add rows with subtotals
                            Object.entries(groupedData).forEach(([parent, rows]) => {
                              const subtotal = rows.reduce((sum, row) => sum + Number(row.total_amount || 0), 0);
                              
                              // Add parent subtotal row
                              tableRows.push(
                                <Tr key={`parent-${parent}`} bg="gray.500" fontWeight="bold">
                                  <Td color="white" fontWeight="bold">{parent}</Td>
                                  <Td color="white" fontWeight="bold" textAlign="right">
                                    {subtotal.toLocaleString('nl-NL', {minimumFractionDigits: 2, maximumFractionDigits: 2})} €
                                  </Td>
                                </Tr>
                              );
                              
                              // Add detail rows
                              rows.forEach((row, index) => {
                                tableRows.push(
                                  <Tr key={`detail-${parent}-${index}`} bg={index % 2 === 0 ? 'gray.600' : 'gray.700'}>
                                    <Td color="white" pl={8}>&nbsp;&nbsp;{row.ledger || 'N/A'}</Td>
                                    <Td color="white" textAlign="right">
                                      {Number(row.total_amount || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2, maximumFractionDigits: 2})} €
                                    </Td>
                                  </Tr>
                                );
                              });
                            });
                            
                            // Add grand total row
                            tableRows.push(
                              <Tr key="grand-total" bg="gray.500" fontWeight="bold" borderTop="2px" borderColor="gray.300">
                                <Td color="white" fontWeight="bold">TOTAL</Td>
                                <Td color="white" fontWeight="bold" textAlign="right">
                                  {grandTotal.toLocaleString('nl-NL', {minimumFractionDigits: 2, maximumFractionDigits: 2})} €
                                </Td>
                              </Tr>
                            );
                            
                            return tableRows;
                          })(
                          )}
                        </Tbody>
                      </Table>
                      </TableContainer>
                    </Box>
                    </CardBody>
                  </Card>
                </HStack>
              </VStack>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
};

export default ProfitLoss;