import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Box, Heading, Text, Button, VStack } from '@chakra-ui/react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      // Note: Using hardcoded strings as class components can't use useTranslation hook
      // Translations: nl="Er is een fout opgetreden" / en="Something went wrong"
      const currentLang = localStorage.getItem('i18nextLng') || 'en';
      const errorTitle = currentLang === 'nl' ? 'Er is een fout opgetreden' : 'Something went wrong';
      const errorMessage = currentLang === 'nl' ? 'Er is een onverwachte fout opgetreden' : 'An unexpected error occurred';
      const tryAgainText = currentLang === 'nl' ? 'Opnieuw proberen' : 'Try Again';
      
      return (
        <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center">
          <VStack spacing={4} textAlign="center" p={8}>
            <Heading color="red.400" size="lg">⚠️ {errorTitle}</Heading>
            <Text color="gray.300">{errorMessage}</Text>
            <Button 
              colorScheme="orange" 
              onClick={() => this.setState({ hasError: false, error: undefined })}
            >
              {tryAgainText}
            </Button>
          </VStack>
        </Box>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;