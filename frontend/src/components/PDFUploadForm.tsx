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
import React from 'react';
import * as Yup from 'yup';
import { useTenant } from '../context/TenantContext';
import { useTenantFunctions } from '../hooks/useTenantFunctions';
import { FieldHelp } from './help';
import AccountSelect from './common/AccountSelect';
import { useAccountLookup } from '../hooks/useAccountLookup';
import DuplicateWarningDialog from './DuplicateWarningDialog';
import InvoiceGenerator from './InvoiceGenerator';
import MissingInvoices from './MissingInvoices';
import PDFValidation from './PDFValidation';
import { usePDFUpload } from '../hooks/usePDFUpload';
import type { UploadFormValues } from '../hooks/usePDFUpload';



const validationSchema = Yup.object({
  file: Yup.mixed().required('File is required'),
  folderId: Yup.string().required('Folder selection is required')
});

const PDFUploadForm: React.FC = () => {
  const { currentTenant } = useTenant();
  const { hasFunction } = useTenantFunctions();
  const { accounts: chartAccounts } = useAccountLookup();
  const {
    loading,
    tenantSwitching,
    message,
    setMessage,
    uploadProgress,
    parsedData,
    vendorData,
    preparedTransactions,
    setPreparedTransactions,
    allFolders,
    filteredFolders,
    searchTerm,
    showCreateFolder,
    setShowCreateFolder,
    newFolderName,
    setNewFolderName,
    showDuplicateDialog,
    duplicateInfo,
    duplicateLoading,
    handleSearch,
    handleSubmit,
    approveTransactions,
    createFolder,
    handleDuplicateContinue,
    handleDuplicateCancel,
  } = usePDFUpload();
  return (
    <Box maxW="800px" mx="auto" p={4}>
      <Tabs variant="enclosed" colorScheme="orange">
        <TabList>
          <Tab color="white">📄 Upload Invoices</Tab>
          <Tab color="white">🔍 Check Invoice Exists</Tab>
          {hasFunction('generate_invoice') && <Tab color="white">🧾 Generate Receipt</Tab>}
          {hasFunction('generate_invoice') && <Tab color="white">📋 Generate Missing Invoices</Tab>}
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
                      {filteredFolders.map((folder, index) => (
                        <option key={`${folder}-${index}`} value={folder} />
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
              <FieldHelp
                tooltip="Uploads the invoice to Google Drive and uses AI to extract date, amount, VAT, and vendor details"
                docsSection="invoices/ai-extraction"
              />

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
                    <AccountSelect 
                      value={transaction.Debet || ''} 
                      accounts={chartAccounts}
                      onChange={(val) => {
                        const updated = [...preparedTransactions];
                        updated[index].Debet = val;
                        setPreparedTransactions(updated);
                      }} 
                    />
                  </Box>
                  <Box flex={1}>
                    <Text fontSize="sm" color="black">Credit:</Text>
                    <AccountSelect 
                      value={transaction.Credit || ''} 
                      accounts={chartAccounts}
                      onChange={(val) => {
                        const updated = [...preparedTransactions];
                        updated[index].Credit = val;
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
          {hasFunction('generate_invoice') && (
            <TabPanel>
              <InvoiceGenerator />
            </TabPanel>
          )}
          {hasFunction('generate_invoice') && (
            <TabPanel>
              <MissingInvoices />
            </TabPanel>
          )}
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