import React, { useState, useEffect } from 'react';
import {
  Box, VStack, FormControl, FormLabel, Input, Select, Button,
  Text, Progress, Textarea, HStack
} from '@chakra-ui/react';
import { Formik, Form, Field } from 'formik';
import * as Yup from 'yup';
import axios from 'axios';



interface Transaction {
  date: string;
  description: string;
  amount: number;
  debet: number;
  credit: number;
}

interface Folder {
  id: string;
  name: string;
  url: string;
}

const validationSchema = Yup.object({
  file: Yup.mixed().required('PDF file is required'),
  folderId: Yup.string().required('Folder selection is required')
});

const PDFUploadForm: React.FC = () => {
  const [folders, setFolders] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [parsedData, setParsedData] = useState<any>(null);
  const [vendorData, setVendorData] = useState<any>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [preparedTransactions, setPreparedTransactions] = useState<any[]>([]);
  const [templateTransactions, setTemplateTransactions] = useState<any[]>([]);
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');

  useEffect(() => {
    fetchFolders();
  }, []);

  const fetchFolders = async () => {
    try {
      const response = await axios.get('http://localhost:5000/api/folders');
      setFolders(response.data);
    } catch (error) {
      console.error('Error fetching folders:', error);
    }
  };

  const handleSubmit = async (values: any, formikHelpers?: any) => {
    setLoading(true);
    const formData = new FormData();
    formData.append('file', values.file);
    formData.append('folderName', values.folderId);

    try {
      const response = await axios.post('http://localhost:5000/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total!);
          setUploadProgress(progress);
        }
      });

      console.log('Upload response:', response.data);
      // Backend returns different structure
      const fileData = {
        name: response.data.filename,
        url: `http://localhost:5000/uploads/${response.data.filename}`,
        folder: response.data.folder,
        txt: response.data.extractedText || 'No text extracted'
      };
      setParsedData(fileData);
      setVendorData(response.data.vendorData);
      setTransactions(response.data.transactions || []);
      setPreparedTransactions(response.data.preparedTransactions || []);
      setTemplateTransactions(response.data.templateTransactions || []);
      console.log('Parsed data set:', fileData);
      console.log('Vendor data set:', response.data.vendorData);
      console.log('Transactions set:', response.data.transactions);
    } catch (error: any) {
      console.error('Upload error:', error);
      
      // Check if it's a duplicate file error
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
            const response = await axios.post('http://localhost:5000/api/upload', retryFormData, {
              headers: { 'Content-Type': 'multipart/form-data' },
              onUploadProgress: (progressEvent) => {
                const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total!);
                setUploadProgress(progress);
              }
            });
            
            const fileData = {
              name: response.data.filename,
              url: `http://localhost:5000/uploads/${response.data.filename}`,
              folder: response.data.folder,
              txt: response.data.extractedText || 'No text extracted'
            };
            setParsedData(fileData);
            setVendorData(response.data.vendorData);
            setTransactions(response.data.transactions || []);
            setPreparedTransactions(response.data.preparedTransactions || []);
            setTemplateTransactions(response.data.templateTransactions || []);
          } catch (retryError) {
            console.error('Retry upload error:', retryError);
          }
          return;
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const approveTransactions = async () => {
    try {
      const response = await axios.post('http://localhost:5000/api/approve-transactions', {
        transactions: preparedTransactions
      });
      alert(response.data.message);
      setPreparedTransactions([]);
    } catch (error) {
      console.error('Approval error:', error);
      alert('Error saving transactions');
    }
  };

  const createFolder = async () => {
    if (!newFolderName.trim()) return;
    
    try {
      await axios.post('http://localhost:5000/api/create-folder', {
        folderName: newFolderName
      });
      
      setFolders([...folders, newFolderName].sort());
      setNewFolderName('');
      setShowCreateFolder(false);
      alert('Folder created successfully!');
    } catch (error) {
      console.error('Create folder error:', error);
      alert('Error creating folder');
    }
  };

  return (
    <Box maxW="800px" mx="auto" p={6}>
      <Text fontSize="2xl" mb={6}>PDF Transaction Processor</Text>
      
      <Formik
        initialValues={{ file: null, folderId: '' }}
        validationSchema={validationSchema}
        onSubmit={handleSubmit}
      >
        {({ setFieldValue, errors, touched }) => (
          <Form>
            <VStack spacing={4}>
              <FormControl isInvalid={!!(errors.file && touched.file)}>
                <FormLabel>Select PDF File</FormLabel>
                <Input
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setFieldValue('file', e.target.files?.[0])}
                />
                {errors.file && touched.file && <Text color="red.500">{errors.file}</Text>}
              </FormControl>

              <FormControl isInvalid={!!(errors.folderId && touched.folderId)}>
                <FormLabel>Select Folder</FormLabel>
                <HStack>
                  <Field as={Select} name="folderId" placeholder="Choose folder" width="58%">
                    {folders.map((folder, index) => (
                      <option key={`${folder}-${index}`} value={folder}>{folder}</option>
                    ))}
                  </Field>
                  <Button onClick={() => setShowCreateFolder(true)} size="sm">
                    + New
                  </Button>
                </HStack>
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
                    <Button onClick={createFolder} colorScheme="green" size="sm">
                      Create
                    </Button>
                    <Button onClick={() => setShowCreateFolder(false)} size="sm">
                      Cancel
                    </Button>
                  </HStack>
                </Box>
              )}

              <Button type="submit" bg="brand.orange" color="white" _hover={{bg: "#e55a00"}} isLoading={loading} w="full">
                Upload & Process
              </Button>

              {loading && <Progress value={uploadProgress} w="full" />}
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
                      value={transaction.TransactionNumber} 
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
                      value={transaction.ReferenceNumber} 
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
                      value={transaction.TransactionDate} 
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
                    value={transaction.TransactionDescription} 
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
                      value={transaction.TransactionAmount} 
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
                      value={transaction.Debet} 
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
                      value={transaction.Credit} 
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
                      value={transaction.Ref1} 
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
                      value={transaction.Ref2} 
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
                      value={transaction.Administration} 
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
                      value={transaction.Ref3} 
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
                      value={transaction.Ref4} 
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
            <Button colorScheme="green" onClick={approveTransactions} size="lg">
              ✓ Approve & Save to Database
            </Button>
            <Button variant="outline" onClick={() => setPreparedTransactions([])}>
              ✗ Cancel
            </Button>
          </HStack>
        </Box>
      )}
    </Box>
  );
};

export default PDFUploadForm;