import React, { useState, useEffect } from 'react';
import { ChakraProvider, Box, VStack, Heading, Button, HStack, Text, Badge } from '@chakra-ui/react';
import PDFUploadForm from './components/PDFUploadForm';

import BankingProcessor from './components/BankingProcessor';
import STRProcessor from './components/STRProcessor';
import STRInvoice from './components/STRInvoice';
import STRPricing from './components/STRPricing';
import MyAdminReports from './components/myAdminReports';
import theme from './theme';

type PageType = 'menu' | 'pdf' | 'banking' | 'str' | 'str-invoice' | 'str-pricing' | 'powerbi';

function App() {
  const [currentPage, setCurrentPage] = useState<PageType>('menu');
  const [status, setStatus] = useState({ mode: 'Production', database: '', folder: '' });

  useEffect(() => {
    fetch('/api/status')
      .then(res => res.json())
      .then(data => setStatus(data))
      .catch(() => setStatus({ mode: 'Production', database: 'finance', folder: 'Facturen' }));
  }, []);

  const renderPage = () => {
    switch (currentPage) {
      case 'pdf':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack justify="space-between">
                <HStack>
                  <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                  <Heading color="orange.400" size="lg">📄 Import Invoices</Heading>
                </HStack>
                <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
              </HStack>
            </Box>
            <PDFUploadForm />
          </Box>
        );

      case 'banking':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack justify="space-between">
                <HStack>
                  <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                  <Heading color="orange.400" size="lg">🏦 Import Banking Accounts</Heading>
                </HStack>
                <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
              </HStack>
            </Box>
            <BankingProcessor />
          </Box>
        );
      case 'str':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack justify="space-between">
                <HStack>
                  <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                  <Heading color="orange.400" size="lg">🏠 Import STR Bookings</Heading>
                </HStack>
                <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
              </HStack>
            </Box>
            <STRProcessor />
          </Box>
        );
      case 'str-invoice':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack justify="space-between">
                <HStack>
                  <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                  <Heading color="orange.400" size="lg">🧾 STR Invoice Generator</Heading>
                </HStack>
                <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
              </HStack>
            </Box>
            <STRInvoice />
          </Box>
        );

      case 'str-pricing':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack justify="space-between">
                <HStack>
                  <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                  <Heading color="orange.400" size="lg">💰 STR Pricing Model</Heading>
                </HStack>
                <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
              </HStack>
            </Box>
            <STRPricing />
          </Box>
        );

      case 'powerbi':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack justify="space-between">
                <HStack>
                  <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                  <Heading color="orange.400" size="lg">📈 myAdmin Reports</Heading>
                </HStack>
                <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
              </HStack>
            </Box>
            <MyAdminReports />
          </Box>
        );

      default:
        return (
          <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center">
            <VStack spacing={8}>
              <VStack spacing={2}>
                <Heading color="orange.400" size="2xl">myAdmin Dashboard</Heading>
                <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'} fontSize="md" px={3} py={1}>
                  {status.mode} Mode
                </Badge>
              </VStack>
              <Text color="gray.300" fontSize="lg">Select a component to get started</Text>
              
              <VStack spacing={4} w="400px">
                <Button size="lg" w="full" colorScheme="orange" onClick={() => setCurrentPage('pdf')}>
                  📄 Import Invoices
                </Button>

                <Button size="lg" w="full" colorScheme="red" onClick={() => setCurrentPage('banking')}>
                  🏦 Import Banking Accounts
                </Button>
                <Button size="lg" w="full" colorScheme="blue" onClick={() => setCurrentPage('str')}>
                  🏠 Import STR Bookings
                </Button>
                <Button size="lg" w="full" colorScheme="teal" onClick={() => setCurrentPage('str-invoice')}>
                  🧾 STR Invoice Generator
                </Button>
                <Button size="lg" w="full" colorScheme="green" onClick={() => setCurrentPage('str-pricing')}>
                  💰 STR Pricing Model
                </Button>

                <Button size="lg" w="full" colorScheme="purple" onClick={() => setCurrentPage('powerbi')}>
                  📈 myAdmin Reports
                </Button>
              </VStack>
            </VStack>
          </Box>
        );
    }
  };

  return (
    <ChakraProvider theme={theme}>
      {renderPage()}
    </ChakraProvider>
  );
}

export default App;