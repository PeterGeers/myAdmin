import React, { useState, useEffect, useMemo } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  HStack,
  Heading,
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
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { FilterPanel } from '../filters/FilterPanel';
import BnbYearMonthMatrix from './BnbYearMonthMatrix';
import BnbActualsCharts from './BnbActualsCharts';

interface BnbFilterOptions {
  years: string[];
  listings: string[];
  channels: string[];
}

/** Amount totals for a BNB period/listing/channel combination. */
export interface BnbAmounts {
  amountGross: number;
  amountNett: number;
  amountChannelFee: number;
  amountTouristTax: number;
  amountVat: number;
}

/** A row of BNB data from the API. */
export interface BnbDataRow {
  year?: string | number;
  quarter?: string | number;
  month?: string | number;
  listing?: string;
  channel?: string;
  amountGross?: number;
  amountNett?: number;
  amountChannelFee?: number;
  amountTouristTax?: number;
  amountVat?: number;
  [key: string]: unknown;
}

/** Nested period data structure: header → amounts */
type MonthData = Record<string, BnbAmounts>;
/** Quarter data: month → MonthData */
type QuarterData = Record<string, MonthData>;
/** Year data: quarter → QuarterData */
type YearData = Record<string, QuarterData>;
/** Full period structure: year → YearData */
type PeriodData = Record<string, YearData>;

const BnbActualsReport: React.FC = () => {
  const { t } = useTypedTranslation('reports');
  const [loading, setLoading] = useState(false);
  
  // Simplified state - using arrays for multi-select
  const [selectedYears, setSelectedYears] = useState<string[]>([new Date().getFullYear().toString()]);
  const [selectedListings, setSelectedListings] = useState<string[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const period = 'year'; // Fixed period value for API calls
  const [displayFormat, setDisplayFormat] = useState<string>('2dec');
  const [viewType, setViewType] = useState<'listing' | 'channel'>('listing');
  const [selectedAmounts, setSelectedAmounts] = useState<string[]>(['amountGross', 'amountNett']);
  
  const [bnbAvailableYears, setBnbAvailableYears] = useState<string[]>([]);
  const [bnbFilterOptions, setBnbFilterOptions] = useState<BnbFilterOptions>({
    years: [],
    listings: [],
    channels: []
  });
  const [bnbListingData, setBnbListingData] = useState<BnbDataRow[]>([]);
  const [bnbChannelData, setBnbChannelData] = useState<BnbDataRow[]>([]);
  const [expandedYears, setExpandedYears] = useState<Set<string>>(new Set());
  const [expandedQuarters, setExpandedQuarters] = useState<Set<string>>(new Set());

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

  // Render expandable BNB data with Listing/Channel as columns (X-axis) and Period as rows (Y-axis)
  const renderExpandableBnbData = (
    data: BnbDataRow[], 
    viewType: 'listing' | 'channel', 
    displayFormat: string, 
    selectedAmounts: string[] = ['amountGross']
  ) => {
    const groupField = viewType === 'listing' ? 'listing' : 'channel';
    
    // Extract unique headers from actual data instead of using filter options
    const headers = Array.from(new Set(data.map(row => row[groupField]))).sort();
    
    // Group data by period first, then by listing/channel
    const periodData = data.reduce((acc, row) => {
      const year = row.year;
      const quarter = row.q || 1;
      const month = row.m || 1;
      
      if (!acc[year]) acc[year] = {};
      
      // Initialize all quarters for this year
      for (let q = 1; q <= 4; q++) {
        if (!acc[year][q]) acc[year][q] = {};
        for (let m = 1; m <= 12; m++) {
          if (!acc[year][q][m]) acc[year][q][m] = {};
        }
      }
      
      if (!acc[year][quarter][month][row[groupField]]) {
        acc[year][quarter][month][row[groupField]] = {
          amountGross: 0, amountNett: 0, amountChannelFee: 0, amountTouristTax: 0, amountVat: 0
        };
      }
      
      acc[year][quarter][month][row[groupField]].amountGross += Number(row.amountGross) || 0;
      acc[year][quarter][month][row[groupField]].amountNett += Number(row.amountNett) || 0;
      acc[year][quarter][month][row[groupField]].amountChannelFee += Number(row.amountChannelFee) || 0;
      acc[year][quarter][month][row[groupField]].amountTouristTax += Number(row.amountTouristTax) || 0;
      acc[year][quarter][month][row[groupField]].amountVat += Number(row.amountVat) || 0;
      
      return acc;
    }, {} as PeriodData);

    const rows: React.ReactElement[] = [];
    
    Object.entries(periodData).sort(([a], [b]) => parseInt(a) - parseInt(b)).forEach(([year, quarterData]: [string, YearData]) => {
      const yearKey = year;
      const isYearExpanded = expandedYears.has(yearKey);
      
      // Calculate year totals for each listing/channel
      const yearTotals: Record<string, BnbAmounts> = {};
      headers.forEach(header => {
        yearTotals[header] = { amountGross: 0, amountNett: 0, amountChannelFee: 0, amountTouristTax: 0, amountVat: 0 };
      });
      
      Object.values(quarterData).forEach((qData: QuarterData) => {
        Object.values(qData).forEach((mData: MonthData) => {
          Object.entries(mData).forEach(([header, amounts]: [string, BnbAmounts]) => {
            if (yearTotals[header]) {
              yearTotals[header].amountGross += amounts.amountGross;
              yearTotals[header].amountNett += amounts.amountNett;
              yearTotals[header].amountChannelFee += amounts.amountChannelFee;
              yearTotals[header].amountTouristTax += amounts.amountTouristTax;
              yearTotals[header].amountVat += amounts.amountVat;
            }
          });
        });
      });
      
      // Year row
      rows.push(
        <Tr key={yearKey} bg="gray.600">
          <Td color="white" fontSize="sm" w="120px">
            <HStack>
              <Button
                size="xs"
                variant="ghost"
                color="white"
                onClick={() => {
                  const newExpanded = new Set(expandedYears);
                  if (isYearExpanded) {
                    newExpanded.delete(yearKey);
                  } else {
                    newExpanded.add(yearKey);
                  }
                  setExpandedYears(newExpanded);
                }}
              >
                {isYearExpanded ? '−' : '+'}
              </Button>
              <Text>{year}</Text>
            </HStack>
          </Td>
          {headers.flatMap(header => 
            selectedAmounts.map(amount => (
              <Td key={`${header}-${amount}`} color="white" fontSize="sm" w="60px" textAlign="right">
                {formatAmount(yearTotals[header]?.[amount] || 0, displayFormat)}
              </Td>
            ))
          )}
          {selectedAmounts.map(amount => (
            <Td key={`year-total-${amount}`} color="white" fontSize="sm" w="80px" textAlign="right" fontWeight="bold">
              {formatAmount(
                headers.reduce((sum, header) => sum + (yearTotals[header]?.[amount] || 0), 0),
                displayFormat
              )}
            </Td>
          ))}
        </Tr>
      );
      
      // Quarter rows (if year expanded) - ensure all quarters 1-4 are shown
      if (isYearExpanded) {
        [1, 2, 3, 4].forEach(quarterNum => {
          const quarter = quarterNum.toString();
          const monthData = quarterData[quarter] || {};
          const quarterKey = `${yearKey}-Q${quarter}`;
          const isQuarterExpanded = expandedQuarters.has(quarterKey);
          
          // Calculate quarter totals - ensure all headers are included
          const quarterTotals: Record<string, BnbAmounts> = {};
          headers.forEach(header => {
            quarterTotals[header as string] = { amountGross: 0, amountNett: 0, amountChannelFee: 0, amountTouristTax: 0, amountVat: 0 };
          });
          
          // Sum all months in this quarter for each header
          Object.values(monthData).forEach((mData: MonthData) => {
            headers.forEach(header => {
              if (mData[header]) {
                quarterTotals[header].amountGross += mData[header].amountGross || 0;
                quarterTotals[header].amountNett += mData[header].amountNett || 0;
                quarterTotals[header].amountChannelFee += mData[header].amountChannelFee || 0;
                quarterTotals[header].amountTouristTax += mData[header].amountTouristTax || 0;
                quarterTotals[header].amountVat += mData[header].amountVat || 0;
              }
            });
          });
          
          // Quarter row
          rows.push(
            <Tr key={quarterKey}>
              <Td color="white" fontSize="sm" w="120px" pl={8}>
                <HStack>
                  <Button
                    size="xs"
                    variant="ghost"
                    color="white"
                    onClick={() => {
                      const newExpanded = new Set(expandedQuarters);
                      if (isQuarterExpanded) {
                        newExpanded.delete(quarterKey);
                      } else {
                        newExpanded.add(quarterKey);
                      }
                      setExpandedQuarters(newExpanded);
                    }}
                  >
                    {isQuarterExpanded ? '−' : '+'}
                  </Button>
                  <Text>Q{quarter}</Text>
                </HStack>
              </Td>
              {headers.flatMap(header => 
                selectedAmounts.map(amount => (
                  <Td key={`${header}-${amount}`} color="white" fontSize="sm" w="60px" textAlign="right">
                    {formatAmount(quarterTotals[header]?.[amount] || 0, displayFormat)}
                  </Td>
                ))
              )}
              {selectedAmounts.map(amount => (
                <Td key={`quarter-total-${amount}`} color="white" fontSize="sm" w="80px" textAlign="right">
                  {formatAmount(
                    headers.reduce((sum, header) => sum + (quarterTotals[header]?.[amount] || 0), 0),
                    displayFormat
                  )}
                </Td>
              ))}
            </Tr>
          );
          
          // Month rows (if quarter expanded) - only show months for this quarter
          if (isQuarterExpanded) {
            const quarterMonths = {
              '1': [1, 2, 3],
              '2': [4, 5, 6], 
              '3': [7, 8, 9],
              '4': [10, 11, 12]
            };
            const monthsInQuarter = quarterMonths[quarter as keyof typeof quarterMonths] || [];
            const monthNames = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            
            monthsInQuarter.forEach(monthNum => {
              const month = monthNum.toString();
              const mData = monthData[month] || {};
              rows.push(
                <Tr key={`${quarterKey}-M${month}`}>
                  <Td color="white" fontSize="sm" w="120px" pl={16}>
                    {monthNames[monthNum]}
                  </Td>
                  {headers.flatMap(header => 
                    selectedAmounts.map(amount => (
                      <Td key={`${header}-${amount}`} color="white" fontSize="sm" w="60px" textAlign="right">
                        {formatAmount(mData[header]?.[amount] || 0, displayFormat)}
                      </Td>
                    ))
                  )}
                  {selectedAmounts.map(amount => (
                    <Td key={`month-total-${amount}`} color="white" fontSize="sm" w="80px" textAlign="right">
                      {formatAmount(
                        headers.reduce((sum, header) => sum + (mData[header]?.[amount] || 0), 0),
                        displayFormat
                      )}
                    </Td>
                  ))}
                </Tr>
              );
            });
          }
        });
      }
    });
    
    return { rows, headers };
  };

  const fetchBnbActualsData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        years: selectedYears.join(','),
        listings: selectedListings.length > 0 ? selectedListings.join(',') : 'all',
        channels: selectedChannels.length > 0 ? selectedChannels.join(',') : 'all',
        period: period
      });
      
      // Fetch listing data
      const listingResponse = await authenticatedGet(buildEndpoint('/api/bnb/bnb-listing-data', params));
      const listingResult = await listingResponse.json();
      if (listingResult.success) {
        setBnbListingData(listingResult.data);
      }

      // Fetch channel data
      const channelResponse = await authenticatedGet(buildEndpoint('/api/bnb/bnb-channel-data', params));
      const channelResult = await channelResponse.json();
      if (channelResult.success) {
        setBnbChannelData(channelResult.data);
      }
    } catch (err) {
      console.error('Error fetching BNB actuals data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Fetch filter options on mount
  useEffect(() => {
    const fetchFilterOptions = async () => {
      try {
        const response = await authenticatedGet(buildEndpoint('/api/bnb/bnb-filter-options'));
        const result = await response.json();
        if (result.success) {
          setBnbFilterOptions({
            years: result.years || [],
            listings: result.listings || [],
            channels: result.channels || []
          });
          setBnbAvailableYears(result.years || []);
        }
      } catch (err) {
        console.error('Error fetching BNB filter options:', err);
      }
    };
    
    fetchFilterOptions();
  }, []);

  // Refetch BNB actuals data when filters change
  const bnbFilterDeps = useMemo(() => [
    selectedYears.join(','),
    selectedListings.join(','),
    selectedChannels.join(','),
    viewType
  ], [selectedYears, selectedListings, selectedChannels, viewType]);
  
  useEffect(() => {
    if (selectedYears.length > 0) {
      fetchBnbActualsData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bnbFilterDeps]);

  const chartData = viewType === 'listing' ? bnbListingData : bnbChannelData;

  return (
    <VStack spacing={4} align="stretch">
      {/* FilterPanel for BNB Actuals - All filters consolidated */}
      <Card bg="gray.700">
        <CardBody>
          <FilterPanel
            layout="grid"
            gridColumns={3}
            size="sm"
            spacing={4}
            filters={[
              {
                type: 'multi',
                label: t('filters.year'),
                options: bnbAvailableYears,
                value: selectedYears,
                onChange: (values) => setSelectedYears(values as string[]),
                placeholder: t('filters.selectYear'),
                isLoading: loading,
              },
              {
                type: 'multi',
                label: t('filters.listings'),
                options: bnbFilterOptions.listings || [],
                value: selectedListings,
                onChange: (values) => setSelectedListings(values as string[]),
                placeholder: t('filters.allListings'),
                treatEmptyAsSelected: true,
              },
              {
                type: 'multi',
                label: t('filters.channels'),
                options: bnbFilterOptions.channels || [],
                value: selectedChannels,
                onChange: (values) => setSelectedChannels(values as string[]),
                placeholder: t('filters.allChannels'),
                treatEmptyAsSelected: true,
              },
              {
                type: 'single',
                label: t('filters.viewType'),
                options: ['listing', 'channel'],
                value: viewType,
                onChange: (value) => setViewType(value as 'listing' | 'channel'),
                getOptionLabel: (option) => option === 'listing' ? t('filters.listing') : t('filters.channel'),
              },
              {
                type: 'single',
                label: t('actuals.displayFormat'),
                options: ['2dec', '0dec', 'k', 'm'],
                value: displayFormat,
                onChange: (value) => setDisplayFormat(value as string),
                getOptionLabel: (option) => {
                  switch (option) {
                    case '2dec': return t('actuals.twoDecimals');
                    case '0dec': return t('actuals.wholeNumbers');
                    case 'k': return t('actuals.thousands');
                    case 'm': return t('actuals.millions');
                    default: return option;
                  }
                },
              },
              {
                type: 'multi',
                label: t('bnb.selectAmounts'),
                options: ['amountGross', 'amountNett', 'amountChannelFee', 'amountTouristTax', 'amountVat'],
                value: selectedAmounts,
                onChange: (values) => setSelectedAmounts(values as string[]),
                getOptionLabel: (option) => {
                  const labels: Record<string, string> = {
                    'amountGross': t('bnb.grossAmount'),
                    'amountNett': t('bnb.netAmount'),
                    'amountChannelFee': t('tables.channelFee'),
                    'amountTouristTax': t('tables.touristTax'),
                    'amountVat': t('tables.vat')
                  };
                  return labels[option] || option;
                },
                placeholder: t('bnb.selectAmounts'),
              },
            ]}
          />
          <Button 
            colorScheme="orange" 
            onClick={fetchBnbActualsData} 
            isLoading={loading} 
            size="sm"
            mt={4}
          >
            {t('actuals.updateData')}
          </Button>
        </CardBody>
      </Card>

      {/* Charts Section */}
      <BnbActualsCharts
        data={chartData}
        viewType={viewType}
        displayFormat={displayFormat}
        selectedAmounts={selectedAmounts}
        formatAmount={formatAmount}
        t={t}
      />

      {/* Expandable BNB Table */}
      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">
            {viewType === 'listing' ? t('bnb.listingSummary') : t('bnb.channelSummary')}
          </Heading>
        </CardHeader>
        <CardBody>
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="white" w="120px">{t('tables.period')}</Th>
                  {(() => {
                    // Extract unique headers from actual data
                    const data = viewType === 'listing' ? bnbListingData : bnbChannelData;
                    const groupField = viewType === 'listing' ? 'listing' : 'channel';
                    const headers = Array.from(new Set(data.map(row => row[groupField]))).sort();
                    
                    return headers.flatMap(header => 
                      selectedAmounts.map(amount => {
                        const amountLabel = {
                          'amountGross': t('tables.gross'),
                          'amountNett': t('tables.net'), 
                          'amountChannelFee': t('tables.channelFee'),
                          'amountTouristTax': t('tables.touristTax'),
                          'amountVat': t('tables.vat')
                        }[amount] || amount;
                        return (
                          <Th key={`${header}-${amount}`} color="white" w="60px" textAlign="right">
                            {header} {amountLabel}
                          </Th>
                        );
                      })
                    );
                  })()}
                  {selectedAmounts.map(amount => {
                    const amountLabel = {
                      'amountGross': t('bnb.grossRevenue'),
                      'amountNett': t('bnb.netRevenue'), 
                      'amountChannelFee': t('bnb.channelFees'),
                      'amountTouristTax': t('tables.touristTax'),
                      'amountVat': t('tables.vat')
                    }[amount] || `Total ${amount}`;
                    return (
                      <Th key={`total-${amount}`} color="white" w="80px" textAlign="right">
                        {t('charts.total')} {amountLabel}
                      </Th>
                    );
                  })}
                </Tr>
              </Thead>
              <Tbody>
                {renderExpandableBnbData(
                  viewType === 'listing' ? bnbListingData : bnbChannelData,
                  viewType as 'listing' | 'channel',
                  displayFormat,
                  selectedAmounts
                ).rows}
              </Tbody>
            </Table>
          </TableContainer>
        </CardBody>
      </Card>

      {/* Year-Month Matrix Overview */}
      <BnbYearMonthMatrix
        data={viewType === 'listing' ? bnbListingData : bnbChannelData}
        viewType={viewType}
        displayFormat={displayFormat}
        selectedAmounts={selectedAmounts}
      />
    </VStack>
  );
};

export default BnbActualsReport;
