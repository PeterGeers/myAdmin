import React, { useState, useRef } from 'react';
import { Box, Text, Progress, VStack, Input } from '@chakra-ui/react';
import { processMissingInvoices } from '../utils/missingInvoicesProcessor';

const MissingInvoices: React.FC = () => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsProcessing(true);
    setProgress(0);
    setStatus('Starting process...');

    try {
      await processMissingInvoices(file, (progress, message) => {
        setProgress(progress);
        setStatus(message);
      });
      setStatus('Process completed successfully!');
    } catch (error) {
      setStatus(`Error: ${error}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <Box p={6}>
      <VStack spacing={4} align="stretch">
        <Text fontSize="xl" fontWeight="bold">Missing Invoices Processor</Text>
        
        <Input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={handleFileUpload}
          disabled={isProcessing}
        />
        
        <Text fontSize="sm" color="gray.600">
          Upload missing_invoices.csv file to process
        </Text>

        {isProcessing && (
          <>
            <Progress value={progress} colorScheme="blue" />
            <Text>{status}</Text>
          </>
        )}
        
        {!isProcessing && status && (
          <Text color={status.includes('Error') ? 'red.500' : 'green.500'}>
            {status}
          </Text>
        )}
      </VStack>
    </Box>
  );
};

export default MissingInvoices;