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
  Text,
  VStack
} from '@chakra-ui/react';
import { tenantAwareGet, tenantAwarePost, requireTenant } from '../../services/tenantApiService';
import { useTenant } from '../../context/TenantContext';
import { FilterPanel } from '../filters/FilterPanel';

const BtwReport: React.FC = () => {
  const { currentTenant } = useTenant();
  
  // Simplified state - no administration filter (uses tenant context)
  const [selectedYear, setSelectedYear] = useState<string>(new Date().getFullYear().toString());
  const [selectedQuarter, setSelectedQuarter] = useState<string>('1');
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
        {
          administration: currentTenant,
          year: selectedYear,
          quarter: selectedQuarter
        }
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
        const filename = `BTW_${currentTenant}_${selectedYear}_Q${selectedQuarter}.html`;
        
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

      <Card bg="gray.700">
        <CardBody>
          <FilterPanel
            layout="horizontal"
            size="sm"
            spacing={4}
            filters={[
              {
                type: 'single',
                label: 'Year',
                options: btwAvailableYears,
                value: selectedYear,
                onChange: (value) => setSelectedYear(value as string),
                placeholder: 'Select year',
                isLoading: btwLoading,
              },
              {
                type: 'single',
                label: 'Quarter',
                options: ['1', '2', '3', '4'],
                value: selectedQuarter,
                onChange: (value) => setSelectedQuarter(value as string),
                placeholder: 'Select quarter',
                getOptionLabel: (q) => `Q${q}`,
              },
            ]}
          />
          <Button 
            colorScheme="orange" 
            onClick={generateBtwReport} 
            isLoading={btwLoading}
            isDisabled={!currentTenant}
            size="sm"
            mt={4}
          >
            Generate BTW Report
          </Button>
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
