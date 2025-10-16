import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Heading, Select, Button, Text,
  Card, CardBody, CardHeader, Grid, GridItem, Input,
  Alert, AlertIcon, Spinner
} from '@chakra-ui/react';
import { Chart } from 'react-google-charts';

interface ReportData {
  labels: string[];
  values: number[];
  total: number;
}

interface FilterState {
  dateFrom: string;
  dateTo: string;
  category: string;
  administration: string;
}

const ReportingDashboard: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    dateFrom: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    dateTo: new Date().toISOString().split('T')[0],
    category: 'all',
    administration: 'all'
  });

  const fetchReportData = async () => {
    setLoading(true);
    setError('');
    
    try {
      const params = new URLSearchParams({
        dateFrom: filters.dateFrom,
        dateTo: filters.dateTo,
        category: filters.category,
        administration: filters.administration
      });
      
      const response = await fetch(`http://localhost:5000/api/reports/financial-summary?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setReportData(data.data);
      } else {
        setError(data.error || 'Failed to fetch report data');
      }
    } catch (err) {
      setError('Network error occurred');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReportData();
  }, []);

  const handleFilterChange = (field: keyof FilterState, value: string) => {
    setFilters(prev => ({ ...prev, [field]: value }));
  };

  const exportToCsv = () => {
    if (!reportData) return;
    
    const csvContent = [
      ['Category', 'Amount'],
      ...reportData.labels.map((label, index) => [label, reportData.values[index]])
    ].map(row => row.join(',')).join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `financial-report-${filters.dateFrom}-${filters.dateTo}.csv`;
    a.click();
  };

  const chartData = reportData ? [
    ['Category', 'Amount'],
    ...reportData.labels.map((label, index) => [label, reportData.values[index]])
  ] : [];

  const chartOptions = {
    title: 'Financial Summary',
    backgroundColor: 'transparent',
    titleTextStyle: { color: '#fff' },
    legendTextStyle: { color: '#fff' },
    hAxis: { textStyle: { color: '#fff' } },
    vAxis: { textStyle: { color: '#fff' } }
  };

  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">

        {/* Filters */}
        <Card bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">Filters</Heading>
          </CardHeader>
          <CardBody>
            <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
              <GridItem>
                <Text color="white" mb={2}>From Date</Text>
                <Input
                  type="date"
                  value={filters.dateFrom}
                  onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
                  bg="gray.600"
                  color="white"
                />
              </GridItem>
              <GridItem>
                <Text color="white" mb={2}>To Date</Text>
                <Input
                  type="date"
                  value={filters.dateTo}
                  onChange={(e) => handleFilterChange('dateTo', e.target.value)}
                  bg="gray.600"
                  color="white"
                />
              </GridItem>
              <GridItem>
                <Text color="white" mb={2}>Category</Text>
                <Select
                  value={filters.category}
                  onChange={(e) => handleFilterChange('category', e.target.value)}
                  bg="gray.600"
                  color="white"
                >
                  <option value="all">All Categories</option>
                  <option value="income">Income</option>
                  <option value="expense">Expenses</option>
                  <option value="vat">VAT</option>
                </Select>
              </GridItem>
              <GridItem>
                <Text color="white" mb={2}>Administration</Text>
                <Select
                  value={filters.administration}
                  onChange={(e) => handleFilterChange('administration', e.target.value)}
                  bg="gray.600"
                  color="white"
                >
                  <option value="all">All</option>
                  <option value="GoodwinSolutions">GoodwinSolutions</option>
                  <option value="PeterPrive">PeterPrive</option>
                </Select>
              </GridItem>
            </Grid>
            <HStack mt={4}>
              <Button colorScheme="orange" onClick={fetchReportData} isLoading={loading}>
                Update Report
              </Button>
              <Button variant="outline" onClick={exportToCsv} isDisabled={!reportData}>
                Export CSV
              </Button>
            </HStack>
          </CardBody>
        </Card>

        {/* Error Display */}
        {error && (
          <Alert status="error">
            <AlertIcon />
            {error}
          </Alert>
        )}

        {/* Loading */}
        {loading && (
          <Box textAlign="center">
            <Spinner size="xl" color="orange.400" />
            <Text color="white" mt={2}>Loading report data...</Text>
          </Box>
        )}

        {/* Charts */}
        {reportData && !loading && (
          <Grid templateColumns="repeat(auto-fit, minmax(400px, 1fr))" gap={6}>
            <GridItem>
              <Card bg="gray.700">
                <CardHeader>
                  <Heading size="md" color="white">Bar Chart</Heading>
                </CardHeader>
                <CardBody>
                  <Chart
                    chartType="ColumnChart"
                    data={chartData}
                    options={chartOptions}
                    width="100%"
                    height="300px"
                  />
                </CardBody>
              </Card>
            </GridItem>
            
            <GridItem>
              <Card bg="gray.700">
                <CardHeader>
                  <Heading size="md" color="white">Pie Chart</Heading>
                </CardHeader>
                <CardBody>
                  <Chart
                    chartType="PieChart"
                    data={chartData}
                    options={{
                      ...chartOptions,
                      title: 'Distribution'
                    }}
                    width="100%"
                    height="300px"
                  />
                </CardBody>
              </Card>
            </GridItem>
          </Grid>
        )}

        {/* Summary */}
        {reportData && (
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">Summary</Heading>
            </CardHeader>
            <CardBody>
              <Text color="white" fontSize="lg">
                Total Amount: <Text as="span" color="orange.400" fontWeight="bold">
                  €{reportData.total.toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
                </Text>
              </Text>
              <Text color="gray.300" mt={2}>
                Period: {filters.dateFrom} to {filters.dateTo}
              </Text>
            </CardBody>
          </Card>
        )}
      </VStack>
    </Box>
  );
};

export default ReportingDashboard;