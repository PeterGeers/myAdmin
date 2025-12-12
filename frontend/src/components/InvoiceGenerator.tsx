import React, { useState } from 'react';
import {
  Box, Button, Heading, VStack, Input, FormControl, FormLabel,
  Alert, AlertIcon, HStack
} from '@chakra-ui/react';

const InvoiceGenerator: React.FC = () => {
  const [companyName, setCompanyName] = useState('Intratuin');
  const [filename, setFilename] = useState('Intratuin 202502.jpg');
  const [totalAmount, setTotalAmount] = useState('193.29');
  const [vatAmount, setVatAmount] = useState('33.55');
  const [date, setDate] = useState('13-05-2025');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const generateInvoice = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/invoice/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: companyName,
          filename: filename,
          total_amount: parseFloat(totalAmount),
          vat_amount: parseFloat(vatAmount),
          date: date
        })
      });

      const data = await response.json();

      if (data.success) {
        setMessage(`Kassabon gegenereerd: ${data.filename}`);
        // Download the file
        window.open(`/api/invoice/download/${data.filename}`, '_blank');
      } else {
        setMessage(`Fout: ${data.error}`);
      }
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
        >
          Genereer Kassabon
        </Button>
      </VStack>
    </Box>
  );
};

export default InvoiceGenerator;
