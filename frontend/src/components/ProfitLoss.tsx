/**
 * ProfitLoss Component
 *
 * Main P&L page with three tabs: Mutaties, BNB Revenue, and Profit/Loss.
 * Delegates filter panels to ProfitLossFilterPanel and chart to ProfitLossChartPanel.
 */

import React, { useState, useEffect } from 'react';
import {
  Box, VStack, Tr, Td, Table, Thead, Tbody, TableContainer,
  Card, CardBody, CardHeader, Heading,
  Tabs, TabList, TabPanels, Tab, TabPanel,
} from '@chakra-ui/react';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { FilterableHeader } from './filters/FilterableHeader';
import { MutatiesFilterPanel, BnbFilterPanel, BalanceFilterPanel } from './ProfitLossFilterPanel';
import { ProfitLossChartPanel, BalanceRecord } from './ProfitLossChartPanel';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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

const MUTATIES_INITIAL_FILTERS: Record<string, string> = {
  TransactionDescription: '', Reknum: '', AccountName: '', Administration: '', ReferenceNumber: '',
};

const BNB_INITIAL_FILTERS: Record<string, string> = {
  channel: '', listing: '', guestName: '', reservationCode: '',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ProfitLoss: React.FC = () => {
  const [mutatiesData, setMutatiesData] = useState<MutatiesRecord[]>([]);
  const [bnbData, setBnbData] = useState<BnbRecord[]>([]);
  const [balanceData, setBalanceData] = useState<BalanceRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const {
    filters: mutatiesFiltersSearch, setFilter: setMutatiesFilter,
    handleSort: handleMutatiesSort, sortField: mutatiesSortField,
    sortDirection: mutatiesSortDirection, processedData: filteredMutatiesData,
  } = useFilterableTable<MutatiesRecord>(mutatiesData, { initialFilters: MUTATIES_INITIAL_FILTERS });

  const {
    filters: bnbFiltersSearch, setFilter: setBnbFilter,
    handleSort: handleBnbSort, sortField: bnbSortField,
    sortDirection: bnbSortDirection, processedData: filteredBnbData,
  } = useFilterableTable<BnbRecord>(bnbData, { initialFilters: BNB_INITIAL_FILTERS });

  const [mutatiesFilters, setMutatiesFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    administration: 'all', profitLoss: 'all',
  });

  const [bnbFilters, setBnbFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    channel: 'all', listing: 'all',
  });

  const [balanceFilters, setBalanceFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    administration: 'all', profitLoss: 'all',
  });

  // ---------------------------------------------------------------------------
  // API handlers
  // ---------------------------------------------------------------------------

  const fetchMutatiesData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams(mutatiesFilters);
      const response = await fetch(`http://localhost:5000/api/reports/mutaties-table?${params}`);
      const data = await response.json();
      if (data.success) setMutatiesData(data.data);
    } catch (err) {
      console.error('Error fetching mutaties data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchBalanceData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams(balanceFilters);
      const response = await fetch(`http://localhost:5000/api/reports/balance-data?${params}`);
      const data = await response.json();
      if (data.success) {
        setBalanceData(data.data.filter((row: BalanceRecord) => Math.abs(Number(row.total_amount || 0)) > 0.01));
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
      const params = new URLSearchParams(bnbFilters);
      const response = await fetch(`http://localhost:5000/api/bnb/bnb-table?${params}`);
      const data = await response.json();
      if (data.success) setBnbData(data.data);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------------------------------------------------------------------------
  // CSV export
  // ---------------------------------------------------------------------------

  const exportMutatiesCsv = () => {
    const csvContent = [
      ['Date', 'Reference', 'Description', 'Amount', 'Debet', 'Credit', 'Administration'],
      ...mutatiesData.map(row => [row.TransactionDate, row.ReferenceNumber, row.TransactionDescription, row.Amount, row.Reknum, row.AccountName, row.Administration]),
    ].map(row => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `mutaties-${mutatiesFilters.dateFrom}-${mutatiesFilters.dateTo}.csv`;
    a.click();
  };

  const exportBnbCsv = () => {
    const csvContent = [
      ['Check-in Date', 'Check-out Date', 'Channel', 'Listing', 'Nights', 'Guests', 'Gross Amount', 'Net Amount', 'Guest Name', 'Reservation Code'],
      ...bnbData.map(row => [row.checkinDate, row.checkoutDate, row.channel, row.listing, row.nights, row.guests, row.amountGross, row.amountNett, row.guestName, row.reservationCode]),
    ].map(row => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `bnb-${bnbFilters.dateFrom}-${bnbFilters.dateTo}.csv`;
    a.click();
  };

  // ---------------------------------------------------------------------------
  // Sort helpers
  // ---------------------------------------------------------------------------

  const mutatiesColumnSort = (field: string): 'asc' | 'desc' | null => mutatiesSortField === field ? mutatiesSortDirection : null;
  const bnbColumnSort = (field: string): 'asc' | 'desc' | null => bnbSortField === field ? bnbSortDirection : null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Box p={6} bg="gray.800" minH="100vh">
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
                <MutatiesFilterPanel
                  filters={mutatiesFilters} setFilters={setMutatiesFilters}
                  onFetch={fetchMutatiesData} onExport={exportMutatiesCsv}
                  loading={loading} filteredCount={filteredMutatiesData.length} totalCount={mutatiesData.length}
                />
                <Card bg="gray.700">
                  <CardHeader><Heading size="md" color="white">Mutaties Data</Heading></CardHeader>
                  <CardBody>
                    <TableContainer maxH="500px" overflowY="auto">
                      <Table size="sm" variant="simple">
                        <Thead position="sticky" top={0} bg="gray.600">
                          <Tr>
                            <FilterableHeader label="Date" sortable sortDirection={mutatiesColumnSort('TransactionDate')} onSort={() => handleMutatiesSort('TransactionDate')} />
                            <FilterableHeader label="Reference" filterValue={mutatiesFiltersSearch.ReferenceNumber} onFilterChange={(v) => setMutatiesFilter('ReferenceNumber', v)} sortable sortDirection={mutatiesColumnSort('ReferenceNumber')} onSort={() => handleMutatiesSort('ReferenceNumber')} />
                            <FilterableHeader label="Description" filterValue={mutatiesFiltersSearch.TransactionDescription} onFilterChange={(v) => setMutatiesFilter('TransactionDescription', v)} sortable sortDirection={mutatiesColumnSort('TransactionDescription')} onSort={() => handleMutatiesSort('TransactionDescription')} />
                            <FilterableHeader label="Amount" isNumeric sortable sortDirection={mutatiesColumnSort('Amount')} onSort={() => handleMutatiesSort('Amount')} />
                            <FilterableHeader label="Account" filterValue={mutatiesFiltersSearch.Reknum} onFilterChange={(v) => setMutatiesFilter('Reknum', v)} sortable sortDirection={mutatiesColumnSort('Reknum')} onSort={() => handleMutatiesSort('Reknum')} />
                            <FilterableHeader label="Account Name" filterValue={mutatiesFiltersSearch.AccountName} onFilterChange={(v) => setMutatiesFilter('AccountName', v)} sortable sortDirection={mutatiesColumnSort('AccountName')} onSort={() => handleMutatiesSort('AccountName')} />
                            <FilterableHeader label="Administration" filterValue={mutatiesFiltersSearch.Administration} onFilterChange={(v) => setMutatiesFilter('Administration', v)} sortable sortDirection={mutatiesColumnSort('Administration')} onSort={() => handleMutatiesSort('Administration')} />
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
                <BnbFilterPanel
                  filters={bnbFilters} setFilters={setBnbFilters}
                  onFetch={fetchBnbData} onExport={exportBnbCsv}
                  loading={loading} filteredCount={filteredBnbData.length} totalCount={bnbData.length}
                />
                <Card bg="gray.700">
                  <CardHeader><Heading size="md" color="white">BNB Revenue Data</Heading></CardHeader>
                  <CardBody>
                    <TableContainer maxH="500px" overflowY="auto">
                      <Table size="sm" variant="simple">
                        <Thead position="sticky" top={0} bg="gray.600">
                          <Tr>
                            <FilterableHeader label="Check-in" sortable sortDirection={bnbColumnSort('checkinDate')} onSort={() => handleBnbSort('checkinDate')} />
                            <FilterableHeader label="Check-out" sortable sortDirection={bnbColumnSort('checkoutDate')} onSort={() => handleBnbSort('checkoutDate')} />
                            <FilterableHeader label="Channel" filterValue={bnbFiltersSearch.channel} onFilterChange={(v) => setBnbFilter('channel', v)} sortable sortDirection={bnbColumnSort('channel')} onSort={() => handleBnbSort('channel')} />
                            <FilterableHeader label="Listing" filterValue={bnbFiltersSearch.listing} onFilterChange={(v) => setBnbFilter('listing', v)} sortable sortDirection={bnbColumnSort('listing')} onSort={() => handleBnbSort('listing')} />
                            <FilterableHeader label="Nights" isNumeric sortable sortDirection={bnbColumnSort('nights')} onSort={() => handleBnbSort('nights')} />
                            <FilterableHeader label="Guests" isNumeric sortable sortDirection={bnbColumnSort('guests')} onSort={() => handleBnbSort('guests')} />
                            <FilterableHeader label="Gross" isNumeric sortable sortDirection={bnbColumnSort('amountGross')} onSort={() => handleBnbSort('amountGross')} />
                            <FilterableHeader label="Net" isNumeric sortable sortDirection={bnbColumnSort('amountNett')} onSort={() => handleBnbSort('amountNett')} />
                            <FilterableHeader label="Guest" filterValue={bnbFiltersSearch.guestName} onFilterChange={(v) => setBnbFilter('guestName', v)} sortable sortDirection={bnbColumnSort('guestName')} onSort={() => handleBnbSort('guestName')} />
                            <FilterableHeader label="Reservation" filterValue={bnbFiltersSearch.reservationCode} onFilterChange={(v) => setBnbFilter('reservationCode', v)} sortable sortDirection={bnbColumnSort('reservationCode')} onSort={() => handleBnbSort('reservationCode')} />
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
                <BalanceFilterPanel
                  filters={balanceFilters} setFilters={setBalanceFilters}
                  onFetch={fetchBalanceData} loading={loading} recordCount={balanceData.length}
                />
                <ProfitLossChartPanel balanceData={balanceData} />
              </VStack>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
};

export default ProfitLoss;
