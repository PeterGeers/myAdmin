import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Heading, Select, Button, Text,
  Card, CardBody, CardHeader, Grid, GridItem, Input,
  Table, Thead, Tbody, Tr, Th, Td, TableContainer,
  Tabs, TabList, TabPanels, Tab, TabPanel,
  Menu, MenuButton, MenuList, MenuItem, Checkbox
} from '@chakra-ui/react';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, PieChart, Pie, Legend, LineChart, Line, RadialBarChart, RadialBar } from 'recharts';

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
  amountChannelFee?: number;
  amountTouristTax?: number;
  amountVat?: number;
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
  const [refSummaryData, setRefSummaryData] = useState<any[]>([]);
  const [selectedReferenceDetails, setSelectedReferenceDetails] = useState<any[]>([]);
  const [selectedReference, setSelectedReference] = useState<string>('');
  const [filterOptions, setFilterOptions] = useState({
    administrations: [],
    ledgers: [],
    references: []
  });
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
    listing: 'all',
    selectedAmounts: ['amountGross', 'amountNett'] // Default selection
  });



  // Check Reference Filters
  const [checkRefFilters, setCheckRefFilters] = useState({
    referenceNumber: 'all',
    ledger: 'all',
    administration: 'all'
  });



  // Actuals Dashboard State
  const [actualsFilters, setActualsFilters] = useState({
    years: [new Date().getFullYear().toString()],
    administration: 'all',
    displayFormat: '2dec'
  });
  const [availableYears, setAvailableYears] = useState<string[]>([]);

  // BNB Actuals State
  const [bnbActualsFilters, setBnbActualsFilters] = useState({
    years: [new Date().getFullYear().toString()],
    listings: 'all',
    channels: 'all',
    period: 'year',
    displayFormat: '2dec',
    viewType: 'listing', // 'listing' or 'channel'
    selectedAmounts: ['amountGross', 'amountNett'] // Default selection
  });
  const [bnbAvailableYears, setBnbAvailableYears] = useState<string[]>([]);
  const [bnbFilterOptions, setBnbFilterOptions] = useState({
    years: [],
    listings: [],
    channels: []
  });
  const [bnbListingData, setBnbListingData] = useState<any[]>([]);
  const [bnbChannelData, setBnbChannelData] = useState<any[]>([]);
  const [expandedYears, setExpandedYears] = useState<Set<string>>(new Set());
  const [expandedQuarters, setExpandedQuarters] = useState<Set<string>>(new Set());
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());
  const [drillDownLevel, setDrillDownLevel] = useState<'year' | 'quarter' | 'month'>('year');
  
  // BTW State
  const [btwFilters, setBtwFilters] = useState({
    administration: 'GoodwinSolutions',
    year: new Date().getFullYear().toString(),
    quarter: '1'
  });
  const [btwReport, setBtwReport] = useState<string>('');
  const [btwTransaction, setBtwTransaction] = useState<any>(null);
  const [btwLoading, setBtwLoading] = useState(false);
  
  // Reference Analysis State
  const [refAnalysisFilters, setRefAnalysisFilters] = useState({
    years: [new Date().getFullYear().toString()],
    administration: 'all',
    referenceNumber: '',
    accounts: [] as string[]
  });
  const [refAnalysisData, setRefAnalysisData] = useState<any[]>([]);
  const [refTrendData, setRefTrendData] = useState<any[]>([]);
  const [availableReferences, setAvailableReferences] = useState<string[]>([]);
  const [availableRefAccounts, setAvailableRefAccounts] = useState<any[]>([]);
  const [refAnalysisLoading, setRefAnalysisLoading] = useState(false);

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
  const renderExpandableBnbData = (data: any[], viewType: 'listing' | 'channel', displayFormat: string, selectedAmounts: string[] = ['amountGross']) => {
    const groupField = viewType === 'listing' ? 'listing' : 'channel';
    const headers = viewType === 'listing' ? bnbFilterOptions.listings : bnbFilterOptions.channels;
    
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

  // Render hierarchical data with Parent totals and indented ledgers
  const renderHierarchicalData = (data: any[], years: string[], displayFormat: string) => {
    const sortedYears = [...years].sort((a, b) => parseInt(a) - parseInt(b));
    

    
    // Generate column keys based on drill-down level
    const getColumnKeys = () => {
      if (drillDownLevel === 'year') {
        return sortedYears;
      } else if (drillDownLevel === 'quarter') {
        return sortedYears.flatMap(year => ['Q1', 'Q2', 'Q3', 'Q4'].map(q => `${year}-${q}`));
      } else {
        return sortedYears.flatMap(year => 
          ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            .map(m => `${year}-${m}`)
        );
      }
    };
    
    const columnKeys = getColumnKeys();
    
    const grouped = data.reduce((acc, row) => {
      if (!acc[row.Parent]) {
        acc[row.Parent] = { parent: row.Parent, ledgers: {}, totals: {} };
      }
      
      // Group ledgers by name and accumulate amounts by period
      if (!acc[row.Parent].ledgers[row.ledger]) {
        acc[row.Parent].ledgers[row.ledger] = {};
        columnKeys.forEach(key => {
          acc[row.Parent].ledgers[row.ledger][key] = 0;
        });
      }
      
      // Determine the key based on drill-down level
      let periodKey = '';
      if (drillDownLevel === 'year') {
        periodKey = String(row.jaar);
      } else if (drillDownLevel === 'quarter') {
        const quarter = row.kwartaal || 1;
        periodKey = `${row.jaar}-Q${quarter}`;
      } else {
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const month = row.maand || 1;
        periodKey = `${row.jaar}-${monthNames[month - 1]}`;
      }
      
      if (columnKeys.includes(periodKey)) {
        acc[row.Parent].ledgers[row.ledger][periodKey] = (acc[row.Parent].ledgers[row.ledger][periodKey] || 0) + (Number(row.Amount) || 0);
      }
      
      // Calculate parent totals
      columnKeys.forEach(key => {
        if (!acc[row.Parent].totals[key]) acc[row.Parent].totals[key] = 0;
        if (key === periodKey) {
          acc[row.Parent].totals[key] += Number(row.Amount) || 0;
        }
      });
      
      return acc;
    }, {} as any);

    const rows: React.ReactElement[] = [];
    let totalIndex = 0;
    const grandTotals: { [key: string]: number } = {};

    // Initialize grand totals
    columnKeys.forEach(key => {
      grandTotals[key] = 0;
    });

    Object.values(grouped).forEach((group: any) => {
      // Add to grand totals
      columnKeys.forEach(key => {
        grandTotals[key] = (grandTotals[key] || 0) + (group.totals[key] || 0);
      });
      
      const isExpanded = expandedParents.has(`profitloss-${group.parent}`);
      
      // Parent row with totals and expand/collapse button
      rows.push(
        <Tr key={`parent-${totalIndex}`} bg="gray.600">
          <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
            <HStack>
              <Button
                size="xs"
                variant="ghost"
                color="white"
                onClick={() => {
                  const newExpanded = new Set(expandedParents);
                  const key = `profitloss-${group.parent}`;
                  if (isExpanded) {
                    newExpanded.delete(key);
                  } else {
                    newExpanded.add(key);
                  }
                  setExpandedParents(newExpanded);
                }}
              >
                {isExpanded ? '−' : '+'}
              </Button>
              <Text>{group.parent}</Text>
            </HStack>
          </Td>
          {columnKeys.map(key => (
            <Td key={key} color="white" fontSize="sm" width="60px" textAlign="right" fontWeight="bold" border="none" py={1}>
              {formatAmount(Math.round((group.totals[key] || 0) * 100) / 100, displayFormat)}
            </Td>
          ))}
        </Tr>
      );
      
      // Ledger rows consolidated by ledger name (only if expanded)
      if (isExpanded) {
        Object.entries(group.ledgers).forEach(([ledgerName, ledgerAmounts]: [string, any], ledgerIndex: number) => {
          rows.push(
            <Tr key={`ledger-${totalIndex}-${ledgerIndex}`}>
              <Td color="white" fontSize="sm" width="120px" paddingLeft="32px" border="none" py={1}>
                {ledgerName}
              </Td>
              {columnKeys.map(key => (
                <Td key={key} color="white" fontSize="sm" width="60px" textAlign="right" border="none" py={1}>
                  {formatAmount(Math.round((ledgerAmounts[key] || 0) * 100) / 100, displayFormat)}
                </Td>
              ))}
            </Tr>
          );
        });
      }
      
      totalIndex++;
    });

    // Add grand total row
    rows.push(
      <Tr key="grand-total" bg="orange.600">
        <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
          TOTAL
        </Td>
        {columnKeys.map(key => (
          <Td key={key} color="white" fontSize="sm" width="60px" textAlign="right" fontWeight="bold" border="none" py={1}>
            {formatAmount(Math.round((grandTotals[key] || 0) * 100) / 100, displayFormat)}
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
      const isExpanded = expandedParents.has(`balance-${group.parent}`);
      
      // Parent row with total and expand/collapse button
      rows.push(
        <Tr key={`parent-${totalIndex}`} bg="gray.600">
          <Td color="white" fontSize="sm" width="120px" fontWeight="bold" border="none" py={1}>
            <HStack>
              <Button
                size="xs"
                variant="ghost"
                color="white"
                onClick={() => {
                  const newExpanded = new Set(expandedParents);
                  const key = `balance-${group.parent}`;
                  if (isExpanded) {
                    newExpanded.delete(key);
                  } else {
                    newExpanded.add(key);
                  }
                  setExpandedParents(newExpanded);
                }}
              >
                {isExpanded ? '−' : '+'}
              </Button>
              <Text>{group.parent}</Text>
            </HStack>
          </Td>
          <Td color="white" fontSize="sm" width="100px" textAlign="right" fontWeight="bold" border="none" py={1}>
            {formatAmount(group.total, displayFormat)}
          </Td>
        </Tr>
      );
      
      // Ledger rows indented under parent (only if expanded)
      if (isExpanded) {
        group.ledgers.forEach((ledger: any, ledgerIndex: number) => {
          rows.push(
            <Tr key={`ledger-${totalIndex}-${ledgerIndex}`}>
              <Td color="white" fontSize="sm" width="120px" paddingLeft="32px" border="none" py={1}>
                {ledger.ledger}
              </Td>
              <Td color="white" fontSize="sm" width="100px" textAlign="right" border="none" py={1}>
                {formatAmount(Number(ledger.Amount) || 0, displayFormat)}
              </Td>
            </Tr>
          );
        });
      }
      
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
      } else if (field === 'nights' || field === 'guests' || field === 'amountGross' || field === 'amountNett' || field === 'amountChannelFee' || field === 'amountTouristTax' || field === 'amountVat') {
        aVal = Number(aVal) || 0;
        bVal = Number(bVal) || 0;
      }
      
      // Ensure values are not undefined
      const safeAVal = aVal ?? '';
      const safeBVal = bVal ?? '';
      
      if (safeAVal < safeBVal) return newDirection === 'asc' ? -1 : 1;
      if (safeAVal > safeBVal) return newDirection === 'asc' ? 1 : -1;
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
        dateTo: new Date().toISOString().split('T')[0],
        administration: 'all',
        profitLoss: 'all'
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
        years: actualsFilters.years.join(','),
        administration: actualsFilters.administration,
        groupBy: drillDownLevel
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/actuals-profitloss?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setProfitLossData(data.data);
      }
    } catch (err) {
      console.error('Error fetching profit/loss data:', err);
    } finally {
      setLoading(false);
    }
  };



  const fetchFilterOptions = async (administration = 'all', ledger = 'all') => {
    try {
      const params = new URLSearchParams();
      if (administration !== 'all') params.append('administration', administration);
      if (ledger !== 'all') params.append('ledger', ledger);
      
      const response = await fetch(`http://localhost:5000/api/reports/filter-options?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setFilterOptions({
          administrations: data.administrations || [],
          ledgers: data.ledgers || [],
          references: data.references || []
        });
      }
    } catch (err) {
      console.error('Error fetching filter options:', err);
    }
  };

  const fetchCheckRefData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        referenceNumber: 'all', // Always get summary for all references
        ledger: checkRefFilters.ledger,
        administration: checkRefFilters.administration
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/check-reference?${params}`);
      const data = await response.json();
      
      if (data.success) {
        const filteredSummary = data.summary.filter((row: any) => {
          const amount = parseFloat(row.total_amount || 0);
          return Math.abs(amount) > 0.01;
        });
        setRefSummaryData(filteredSummary);
      }
    } catch (err) {
      console.error('Error fetching check reference data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchReferenceDetails = async (referenceNumber: string) => {
    try {
      const params = new URLSearchParams({
        referenceNumber: referenceNumber,
        ledger: checkRefFilters.ledger,
        administration: checkRefFilters.administration
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/check-reference?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setSelectedReferenceDetails(data.transactions);
        setSelectedReference(referenceNumber);
      }
    } catch (err) {
      console.error('Error fetching reference details:', err);
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

  const fetchBnbFilterOptions = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/reports/bnb-filter-options');
      const data = await response.json();
      if (data.success) {
        setBnbFilterOptions({
          years: data.years || [],
          listings: data.listings || [],
          channels: data.channels || []
        });
        setBnbAvailableYears(data.years || []);
      }
    } catch (err) {
      console.error('Error fetching BNB filter options:', err);
    }
  };

  const fetchBnbActualsData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        years: bnbActualsFilters.years.join(','),
        listings: bnbActualsFilters.listings,
        channels: bnbActualsFilters.channels,
        period: bnbActualsFilters.period
      });
      
      // Fetch listing data
      const listingResponse = await fetch(`http://localhost:5000/api/reports/bnb-listing-data?${params}`);
      const listingResult = await listingResponse.json();
      if (listingResult.success) {
        setBnbListingData(listingResult.data);
      }

      // Fetch channel data
      const channelResponse = await fetch(`http://localhost:5000/api/reports/bnb-channel-data?${params}`);
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

  const fetchActualsData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        years: actualsFilters.years.join(','),
        administration: actualsFilters.administration,
        groupBy: drillDownLevel // 'year', 'quarter', or 'month'
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

  const generateBtwReport = async () => {
    setBtwLoading(true);
    try {
      const response = await fetch('http://localhost:5000/api/btw/generate-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(btwFilters)
      });
      
      const data = await response.json();
      
      if (data.success) {
        setBtwReport(data.html_report);
        setBtwTransaction(data.transaction);
      } else {
        console.error('BTW report generation failed:', data.error);
      }
    } catch (err) {
      console.error('Error generating BTW report:', err);
    } finally {
      setBtwLoading(false);
    }
  };

  const saveBtwTransaction = async () => {
    if (!btwTransaction) return;
    
    setBtwLoading(true);
    try {
      const response = await fetch('http://localhost:5000/api/btw/save-transaction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction: btwTransaction })
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Upload report to Google Drive
        const filename = `BTW_${btwFilters.administration}_${btwFilters.year}_Q${btwFilters.quarter}.html`;
        
        const uploadResponse = await fetch('http://localhost:5000/api/btw/upload-report', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            html_content: btwReport, 
            filename: filename 
          })
        });
        
        const uploadData = await uploadResponse.json();
        
        if (uploadData.success) {
          alert(`BTW transaction saved successfully! Report uploaded to ${uploadData.location}.`);
        } else {
          alert('BTW transaction saved, but report upload failed: ' + uploadData.error);
        }
      } else {
        alert('Failed to save BTW transaction: ' + data.error);
      }
    } catch (err) {
      console.error('Error saving BTW transaction:', err);
      alert('Error saving BTW transaction: ' + err);
    } finally {
      setBtwLoading(false);
    }
  };

  const fetchReferenceAnalysis = async () => {
    setRefAnalysisLoading(true);
    try {
      const params = new URLSearchParams({
        years: refAnalysisFilters.years.join(','),
        administration: refAnalysisFilters.administration,
        reference_number: refAnalysisFilters.referenceNumber,
        accounts: refAnalysisFilters.accounts.join(',')
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/reference-analysis?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setRefAnalysisData(data.transactions);
        setRefTrendData(data.trend_data);
        setAvailableReferences(data.reference_numbers);
        setAvailableRefAccounts(data.available_accounts);
      }
    } catch (err) {
      console.error('Error fetching reference analysis:', err);
    } finally {
      setRefAnalysisLoading(false);
    }
  };

  const fetchAvailableReferences = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/reports/reference-analysis');
      const data = await response.json();
      if (data.success) {
        setAvailableReferences(data.reference_numbers);
      }
    } catch (err) {
      console.error('Error fetching available references:', err);
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
    fetchBnbFilterOptions();
    fetchBnbActualsData();
    fetchAvailableReferences();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refetch data when drill-down level changes
  useEffect(() => {
    fetchActualsData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drillDownLevel]);

  // Refetch BNB actuals data when filters change
  useEffect(() => {
    if (bnbActualsFilters.years.length > 0) {
      fetchBnbActualsData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bnbActualsFilters.years, bnbActualsFilters.listings, bnbActualsFilters.channels, bnbActualsFilters.viewType]);

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
            <Tab color="white">🏡 BNB Actuals</Tab>
            <Tab color="white">🔍 Check Reference</Tab>
            <Tab color="white">🧾 BTW aangifte</Tab>
            <Tab color="white">📈 View ReferenceNumber</Tab>
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
                    
                    {/* Amount Selection Filter */}
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
                          ].map(amount => (
                            <MenuItem key={amount.key} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
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
                        <Text color="white" mb={2}>Drill Down Level</Text>
                        <HStack>
                          <Button 
                            size="sm" 
                            colorScheme={drillDownLevel === 'year' ? 'orange' : 'gray'}
                            onClick={() => {
                              setDrillDownLevel('year');
                              setExpandedParents(new Set()); // Reset expanded state
                            }}
                            isLoading={loading && drillDownLevel !== 'year'}
                          >
                            📅 Year
                          </Button>
                          <Button 
                            size="sm" 
                            colorScheme={drillDownLevel === 'quarter' ? 'orange' : 'gray'}
                            onClick={() => {
                              setDrillDownLevel('quarter');
                              setExpandedParents(new Set()); // Reset expanded state
                            }}
                            isLoading={loading && drillDownLevel !== 'quarter'}
                          >
                            📊 Quarter
                          </Button>
                          <Button 
                            size="sm" 
                            colorScheme={drillDownLevel === 'month' ? 'orange' : 'gray'}
                            onClick={() => {
                              setDrillDownLevel('month');
                              setExpandedParents(new Set()); // Reset expanded state
                            }}
                            isLoading={loading && drillDownLevel !== 'month'}
                          >
                            📈 Month
                          </Button>
                        </HStack>
                      </GridItem>
                      <GridItem>
                        <Button colorScheme="orange" onClick={fetchActualsData} isLoading={loading} size="sm">
                          Update Data
                        </Button>
                      </GridItem>
                      <GridItem>
                        <VStack align="start" spacing={1}>
                          <Text color="gray.400" fontSize="xs">
                            Current View: {drillDownLevel === 'year' ? '📅 Yearly Summary' : drillDownLevel === 'quarter' ? '📊 Quarterly Breakdown' : '📈 Monthly Detail'}
                          </Text>
                          <Text color="gray.500" fontSize="xs">
                            {drillDownLevel === 'year' ? 'Shows annual totals' : drillDownLevel === 'quarter' ? 'Shows quarterly data' : 'Shows monthly granularity'}
                          </Text>
                        </VStack>
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
                              data={(() => {
                                const hasExpandedParents = Array.from(expandedParents).some(key => key.startsWith('balance-'));
                                if (hasExpandedParents) {
                                  // Show ledger data for expanded parents only
                                  return balanceData.filter(row => expandedParents.has(`balance-${row.Parent}`)).reduce((acc, row) => {
                                    const existing = acc.find(item => item.name === row.ledger);
                                    const value = Math.abs(Number(row.Amount) || 0);
                                    if (existing) {
                                      existing.value += value;
                                    } else {
                                      acc.push({ name: row.ledger, value });
                                    }
                                    return acc;
                                  }, [] as any[]).filter(item => item.value > 0);
                                } else {
                                  // Show parent data - use same logic as renderBalanceData
                                  const grouped = balanceData.reduce((acc, row) => {
                                    if (!acc[row.Parent]) {
                                      acc[row.Parent] = { parent: row.Parent, ledgers: [], total: 0 };
                                    }
                                    acc[row.Parent].ledgers.push(row);
                                    acc[row.Parent].total += Number(row.Amount) || 0;
                                    return acc;
                                  }, {} as any);
                                  return Object.values(grouped).map((group: any) => ({
                                    name: group.parent,
                                    value: Math.abs(group.total)
                                  })).filter(item => item.value > 0);
                                }
                              })()}
                              cx="50%"
                              cy="50%"
                              labelLine={false}
                              outerRadius={80}
                              fill="#8884d8"
                              dataKey="value"
                              label={(entry) => entry.name}
                            >
                              {(() => {
                                const hasExpandedParents = Array.from(expandedParents).some(key => key.startsWith('balance-'));
                                const data = hasExpandedParents 
                                  ? balanceData.filter(row => expandedParents.has(`balance-${row.Parent}`)).reduce((acc, row) => {
                                      const existing = acc.find(item => item.name === row.ledger);
                                      const value = Math.abs(Number(row.Amount) || 0);
                                      if (existing) {
                                        existing.value += value;
                                      } else {
                                        acc.push({ name: row.ledger, value });
                                      }
                                      return acc;
                                    }, [] as any[]).filter(item => item.value > 0)
                                  : (() => {
                                      const grouped = balanceData.reduce((acc, row) => {
                                        if (!acc[row.Parent]) {
                                          acc[row.Parent] = { parent: row.Parent, ledgers: [], total: 0 };
                                        }
                                        acc[row.Parent].ledgers.push(row);
                                        acc[row.Parent].total += Number(row.Amount) || 0;
                                        return acc;
                                      }, {} as any);
                                      return Object.values(grouped).map((group: any) => ({
                                        name: group.parent,
                                        value: Math.abs(group.total)
                                      })).filter(item => item.value > 0);
                                    })();
                                return data.map((entry, index) => (
                                  <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                                ));
                              })()}
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
                                {drillDownLevel === 'year' && [...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map(year => (
                                  <Th key={year} color="white" width="60px" textAlign="right" border="none">{year}</Th>
                                ))}
                                {drillDownLevel === 'quarter' && [...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map(year => 
                                  ['Q1', 'Q2', 'Q3', 'Q4'].map(quarter => (
                                    <Th key={`${year}-${quarter}`} color="white" width="60px" textAlign="right" border="none">
                                      {year} {quarter}
                                    </Th>
                                  ))
                                ).flat()}
                                {drillDownLevel === 'month' && [...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map(year => 
                                  ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'].map(month => (
                                    <Th key={`${year}-${month}`} color="white" width="60px" textAlign="right" border="none">
                                      {year} {month}
                                    </Th>
                                  ))
                                ).flat()}
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
                        <ResponsiveContainer width="100%" height={480}>
                          <BarChart
                            data={(() => {
                              const hasExpandedParents = Array.from(expandedParents).some(key => key.startsWith('profitloss-'));
                              const filteredData = profitLossData.filter(row => row.ledger !== '8099');
                              
                              if (hasExpandedParents) {
                                // Show ledger data for expanded parents only
                                return filteredData
                                  .filter(row => expandedParents.has(`profitloss-${row.Parent}`))
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
                                  .filter(item => actualsFilters.years.some(year => Math.abs(item[year] || 0) > 0));
                              } else {
                                // Show parent data
                                return filteredData
                                  .reduce((acc, row) => {
                                    const existing = acc.find(item => item.name === row.Parent);
                                    const value = Number(row.Amount) || 0;
                                    if (existing) {
                                      existing[row.jaar] = (existing[row.jaar] || 0) + value;
                                    } else {
                                      const newItem: any = { name: row.Parent };
                                      actualsFilters.years.forEach(year => {
                                        newItem[year] = 0;
                                      });
                                      newItem[row.jaar] = value;
                                      acc.push(newItem);
                                    }
                                    return acc;
                                  }, [] as any[])
                                  .filter(item => actualsFilters.years.some(year => Math.abs(item[year] || 0) > 0));
                              }
                            })()}
                            margin={{ top: 0, right: 15, left: 15, bottom: 10 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} fontSize={10} tick={{fill: 'white'}} />
                            <YAxis tick={{fill: 'white'}} />
                            <Tooltip formatter={(value) => formatAmount(Number(value), actualsFilters.displayFormat)} />
                            <Legend wrapperStyle={{color: 'white', paddingTop: '5px'}} />
                            {[...actualsFilters.years].sort((a, b) => parseInt(a) - parseInt(b)).map((year, index) => (
                              <Bar key={year} dataKey={year} fill={`hsl(${index * 60}, 70%, 60%)`} />
                            ))}
                          </BarChart>
                        </ResponsiveContainer>
                        <Text color="gray.400" fontSize="xs" mt={2} textAlign="center">
                          * 8099 Bijzondere baten en lasten not included
                        </Text>
                      </CardBody>
                    </Card>
                  </GridItem>
                </Grid>
              </VStack>
            </TabPanel>



            {/* BNB Actuals Tab */}
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
                            {bnbActualsFilters.years.length > 0 ? bnbActualsFilters.years.join(', ') : 'Select years...'}
                          </MenuButton>
                          <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
                            {bnbAvailableYears.map(year => (
                              <MenuItem key={year} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
                                <Checkbox
                                  isChecked={bnbActualsFilters.years.includes(year)}
                                  onChange={(e) => {
                                    const isChecked = e.target.checked;
                                    setBnbActualsFilters(prev => ({
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
                        <Text color="white" mb={2}>Listing</Text>
                        <Select 
                          value={bnbActualsFilters.listings}
                          onChange={(e) => setBnbActualsFilters(prev => ({...prev, listings: e.target.value}))}
                          bg="gray.600" 
                          color="white" 
                          size="sm"
                        >
                          <option value="all">All Listings</option>
                          {bnbFilterOptions.listings.map(listing => (
                            <option key={listing} value={listing}>{listing}</option>
                          ))}
                        </Select>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Channel</Text>
                        <Select 
                          value={bnbActualsFilters.channels}
                          onChange={(e) => setBnbActualsFilters(prev => ({...prev, channels: e.target.value}))}
                          bg="gray.600" 
                          color="white" 
                          size="sm"
                        >
                          <option value="all">All Channels</option>
                          {bnbFilterOptions.channels.map(channel => (
                            <option key={channel} value={channel}>{channel}</option>
                          ))}
                        </Select>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>View Type</Text>
                        <Select 
                          value={bnbActualsFilters.viewType}
                          onChange={(e) => setBnbActualsFilters(prev => ({...prev, viewType: e.target.value as 'listing' | 'channel'}))}
                          bg="gray.600" 
                          color="white" 
                          size="sm"
                        >
                          <option value="listing">Listing</option>
                          <option value="channel">Channel</option>
                        </Select>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Display Format</Text>
                        <Select 
                          value={bnbActualsFilters.displayFormat}
                          onChange={(e) => setBnbActualsFilters(prev => ({...prev, displayFormat: e.target.value}))}
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
                        <Text color="white" mb={2}>Show Amounts</Text>
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
                            {bnbActualsFilters.selectedAmounts.length > 0 ? `${bnbActualsFilters.selectedAmounts.length} selected` : 'Select amounts...'}
                          </MenuButton>
                          <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
                            {[
                              { key: 'amountGross', label: 'Gross Amount' },
                              { key: 'amountNett', label: 'Net Amount' },
                              { key: 'amountChannelFee', label: 'Channel Fee' },
                              { key: 'amountTouristTax', label: 'Tourist Tax' },
                              { key: 'amountVat', label: 'VAT Amount' }
                            ].map(amount => (
                              <MenuItem key={amount.key} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
                                <Checkbox
                                  isChecked={bnbActualsFilters.selectedAmounts.includes(amount.key)}
                                  onChange={(e) => {
                                    const isChecked = e.target.checked;
                                    setBnbActualsFilters(prev => ({
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
                      </GridItem>
                      <GridItem>
                        <Button colorScheme="orange" onClick={fetchBnbActualsData} isLoading={loading} size="sm">
                          Update Data
                        </Button>
                      </GridItem>
                    </Grid>
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
                          const data = bnbActualsFilters.viewType === 'listing' ? bnbListingData : bnbChannelData;
                          const trendData = data.reduce((acc, row) => {
                            const period = `${row.year}-Q${row.q || 1}`;
                            if (!acc[period]) {
                              acc[period] = { period, year: row.year, quarter: row.q || 1 };
                              bnbActualsFilters.selectedAmounts.forEach(amount => {
                                acc[period][amount] = 0;
                              });
                            }
                            bnbActualsFilters.selectedAmounts.forEach(amount => {
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
                        <Tooltip formatter={(value) => formatAmount(Number(value), bnbActualsFilters.displayFormat)} />
                        <Legend wrapperStyle={{color: 'white'}} />
                        {bnbActualsFilters.selectedAmounts.map((amount, index) => {
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
                          {bnbActualsFilters.viewType === 'listing' ? 'Listing' : 'Channel'} Distribution
                        </Heading>
                      </CardHeader>
                      <CardBody>
                        <ResponsiveContainer width="100%" height={300}>
                          <PieChart>
                            <Pie
                              data={(() => {
                                const data = bnbActualsFilters.viewType === 'listing' ? bnbListingData : bnbChannelData;
                                const primaryAmount = bnbActualsFilters.selectedAmounts[0] || 'amountGross';
                                const grouped = data.reduce((acc, row) => {
                                  const key = row[bnbActualsFilters.viewType];
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
                                const data = bnbActualsFilters.viewType === 'listing' ? bnbListingData : bnbChannelData;
                                const primaryAmount = bnbActualsFilters.selectedAmounts[0] || 'amountGross';
                                const grouped = data.reduce((acc, row) => {
                                  const key = row[bnbActualsFilters.viewType];
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
                            <Tooltip formatter={(value) => formatAmount(Number(value), bnbActualsFilters.displayFormat)} />
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
                          const data = bnbActualsFilters.viewType === 'listing' ? bnbListingData : bnbChannelData;
                          const primaryAmount = bnbActualsFilters.selectedAmounts[0] || 'amountGross';
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
                                  {difference >= 0 ? '+' : ''}{formatAmount(difference, bnbActualsFilters.displayFormat)}
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
                      {bnbActualsFilters.viewType === 'listing' ? 'Listing' : 'Channel'} Summary
                    </Heading>
                  </CardHeader>
                  <CardBody>
                    <TableContainer>
                      <Table size="sm" variant="simple">
                        <Thead>
                          <Tr>
                            <Th color="white" w="120px">Period</Th>
                            {(bnbActualsFilters.viewType === 'listing' ? bnbFilterOptions.listings : bnbFilterOptions.channels).flatMap(header => 
                              bnbActualsFilters.selectedAmounts.map(amount => {
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
                            )}
                            {bnbActualsFilters.selectedAmounts.map(amount => {
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
                            bnbActualsFilters.viewType === 'listing' ? bnbListingData : bnbChannelData,
                            bnbActualsFilters.viewType as 'listing' | 'channel',
                            bnbActualsFilters.displayFormat,
                            bnbActualsFilters.selectedAmounts
                          ).rows}
                        </Tbody>
                      </Table>
                    </TableContainer>
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
                        <Text color="white" fontSize="sm">Administration</Text>
                        <Select
                          value={checkRefFilters.administration}
                          onChange={(e) => {
                            const newAdmin = e.target.value;
                            setCheckRefFilters(prev => ({
                              ...prev, 
                              administration: newAdmin,
                              ledger: 'all',
                              referenceNumber: 'all'
                            }));
                            fetchFilterOptions(newAdmin, 'all');
                          }}
                          bg="gray.600"
                          color="white"
                          size="sm"
                          w="200px"
                        >
                          <option value="all">All</option>
                          {filterOptions.administrations.map((admin, index) => (
                            <option key={index} value={admin}>{admin}</option>
                          ))}
                        </Select>
                      </VStack>
                      <VStack spacing={1}>
                        <Text color="white" fontSize="sm">Ledger</Text>
                        <Select
                          value={checkRefFilters.ledger}
                          onChange={(e) => {
                            const newLedger = e.target.value;
                            setCheckRefFilters(prev => ({
                              ...prev, 
                              ledger: newLedger,
                              referenceNumber: 'all'
                            }));
                            fetchFilterOptions(checkRefFilters.administration, newLedger);
                          }}
                          bg="gray.600"
                          color="white"
                          size="sm"
                          w="200px"
                        >
                          <option value="all">All Ledgers</option>
                          {filterOptions.ledgers.map((ledger, index) => (
                            <option key={index} value={ledger}>{ledger}</option>
                          ))}
                        </Select>
                      </VStack>
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
                          {filterOptions.references.map((reference, index) => (
                            <option key={index} value={reference}>{reference}</option>
                          ))}
                        </Select>
                      </VStack>
                      <Button colorScheme="orange" onClick={fetchCheckRefData} isLoading={loading} size="sm">
                        Check References
                      </Button>
                    </HStack>
                  </CardBody>
                </Card>

                {/* Table 1: Reference Summary */}
                <Card bg="gray.700">
                  <CardHeader pb={2}>
                    <Heading size="md" color="white">Table 1: Reference Summary</Heading>
                  </CardHeader>
                  <CardBody pt={0}>
                    <TableContainer>
                      <Table size="sm" variant="simple" style={{borderCollapse: 'collapse'}}>
                        <Thead>
                          <Tr>
                            <Th color="white" width="200px" border="none">Reference Number</Th>
                            <Th color="white" width="120px" textAlign="right" border="none">Amount</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {refSummaryData.map((row, index) => (
                            <Tr 
                              key={index} 
                              cursor="pointer" 
                              _hover={{ bg: "gray.600" }}
                              bg={selectedReference === row.ReferenceNumber ? "gray.600" : "transparent"}
                              onClick={() => fetchReferenceDetails(row.ReferenceNumber)}
                            >
                              <Td color="white" fontSize="sm" border="none" py={1}>
                                {row.ReferenceNumber}
                              </Td>
                              <Td color="white" fontSize="sm" textAlign="right" border="none" py={1}>
                                {formatAmount(Number(row.total_amount) || 0, '2dec')}
                              </Td>
                            </Tr>
                          ))}
                          {/* Total Row */}
                          <Tr bg="orange.600">
                            <Td color="white" fontSize="sm" fontWeight="bold" border="none" py={1}>
                              TOTAL
                            </Td>
                            <Td color="white" fontSize="sm" textAlign="right" fontWeight="bold" border="none" py={1}>
                              {formatAmount(
                                refSummaryData.reduce((sum, row) => sum + (Number(row.total_amount) || 0), 0),
                                '2dec'
                              )}
                            </Td>
                          </Tr>
                        </Tbody>
                      </Table>
                    </TableContainer>
                  </CardBody>
                </Card>

                {/* Table 2: Transaction Details */}
                {selectedReferenceDetails.length > 0 && (
                  <Card bg="gray.700">
                    <CardHeader pb={2}>
                      <Heading size="md" color="white">Table 2: Transaction Details</Heading>
                    </CardHeader>
                    <CardBody pt={0}>
                      <TableContainer>
                        <Table size="sm" variant="simple" style={{borderCollapse: 'collapse'}}>
                          <Thead>
                            <Tr>
                              <Th color="white" width="120px" border="none">Transaction Date</Th>
                              <Th color="white" width="120px" border="none">Transaction Number</Th>
                              <Th color="white" width="100px" textAlign="right" border="none">Amount</Th>
                              <Th color="white" border="none">Description</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {selectedReferenceDetails.map((row, index) => (
                              <Tr key={index}>
                                <Td color="white" fontSize="sm" border="none" py={1}>
                                  {new Date(row.TransactionDate).toISOString().split('T')[0]}
                                </Td>
                                <Td color="white" fontSize="sm" border="none" py={1}>
                                  {row.TransactionNumber}
                                </Td>
                                <Td color="white" fontSize="sm" textAlign="right" border="none" py={1}>
                                  {formatAmount(Number(row.Amount) || 0, '2dec')}
                                </Td>
                                <Td color="white" fontSize="sm" border="none" py={1}>
                                  {row.TransactionDescription}
                                </Td>
                              </Tr>
                            ))}
                            {/* Total Row */}
                            <Tr bg="orange.600">
                              <Td color="white" fontSize="sm" fontWeight="bold" border="none" py={1} colSpan={2}>
                                TOTAL
                              </Td>
                              <Td color="white" fontSize="sm" textAlign="right" fontWeight="bold" border="none" py={1}>
                                {formatAmount(
                                  selectedReferenceDetails.reduce((sum, row) => sum + (Number(row.Amount) || 0), 0),
                                  '2dec'
                                )}
                              </Td>
                              <Td border="none"></Td>
                            </Tr>
                          </Tbody>
                        </Table>
                      </TableContainer>
                    </CardBody>
                  </Card>
                )}
              </VStack>
            </TabPanel>

            {/* BTW aangifte Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                <Card bg="gray.700">
                  <CardBody>
                    <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
                      <GridItem>
                        <Text color="white" mb={2}>Administration</Text>
                        <Select
                          value={btwFilters.administration}
                          onChange={(e) => setBtwFilters(prev => ({...prev, administration: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                        >
                          <option value="GoodwinSolutions">GoodwinSolutions</option>
                          <option value="PeterPrive">PeterPrive</option>
                        </Select>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Year</Text>
                        <Select
                          value={btwFilters.year}
                          onChange={(e) => setBtwFilters(prev => ({...prev, year: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                        >
                          {[2023, 2024, 2025, 2026].map(year => (
                            <option key={year} value={year.toString()}>{year}</option>
                          ))}
                        </Select>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Quarter</Text>
                        <Select
                          value={btwFilters.quarter}
                          onChange={(e) => setBtwFilters(prev => ({...prev, quarter: e.target.value}))}
                          bg="gray.600"
                          color="white"
                          size="sm"
                        >
                          <option value="1">Q1</option>
                          <option value="2">Q2</option>
                          <option value="3">Q3</option>
                          <option value="4">Q4</option>
                        </Select>
                      </GridItem>
                      <GridItem>
                        <Button 
                          colorScheme="orange" 
                          onClick={generateBtwReport} 
                          isLoading={btwLoading}
                          size="sm"
                        >
                          Generate BTW Report
                        </Button>
                      </GridItem>
                    </Grid>
                  </CardBody>
                </Card>

                {/* BTW Report Display */}
                {btwReport && (
                  <Card bg="gray.700">
                    <CardHeader>
                      <HStack justify="space-between">
                        <Heading size="md" color="white">BTW Declaration Report</Heading>
                        {btwTransaction && (
                          <Button 
                            colorScheme="green" 
                            onClick={saveBtwTransaction}
                            isLoading={btwLoading}
                            size="sm"
                          >
                            Save Transaction & Upload Report
                          </Button>
                        )}
                      </HStack>
                    </CardHeader>
                    <CardBody>
                      <Box 
                        bg="white" 
                        p={4} 
                        borderRadius="md" 
                        maxH="600px" 
                        overflowY="auto"
                        dangerouslySetInnerHTML={{ __html: btwReport }}
                      />
                    </CardBody>
                  </Card>
                )}

                {/* Transaction Preview */}
                {btwTransaction && (
                  <Card bg="gray.700">
                    <CardHeader>
                      <Heading size="md" color="white">Transaction Preview</Heading>
                    </CardHeader>
                    <CardBody>
                      <Grid templateColumns="repeat(2, 1fr)" gap={4}>
                        <GridItem>
                          <Text color="white" fontSize="sm"><strong>Transaction Number:</strong> {btwTransaction.TransactionNumber}</Text>
                        </GridItem>
                        <GridItem>
                          <Text color="white" fontSize="sm"><strong>Date:</strong> {btwTransaction.TransactionDate}</Text>
                        </GridItem>
                        <GridItem colSpan={2}>
                          <Text color="white" fontSize="sm"><strong>Description:</strong> {btwTransaction.TransactionDescription}</Text>
                        </GridItem>
                        <GridItem>
                          <Text color="white" fontSize="sm"><strong>Amount:</strong> €{Math.round(Number(btwTransaction.TransactionAmount)).toLocaleString('nl-NL')}</Text>
                        </GridItem>
                        <GridItem>
                          <Text color="white" fontSize="sm"><strong>Administration:</strong> {btwTransaction.Administration}</Text>
                        </GridItem>
                        <GridItem>
                          <Text color="white" fontSize="sm"><strong>Debet:</strong> {btwTransaction.Debet}</Text>
                        </GridItem>
                        <GridItem>
                          <Text color="white" fontSize="sm"><strong>Credit:</strong> {btwTransaction.Credit}</Text>
                        </GridItem>
                        <GridItem colSpan={2}>
                          <Text color="white" fontSize="sm"><strong>Reference:</strong> {btwTransaction.ReferenceNumber}</Text>
                        </GridItem>
                      </Grid>
                    </CardBody>
                  </Card>
                )}

                {/* Instructions */}
                {!btwReport && (
                  <Card bg="gray.700">
                    <CardBody>
                      <VStack spacing={3} align="start">
                        <Heading size="md" color="white">BTW Declaration Instructions</Heading>
                        <Text color="white" fontSize="sm">
                          1. Select the administration, year, and quarter for the BTW declaration
                        </Text>
                        <Text color="white" fontSize="sm">
                          2. Click "Generate BTW Report" to create the declaration based on your financial data
                        </Text>
                        <Text color="white" fontSize="sm">
                          3. Review the generated report and transaction details
                        </Text>
                        <Text color="white" fontSize="sm">
                          4. Click "Save Transaction & Upload Report" to save the BTW transaction and upload the report to Google Drive
                        </Text>
                        <Text color="gray.400" fontSize="xs">
                          The system will automatically calculate BTW amounts based on accounts 2010, 2020, and 2021.
                        </Text>
                      </VStack>
                    </CardBody>
                  </Card>
                )}
              </VStack>
            </TabPanel>

            {/* View ReferenceNumber Tab */}
            <TabPanel>
              <VStack spacing={4} align="stretch">
                <Card bg="gray.700">
                  <CardBody>
                    <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
                      <GridItem>
                        <Text color="white" mb={2}>Administration</Text>
                        <Select
                          value={refAnalysisFilters.administration}
                          onChange={(e) => setRefAnalysisFilters(prev => ({...prev, administration: e.target.value}))}
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
                            {refAnalysisFilters.years.length > 0 ? refAnalysisFilters.years.join(', ') : 'Select years...'}
                          </MenuButton>
                          <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
                            {availableYears.map(year => (
                              <MenuItem key={year} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
                                <Checkbox
                                  isChecked={refAnalysisFilters.years.includes(year)}
                                  onChange={(e) => {
                                    const isChecked = e.target.checked;
                                    setRefAnalysisFilters(prev => ({
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
                        <Text color="white" mb={2}>Reference Number (Regex)</Text>
                        <Input
                          value={refAnalysisFilters.referenceNumber}
                          onChange={(e) => setRefAnalysisFilters(prev => ({...prev, referenceNumber: e.target.value}))}
                          placeholder="Enter regex pattern or select from list"
                          bg="gray.600"
                          color="white"
                          size="sm"
                          list="reference-list"
                        />
                        <datalist id="reference-list">
                          {availableReferences.map((ref, index) => (
                            <option key={index} value={ref} />
                          ))}
                        </datalist>
                      </GridItem>
                      <GridItem>
                        <Text color="white" mb={2}>Accounts</Text>
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
                            {refAnalysisFilters.accounts.length > 0 ? `${refAnalysisFilters.accounts.length} selected` : 'Select accounts...'}
                          </MenuButton>
                          <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
                            {availableRefAccounts.map(account => (
                              <MenuItem key={account.Reknum} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
                                <Checkbox
                                  isChecked={refAnalysisFilters.accounts.includes(account.Reknum)}
                                  onChange={(e) => {
                                    const isChecked = e.target.checked;
                                    setRefAnalysisFilters(prev => ({
                                      ...prev,
                                      accounts: isChecked 
                                        ? [...prev.accounts, account.Reknum]
                                        : prev.accounts.filter(a => a !== account.Reknum)
                                    }));
                                  }}
                                  colorScheme="orange"
                                >
                                  <Text color="white" ml={2}>{account.Reknum} - {account.AccountName}</Text>
                                </Checkbox>
                              </MenuItem>
                            ))}
                          </MenuList>
                        </Menu>
                      </GridItem>
                      <GridItem>
                        <Button 
                          colorScheme="orange" 
                          onClick={fetchReferenceAnalysis} 
                          isLoading={refAnalysisLoading}
                          size="sm"
                        >
                          Analyze Reference
                        </Button>
                      </GridItem>
                    </Grid>
                  </CardBody>
                </Card>

                {/* Trend Chart */}
                {refTrendData.length > 0 && (
                  <Card bg="gray.700">
                    <CardHeader>
                      <Heading size="md" color="white">Expense Trend by Quarter</Heading>
                    </CardHeader>
                    <CardBody>
                      <ResponsiveContainer width="100%" height={400}>
                        <LineChart
                          data={refTrendData.map(item => ({
                            period: `${item.jaar}-Q${item.kwartaal}`,
                            amount: Math.abs(Number(item.total_amount)),
                            label: `€${Math.abs(Number(item.total_amount)).toLocaleString('nl-NL', {minimumFractionDigits: 0})}`
                          }))}
                          margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="period" tick={{fill: 'white'}} />
                          <YAxis tick={{fill: 'white'}} />
                          <Tooltip formatter={(value) => [`€${Number(value).toLocaleString('nl-NL')}`, 'Amount']} />
                          <Line 
                            type="monotone" 
                            dataKey="amount" 
                            stroke="#f56500" 
                            strokeWidth={3}
                            dot={{ fill: '#f56500', strokeWidth: 2, r: 6 }}
                          />
                          {/* Add labels on top of each point */}
                          {refTrendData.map((item, index) => {
                            const x = (index / (refTrendData.length - 1)) * 100;
                            return (
                              <text
                                key={index}
                                x={`${x}%`}
                                y="15"
                                textAnchor="middle"
                                fill="white"
                                fontSize="12"
                              >
                                €{Math.abs(Number(item.total_amount)).toLocaleString('nl-NL', {minimumFractionDigits: 0})}
                              </text>
                            );
                          })}
                        </LineChart>
                      </ResponsiveContainer>
                    </CardBody>
                  </Card>
                )}

                {/* Transactions Table */}
                {refAnalysisData.length > 0 && (
                  <Card bg="gray.700">
                    <CardHeader>
                      <Heading size="md" color="white">Transactions ({refAnalysisData.length})</Heading>
                    </CardHeader>
                    <CardBody>
                      <TableContainer maxH="600px" overflowY="auto">
                        <Table size="sm" variant="simple">
                          <Thead position="sticky" top={0} bg="gray.700" zIndex={1}>
                            <Tr>
                              <Th color="white">Date</Th>
                              <Th color="white">Description</Th>
                              <Th color="white" isNumeric>Amount</Th>
                              <Th color="white">Account</Th>
                              <Th color="white">Reference</Th>
                              <Th color="white">Administration</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {refAnalysisData.map((row, index) => (
                              <Tr key={index}>
                                <Td color="white" fontSize="sm">
                                  {new Date(row.TransactionDate).toLocaleDateString('nl-NL')}
                                </Td>
                                <Td color="white" fontSize="sm" maxW="300px" isTruncated title={row.TransactionDescription}>
                                  {row.TransactionDescription}
                                </Td>
                                <Td color="white" fontSize="sm" isNumeric>
                                  €{Number(row.Amount).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                                </Td>
                                <Td color="white" fontSize="sm">
                                  {row.Reknum} - {row.AccountName}
                                </Td>
                                <Td color="white" fontSize="sm" maxW="150px" isTruncated title={row.ReferenceNumber}>
                                  {row.ReferenceNumber}
                                </Td>
                                <Td color="white" fontSize="sm">
                                  {row.Administration}
                                </Td>
                              </Tr>
                            ))}
                          </Tbody>
                        </Table>
                      </TableContainer>
                      
                      {/* Summary */}
                      <Box mt={4} p={3} bg="gray.600" borderRadius="md">
                        <Text color="white" fontWeight="bold">
                          Total: €{refAnalysisData.reduce((sum, row) => sum + Math.abs(Number(row.Amount)), 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                        </Text>
                      </Box>
                    </CardBody>
                  </Card>
                )}

                {/* Instructions */}
                {refAnalysisData.length === 0 && !refAnalysisLoading && (
                  <Card bg="gray.700">
                    <CardBody>
                      <VStack spacing={3} align="start">
                        <Heading size="md" color="white">Reference Number Analysis Instructions</Heading>
                        <Text color="white" fontSize="sm">
                          1. Select administration (or All for combined analysis)
                        </Text>
                        <Text color="white" fontSize="sm">
                          2. Choose one or more years to include in the analysis
                        </Text>
                        <Text color="white" fontSize="sm">
                          3. Enter a reference number or regex pattern (e.g., "AMZN" or ".*Amazon.*")
                        </Text>
                        <Text color="white" fontSize="sm">
                          4. Optionally filter by specific accounts
                        </Text>
                        <Text color="white" fontSize="sm">
                          5. Click "Analyze Reference" to view trends and transactions
                        </Text>
                        <Text color="gray.400" fontSize="xs">
                          The trend chart shows quarterly spending patterns with amounts displayed above each data point.
                        </Text>
                      </VStack>
                    </CardBody>
                  </Card>
                )}
              </VStack>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
};

export default MyAdminReports;