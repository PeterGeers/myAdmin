import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Button,
  Card,
  CardBody,
  Checkbox,
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
import { authenticatedGet, buildEndpoint } from '../../services/apiService';

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

const BnbRevenueReport: React.FC = () => {
  const [bnbData, setBnbData] = useState<BnbRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [bnbSortField, setBnbSortField] = useState<string>('');
  const [bnbSortDirection, setBnbSortDirection] = useState<'asc' | 'desc'>('desc');
  const [bnbSearchFilters, setBnbSearchFilters] = useState({
    channel: '',
    listing: '',
    guestName: '',
    reservationCode: ''
  });
  
  const [bnbFilters, setBnbFilters] = useState({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    channel: 'all',
    listing: 'all',
    selectedAmounts: ['amountGross', 'amountNett']
  });

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
      } else if (field === 'nights' || field === 'guests' || field === 'amountGross' || field === 'amountNett' || field === 'amountChannelFee' || field === 'amountTouristTax' || field === 'amountVat') {
        aVal = Number(aVal) || 0;
        bVal = Number(bVal) || 0;
      }
      
      const safeAVal = aVal ?? '';
      const safeBVal = bVal ?? '';
      
      if (safeAVal < safeBVal) return newDirection === 'asc' ? -1 : 1;
      if (safeAVal > safeBVal) return newDirection === 'asc' ? 1 : -1;
      return 0;
    });
    
    setBnbData(sortedData);
  };

  const filteredBnbData = useMemo(() => {
    return bnbData.filter(row => {
      return Object.entries(bnbSearchFilters).every(([key, value]) => {
        if (!value) return true;
        const fieldValue = row[key as keyof BnbRecord]?.toString().toLowerCase() || '';
        return fieldValue.includes(value.toLowerCase());
      });
    });
  }, [bnbData, bnbSearchFilters]);

  const fetchBnbData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        dateFrom: bnbFilters.dateFrom,
        dateTo: bnbFilters.dateTo,
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
      ...filteredBnbData.map(row => [
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
    a.download = `bnb-${bnbFilters.dateFrom}-${bnbFilters.dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filteredBnbData, bnbFilters.dateFrom, bnbFilters.dateTo]);

  useEffect(() => {
    fetchBnbData();
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
          
          <HStack spacing={4} wrap="wrap" mt={4}>
            <Text color="white" fontSize="sm">Show Amounts:</Text>
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
                {bnbFilters.selectedAmounts.length > 0 ? `${bnbFilters.selectedAmounts.length} selected` : 'Select amounts...'}
              </MenuButton>
              <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
                {[
                  { key: 'amountGross', label: 'Gross Amount' },
                  { key: 'amountNett', label: 'Net Amount' },
                  { key: 'amountChannelFee', label: 'Channel Fee' },
                  { key: 'amountTouristTax', label: 'Tourist Tax' },
                  { key: 'amountVat', label: 'VAT Amount' }
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
                  {bnbFilters.selectedAmounts.includes('amountGross') && (
                    <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountGross')}>
                      Gross {bnbSortField === 'amountGross' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                    </Th>
                  )}
                  {bnbFilters.selectedAmounts.includes('amountNett') && (
                    <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountNett')}>
                      Net {bnbSortField === 'amountNett' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                    </Th>
                  )}
                  {bnbFilters.selectedAmounts.includes('amountChannelFee') && (
                    <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountChannelFee')}>
                      Channel Fee {bnbSortField === 'amountChannelFee' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                    </Th>
                  )}
                  {bnbFilters.selectedAmounts.includes('amountTouristTax') && (
                    <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountTouristTax')}>
                      Tourist Tax {bnbSortField === 'amountTouristTax' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                    </Th>
                  )}
                  {bnbFilters.selectedAmounts.includes('amountVat') && (
                    <Th color="white" cursor="pointer" onClick={() => handleBnbSort('amountVat')}>
                      VAT {bnbSortField === 'amountVat' && (bnbSortDirection === 'asc' ? '↑' : '↓')}
                    </Th>
                  )}
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
        </CardBody>
      </Card>
    </VStack>
  );
};

export default BnbRevenueReport;
