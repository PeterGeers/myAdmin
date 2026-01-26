import React, { useState } from 'react';
import {
  Box, Button, Heading, VStack, Input, FormControl, FormLabel,
  Alert, AlertIcon, HStack
} from '@chakra-ui/react';
import { generateReceipt, downloadReceipt } from '../utils/receiptGenerator';
import { useTenant } from '../context/TenantContext';

const InvoiceGenerator: React.FC = () => {
  const { currentTenant } = useTenant();
  const [companyName, setCompanyName] = useState('Intratuin');
  const [filename, setFilename] = useState('Intratuin 202502.jpg');
  const [totalAmount, setTotalAmount] = useState('193.29');
  const [vatAmount, setVatAmount] = useState('33.55');
  const [date, setDate] = useState('13-05-2025');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const generateInvoice = () => {
    if (!currentTenant) {
      setMessage('Error: No tenant selected. Please select a tenant first.');
      return;
    }
    
    try {
      setLoading(true);
      
      const canvas = generateReceipt({
        supplierName: companyName,
        transactionDate: date,
        totalAmount: parseFloat(totalAmount),
        vatAmount: parseFloat(vatAmount)
      });
      
      downloadReceipt(canvas, filename);
      setMessage(`Kassabon gedownload: ${filename}`);
    } catch (error) {
      setMessage(`Fout: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box w="100%" p={4}>
      <Heading size="lg" mb={6} color="white">Kassabon Generator</Heading>

      {message && (
        <Alert status={message.includes('Fout') ? 'error' : 'success'} mb={4}>
          <AlertIcon />
          {message}
        </Alert>
      )}

      <VStack align="stretch" spacing={4} maxW="500px">
        <FormControl>
          <FormLabel color="white">Bedrijfsnaam</FormLabel>
          <Input
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            bg="white"
            placeholder="Intratuin"
          />
        </FormControl>

        <FormControl>
          <FormLabel color="white">Bestandsnaam</FormLabel>
          <Input
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            bg="white"
            placeholder="Intratuin 202502.jpg"
          />
        </FormControl>

        <FormControl>
          <FormLabel color="white">Datum (DD-MM-YYYY)</FormLabel>
          <Input
            value={date}
            onChange={(e) => setDate(e.target.value)}
            bg="white"
            placeholder="13-05-2025"
          />
        </FormControl>

        <HStack>
          <FormControl>
            <FormLabel color="white">Totaalbedrag (€)</FormLabel>
            <Input
              type="number"
              step="0.01"
              value={totalAmount}
              onChange={(e) => setTotalAmount(e.target.value)}
              bg="white"
            />
          </FormControl>

          <FormControl>
            <FormLabel color="white">BTW-bedrag (€)</FormLabel>
            <Input
              type="number"
              step="0.01"
              value={vatAmount}
              onChange={(e) => setVatAmount(e.target.value)}
              bg="white"
            />
          </FormControl>
        </HStack>

        <Button
          colorScheme="orange"
          onClick={generateInvoice}
          isLoading={loading}
          size="lg"
          isDisabled={!currentTenant}
        >
          Genereer Kassabon
        </Button>
      </VStack>
    </Box>
  );
};

export default InvoiceGenerator;
