import React, { useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  Select,
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
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import { buildApiUrl } from '../../config';
import { authenticatedGet } from '../../services/apiService';

interface BnbFutureRecord {
  date: string;
  channel: string;
  listing: string;
  amount: number;
  items: number;
}

const BnbFutureReport: React.FC = () => {
  const [bnbFutureData, setBnbFutureData] = useState<BnbFutureRecord[]>([]);
  const [bnbFutureLoading, setBnbFutureLoading] = useState(false);
  const [bnbFutureFilters, setBnbFutureFilters] = useState({
    channel: 'all',
    listing: 'all',
    yearFrom: 'all',
    yearTo: 'all',
  });

  const fetchBnbFutureData = async () => {
    setBnbFutureLoading(true);
    try {
      const response = await authenticatedGet(buildApiUrl('/api/str/future-trend'));
      const data = await response.json();
      
      if (data.success) {
        setBnbFutureData(data.data);
      }
    } catch (err) {
      console.error('Error fetching BNB future data:', err);
    } finally {
      setBnbFutureLoading(false);
    }
  };

  // Filter data based on current filters
  const filteredData = bnbFutureData.filter(row => {
    const rowYear = new Date(row.date).getFullYear();
    const yearFromMatch = bnbFutureFilters.yearFrom === 'all' || rowYear >= parseInt(bnbFutureFilters.yearFrom);
    const yearToMatch = bnbFutureFilters.yearTo === 'all' || rowYear <= parseInt(bnbFutureFilters.yearTo);
    return (
      yearFromMatch && yearToMatch &&
      (bnbFutureFilters.channel === 'all' || row.channel === bnbFutureFilters.channel) &&
      (bnbFutureFilters.listing === 'all' || row.listing === bnbFutureFilters.listing)
    );
  });

  // Prepare chart data - group by date and listing
  const chartData = (() => {
    const grouped = filteredData.reduce((acc, row) => {
      if (!acc[row.date]) {
        acc[row.date] = { date: row.date };
      }
      if (!acc[row.date][row.listing]) {
        acc[row.date][row.listing] = 0;
      }
      acc[row.date][row.listing] += row.amount || 0;
      return acc;
    }, {} as any);
    return Object.values(grouped).sort((a: any, b: any) => 
      new Date(a.date).getTime() - new Date(b.date).getTime()
    );
  })();

  // Get unique listings for chart areas
  const uniqueListings = Array.from(new Set(filteredData.map(row => row.listing))).sort();

  // Get unique years for filters
  const uniqueYears = Array.from(new Set(bnbFutureData.map(row => new Date(row.date).getFullYear()))).sort((a, b) => a - b);

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardBody>
          <HStack spacing={4} wrap="wrap">
            <VStack spacing={1}>
              <Text color="white" fontSize="sm">Year From</Text>
              <Select
                value={bnbFutureFilters.yearFrom}
                onChange={(e) => setBnbFutureFilters(prev => ({...prev, yearFrom: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
                w="150px"
              >
                <option value="all">All Years</option>
                {uniqueYears.map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </Select>
            </VStack>
            <VStack spacing={1}>
              <Text color="white" fontSize="sm">Year To</Text>
              <Select
                value={bnbFutureFilters.yearTo}
                onChange={(e) => setBnbFutureFilters(prev => ({...prev, yearTo: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
                w="150px"
              >
                <option value="all">All Years</option>
                {uniqueYears.map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </Select>
            </VStack>
            <VStack spacing={1}>
              <Text color="white" fontSize="sm">Channel</Text>
              <Select
                value={bnbFutureFilters.channel}
                onChange={(e) => setBnbFutureFilters(prev => ({...prev, channel: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
                w="150px"
              >
                <option value="all">All Channels</option>
                {Array.from(new Set(bnbFutureData.map(row => row.channel))).sort().map(channel => (
                  <option key={channel} value={channel}>{channel}</option>
                ))}
              </Select>
            </VStack>
            <VStack spacing={1}>
              <Text color="white" fontSize="sm">Listing</Text>
              <Select
                value={bnbFutureFilters.listing}
                onChange={(e) => setBnbFutureFilters(prev => ({...prev, listing: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
                w="200px"
              >
                <option value="all">All Listings</option>
                {Array.from(new Set(bnbFutureData.map(row => row.listing))).sort().map(listing => (
                  <option key={listing} value={listing}>{listing}</option>
                ))}
              </Select>
            </VStack>
            <Button 
              colorScheme="orange" 
              onClick={fetchBnbFutureData} 
              isLoading={bnbFutureLoading}
              size="sm"
            >
              Refresh Data
            </Button>
          </HStack>
        </CardBody>
      </Card>

      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">BNB Future Revenue Projections by Listing</Heading>
        </CardHeader>
        <CardBody>
          {bnbFutureData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <AreaChart
                data={chartData}
                margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="date" 
                  tick={{fill: 'white'}} 
                  tickFormatter={(value) => new Date(value).toLocaleDateString('nl-NL', { month: 'short', year: 'numeric' })}
                />
                <YAxis tick={{fill: 'white'}} />
                <Tooltip 
                  formatter={(value) => [`€${Number(value).toLocaleString('nl-NL', {minimumFractionDigits: 2})}`]}
                  labelFormatter={(label) => new Date(label).toLocaleDateString('nl-NL')}
                />
                <Legend wrapperStyle={{color: 'white'}} />
                {uniqueListings.map((listing, index) => (
                  <Area
                    key={listing}
                    type="monotone"
                    dataKey={listing}
                    stackId="1"
                    stroke={`hsl(${index * (360 / uniqueListings.length)}, 70%, 60%)`}
                    fill={`hsl(${index * (360 / uniqueListings.length)}, 70%, 60%)`}
                    name={listing}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <Text color="white" textAlign="center" py={8}>
              No future revenue data available. Click "Refresh Data" to load projections.
            </Text>
          )}
        </CardBody>
      </Card>

      {bnbFutureData.length > 0 && (
        <Card bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">Detailed Projections</Heading>
          </CardHeader>
          <CardBody>
            <TableContainer>
              <Table size="sm" variant="simple">
                <Thead>
                  <Tr>
                    <Th color="white">Date</Th>
                    <Th color="white">Channel</Th>
                    <Th color="white">Listing</Th>
                    <Th color="white" isNumeric>Amount</Th>
                    <Th color="white" isNumeric>Items</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {filteredData.map((row, index) => (
                    <Tr key={index}>
                      <Td color="white" fontSize="sm">
                        {new Date(row.date).toLocaleDateString('nl-NL')}
                      </Td>
                      <Td color="white" fontSize="sm">{row.channel}</Td>
                      <Td color="white" fontSize="sm">{row.listing}</Td>
                      <Td color="white" fontSize="sm" isNumeric>
                        €{Number(row.amount || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                      </Td>
                      <Td color="white" fontSize="sm" isNumeric>{row.items}</Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </TableContainer>
          </CardBody>
        </Card>
      )}
    </VStack>
  );
};

export default BnbFutureReport;
