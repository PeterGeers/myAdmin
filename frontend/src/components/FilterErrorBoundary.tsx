import { Box, Button, Text, VStack } from '@chakra-ui/react';
import React from 'react';

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

interface FilterErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ComponentType<{ error: Error; retry: () => void }>;
}

class FilterErrorBoundary extends React.Component<FilterErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: FilterErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    this.setState({
      error,
      errorInfo
    });

    // Log error for debugging
    console.error('Filter Error Boundary caught an error:', error, errorInfo);
  }

  handleRetry = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null
    });
  };

  render() {
    if (this.state.hasError) {
      // Custom fallback component if provided
      if (this.props.fallback) {
        const FallbackComponent = this.props.fallback;
        return <FallbackComponent error={this.state.error!} retry={this.handleRetry} />;
      }

      // Note: Using hardcoded strings as class components can't use useTranslation hook
      // Translations: nl="Filter Fout" / en="Filter Error"
      const currentLang = localStorage.getItem('i18nextLng') || 'en';
      const filterErrorTitle = currentLang === 'nl' ? 'Filter Fout' : 'Filter Error';
      const filterErrorDesc = currentLang === 'nl' 
        ? 'Het filtercomponent heeft een fout aangetroffen en kan niet correct worden weergegeven.'
        : 'The filter component encountered an error and cannot be displayed properly.';
      const errorLabel = currentLang === 'nl' ? 'Fout' : 'Error';
      const unknownError = currentLang === 'nl' ? 'Onbekende fout' : 'Unknown error';
      const tryAgainText = currentLang === 'nl' ? 'Opnieuw proberen' : 'Try Again';

      // Default error UI
      return (
        <Box
          p={4}
          bg="red.50"
          borderRadius="md"
          border="1px solid"
          borderColor="red.200"
          role="alert"
          aria-live="assertive"
        >
          <VStack spacing={3} align="stretch">
            <Text color="red.800" fontWeight="bold" fontSize="sm">
              ⚠️ {filterErrorTitle}
            </Text>
            <Text color="red.700" fontSize="sm">
              {filterErrorDesc}
            </Text>
            <Text color="red.600" fontSize="xs">
              {errorLabel}: {this.state.error?.message || unknownError}
            </Text>
            <Button
              size="sm"
              colorScheme="red"
              variant="outline"
              onClick={this.handleRetry}
              alignSelf="flex-start"
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

export default FilterErrorBoundary;