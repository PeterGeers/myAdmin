import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Heading, Select, Button, Text,
  Card, CardBody, CardHeader, Grid, GridItem, Input,
  Table, Thead, Tbody, Tr, Th, Td, TableContainer,
  Tabs, TabList, TabPanels, Tab, TabPanel, Badge
} from '@chakra-ui/react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { FilterableHeader } from './filters/FilterableHeader';

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

const MUTATIES_INITIAL_FILTERS: Record<string, string> = {
  TransactionDescription: '',
  Reknum: '',
  AccountName: '',
  Administration: '',
  ReferenceNumber: ''
};

const BNB_INITIAL_FILTERS: Record<string, string> = {
  channel: '',
  listing: '',
  guestName: '',
  reservationCode: ''
};

const ProfitLoss: React.FC = () => {
  const [mutatiesData, setMutatiesData] = useState<MutatiesRecord[]>([]);
  const [bnbData, setBnbData] = useState<BnbRecord[]>([]);
  const [balanceData, setBalanceData] = useState<BalanceRecord[]>([]);
  const [loading, setLoading] = useState(false);

  // Mutaties column filters + sort via useFilterableTable
  const {
    filters: mutatiesFiltersSearch,
    setFilter: setMutatiesFilter,
    handleSort: handleMutatiesSort,
    sortField: mutatiesSortField,
    sortDirection: mutatiesSortDirection,
    processedData: filteredMutatiesData
  } = useFilterableTable<MutatiesRecord>(mutatiesData, {
    initialFilters: MUTATIES_INITIAL_FILTERS,
  });

  // BNB column filters + sort via useFilterableTable
  const {
    filters: bnbFiltersSearch,
    setFilter: setBnbFilter,
    handleSort: handleBnbSort,
    sortField: bnbSortField,
    sortDirection: bnbSortDirection,
    processedData: filteredBnbData
  } = useFilterableTable<BnbRecord>(bnbData, {
    initialFilters: BNB_INITIAL_FILTERS,
  });
  
  // Mutaties above-table filters (date range, administration, profit/loss)
  const [mutatiesFilters, setMutatiesFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    administration: 'all',
    profitLoss: 'all'
  });

  // BNB above-table filters (date range, channel, listing)
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
      
      const response = await fetch(`http://localhost:5000/api/bnb/bnb-table?${params}`);
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

  /** Helper to derive sortDirection prop for FilterableHeader */
  const mutatiesColumnSort = (field: string): 'asc' | 'desc' | null => {
    return mutatiesSortField === field ? mutatiesSortDirection : null;
  };

  const bnbColumnSort = (field: string): 'asc' | 'desc' | null => {
    return bnbSortField === field ? bnbSortDirection : null;
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
                            <FilterableHeader
                              label="Date"
                              sortable
                              sortDirection={mutatiesColumnSort('TransactionDate')}
                              onSort={() => handleMutatiesSort('TransactionDate')}
                            />
                            <FilterableHeader
                              label="Reference"
                              filterValue={mutatiesFiltersSearch.ReferenceNumber}
                              onFilterChange={(v) => setMutatiesFilter('ReferenceNumber', v)}
                              sortable
                              sortDirection={mutatiesColumnSort('ReferenceNumber')}
                              onSort={() => handleMutatiesSort('ReferenceNumber')}
                            />
                            <FilterableHeader
                              label="Description"
                              filterValue={mutatiesFiltersSearch.TransactionDescription}
                              onFilterChange={(v) => setMutatiesFilter('TransactionDescription', v)}
                              sortable
                              sortDirection={mutatiesColumnSort('TransactionDescription')}
                              onSort={() => handleMutatiesSort('TransactionDescription')}
                            />
                            <FilterableHeader
                              label="Amount"
                              isNumeric
                              sortable
                              sortDirection={mutatiesColumnSort('Amount')}
                              onSort={() => handleMutatiesSort('Amount')}
                            />
                            <FilterableHeader
                              label="Account"
                              filterValue={mutatiesFiltersSearch.Reknum}
                              onFilterChange={(v) => setMutatiesFilter('Reknum', v)}
                              sortable
                              sortDirection={mutatiesColumnSort('Reknum')}
                              onSort={() => handleMutatiesSort('Reknum')}
                            />
                            <FilterableHeader
                              label="Account Name"
                              filterValue={mutatiesFiltersSearch.AccountName}
                              onFilterChange={(v) => setMutatiesFilter('AccountName', v)}
                              sortable
                              sortDirection={mutatiesColumnSort('AccountName')}
                              onSort={() => handleMutatiesSort('AccountName')}
                            />
                            <FilterableHeader
                              label="Administration"
                              filterValue={mutatiesFiltersSearch.Administration}
                              onFilterChange={(v) => setMutatiesFilter('Administration', v)}
                              sortable
                              sortDirection={mutatiesColumnSort('Administration')}
                              onSort={() => handleMutatiesSort('Administration')}
                            />
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
                            <FilterableHeader
                              label="Check-in"
                              sortable
                              sortDirection={bnbColumnSort('checkinDate')}
                              onSort={() => handleBnbSort('checkinDate')}
                            />
                            <FilterableHeader
                              label="Check-out"
                              sortable
                              sortDirection={bnbColumnSort('checkoutDate')}
                              onSort={() => handleBnbSort('checkoutDate')}
                            />
                            <FilterableHeader
                              label="Channel"
                              filterValue={bnbFiltersSearch.channel}
                              onFilterChange={(v) => setBnbFilter('channel', v)}
                              sortable
                              sortDirection={bnbColumnSort('channel')}
                              onSort={() => handleBnbSort('channel')}
                            />
                            <FilterableHeader
                              label="Listing"
                              filterValue={bnbFiltersSearch.listing}
                              onFilterChange={(v) => setBnbFilter('listing', v)}
                              sortable
                              sortDirection={bnbColumnSort('listing')}
                              onSort={() => handleBnbSort('listing')}
                            />
                            <FilterableHeader
                              label="Nights"
                              isNumeric
                              sortable
                              sortDirection={bnbColumnSort('nights')}
                              onSort={() => handleBnbSort('nights')}
                            />
                            <FilterableHeader
                              label="Guests"
                              isNumeric
                              sortable
                              sortDirection={bnbColumnSort('guests')}
                              onSort={() => handleBnbSort('guests')}
                            />
                            <FilterableHeader
                              label="Gross"
                              isNumeric
                              sortable
                              sortDirection={bnbColumnSort('amountGross')}
                              onSort={() => handleBnbSort('amountGross')}
                            />
                            <FilterableHeader
                              label="Net"
                              isNumeric
                              sortable
                              sortDirection={bnbColumnSort('amountNett')}
                              onSort={() => handleBnbSort('amountNett')}
                            />
                            <FilterableHeader
                              label="Guest"
                              filterValue={bnbFiltersSearch.guestName}
                              onFilterChange={(v) => setBnbFilter('guestName', v)}
                              sortable
                              sortDirection={bnbColumnSort('guestName')}
                              onSort={() => handleBnbSort('guestName')}
                            />
                            <FilterableHeader
                              label="Reservation"
                              filterValue={bnbFiltersSearch.reservationCode}
                              onFilterChange={(v) => setBnbFilter('reservationCode', v)}
                              sortable
                              sortDirection={bnbColumnSort('reservationCode')}
                              onSort={() => handleBnbSort('reservationCode')}
                            />
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
                      <Button colorScheme="orange" onClick={fetchBalanceData} isLoading={loading} size="sm" alignSelf="flex-end">
                        Update Profit/Loss
                      </Button>
                      <Badge colorScheme="purple" alignSelf="flex-end">{balanceData.length} records</Badge>
                    </HStack>
                  </CardBody>
                </Card>

                {/* Profit/Loss Chart and Table */}
                <HStack spacing={4} align="start">
                  <Card bg="gray.700">
                    <CardBody>
                      <ResponsiveContainer width={500} height={400}>
                        <PieChart>
                          <Pie
                            data={balanceData.map(row => ({
                              name: row.ledger || 'N/A',
                              value: Math.abs(Number(row.total_amount || 0))
                            }))}
                            cx="50%"
                            cy="50%"
                            innerRadius={80}
                            outerRadius={160}
                            paddingAngle={2}
                            dataKey="value"
                          >
                            {balanceData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                            ))}
                          </Pie>
                          <Tooltip 
                            content={({ active, payload }: any) => {
                              if (active && payload && payload.length) {
                                return (
                                  <Box bg="gray.700" p={2} border="1px solid" borderColor="gray.500" borderRadius="md">
                                    <Text color="white" fontSize="sm">{payload[0].name}</Text>
                                    <Text color="white" fontSize="sm">
                                      €{Number(payload[0].value).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                                    </Text>
                                  </Box>
                                );
                              }
                              return null;
                            }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
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