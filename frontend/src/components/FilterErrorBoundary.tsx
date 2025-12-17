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
              ⚠️ Filter Error
            </Text>
            <Text color="red.700" fontSize="sm">
              The filter component encountered an error and cannot be displayed properly.
            </Text>
            <Text color="red.600" fontSize="xs">
              Error: {this.state.error?.message || 'Unknown error'}
            </Text>
            <Button
              size="sm"
              colorScheme="red"
              variant="outline"
              onClick={this.handleRetry}
              alignSelf="flex-start"
            >
              Try Again
            </Button>
          </VStack>
        </Box>
      );
    }

    return this.props.children;
  }
}

export default FilterErrorBoundary;