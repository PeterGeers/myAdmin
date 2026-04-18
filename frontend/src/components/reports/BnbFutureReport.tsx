import React, { useState, useMemo } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
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
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { FilterPanel } from '../filters/FilterPanel';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { FilterConfig } from '../filters/types';

interface BnbFutureRecord {
  date: string;
  channel: string;
  listing: string;
  amount: number;
  items: number;
}

const INITIAL_TABLE_FILTERS: Record<string, string> = {
  date: '',
  channel: '',
  listing: '',
  amount: '',
  items: '',
};

const BnbFutureReport: React.FC = () => {
  const { t } = useTypedTranslation('reports');
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
      const response = await authenticatedGet(buildEndpoint('/api/str/future-trend'));
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

  // Get unique values for dropdown filters
  const uniqueYears = useMemo(() =>
    Array.from(new Set(bnbFutureData.map(row => new Date(row.date).getFullYear())))
      .sort((a, b) => a - b)
      .map(String),
    [bnbFutureData]
  );

  const uniqueChannels = useMemo(() =>
    Array.from(new Set(bnbFutureData.map(row => row.channel))).sort(),
    [bnbFutureData]
  );

  const uniqueListings = useMemo(() =>
    Array.from(new Set(bnbFutureData.map(row => row.listing))).sort(),
    [bnbFutureData]
  );

  // Apply dropdown filters (server-side style: channel, listing, year range)
  const dropdownFilteredData = useMemo(() =>
    bnbFutureData.filter(row => {
      const rowYear = new Date(row.date).getFullYear();
      const yearFromMatch = bnbFutureFilters.yearFrom === 'all' || rowYear >= parseInt(bnbFutureFilters.yearFrom);
      const yearToMatch = bnbFutureFilters.yearTo === 'all' || rowYear <= parseInt(bnbFutureFilters.yearTo);
      return (
        yearFromMatch && yearToMatch &&
        (bnbFutureFilters.channel === 'all' || row.channel === bnbFutureFilters.channel) &&
        (bnbFutureFilters.listing === 'all' || row.listing === bnbFutureFilters.listing)
      );
    }),
    [bnbFutureData, bnbFutureFilters]
  );

  // Column text filters + sort via framework hook (operates on dropdown-filtered data)
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<BnbFutureRecord>(dropdownFilteredData, {
    initialFilters: INITIAL_TABLE_FILTERS,
    defaultSort: { field: 'date', direction: 'asc' },
  });

  // Prepare chart data - group by date and listing (uses dropdown-filtered data for chart)
  const chartData = useMemo(() => {
    const grouped = dropdownFilteredData.reduce((acc, row) => {
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
  }, [dropdownFilteredData]);

  // Get unique listings for chart areas (from dropdown-filtered data)
  const chartListings = useMemo(() =>
    Array.from(new Set(dropdownFilteredData.map(row => row.listing))).sort(),
    [dropdownFilteredData]
  );

  // FilterPanel configuration for dropdown filters
  const panelFilters: FilterConfig<string>[] = [
    {
      type: 'single',
      label: t('bnb.yearFrom'),
      options: ['all', ...uniqueYears],
      value: bnbFutureFilters.yearFrom,
      onChange: (v) => setBnbFutureFilters(prev => ({ ...prev, yearFrom: v as string })),
      getOptionLabel: (opt) => opt === 'all' ? t('bnb.allYears') : opt,
      size: 'sm',
    },
    {
      type: 'single',
      label: t('bnb.yearTo'),
      options: ['all', ...uniqueYears],
      value: bnbFutureFilters.yearTo,
      onChange: (v) => setBnbFutureFilters(prev => ({ ...prev, yearTo: v as string })),
      getOptionLabel: (opt) => opt === 'all' ? t('bnb.allYears') : opt,
      size: 'sm',
    },
    {
      type: 'single',
      label: t('filters.channel'),
      options: ['all', ...uniqueChannels],
      value: bnbFutureFilters.channel,
      onChange: (v) => setBnbFutureFilters(prev => ({ ...prev, channel: v as string })),
      getOptionLabel: (opt) => opt === 'all' ? t('filters.allChannels') : opt,
      size: 'sm',
    },
    {
      type: 'single',
      label: t('filters.listing'),
      options: ['all', ...uniqueListings],
      value: bnbFutureFilters.listing,
      onChange: (v) => setBnbFutureFilters(prev => ({ ...prev, listing: v as string })),
      getOptionLabel: (opt) => opt === 'all' ? t('filters.allListings') : opt,
      size: 'sm',
    },
  ];

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardBody>
          <HStack spacing={4} wrap="wrap" align="flex-end">
            <FilterPanel
              filters={panelFilters}
              layout="horizontal"
              size="sm"
            />
            <Button
              colorScheme="orange"
              onClick={fetchBnbFutureData}
              isLoading={bnbFutureLoading}
              size="sm"
            >
              {t('actions.refreshData')}
            </Button>
          </HStack>
        </CardBody>
      </Card>

      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">{t('bnb.futureRevenueProjections')}</Heading>
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
                  tick={{ fill: 'white' }}
                  tickFormatter={(value) => new Date(value).toLocaleDateString('nl-NL', { month: 'short', year: 'numeric' })}
                />
                <YAxis tick={{ fill: 'white' }} />
                <Tooltip
                  formatter={(value) => [`€${Number(value).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`]}
                  labelFormatter={(label) => new Date(label).toLocaleDateString('nl-NL')}
                />
                <Legend wrapperStyle={{ color: 'white' }} />
                {chartListings.map((listing, index) => (
                  <Area
                    key={listing}
                    type="monotone"
                    dataKey={listing}
                    stackId="1"
                    stroke={`hsl(${index * (360 / chartListings.length)}, 70%, 60%)`}
                    fill={`hsl(${index * (360 / chartListings.length)}, 70%, 60%)`}
                    name={listing}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <Text color="white" textAlign="center" py={8}>
              {t('bnb.noFutureData')}
            </Text>
          )}
        </CardBody>
      </Card>

      {bnbFutureData.length > 0 && (
        <Card bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">{t('bnb.detailedProjections')}</Heading>
          </CardHeader>
          <CardBody>
            <TableContainer>
              <Table size="sm" variant="simple">
                <Thead>
                  <Tr>
                    <FilterableHeader
                      label={t('tables.date')}
                      filterValue={filters.date}
                      onFilterChange={(v) => setFilter('date', v)}
                      sortable
                      sortDirection={columnSortDirection('date')}
                      onSort={() => handleSort('date')}
                    />
                    <FilterableHeader
                      label={t('filters.channel')}
                      filterValue={filters.channel}
                      onFilterChange={(v) => setFilter('channel', v)}
                      sortable
                      sortDirection={columnSortDirection('channel')}
                      onSort={() => handleSort('channel')}
                    />
                    <FilterableHeader
                      label={t('filters.listing')}
                      filterValue={filters.listing}
                      onFilterChange={(v) => setFilter('listing', v)}
                      sortable
                      sortDirection={columnSortDirection('listing')}
                      onSort={() => handleSort('listing')}
                    />
                    <FilterableHeader
                      label={t('tables.amount')}
                      filterValue={filters.amount}
                      onFilterChange={(v) => setFilter('amount', v)}
                      sortable
                      sortDirection={columnSortDirection('amount')}
                      onSort={() => handleSort('amount')}
                      isNumeric
                    />
                    <FilterableHeader
                      label={t('bnb.items')}
                      filterValue={filters.items}
                      onFilterChange={(v) => setFilter('items', v)}
                      sortable
                      sortDirection={columnSortDirection('items')}
                      onSort={() => handleSort('items')}
                      isNumeric
                    />
                  </Tr>
                </Thead>
                <Tbody>
                  {processedData.map((row, index) => (
                    <Tr key={index}>
                      <Td color="white" fontSize="sm">
                        {new Date(row.date).toLocaleDateString('nl-NL')}
                      </Td>
                      <Td color="white" fontSize="sm">{row.channel}</Td>
                      <Td color="white" fontSize="sm">{row.listing}</Td>
                      <Td color="white" fontSize="sm" isNumeric>
                        €{Number(row.amount || 0).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
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
