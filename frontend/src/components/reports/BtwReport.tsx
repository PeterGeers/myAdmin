import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Grid,
  GridItem,
  Heading,
  HStack,
  Select,
  Text,
  VStack
} from '@chakra-ui/react';
import { buildApiUrl } from '../../config';
import { authenticatedGet, authenticatedPost } from '../../services/apiService';
import { tenantAwareGet, tenantAwarePost, requireTenant } from '../../services/tenantApiService';
import { useTenant } from '../../context/TenantContext';
import UnifiedAdminYearFilter from '../UnifiedAdminYearFilter';
import { createBtwFilterAdapter } from '../UnifiedAdminYearFilterAdapters';

const BtwReport: React.FC = () => {
  const { currentTenant } = useTenant();
  
  const [btwFilters, setBtwFilters] = useState({
    administration: currentTenant || 'GoodwinSolutions',
    year: new Date().getFullYear().toString(),
    quarter: '1'
  });
  const [btwAvailableYears, setBtwAvailableYears] = useState<string[]>([]);
  const [btwReport, setBtwReport] = useState<string>('');
  const [btwTransaction, setBtwTransaction] = useState<any>(null);
  const [btwLoading, setBtwLoading] = useState(false);

  const fetchBtwAvailableYears = async () => {
    try {
      const response = await tenantAwareGet('/api/reports/available-years');
      const data = await response.json();
      if (data.success) {
        setBtwAvailableYears(data.years);
      }
    } catch (err) {
      console.error('Error fetching BTW available years:', err);
    }
  };

  const generateBtwReport = async () => {
    // Validate tenant selection before processing
    try {
      requireTenant();
    } catch (error) {
      console.error('Tenant validation failed:', error);
      alert('Error: No tenant selected. Please select a tenant first.');
      return;
    }

    setBtwLoading(true);
    try {
      const response = await tenantAwarePost(
        '/api/btw/generate-report',
        btwFilters
      );
      
      const data = await response.json();
      
      if (data.success) {
        setBtwReport(data.html_report);
        setBtwTransaction(data.transaction);
      } else {
        console.error('BTW report generation failed:', data.error);
        alert('Failed to generate BTW report: ' + data.error);
      }
    } catch (err) {
      console.error('Error generating BTW report:', err);
      alert('Error generating BTW report: ' + err);
    } finally {
      setBtwLoading(false);
    }
  };

  const saveBtwTransaction = async () => {
    if (!btwTransaction) return;
    
    // Validate tenant selection before processing
    try {
      requireTenant();
    } catch (error) {
      console.error('Tenant validation failed:', error);
      alert('Error: No tenant selected. Please select a tenant first.');
      return;
    }
    
    setBtwLoading(true);
    try {
      const response = await tenantAwarePost(
        '/api/btw/save-transaction',
        { transaction: btwTransaction }
      );
      
      const data = await response.json();
      
      if (data.success) {
        const filename = `BTW_${btwFilters.administration}_${btwFilters.year}_Q${btwFilters.quarter}.html`;
        
        const uploadResponse = await tenantAwarePost(
          '/api/btw/upload-report',
          { 
            html_content: btwReport, 
            filename: filename 
          }
        );
        
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

  useEffect(() => {
    fetchBtwAvailableYears();
  }, []);

  // Auto-refresh on tenant change
  useEffect(() => {
    if (currentTenant) {
      // Update filters with new tenant
      setBtwFilters(prev => ({
        ...prev,
        administration: currentTenant
      }));
      
      // Clear previous tenant data
      setBtwReport('');
      setBtwTransaction(null);
      
      // Refresh available years for new tenant
      fetchBtwAvailableYears();
    }
  }, [currentTenant]);

  return (
    <VStack spacing={4} align="stretch">
      {!currentTenant && (
        <Alert status="warning">
          <AlertIcon />
          No tenant selected. Please select a tenant first to generate BTW reports.
        </Alert>
      )}

      <UnifiedAdminYearFilter
        {...createBtwFilterAdapter(btwFilters, setBtwFilters, btwAvailableYears)}
        size="sm"
        isLoading={btwLoading}
      />

      <Card bg="gray.700">
        <CardBody>
          <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
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
                isDisabled={!currentTenant}
                size="sm"
              >
                Generate BTW Report
              </Button>
            </GridItem>
          </Grid>
        </CardBody>
      </Card>

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
                  isDisabled={!currentTenant}
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
              color="black"
              fontSize="sm"
            >
              <div dangerouslySetInnerHTML={{ __html: btwReport }} />
            </Box>
          </CardBody>
        </Card>
      )}

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
  );
};

export default BtwReport;
