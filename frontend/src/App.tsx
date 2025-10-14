import React from 'react';
import { ChakraProvider, Box, Tabs, TabList, TabPanels, Tab, TabPanel, Heading } from '@chakra-ui/react';
import PDFUploadForm from './components/PDFUploadForm';
import BankingProcessor from './components/BankingProcessor';
import STRProcessor from './components/STRProcessor';
import theme from './theme';

function App() {
  return (
    <ChakraProvider theme={theme}>
      <Box p={4} bg="gray.900" minH="100vh">
        <Heading mb={6} color="orange.400" textAlign="center">
          myAdmin - Administrative Tools
        </Heading>
        
        <Tabs variant="enclosed" colorScheme="orange">
          <TabList>
            <Tab>PDF Transaction Processor</Tab>
            <Tab>Banking Processor</Tab>
            <Tab>STR Processor</Tab>
          </TabList>
          
          <TabPanels>
            <TabPanel p={0} pt={4}>
              <PDFUploadForm />
            </TabPanel>
            <TabPanel p={0} pt={4}>
              <BankingProcessor />
            </TabPanel>
            <TabPanel p={0} pt={4}>
              <STRProcessor />
            </TabPanel>
          </TabPanels>
        </Tabs>
      </Box>
    </ChakraProvider>
  );
}

export default App;