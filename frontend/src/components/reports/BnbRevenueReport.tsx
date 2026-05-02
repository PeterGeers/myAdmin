import React, { useState, useEffect, useCallback } from 'react';
import {
  Button,
  Card,
  CardBody,
  Checkbox,
  HStack,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Thead,
  Tr,
  VStack
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { FilterableHeader } from '../filters/FilterableHeader';

interface BnbRecord {
  checkinDate: string;
  checkoutDate: string;
  channel: string;
  listing: string;
  nights: number;
  amountGross: number;
  amountNett: number;
  amountChannelFee?: number;
  amountTouristTax?: number;
  amountVat?: number;
  guestName: string;
  guests: number;
  reservationCode: string;
}

const INITIAL_FILTERS: Record<string, string> = {
  channel: '',
  listing: '',
  guestName: '',
  checkinDate: '',
  checkoutDate: '',
};

const BnbRevenueReport: React.FC = () => {
  const { t } = useTypedTranslation('reports');
  const [bnbData, setBnbData] = useState<BnbRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const [bnbFilters, setBnbFilters] = useState({
    channel: 'all',
    listing: 'all',
    selectedAmounts: ['amountGross', 'amountNett']
  });

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<BnbRecord>(bnbData, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'checkinDate', direction: 'desc' },
  });

  const fetchBnbData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        channel: bnbFilters.channel,
        listing: bnbFilters.listing
      });

      const response = await authenticatedGet(buildEndpoint('/api/bnb/bnb-table', params));
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

  const exportBnbCsv = useCallback(() => {
    const csvContent = [
      ['Check-in Date', 'Check-out Date', 'Channel', 'Listing', 'Nights', 'Guests', 'Gross Amount', 'Net Amount', 'Guest Name', 'Reservation Code'],
      ...processedData.map(row => [
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

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bnb-revenue-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [processedData]);

  useEffect(() => {
    fetchBnbData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardBody>
          <HStack spacing={4} wrap="wrap">
            <Button colorScheme="orange" onClick={fetchBnbData} isLoading={loading} size="sm">
              {t('bnb.updateBnbData')}
            </Button>
            <Button variant="outline" onClick={exportBnbCsv} size="sm">
              {t('export.exportToCsv')}
            </Button>
          </HStack>

          <HStack spacing={4} wrap="wrap" mt={4}>
            <Text color="white" fontSize="sm">{t('filters.showAmounts')}:</Text>
            <Menu closeOnSelect={false}>
              <MenuButton
                as={Button}
                bg="orange.500"
                color="white"
                size="sm"
                rightIcon={<span>▼</span>}
                _hover={{ bg: "orange.600" }}
                _active={{ bg: "orange.600" }}
              >
                {bnbFilters.selectedAmounts.length > 0 ? t('bnb.amountsSelected', { count: bnbFilters.selectedAmounts.length }) : t('bnb.selectAmounts')}
              </MenuButton>
              <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
                {[
                  { key: 'amountGross', label: t('bnb.grossAmount') },
                  { key: 'amountNett', label: t('bnb.netAmount') },
                  { key: 'amountChannelFee', label: t('tables.channelFee') },
                  { key: 'amountTouristTax', label: t('tables.touristTax') },
                  { key: 'amountVat', label: t('tables.vat') }
                ].map((amount, index) => (
                  <MenuItem key={`bnb-amount-${amount.key}-${index}`} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
                    <Checkbox
                      isChecked={bnbFilters.selectedAmounts.includes(amount.key)}
                      onChange={(e) => {
                        const isChecked = e.target.checked;
                        setBnbFilters(prev => ({
                          ...prev,
                          selectedAmounts: isChecked
                            ? [...prev.selectedAmounts, amount.key]
                            : prev.selectedAmounts.filter(a => a !== amount.key)
                        }));
                      }}
                      colorScheme="orange"
                    >
                      <Text color="white" ml={2}>{amount.label}</Text>
                    </Checkbox>
                  </MenuItem>
                ))}
              </MenuList>
            </Menu>
          </HStack>
        </CardBody>
      </Card>

      <Card bg="gray.800">
        <CardBody>
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <FilterableHeader
                    label={t('tables.checkIn')}
                    filterValue={filters.checkinDate}
                    onFilterChange={(v) => setFilter('checkinDate', v)}
                    sortable
                    sortDirection={sortField === 'checkinDate' ? sortDirection : null}
                    onSort={() => handleSort('checkinDate')}
                  />
                  <FilterableHeader
                    label={t('tables.checkOut')}
                    filterValue={filters.checkoutDate}
                    onFilterChange={(v) => setFilter('checkoutDate', v)}
                    sortable
                    sortDirection={sortField === 'checkoutDate' ? sortDirection : null}
                    onSort={() => handleSort('checkoutDate')}
                  />
                  <FilterableHeader
                    label={t('filters.channel')}
                    filterValue={filters.channel}
                    onFilterChange={(v) => setFilter('channel', v)}
                    sortable
                    sortDirection={sortField === 'channel' ? sortDirection : null}
                    onSort={() => handleSort('channel')}
                  />
                  <FilterableHeader
                    label={t('filters.listing')}
                    filterValue={filters.listing}
                    onFilterChange={(v) => setFilter('listing', v)}
                    sortable
                    sortDirection={sortField === 'listing' ? sortDirection : null}
                    onSort={() => handleSort('listing')}
                  />
                  <FilterableHeader
                    label={t('tables.nights')}
                    sortable
                    sortDirection={sortField === 'nights' ? sortDirection : null}
                    onSort={() => handleSort('nights')}
                    isNumeric
                  />
                  {bnbFilters.selectedAmounts.includes('amountGross') && (
                    <FilterableHeader
                      label={t('tables.gross')}
                      sortable
                      sortDirection={sortField === 'amountGross' ? sortDirection : null}
                      onSort={() => handleSort('amountGross')}
                      isNumeric
                    />
                  )}
                  {bnbFilters.selectedAmounts.includes('amountNett') && (
                    <FilterableHeader
                      label={t('tables.net')}
                      sortable
                      sortDirection={sortField === 'amountNett' ? sortDirection : null}
                      onSort={() => handleSort('amountNett')}
                      isNumeric
                    />
                  )}
                  {bnbFilters.selectedAmounts.includes('amountChannelFee') && (
                    <FilterableHeader
                      label={t('tables.channelFee')}
                      sortable
                      sortDirection={sortField === 'amountChannelFee' ? sortDirection : null}
                      onSort={() => handleSort('amountChannelFee')}
                      isNumeric
                    />
                  )}
                  {bnbFilters.selectedAmounts.includes('amountTouristTax') && (
                    <FilterableHeader
                      label={t('tables.touristTax')}
                      sortable
                      sortDirection={sortField === 'amountTouristTax' ? sortDirection : null}
                      onSort={() => handleSort('amountTouristTax')}
                      isNumeric
                    />
                  )}
                  {bnbFilters.selectedAmounts.includes('amountVat') && (
                    <FilterableHeader
                      label={t('tables.vat')}
                      sortable
                      sortDirection={sortField === 'amountVat' ? sortDirection : null}
                      onSort={() => handleSort('amountVat')}
                      isNumeric
                    />
                  )}
                  <FilterableHeader
                    label={t('tables.guest')}
                    filterValue={filters.guestName}
                    onFilterChange={(v) => setFilter('guestName', v)}
                    sortable
                    sortDirection={sortField === 'guestName' ? sortDirection : null}
                    onSort={() => handleSort('guestName')}
                  />
                </Tr>
              </Thead>
              <Tbody>
                {processedData.map((row, index) => (
                  <Tr key={index} _hover={{ bg: 'gray.700' }}>
                    <Td color="white" fontSize="sm">{new Date(row.checkinDate).toLocaleDateString('nl-NL')}</Td>
                    <Td color="white" fontSize="sm">{new Date(row.checkoutDate).toLocaleDateString('nl-NL')}</Td>
                    <Td color="white" fontSize="sm">{row.channel}</Td>
                    <Td color="white" fontSize="sm">{row.listing}</Td>
                    <Td color="white" fontSize="sm">{row.nights}</Td>
                    {bnbFilters.selectedAmounts.includes('amountGross') && (
                      <Td color="white" fontSize="sm">€{Number(row.amountGross || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                    )}
                    {bnbFilters.selectedAmounts.includes('amountNett') && (
                      <Td color="white" fontSize="sm">€{Number(row.amountNett || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                    )}
                    {bnbFilters.selectedAmounts.includes('amountChannelFee') && (
                      <Td color="white" fontSize="sm">€{Number(row.amountChannelFee || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                    )}
                    {bnbFilters.selectedAmounts.includes('amountTouristTax') && (
                      <Td color="white" fontSize="sm">€{Number(row.amountTouristTax || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                    )}
                    {bnbFilters.selectedAmounts.includes('amountVat') && (
                      <Td color="white" fontSize="sm">€{Number(row.amountVat || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Td>
                    )}
                    <Td color="white" fontSize="sm">{row.guestName}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
          <Text color="gray.400" fontSize="xs" mt={2}>
            {t('tables.showing')} {processedData.length} {t('tables.of')} {bnbData.length} {t('tables.records')}
          </Text>
        </CardBody>
      </Card>
    </VStack>
  );
};

export default BnbRevenueReport;
