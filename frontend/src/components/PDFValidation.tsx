import React, { useState } from 'react';
import {
  Box, Button, Table, Thead, Tbody, Tr, Th, Td, Text, VStack, HStack,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter,
  Input, FormControl, FormLabel, useDisclosure, Alert, AlertIcon, Spinner,
  Progress, Stat, StatLabel, StatNumber, StatGroup, Select
} from '@chakra-ui/react';
import { authenticatedGet, authenticatedPost } from '../services/apiService';
import { useTenant } from '../context/TenantContext';

interface ValidationRecord {
  status: string;
  record: {
    ID: number;
    TransactionNumber: string;
    TransactionDate: string;
    TransactionDescription: string;
    TransactionAmount: number;
    ReferenceNumber: string;
    Ref3: string;
    Ref4: string;
    Administration: string;
  };
  error?: string;
  new_url?: string;
}

interface UpdateFormData {
  old_ref3: string;
  old_ref4: string;
  reference_number: string;
  ref3: string;
  ref4: string;
}

const PDFValidation: React.FC = () => {
  const { currentTenant } = useTenant();
  const [validationResults, setValidationResults] = useState<ValidationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState({ total: 0, ok: 0, failed: 0 });
  const [selectedYear, setSelectedYear] = useState('2025');
  // Remove selectedAdmin state as we'll use currentTenant instead
  const [availableAdmins, setAvailableAdmins] = useState<string[]>([]);
  const [updateForm, setUpdateForm] = useState<UpdateFormData>({ old_ref3: '', old_ref4: '', reference_number: '', ref3: '', ref4: '' });
  const { isOpen, onOpen, onClose } = useDisclosure();

  const loadAdministrations = React.useCallback(async () => {
    if (!currentTenant) return;
    
    try {
      const response = await authenticatedGet(`/api/pdf/get-administrations?year=${selectedYear}`, { tenant: currentTenant });
      const data = await response.json();
      if (data.success) {
        setAvailableAdmins(data.administrations);
      }
    } catch (error) {
      console.error('Error loading administrations:', error);
    }
  }, [selectedYear, currentTenant]);

  const validateUrls = async () => {
    if (!currentTenant) {
      console.error('No tenant selected');
      return;
    }
    
    setLoading(true);
    setProgress({ total: 0, ok: 0, failed: 0 });
    setValidationResults([]);
    
    try {
      // Get the auth token
      const { getCurrentAuthTokens } = await import('../services/authService');
      const tokens = await getCurrentAuthTokens();
      
      if (!tokens?.idToken) {
        console.error('No authentication token available');
        setLoading(false);
        return;
      }
      
      // EventSource with auth token and tenant in URL
      const eventSource = new EventSource(
        `http://localhost:5000/api/pdf/validate-urls-stream?year=${selectedYear}&administration=${currentTenant}&token=${encodeURIComponent(tokens.idToken)}`
      );
      
      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'progress') {
          setProgress({
            total: data.total,
            ok: data.ok_count,
            failed: data.failed_count
          });
        } else if (data.type === 'complete') {
          setValidationResults(data.validation_results);
          setProgress({
            total: data.total_records,
            ok: data.ok_count,
            failed: data.failed_count
          });
          eventSource.close();
          setLoading(false);
        } else if (data.type === 'error') {
          console.error('Validation failed:', data.error);
          eventSource.close();
          setLoading(false);
        }
      };
      
      eventSource.onerror = () => {
        eventSource.close();
        setLoading(false);
      };
      
    } catch (error) {
      console.error('Error validating URLs:', error);
      setLoading(false);
    }
  };

  // Load administrations when year or tenant changes
  React.useEffect(() => {
    loadAdministrations();
  }, [selectedYear, loadAdministrations]);

  const openUpdateModal = (record: ValidationRecord['record']) => {
    setUpdateForm({
      old_ref3: record.Ref3 || '',
      old_ref4: record.Ref4 || '',
      reference_number: record.ReferenceNumber || '',
      ref3: record.Ref3 || '',
      ref4: record.Ref4 || ''
    });
    onOpen();
  };

  const revalidateUrl = async (newUrl: string, oldUrl: string) => {
    try {
      const response = await authenticatedGet(`/api/pdf/validate-single-url?url=${encodeURIComponent(newUrl)}`, { tenant: currentTenant || undefined });
      const data = await response.json();
      
      if (data.success) {
        if (data.status === 'ok') {
          // Remove all records with the old URL (now fixed)
          setValidationResults(prev => 
            prev.filter(result => result.record.Ref3 !== oldUrl)
          );
        } else {
          // Update status to show new validation result
          setValidationResults(prev => 
            prev.map(result => 
              result.record.Ref3 === oldUrl 
                ? { ...result, status: data.status, record: { ...result.record, Ref3: newUrl } }
                : result
            )
          );
        }
      }
    } catch (error) {
      console.error('Error re-validating URL:', error);
    }
  };

  const updateRecord = async () => {
    try {
      const response = await authenticatedPost('/api/pdf/update-record', updateForm, { tenant: currentTenant || undefined });
      const data = await response.json();
      
      if (data.success) {
        onClose();
        // Re-validate the new URL to check if it works
        await revalidateUrl(updateForm.ref3, updateForm.old_ref3);
      } else {
        console.error('Update failed:', data.error);
      }
    } catch (error) {
      console.error('Error updating record:', error);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ok': return 'green.500';
      case 'updated': return 'green.500';
      case 'gmail_not_accessible': return 'yellow.500';
      case 'gmail_not_found': return 'red.500';
      case 'gmail_manual_check': return 'yellow.600';
      case 'file_not_found': return 'red.500';
      case 'file_not_in_folder': return 'orange.500';
      case 'missing': return 'red.600';
      case 'error': return 'red.700';
      default: return 'gray.500';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'ok': return 'OK';
      case 'updated': return 'Fixed';
      case 'gmail_not_accessible': return 'Gmail (Not Accessible)';
      case 'gmail_not_found': return 'Gmail Not Found';
      case 'gmail_manual_check': return 'Gmail (Manual Check)';
      case 'file_not_found': return 'File Not Found';
      case 'file_not_in_folder': return 'File Not in Folder';
      case 'missing': return 'Missing';
      case 'error': return 'Error';
      default: return status;
    }
  };

  return (
    <Box p={6} bg="gray.900" minH="100vh" color="white">
      <VStack spacing={6} align="stretch">
        <HStack>
          <Select 
            value={selectedYear} 
            onChange={(e) => setSelectedYear(e.target.value)}
            width="120px"
            bg="gray.700"
            color="white"
          >
            <option value="2025">2025</option>
            <option value="2024">2024</option>
            <option value="2023">2023</option>
            <option value="2022">2022</option>
            <option value="2021">2021</option>
            <option value="2020">2020</option>
            <option value="2019">2019</option>
            <option value="2018">2018</option>
            <option value="2017">2017</option>
            <option value="2016">2016</option>
            <option value="2015">2015</option>
            <option value="all">All Years</option>
          </Select>
          <Text color="gray.300" minW="150px">
            Tenant: {currentTenant || 'No tenant selected'}
          </Text>
          <Button 
            colorScheme="orange" 
            onClick={validateUrls} 
            isLoading={loading}
            isDisabled={!currentTenant}
          >
            Validate PDF URLs
          </Button>
          {validationResults.length > 0 && (
            <Button 
              colorScheme="blue" 
              onClick={validateUrls} 
              isLoading={loading}
              isDisabled={!currentTenant}
            >
              Refresh Results
            </Button>
          )}
          {progress.total > 0 && (
            <Text color="gray.300">
              Processed {progress.total} records - {progress.ok} OK, {progress.failed} issues
            </Text>
          )}
        </HStack>

        {loading && (
          <Box textAlign="center">
            <Spinner size="lg" color="orange.500" />
            <Text mt={2} color="gray.300">
              Validating URLs... {progress.total > 0 ? `${progress.ok + progress.failed}/${progress.total}` : ''}
            </Text>
            {progress.total > 0 && (
              <Progress 
                value={(progress.ok + progress.failed) / progress.total * 100} 
                colorScheme="orange" 
                size="lg" 
                mt={2}
                width="300px"
                mx="auto"
              />
            )}
          </Box>
        )}

        {progress.total > 0 && (
          <Box>
            <StatGroup bg="gray.800" p={4} borderRadius="md">
              <Stat>
                <StatLabel color="gray.300">Total Records</StatLabel>
                <StatNumber color="white">{progress.total}</StatNumber>
              </Stat>
              <Stat>
                <StatLabel color="gray.300">Valid URLs</StatLabel>
                <StatNumber color="green.400">{progress.ok}</StatNumber>
              </Stat>
              <Stat>
                <StatLabel color="gray.300">Issues Found</StatLabel>
                <StatNumber color="red.400">{progress.failed}</StatNumber>
              </Stat>
            </StatGroup>
            <Progress 
              value={progress.total > 0 ? ((progress.ok + progress.failed) / progress.total) * 100 : 0} 
              colorScheme="orange" 
              size="lg" 
              mt={2}
            />
          </Box>
        )}

        {validationResults.length > 0 && (
          <Box overflowX="auto">
            <Table variant="simple" bg="gray.800" borderRadius="md">
              <Thead>
                <Tr>
                  <Th color="orange.400">Status</Th>

                  <Th color="orange.400">Transaction Number</Th>
                  <Th color="orange.400">Date</Th>
                  <Th color="orange.400">Description</Th>
                  <Th color="orange.400">Amount</Th>
                  <Th color="orange.400">Reference</Th>
                  <Th color="orange.400">Ref3 (URL)</Th>
                  <Th color="orange.400">Ref4 (Document)</Th>
                  <Th color="orange.400">Administration</Th>
                  <Th color="orange.400">Actions</Th>
                </Tr>
              </Thead>
              <Tbody>
                {validationResults.map((result, index) => (
                  <Tr key={index}>
                    <Td>
                      <Text color={getStatusColor(result.status)} fontWeight="bold">
                        {getStatusText(result.status)}
                      </Text>
                    </Td>

                    <Td>{result.record.TransactionNumber}</Td>
                    <Td>{result.record.TransactionDate}</Td>
                    <Td maxW="200px" isTruncated>{result.record.TransactionDescription}</Td>
                    <Td>{result.record.TransactionAmount}</Td>
                    <Td>{result.record.ReferenceNumber}</Td>
                    <Td maxW="200px" isTruncated>{result.record.Ref3}</Td>
                    <Td>{result.record.Ref4}</Td>
                    <Td>{result.record.Administration}</Td>
                    <Td>
                      <Button size="sm" colorScheme="blue" onClick={() => openUpdateModal(result.record)}>
                        Update
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>
        )}

        {validationResults.length === 0 && !loading && (
          <Alert status="info" bg="gray.800" color="white">
            <AlertIcon />
            Click "Validate PDF URLs" to check for missing or broken Google Drive links
          </Alert>
        )}
      </VStack>

      <Modal isOpen={isOpen} onClose={onClose} size="lg">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>Update Record</ModalHeader>
          <ModalBody>
            <VStack spacing={4}>
              <FormControl>
                <FormLabel>Reference Number</FormLabel>
                <Input
                  value={updateForm.reference_number}
                  onChange={(e) => setUpdateForm({...updateForm, reference_number: e.target.value})}
                  bg="gray.700"
                  color="white"
                />
              </FormControl>
              <FormControl>
                <FormLabel>Document URL (Ref3)</FormLabel>
                <Input
                  value={updateForm.ref3}
                  onChange={(e) => setUpdateForm({...updateForm, ref3: e.target.value})}
                  bg="gray.700"
                  color="white"
                />
              </FormControl>
              <FormControl>
                <FormLabel>Document Name (Ref4)</FormLabel>
                <Input
                  value={updateForm.ref4}
                  onChange={(e) => setUpdateForm({...updateForm, ref4: e.target.value})}
                  bg="gray.700"
                  color="white"
                />
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button colorScheme="blue" mr={3} onClick={updateRecord}>
              Update
            </Button>
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
};

export default PDFValidation;