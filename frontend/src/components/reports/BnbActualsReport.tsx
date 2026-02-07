import React, { useState, useEffect, useMemo } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Grid,
  GridItem,
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
import {
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { FilterPanel } from '../filters/FilterPanel';

interface BnbFilterOptions {
  years: string[];
  listings: string[];
  channels: string[];
}

const BnbActualsReport: React.FC = () => {
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
  const [bnbListingData, setBnbListingData] = useState<any[]>([]);
  const [bnbChannelData, setBnbChannelData] = useState<any[]>([]);
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
    data: any[], 
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
    }, {} as any);

    const rows: React.ReactElement[] = [];
    
    Object.entries(periodData).sort(([a], [b]) => parseInt(a) - parseInt(b)).forEach(([year, quarterData]: [string, any]) => {
      const yearKey = year;
      const isYearExpanded = expandedYears.has(yearKey);
      
      // Calculate year totals for each listing/channel
      const yearTotals: any = {};
      headers.forEach(header => {
        yearTotals[header] = { amountGross: 0, amountNett: 0, amountChannelFee: 0, amountTouristTax: 0, amountVat: 0 };
      });
      
      Object.values(quarterData).forEach((qData: any) => {
        Object.values(qData).forEach((mData: any) => {
          Object.entries(mData).forEach(([header, amounts]: [string, any]) => {
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
          const quarterTotals: any = {};
          headers.forEach(header => {
            quarterTotals[header] = { amountGross: 0, amountNett: 0, amountChannelFee: 0, amountTouristTax: 0, amountVat: 0 };
          });
          
          // Sum all months in this quarter for each header
          Object.values(monthData).forEach((mData: any) => {
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
                label: 'Years',
                options: bnbAvailableYears,
                value: selectedYears,
                onChange: (values) => setSelectedYears(values as string[]),
                placeholder: 'Select year(s)',
                isLoading: loading,
              },
              {
                type: 'multi',
                label: 'Listings',
                options: bnbFilterOptions.listings || [],
                value: selectedListings,
                onChange: (values) => setSelectedListings(values as string[]),
                placeholder: 'All Listings',
                treatEmptyAsSelected: true,
              },
              {
                type: 'multi',
                label: 'Channels',
                options: bnbFilterOptions.channels || [],
                value: selectedChannels,
                onChange: (values) => setSelectedChannels(values as string[]),
                placeholder: 'All Channels',
                treatEmptyAsSelected: true,
              },
              {
                type: 'single',
                label: 'View Type',
                options: ['listing', 'channel'],
                value: viewType,
                onChange: (value) => setViewType(value as 'listing' | 'channel'),
                getOptionLabel: (option) => option === 'listing' ? 'Listing' : 'Channel',
              },
              {
                type: 'single',
                label: 'Display Format',
                options: ['2dec', '0dec', 'k', 'm'],
                value: displayFormat,
                onChange: (value) => setDisplayFormat(value as string),
                getOptionLabel: (option) => {
                  switch (option) {
                    case '2dec': return '€1,234.56 (2 decimals)';
                    case '0dec': return '€1,235 (whole numbers)';
                    case 'k': return '€1.2K (thousands)';
                    case 'm': return '€1.2M (millions)';
                    default: return option;
                  }
                },
              },
              {
                type: 'multi',
                label: 'Show Amounts',
                options: [
                  { key: 'amountGross', label: 'Gross Amount' },
                  { key: 'amountNett', label: 'Net Amount' },
                  { key: 'amountChannelFee', label: 'Channel Fee' },
                  { key: 'amountTouristTax', label: 'Tourist Tax' },
                  { key: 'amountVat', label: 'VAT Amount' }
                ],
                value: selectedAmounts,
                onChange: (values) => setSelectedAmounts(values as string[]),
                getOptionLabel: (option) => option.label,
                getOptionValue: (option) => option.key,
                placeholder: 'Select amounts...',
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
            Update Data
          </Button>
        </CardBody>
      </Card>

      {/* Revenue Trend Chart */}
      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">Revenue Trend Over Time</Heading>
        </CardHeader>
        <CardBody>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart
              data={(() => {
                const data = viewType === 'listing' ? bnbListingData : bnbChannelData;
                const trendData = data.reduce((acc, row) => {
                  const period = `${row.year}-Q${row.q || 1}`;
                  if (!acc[period]) {
                    acc[period] = { period, year: row.year, quarter: row.q || 1 };
                    selectedAmounts.forEach(amount => {
                      acc[period][amount] = 0;
                    });
                  }
                  selectedAmounts.forEach(amount => {
                    acc[period][amount] += Number(row[amount]) || 0;
                  });
                  return acc;
                }, {} as any);
                return Object.values(trendData).sort((a: any, b: any) => {
                  if (a.year !== b.year) return a.year - b.year;
                  return a.quarter - b.quarter;
                });
              })()}
              margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" tick={{fill: 'white'}} />
              <YAxis tick={{fill: 'white'}} />
              <Tooltip formatter={(value) => formatAmount(Number(value), displayFormat)} />
              <Legend wrapperStyle={{color: 'white'}} />
              {selectedAmounts.map((amount, index) => {
                const amountLabel = {
                  'amountGross': 'Gross Revenue',
                  'amountNett': 'Net Revenue',
                  'amountChannelFee': 'Channel Fees',
                  'amountTouristTax': 'Tourist Tax',
                  'amountVat': 'VAT'
                }[amount] || amount;
                return (
                  <Line
                    key={amount}
                    type="monotone"
                    dataKey={amount}
                    stroke={`hsl(${index * 60}, 70%, 60%)`}
                    strokeWidth={2}
                    name={amountLabel}
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      {/* Charts Grid */}
      <Grid templateColumns={{ base: "1fr", lg: "1fr 400px" }} gap={4}>
        <GridItem>
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">
                {viewType === 'listing' ? 'Listing' : 'Channel'} Distribution
              </Heading>
            </CardHeader>
            <CardBody>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={(() => {
                      const data = viewType === 'listing' ? bnbListingData : bnbChannelData;
                      const primaryAmount = selectedAmounts[0] || 'amountGross';
                      const grouped = data.reduce((acc, row) => {
                        const key = row[viewType];
                        if (!acc[key]) acc[key] = 0;
                        acc[key] += Number(row[primaryAmount]) || 0;
                        return acc;
                      }, {} as any);
                      return Object.entries(grouped)
                        .map(([name, value]) => ({ name, value: Math.abs(Number(value)) }))
                        .filter(item => item.value > 0)
                        .sort((a, b) => b.value - a.value);
                    })()}
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                    label={(entry: any) => `${entry.name}: ${(entry.percent * 100).toFixed(1)}%`}
                  >
                    {(() => {
                      const data = viewType === 'listing' ? bnbListingData : bnbChannelData;
                      const primaryAmount = selectedAmounts[0] || 'amountGross';
                      const grouped = data.reduce((acc, row) => {
                        const key = row[viewType];
                        if (!acc[key]) acc[key] = 0;
                        acc[key] += Number(row[primaryAmount]) || 0;
                        return acc;
                      }, {} as any);
                      return Object.entries(grouped)
                        .map(([name, value]) => ({ name, value: Math.abs(Number(value)) }))
                        .filter(item => item.value > 0)
                        .sort((a, b) => b.value - a.value)
                        .map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                        ));
                    })()}
                  </Pie>
                  <Tooltip formatter={(value) => formatAmount(Number(value), displayFormat)} />
                </PieChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>
        </GridItem>
        
        <GridItem>
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">Year-over-Year Performance</Heading>
            </CardHeader>
            <CardBody>
              {(() => {
                const data = viewType === 'listing' ? bnbListingData : bnbChannelData;
                const primaryAmount = selectedAmounts[0] || 'amountGross';
                const years = Array.from(new Set(data.map(row => row.year))).sort((a, b) => b - a);
                const currentYear = years[0];
                const previousYear = years[1];
                
                const currentTotal = data
                  .filter(row => row.year === currentYear)
                  .reduce((sum, row) => sum + (Number(row[primaryAmount]) || 0), 0);
                const previousTotal = data
                  .filter(row => row.year === previousYear)
                  .reduce((sum, row) => sum + (Number(row[primaryAmount]) || 0), 0);
                
                const percentage = previousTotal > 0 ? (currentTotal / previousTotal) * 100 : 0;
                const difference = currentTotal - previousTotal;
                
                const getColor = (pct: number) => {
                  if (pct >= 100) return '#22c55e'; // Green
                  if (pct >= 90) return '#eab308';  // Yellow
                  return '#ef4444'; // Red
                };
                
                return (
                  <VStack spacing={4}>
                    <ResponsiveContainer width="100%" height={200}>
                      <RadialBarChart
                        cx="50%"
                        cy="50%"
                        innerRadius="60%"
                        outerRadius="90%"
                        startAngle={180}
                        endAngle={0}
                        data={[
                          { name: 'background', value: 150, fill: '#1f2937' },
                          { name: 'performance', value: Math.min(percentage, 150), fill: getColor(percentage) }
                        ]}
                      >
                        <RadialBar dataKey="value" />
                        {/* Custom Needle */}
                        <g>
                          <line
                            x1="50%"
                            y1="50%"
                            x2={`${50 + 35 * Math.cos((180 - (percentage / 150) * 180) * Math.PI / 180)}%`}
                            y2={`${50 - 35 * Math.sin((180 - (percentage / 150) * 180) * Math.PI / 180)}%`}
                            stroke="white"
                            strokeWidth="3"
                            strokeLinecap="round"
                          />
                          <circle
                            cx="50%"
                            cy="50%"
                            r="4"
                            fill="white"
                          />
                        </g>
                      </RadialBarChart>
                    </ResponsiveContainer>
                    <VStack spacing={2} textAlign="center">
                      <Text color="white" fontSize="2xl" fontWeight="bold">
                        {percentage.toFixed(1)}%
                      </Text>
                      <Text color="white" fontSize="sm">
                        {currentYear} vs {previousYear}
                      </Text>
                      <Text color={difference >= 0 ? 'green.400' : 'red.400'} fontSize="sm">
                        {difference >= 0 ? '+' : ''}{formatAmount(difference, displayFormat)}
                      </Text>
                      <Text color="gray.400" fontSize="xs">
                        {percentage >= 100 ? 'Growth' : percentage >= 90 ? 'Slight Decline' : 'Significant Decline'}
                      </Text>
                    </VStack>
                  </VStack>
                );
              })()}
            </CardBody>
          </Card>
        </GridItem>
      </Grid>

      {/* Expandable BNB Table */}
      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">
            {viewType === 'listing' ? 'Listing' : 'Channel'} Summary
          </Heading>
        </CardHeader>
        <CardBody>
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="white" w="120px">Period</Th>
                  {(() => {
                    // Extract unique headers from actual data
                    const data = viewType === 'listing' ? bnbListingData : bnbChannelData;
                    const groupField = viewType === 'listing' ? 'listing' : 'channel';
                    const headers = Array.from(new Set(data.map(row => row[groupField]))).sort();
                    
                    return headers.flatMap(header => 
                      selectedAmounts.map(amount => {
                        const amountLabel = {
                          'amountGross': 'Gross',
                          'amountNett': 'Net', 
                          'amountChannelFee': 'Fee',
                          'amountTouristTax': 'Tax',
                          'amountVat': 'VAT'
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
                      'amountGross': 'Total Gross',
                      'amountNett': 'Total Net', 
                      'amountChannelFee': 'Total Fee',
                      'amountTouristTax': 'Total Tax',
                      'amountVat': 'Total VAT'
                    }[amount] || `Total ${amount}`;
                    return (
                      <Th key={`total-${amount}`} color="white" w="80px" textAlign="right">
                        {amountLabel}
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
    </VStack>
  );
};

export default BnbActualsReport;
