import React, { useState } from 'react';
import { ChakraProvider, Box, VStack, Heading, Button, HStack, Text } from '@chakra-ui/react';
import PDFUploadForm from './components/PDFUploadForm';
import BankingProcessor from './components/BankingProcessor';
import STRProcessor from './components/STRProcessor';
import ReportingDashboard from './components/ReportingDashboard';
import PowerBIReports from './components/PowerBIReports';
import theme from './theme';

type PageType = 'menu' | 'pdf' | 'banking' | 'str' | 'reporting' | 'powerbi';

function App() {
  const [currentPage, setCurrentPage] = useState<PageType>('menu');

  const renderPage = () => {
    switch (currentPage) {
      case 'pdf':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack>
                <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                <Heading color="orange.400" size="lg">📄 PDF Transaction Processor</Heading>
              </HStack>
            </Box>
            <PDFUploadForm />
          </Box>
        );
      case 'banking':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack>
                <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                <Heading color="orange.400" size="lg">🏦 Banking Processor</Heading>
              </HStack>
            </Box>
            <BankingProcessor />
          </Box>
        );
      case 'str':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack>
                <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                <Heading color="orange.400" size="lg">🏠 STR Processor</Heading>
              </HStack>
            </Box>
            <STRProcessor />
          </Box>
        );
      case 'reporting':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack>
                <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                <Heading color="orange.400" size="lg">📊 Reporting Dashboard</Heading>
              </HStack>
            </Box>
            <ReportingDashboard />
          </Box>
        );
      case 'powerbi':
        return (
          <Box minH="100vh" bg="gray.900">
            <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
              <HStack>
                <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                <Heading color="orange.400" size="lg">📈 PowerBI Reports</Heading>
              </HStack>
            </Box>
            <PowerBIReports />
          </Box>
        );

      default:
        return (
          <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center">
            <VStack spacing={8}>
              <Heading color="orange.400" size="2xl">myAdmin Dashboard</Heading>
              <Text color="gray.300" fontSize="lg">Select a component to get started</Text>
              
              <VStack spacing={4} w="400px">
                <Button size="lg" w="full" colorScheme="orange" onClick={() => setCurrentPage('pdf')}>
                  📄 PDF Transaction Processor
                </Button>
                <Button size="lg" w="full" colorScheme="red" onClick={() => setCurrentPage('banking')}>
                  🏦 Banking Processor
                </Button>
                <Button size="lg" w="full" colorScheme="blue" onClick={() => setCurrentPage('str')}>
                  🏠 STR Processor
                </Button>
                <Button size="lg" w="full" colorScheme="green" onClick={() => setCurrentPage('reporting')}>
                  📊 Reporting Dashboard
                </Button>
                <Button size="lg" w="full" colorScheme="purple" onClick={() => setCurrentPage('powerbi')}>
                  📈 PowerBI Reports
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