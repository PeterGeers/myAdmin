import {
    Box,
    Button,
    FormControl, FormLabel,
    HStack,
    Input,
    Progress,
    Tab,
    TabList,
    TabPanel,
    TabPanels,
    Tabs,
    Text,
    Textarea,
    VStack
} from '@chakra-ui/react';
import { Form, Formik } from 'formik';
import React, { useEffect, useState } from 'react';
import * as Yup from 'yup';
import { buildApiUrl } from '../config';
import { authenticatedGet, authenticatedPost, authenticatedFormData } from '../services/apiService';
import { useTenant } from '../context/TenantContext';
import DuplicateWarningDialog from './DuplicateWarningDialog';
import InvoiceGenerator from './InvoiceGenerator';
import MissingInvoices from './MissingInvoices';
import PDFValidation from './PDFValidation';



// interface Transaction {
//   date: string;
//   description: string;
//   amount: number;
//   debet: number;
//   credit: number;
// }

// interface Folder {
//   id: string;
//   name: string;
//   url: string;
// }

const validationSchema = Yup.object({
  file: Yup.mixed().required('File is required'),
  folderId: Yup.string().required('Folder selection is required')
});

const PDFUploadForm: React.FC = () => {
  const { currentTenant } = useTenant();
  const [loading, setLoading] = useState(false);
  const [tenantSwitching, setTenantSwitching] = useState(false);
  const [message, setMessage] = useState<string>('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [parsedData, setParsedData] = useState<any>(null);
  const [vendorData, setVendorData] = useState<any>(null);
  // const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [preparedTransactions, setPreparedTransactions] = useState<any[]>([]);
  // const [templateTransactions, setTemplateTransactions] = useState<any[]>([]);
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [allFolders, setAllFolders] = useState<string[]>([]);
  const [filteredFolders, setFilteredFolders] = useState<string[]>([]);
  
  // Duplicate detection state
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false);
  const [duplicateInfo, setDuplicateInfo] = useState<any>(null);
  const [duplicateLoading, setDuplicateLoading] = useState(false);
  const [pendingTransactions, setPendingTransactions] = useState<any[]>([]);

  useEffect(() => {
    fetchFolders();
  }, []);

  // SECURITY: Auto-refresh on tenant change to ensure data isolation
  // Clears all previous tenant data and refreshes folders for new tenant
  useEffect(() => {
    if (currentTenant) {
      setTenantSwitching(true);
      
      // Clear previous tenant data when switching to prevent data leakage
      setParsedData(null);
      setVendorData(null);
      setPreparedTransactions([]);
      setPendingTransactions([]);
      setDuplicateInfo(null);
      setShowDuplicateDialog(false);
      
      // Refresh folders for new tenant
      fetchFolders().finally(() => {
        setTenantSwitching(false);
      });
    }
  }, [currentTenant]);

  const fetchFolders = async () => {
    try {
      const response = await authenticatedGet('/api/folders', { tenant: currentTenant || undefined });
      const data = await response.json();
      setAllFolders(data);
      setFilteredFolders(data);
      setMessage(''); // Clear any previous error messages
    } catch (error) {
      console.error('Error fetching folders:', error);
      setMessage('Error loading folders. Please try refreshing the page.');
    }
  };

  const handleSearch = (value: string, setFieldValue: any) => {
    setSearchTerm(value);
    
    // Check if the value exactly matches a folder name (selected from datalist)
    const exactMatch = allFolders.find(folder => folder === value);
    
    if (exactMatch) {
      // Exact match - user selected from datalist
      setFilteredFolders([exactMatch]);
      setFieldValue('folderId', exactMatch);
    } else {
      // Filter based on search term
      const filtered = value.trim() === '' ? allFolders : allFolders.filter(folder => 
        folder.toLowerCase().includes(value.toLowerCase())
      );
      setFilteredFolders(filtered);
      
      // Auto-select if exactly 1 folder matches
      if (filtered.length === 1) {
        setFieldValue('folderId', filtered[0]);
      } else if (filtered.length === 0) {
        setFieldValue('folderId', '');
      }
    }
  };

  const handleSubmit = async (values: any, formikHelpers?: any) => {
    if (loading) return; // Prevent multiple submissions
    
    // SECURITY: Validate tenant selection before any file processing
    // This prevents cross-tenant data access and ensures data isolation
    if (!currentTenant) {
      setMessage('Error: No tenant selected. Please select a tenant first.');
      return;
    }
    
    if (filteredFolders.length > 1) {
      setMessage('Please narrow down to exactly 1 folder before uploading.');
      return;
    }
    if (filteredFolders.length === 0) {
      setMessage('No folders match your search. Please adjust the filter.');
      return;
    }
    
    // Clear any previous messages
    setMessage('');
    
    setLoading(true);
    const formData = new FormData();
    formData.append('file', values.file);
    formData.append('folderName', values.folderId);

    try {
      const formData = new FormData();
      formData.append('file', values.file);
      formData.append('folderName', values.folderId);
      
      const responseObj = await authenticatedFormData('/api/upload', formData, {
        tenant: currentTenant || undefined,
        onUploadProgress: (progressEvent) => {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total!);
          setUploadProgress(progress);
        }
      });
      
      const response = await responseObj.json();

      console.log('Upload response:', response);
      // Backend returns different structure
      const fileData = {
        name: response.filename,
        url: `/uploads/${response.filename}`,
        folder: response.folder,
        txt: response.extractedText || 'No text extracted'
      };
      setParsedData(fileData);
      setVendorData(response.vendorData);
      
      // Check for duplicate information in prepared transactions
      const preparedTxns = response.preparedTransactions || [];
      
      // Check if any transaction has duplicate_info
      const hasDuplicates = preparedTxns.some((txn: any) => txn.duplicate_info?.has_duplicates);
      
      if (hasDuplicates) {
        // Find the first transaction with duplicate info
        const txnWithDuplicate = preparedTxns.find((txn: any) => txn.duplicate_info?.has_duplicates);
        
        if (txnWithDuplicate && txnWithDuplicate.duplicate_info) {
          // Store pending transactions for later processing
          setPendingTransactions(preparedTxns);
          
          // Format duplicate info for the dialog
          const dupInfo = txnWithDuplicate.duplicate_info;
          const existingTxn = dupInfo.existing_transactions?.[0];
          
          if (existingTxn) {
            setDuplicateInfo({
              existingTransaction: {
                id: existingTxn.ID?.toString() || '',
                transactionDate: existingTxn.TransactionDate || '',
                transactionDescription: existingTxn.TransactionDescription || '',
                transactionAmount: parseFloat(existingTxn.TransactionAmount) || 0,
                debet: existingTxn.Debet || '',
                credit: existingTxn.Credit || '',
                referenceNumber: existingTxn.ReferenceNumber || '',
                ref1: existingTxn.Ref1 || '',
                ref2: existingTxn.Ref2 || '',
                ref3: existingTxn.Ref3 || '',
                ref4: existingTxn.Ref4 || ''
              },
              newTransaction: {
                id: txnWithDuplicate.ID?.toString() || 'new',
                transactionDate: txnWithDuplicate.TransactionDate || '',
                transactionDescription: txnWithDuplicate.TransactionDescription || '',
                transactionAmount: parseFloat(txnWithDuplicate.TransactionAmount) || 0,
                debet: txnWithDuplicate.Debet || '',
                credit: txnWithDuplicate.Credit || '',
                referenceNumber: txnWithDuplicate.ReferenceNumber || '',
                ref1: txnWithDuplicate.Ref1 || '',
                ref2: txnWithDuplicate.Ref2 || '',
                ref3: txnWithDuplicate.Ref3 || '',
                ref4: txnWithDuplicate.Ref4 || ''
              },
              matchCount: dupInfo.duplicate_count || 1
            });
            
            // Show the duplicate warning dialog
            setShowDuplicateDialog(true);
          }
        }
      } else {
        // No duplicates, proceed normally
        setPreparedTransactions(preparedTxns);
      }
      
      console.log('Parsed data set:', fileData);
      console.log('Vendor data set:', response.vendorData);
      console.log('Transactions set:', response.transactions);
    } catch (error: any) {
      console.error('Upload error:', error);
      
      // Check if it's a duplicate detection error (409 status)
      if (error.response?.status === 409 && error.response?.data?.error === 'duplicate_detected') {
        const dupData = error.response.data.duplicate_info;
        
        if (dupData && dupData.existing_transactions && dupData.existing_transactions.length > 0) {
          const existingTxn = dupData.existing_transactions[0];
          
          // Format duplicate info for the dialog
          setDuplicateInfo({
            existingTransaction: {
              id: existingTxn.id?.toString() || '',
              transactionDate: existingTxn.date || '',
              transactionDescription: existingTxn.description || '',
              transactionAmount: parseFloat(existingTxn.amount) || 0,
              debet: '',
              credit: '',
              referenceNumber: values.folderId || '',
              ref1: '',
              ref2: '',
              ref3: existingTxn.file_url || '',
              ref4: existingTxn.filename || ''
            },
            newTransaction: {
              id: 'new',
              transactionDate: existingTxn.date || '',
              transactionDescription: `New upload: ${values.file.name}`,
              transactionAmount: parseFloat(existingTxn.amount) || 0,
              debet: '',
              credit: '',
              referenceNumber: values.folderId || '',
              ref1: '',
              ref2: '',
              ref3: '',
              ref4: values.file.name || ''
            },
            matchCount: dupData.duplicate_count || 1
          });
          
          // Show the duplicate warning dialog
          setShowDuplicateDialog(true);
          setLoading(false);
          return;
        }
        
        // Fallback if duplicate info is not properly formatted
        setMessage(error.response.data.message || 'This file has already been uploaded.');
        setLoading(false);
        return;
      }
      
      // Check if it's a duplicate file error in Google Drive
      if (error.response?.data?.error?.includes('already exists')) {
        const confirmUseExisting = window.confirm(
          `File "${values.file.name}" already exists in Google Drive.\n\n` +
          'Click OK to use the existing file, or Cancel to upload with a new timestamp.'
        );
        
        if (confirmUseExisting) {
          // Retry with useExisting flag
          const retryFormData = new FormData();
          retryFormData.append('file', values.file);
          retryFormData.append('folderName', values.folderId);
          retryFormData.append('useExisting', 'true');
          
          try {
            const retryFormData = new FormData();
            retryFormData.append('file', values.file);
            retryFormData.append('folderName', values.folderId);
            retryFormData.append('useExisting', 'true');
            
            const responseObj = await authenticatedFormData('/api/upload', retryFormData, {
              tenant: currentTenant || undefined,
              onUploadProgress: (progressEvent) => {
                const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total!);
                setUploadProgress(progress);
              }
            });
            
            const response = await responseObj.json();
            
            const fileData = {
              name: response.filename,
              url: `/uploads/${response.filename}`,
              folder: response.folder,
              txt: response.extractedText || 'No text extracted'
            };
            setParsedData(fileData);
            setVendorData(response.vendorData);
            // setTransactions(response.transactions || []);
            setPreparedTransactions(response.preparedTransactions || []);
            // setTemplateTransactions(response.templateTransactions || []);
          } catch (retryError) {
            console.error('Retry upload error:', retryError);
          }
          return;
        }
      }
      
      // Generic error handling for non-duplicate errors
      if (error.response?.status !== 409) {
        setMessage(`Upload failed: ${error.response?.data?.message || error.message || 'Unknown error'}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const approveTransactions = async () => {
    try {
      const responseObj = await authenticatedPost('/api/approve-transactions', {
        transactions: preparedTransactions
      }, { tenant: currentTenant || undefined });
      const response = await responseObj.json();
      alert(response.message);
      setPreparedTransactions([]);
    } catch (error) {
      console.error('Approval error:', error);
      alert('Error saving transactions');
    }
  };

  const createFolder = async () => {
    if (!newFolderName.trim()) return;
    
    try {
      await authenticatedPost('/api/create-folder', {
        folderName: newFolderName
      }, { tenant: currentTenant || undefined });
      
      // Refresh the folders list after creating
      await fetchFolders();
      setNewFolderName('');
      setShowCreateFolder(false);
      alert('Folder created successfully!');
    } catch (error: any) {
      console.error('Create folder error:', error);
      alert(`Error creating folder: ${error.response?.data?.error || error.message}`);
    }
  };

  const handleDuplicateContinue = async () => {
    setDuplicateLoading(true);
    
    try {
      // Log the user's decision to continue
      if (duplicateInfo) {
        await authenticatedPost('/api/log-duplicate-decision', {
          decision: 'continue',
          duplicate_info: {
            existing_transaction_id: duplicateInfo.existingTransaction.id,
            new_transaction: duplicateInfo.newTransaction,
            reference_number: duplicateInfo.newTransaction.referenceNumber,
            transaction_date: duplicateInfo.newTransaction.transactionDate,
            transaction_amount: duplicateInfo.newTransaction.transactionAmount
          }
        }, { tenant: currentTenant || undefined });
      }
      
      // Check if we have pending transactions (old flow) or need to retry upload (new flow)
      if (pendingTransactions.length > 0) {
        // Old flow: proceed with the pending transactions
        setPreparedTransactions(pendingTransactions);
        setPendingTransactions([]);
      } else {
        // New flow: retry the upload with force flag
        // We need to retry the upload - get the file and folder from duplicateInfo
        const folderName = duplicateInfo?.newTransaction?.referenceNumber;
        const fileName = duplicateInfo?.newTransaction?.ref4;
        
        if (folderName && fileName) {
          // Create a file input to get the file again
          const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
          const file = fileInput?.files?.[0];
          
          if (file) {
            // Retry upload with force flag
            const formData = new FormData();
            formData.append('file', file);
            formData.append('folderName', folderName);
            formData.append('forceUpload', 'true');
            
            const responseObj = await authenticatedFormData('/api/upload', formData, {
              tenant: currentTenant || undefined,
              onUploadProgress: (progressEvent) => {
                const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total!);
                setUploadProgress(progress);
              }
            });
            
            const response = await responseObj.json();
            
            // Process the successful response
            const fileData = {
              name: response.filename,
              url: `/uploads/${response.filename}`,
              folder: response.folder,
              txt: response.extractedText || 'No text extracted'
            };
            setParsedData(fileData);
            setVendorData(response.vendorData);
            setPreparedTransactions(response.preparedTransactions || []);
            
            console.log('Force upload successful:', response);
          }
        }
      }
      
      // Close the dialog
      setShowDuplicateDialog(false);
      setDuplicateInfo(null);
    } catch (error) {
      console.error('Error processing duplicate continue:', error);
      alert('Error processing your decision. Please try again.');
    } finally {
      setDuplicateLoading(false);
    }
  };

  const handleDuplicateCancel = async () => {
    setDuplicateLoading(true);
    
    try {
      // Log the user's decision to cancel
      if (duplicateInfo) {
        await authenticatedPost('/api/log-duplicate-decision', {
          decision: 'cancel',
          duplicate_info: {
            existing_transaction_id: duplicateInfo.existingTransaction.id,
            new_transaction: duplicateInfo.newTransaction,
            reference_number: duplicateInfo.newTransaction.referenceNumber,
            transaction_date: duplicateInfo.newTransaction.transactionDate,
            transaction_amount: duplicateInfo.newTransaction.transactionAmount,
            new_file_url: duplicateInfo.newTransaction.ref3,
            existing_file_url: duplicateInfo.existingTransaction.ref3
          }
        }, { tenant: currentTenant || undefined });
      }
      
      // Clear all pending data
      setPendingTransactions([]);
      setParsedData(null);
      setVendorData(null);
      
      // Close the dialog
      setShowDuplicateDialog(false);
      setDuplicateInfo(null);
      
      alert('Import cancelled. The uploaded file has been cleaned up.');
    } catch (error) {
      console.error('Error cancelling duplicate:', error);
      alert('Error cancelling import. Please try again.');
    } finally {
      setDuplicateLoading(false);
    }
  };

  return (
    <Box maxW="800px" mx="auto" p={4}>
      <Tabs variant="enclosed" colorScheme="orange">
        <TabList>
          <Tab color="white">📄 Upload Invoices</Tab>
          <Tab color="white">🔍 Check Invoice Exists</Tab>
          <Tab color="white">🧾 Generate Receipt</Tab>
          <Tab color="white">📋 Generate Missing Invoices</Tab>
        </TabList>

        <TabPanels>
          <TabPanel>
      
      <Formik
        initialValues={{ file: null, folderId: '' }}
        validationSchema={validationSchema}
        onSubmit={handleSubmit}
      >
        {({ setFieldValue, errors, touched, values }) => (
          <Form>
            <VStack spacing={4}>
              {message && (
                <Box p={3} bg={message.startsWith('Error') ? 'red.100' : 'blue.100'} borderRadius="md" w="full">
                  <Text color={message.startsWith('Error') ? 'red.700' : 'blue.700'} fontSize="sm">
                    {message}
                  </Text>
                </Box>
              )}
              
              <FormControl isInvalid={!!(errors.file && touched.file)}>
                <FormLabel>Select File (PDF, JPG, PNG, MHTML, EML)</FormLabel>
                <Input
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,.mhtml,.eml"
                  onChange={(e) => setFieldValue('file', e.target.files?.[0])}
                  bg="orange.500"
                  color="white"
                  borderColor="orange.600"
                />
                {errors.file && touched.file && <Text color="red.500">{errors.file}</Text>}
              </FormControl>

              <FormControl isInvalid={!!(errors.folderId && touched.folderId)}>
                <FormLabel>Select Folder</FormLabel>
                <VStack spacing={2} align="stretch">
                  <HStack>
                    <Input
                      value={(searchTerm || values.folderId || '').toString()}
                      onChange={(e) => {
                        const value = e.target.value || '';
                        setFieldValue('folderId', value);
                        handleSearch(value, setFieldValue);
                      }}
                      placeholder="Type folder name to search and select..."
                      flex={1}
                      list="folder-options"
                      bg="orange.500"
                      color="white"
                      _placeholder={{ color: "orange.100" }}
                      borderColor="orange.600"
                    />
                    <datalist id="folder-options">
                      {filteredFolders.map((folder) => (
                        <option key={folder} value={folder} />
                      ))}
                    </datalist>
                    <Button 
                      onClick={() => { setSearchTerm(''); setFieldValue('folderId', ''); handleSearch('', setFieldValue); }} 
                      size="sm"
                      colorScheme="blue"
                      color="white"
                    >
                      Clear
                    </Button>
                    <Button 
                      onClick={() => setShowCreateFolder(true)} 
                      size="sm"
                      colorScheme="green"
                      color="white"
                      isDisabled={!currentTenant || tenantSwitching}
                    >
                      + New
                    </Button>
                  </HStack>
                  
                  <Text fontSize="sm" color={filteredFolders.length === 1 ? "green.500" : "gray.600"}>
                    {filteredFolders.length === 1 ? "✓ 1 folder selected" : `${filteredFolders.length} folders match`}
                  </Text>
                </VStack>
                {errors.folderId && touched.folderId && <Text color="red.500">{errors.folderId}</Text>}
              </FormControl>

              {showCreateFolder && (
                <Box p={4} border="1px" borderColor="gray.200" borderRadius="md">
                  <Text mb={2}>Create New Folder:</Text>
                  <HStack>
                    <Input
                      value={newFolderName}
                      onChange={(e) => setNewFolderName(e.target.value)}
                      placeholder="Folder name"
                      flex={1}
                    />
                    <Button onClick={createFolder} colorScheme="green" size="sm" isDisabled={!currentTenant}>
                      Create
                    </Button>
                    <Button onClick={() => setShowCreateFolder(false)} size="sm">
                      Cancel
                    </Button>
                  </HStack>
                </Box>
              )}

              <Button 
                type="submit" 
                bg="brand.orange" 
                color="white" 
                _hover={{bg: "#e55a00"}} 
                isLoading={loading || tenantSwitching} 
                loadingText={tenantSwitching ? "Switching tenant..." : (uploadProgress < 100 ? "Uploading..." : "Checking for duplicates...")}
                w="full"
                isDisabled={filteredFolders.length !== 1 || !currentTenant || tenantSwitching}
              >
                Upload & Process {filteredFolders.length !== 1 ? `(${filteredFolders.length} folders)` : ''}
              </Button>

              {loading && (
                <>
                  <Progress value={uploadProgress} w="full" />
                  {uploadProgress === 100 && (
                    <Text fontSize="sm" color="gray.600" textAlign="center">
                      Checking for duplicate invoices...
                    </Text>
                  )}
                </>
              )}
            </VStack>
          </Form>
        )}
      </Formik>

      {parsedData && (
        <Box mt={8} p={6} border="1px" borderColor="gray.200" borderRadius="lg" bg="gray.200">
          <Text fontSize="lg" mb={4} fontWeight="bold" color="black">Parsed PDF Data</Text>
          <VStack spacing={4} align="stretch">
            <Box p={3} bg="white" borderRadius="md">
              <Text fontSize="sm" color="black">File ID:</Text>
              <Text fontWeight="medium" color="black">{parsedData.name}</Text>
            </Box>
            
            <Box p={3} bg="white" borderRadius="md">
              <Text fontSize="sm" color="black">Google Drive URL:</Text>
              <Text 
                as="a" 
                href={parsedData.url} 
                target="_blank" 
                color="blue.500" 
                textDecoration="underline"
              >
                {parsedData.url}
              </Text>
            </Box>
            
            <Box p={3} bg="white" borderRadius="md">
              <Text fontSize="sm" color="black">Folder:</Text>
              <Text fontWeight="medium" color="black">{parsedData.folder}</Text>
            </Box>
            
            <Box p={3} bg="white" borderRadius="md">
              <Text fontSize="sm" color="black">Extracted Text:</Text>
              <Textarea 
                value={parsedData.txt} 
                readOnly 
                rows={8} 
                bg="gray.50"
                color="black"
                resize="vertical"
              />
            </Box>
          </VStack>
        </Box>
      )}

      {vendorData && (
        <Box mt={6} p={6} border="1px" borderColor="blue.200" borderRadius="lg" bg="blue.50">
          <Text fontSize="lg" mb={4} fontWeight="bold" color="blue.800">Parsed Vendor Data</Text>
          <VStack spacing={3} align="stretch">
            <HStack spacing={4}>
              <Box p={3} bg="white" borderRadius="md" flex={1}>
                <Text fontSize="sm" color="black">Folder:</Text>
                <Text fontWeight="medium" color="black">{parsedData?.folder || 'N/A'}</Text>
              </Box>
              <Box p={3} bg="white" borderRadius="md" flex={1}>
                <Text fontSize="sm" color="black">Filename:</Text>
                <Text fontWeight="medium" color="black">{parsedData?.name || 'N/A'}</Text>
              </Box>
            </HStack>
            
            <HStack spacing={4}>
              <Box p={3} bg="white" borderRadius="md" flex={1}>
                <Text fontSize="sm" color="black">Date:</Text>
                <Text fontWeight="medium" color="black">{vendorData.date || 'N/A'}</Text>
              </Box>
              <Box p={3} bg="white" borderRadius="md" flex={1}>
                <Text fontSize="sm" color="black">URL:</Text>
                <Text 
                  as="a" 
                  href={parsedData?.url} 
                  target="_blank" 
                  color="blue.500" 
                  textDecoration="underline"
                  fontSize="sm"
                >
                  {parsedData?.url || 'N/A'}
                </Text>
              </Box>
            </HStack>
            
            <HStack spacing={4}>
              <Box p={3} bg="white" borderRadius="md" flex={1}>
                <Text fontSize="sm" color="black">Total Amount:</Text>
                <Text fontWeight="medium" color="black">€{vendorData.total_amount || '0.00'}</Text>
              </Box>
              <Box p={3} bg="white" borderRadius="md" flex={1}>
                <Text fontSize="sm" color="black">VAT Amount:</Text>
                <Text fontWeight="medium" color="black">€{vendorData.vat_amount || '0.00'}</Text>
              </Box>
            </HStack>
            
            <Box p={3} bg="white" borderRadius="md">
              <Text fontSize="sm" color="black">Description:</Text>
              <Text fontWeight="medium" color="black">{vendorData.description || 'N/A'}</Text>
            </Box>
          </VStack>
        </Box>
      )}

      {preparedTransactions.length > 0 && (
        <Box mt={8} p={6} border="2px" borderColor="green.200" borderRadius="lg" bg="green.50">
          <Text fontSize="lg" mb={4} fontWeight="bold" color="green.800">
            New Transaction Records (Ready for Approval)
          </Text>
          

          
          {preparedTransactions.map((transaction, index) => (
            <Box key={index} p={4} border="1px" borderColor="green.300" bg="white" borderRadius="md" mb={4}>
              <Text fontSize="md" fontWeight="bold" mb={3} color="green.700">
                Record {index + 1} (ID: {transaction.ID})
              </Text>
              
              <VStack spacing={3} align="stretch">
                <HStack spacing={4}>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Transaction Number:</Text>
                    <Input 
                      value={transaction.TransactionNumber || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].TransactionNumber = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Reference Number:</Text>
                    <Input 
                      value={transaction.ReferenceNumber || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].ReferenceNumber = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Date:</Text>
                    <Input 
                      type="date"
                      value={transaction.TransactionDate || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].TransactionDate = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                </HStack>
                
                <Box>
                  <Text fontSize="sm" color="black">Description:</Text>
                  <Input 
                    value={transaction.TransactionDescription || ''} 
                    onChange={(e) => {
                      const updated = [...preparedTransactions];
                      updated[index].TransactionDescription = e.target.value;
                      setPreparedTransactions(updated);
                    }} 
                  />
                </Box>
                
                <HStack spacing={4}>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Amount:</Text>
                    <Input 
                      type="number" 
                      step="0.01"
                      value={transaction.TransactionAmount || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].TransactionAmount = parseFloat(e.target.value);
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Debet:</Text>
                    <Input 
                      value={transaction.Debet || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].Debet = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Credit:</Text>
                    <Input 
                      value={transaction.Credit || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].Credit = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                </HStack>
                
                <HStack spacing={4}>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Ref1:</Text>
                    <Input 
                      value={transaction.Ref1 || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].Ref1 = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Ref2:</Text>
                    <Input 
                      value={transaction.Ref2 || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].Ref2 = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Administration:</Text>
                    <Input 
                      value={transaction.Administration || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].Administration = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                </HStack>
                
                <HStack spacing={4}>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Ref3 (File URL):</Text>
                    <Input 
                      value={transaction.Ref3 || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].Ref3 = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                      fontSize="xs"
                    />
                  </Box>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Ref4 (Filename):</Text>
                    <Input 
                      value={transaction.Ref4 || ''} 
                      onChange={(e) => {
                        const updated = [...preparedTransactions];
                        updated[index].Ref4 = e.target.value;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                </HStack>
              </VStack>
            </Box>
          ))}
          
          <HStack spacing={4} mt={6}>
            <Button colorScheme="green" onClick={approveTransactions} size="lg" isDisabled={!currentTenant}>
              ✓ Approve & Save to Database
            </Button>
            <Button variant="outline" onClick={() => setPreparedTransactions([])}>
              ✗ Cancel
            </Button>
          </HStack>
        </Box>
      )}
          </TabPanel>
          <TabPanel>
            <PDFValidation />
          </TabPanel>
          <TabPanel>
            <InvoiceGenerator />
          </TabPanel>
          <TabPanel>
            <MissingInvoices />
          </TabPanel>
        </TabPanels>
      </Tabs>
      
      {/* Duplicate Warning Dialog */}
      {duplicateInfo && (
        <DuplicateWarningDialog
          isOpen={showDuplicateDialog}
          duplicateInfo={duplicateInfo}
          onContinue={handleDuplicateContinue}
          onCancel={handleDuplicateCancel}
          isLoading={duplicateLoading}
        />
      )}
    </Box>
  );
};

export default PDFUploadForm;