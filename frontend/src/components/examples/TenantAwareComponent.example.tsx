/**
 * Example Component: Tenant-Aware Data Processing
 * 
 * This example demonstrates the proper implementation of tenant handling
 * using the standardized utilities. Use this as a reference for implementing
 * tenant-aware functionality in your components.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  Text,
  VStack,
  Alert,
  AlertIcon,
  Input,
  HStack
} from '@chakra-ui/react';

// Import tenant utilities
import { useTenant } from '../../context/TenantContext';
import { useTenantValidation } from '../../hooks/useTenantValidation';
import { tenantAwareGet, tenantAwarePost } from '../../services/tenantApiService';

// Types
interface ExampleData {
  id: string;
  name: string;
  administration: string;
  value: number;
}

interface LookupData {
  bank_accounts: Array<{
    rekeningNummer: string;
    administration: string;
  }>;
}

/**
 * Example component demonstrating tenant-aware patterns
 */
const TenantAwareComponent: React.FC = () => {
  // 1. Use tenant context
  const { currentTenant } = useTenant();
  
  // 2. Use tenant validation utilities
  const { 
    validateTenantSelection, 
    validateBankingDataOwnership,
    validateAdministrationAccess 
  } = useTenantValidation();
  
  // Component state
  const [data, setData] = useState<ExampleData[]>([]);
  const [lookupData, setLookupData] = useState<LookupData>({ bank_accounts: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [newItemName, setNewItemName] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  /**
   * Fetch tenant-scoped data
   */
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      
      // Validate tenant selection before API call
      validateTenantSelection();
      
      // Use tenant-aware API call
      const response = await tenantAwareGet('/api/example/data');
      const result = await response.json();
      
      setData(result.data || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, [validateTenantSelection]);

  /**
   * Fetch lookup data for validation
   */
  const fetchLookupData = useCallback(async () => {
    try {
      const response = await tenantAwareGet('/api/example/lookup');
      const result = await response.json();
      setLookupData(result);
    } catch (err) {
      console.error('Failed to fetch lookup data:', err);
    }
  }, []);

  /**
   * Handle file upload with tenant validation
   */
  const handleFileUpload = async () => {
    if (!selectedFile) return;
    
    try {
      setLoading(true);
      setError('');
      
      // 1. Validate tenant selection
      validateTenantSelection();
      
      // 2. Extract IBAN from file (simplified example)
      const fileContent = await selectedFile.text();
      const lines = fileContent.split('\n');
      const iban = lines[1]?.split(',')[0] || ''; // Assume CSV format
      
      // 3. Validate data ownership
      const validation = validateBankingDataOwnership(
        iban, 
        lookupData, 
        selectedFile.name
      );
      
      if (!validation.isValid) {
        setError(validation.reason || 'Validation failed');
        return;
      }
      
      // 4. Process file (tenant context automatically included)
      const formData = new FormData();
      formData.append('file', selectedFile);
      
      const response = await fetch('/api/example/upload', {
        method: 'POST',
        body: formData,
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'X-Tenant': currentTenant || ''
        }
      });
      
      if (!response.ok) {
        throw new Error('Upload failed');
      }
      
      // 5. Refresh data after successful upload
      await fetchData();
      setSelectedFile(null);
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Add new item with tenant validation
   */
  const handleAddItem = async () => {
    if (!newItemName.trim()) return;
    
    try {
      setLoading(true);
      setError('');
      
      // Validate tenant selection
      validateTenantSelection();
      
      // Create new item (tenant context automatically included)
      const newItem = {
        name: newItemName,
        value: Math.random() * 1000
      };
      
      await tenantAwarePost('/api/example/items', newItem);
      
      // Refresh data
      await fetchData();
      setNewItemName('');
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add item');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Handle administration access validation
   */
  const handleAdminOperation = async (administration: string) => {
    try {
      // Validate administration access
      const validation = validateAdministrationAccess(administration);
      
      if (!validation.isValid) {
        setError(validation.reason || 'Access denied');
        return;
      }
      
      // Proceed with admin operation
      console.log(`Admin operation allowed for: ${administration}`);
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Operation failed');
    }
  };

  // 3. Auto-refresh on tenant change (REQUIRED)
  useEffect(() => {
    if (currentTenant) {
      console.log(`Tenant changed to: ${currentTenant}`);
      fetchData();
      fetchLookupData();
      
      // Clear any previous errors
      setError('');
    }
  }, [currentTenant, fetchData, fetchLookupData]);

  // Initial data load
  useEffect(() => {
    if (currentTenant) {
      fetchData();
      fetchLookupData();
    }
  }, []);

  return (
    <Box p={6}>
      <Card>
        <CardHeader>
          <Heading size="md">Tenant-Aware Component Example</Heading>
          <Text color="gray.600">
            Current Tenant: {currentTenant || 'None selected'}
          </Text>
        </CardHeader>
        
        <CardBody>
          <VStack spacing={4} align="stretch">
            
            {/* Error Display */}
            {error && (
              <Alert status="error">
                <AlertIcon />
                {error}
              </Alert>
            )}
            
            {/* File Upload Section */}
            <Box>
              <Heading size="sm" mb={2}>File Upload (with Tenant Validation)</Heading>
              <HStack>
                <Input
                  type="file"
                  accept=".csv,.tsv"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                />
                <Button
                  onClick={handleFileUpload}
                  isLoading={loading}
                  isDisabled={!selectedFile || !currentTenant}
                  colorScheme="blue"
                >
                  Upload
                </Button>
              </HStack>
            </Box>
            
            {/* Add Item Section */}
            <Box>
              <Heading size="sm" mb={2}>Add New Item</Heading>
              <HStack>
                <Input
                  placeholder="Item name"
                  value={newItemName}
                  onChange={(e) => setNewItemName(e.target.value)}
                />
                <Button
                  onClick={handleAddItem}
                  isLoading={loading}
                  isDisabled={!newItemName.trim() || !currentTenant}
                  colorScheme="green"
                >
                  Add
                </Button>
              </HStack>
            </Box>
            
            {/* Admin Operations */}
            <Box>
              <Heading size="sm" mb={2}>Administration Access Test</Heading>
              <HStack>
                <Button
                  onClick={() => handleAdminOperation(currentTenant || '')}
                  size="sm"
                  colorScheme="orange"
                  isDisabled={!currentTenant}
                >
                  Test Current Tenant
                </Button>
                <Button
                  onClick={() => handleAdminOperation('UnauthorizedTenant')}
                  size="sm"
                  colorScheme="red"
                >
                  Test Unauthorized
                </Button>
              </HStack>
            </Box>
            
            {/* Data Display */}
            <Box>
              <Heading size="sm" mb={2}>Tenant Data ({data.length} items)</Heading>
              {loading ? (
                <Text>Loading...</Text>
              ) : data.length > 0 ? (
                <VStack align="stretch" spacing={2}>
                  {data.slice(0, 5).map((item) => (
                    <Box key={item.id} p={2} bg="gray.50" borderRadius="md">
                      <Text fontWeight="bold">{item.name}</Text>
                      <Text fontSize="sm" color="gray.600">
                        Admin: {item.administration} | Value: {item.value.toFixed(2)}
                      </Text>
                    </Box>
                  ))}
                  {data.length > 5 && (
                    <Text fontSize="sm" color="gray.500">
                      ... and {data.length - 5} more items
                    </Text>
                  )}
                </VStack>
              ) : (
                <Text color="gray.500">No data available</Text>
              )}
            </Box>
            
            {/* Refresh Button */}
            <Button
              onClick={fetchData}
              isLoading={loading}
              isDisabled={!currentTenant}
              variant="outline"
            >
              Refresh Data
            </Button>
            
          </VStack>
        </CardBody>
      </Card>
    </Box>
  );
};

export default TenantAwareComponent;