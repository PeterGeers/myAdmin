import React from 'react';
import { ChakraProvider } from '@chakra-ui/react';
import PDFUploadForm from './components/PDFUploadForm';
import theme from './theme';

function App() {
  return (
    <ChakraProvider theme={theme}>
      <PDFUploadForm />
    </ChakraProvider>
  );
}

export default App;