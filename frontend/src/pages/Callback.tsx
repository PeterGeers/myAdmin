/**
 * OAuth Callback Handler
 * 
 * Handles the OAuth redirect after Cognito authentication.
 * Displays loading state while Amplify processes the authentication.
 */

import React, { useEffect } from 'react';
import {
  Box,
  VStack,
  Spinner,
  Text,
  Heading
} from '@chakra-ui/react';
import { useAuth } from '../context/AuthContext';

/**
 * Callback Component
 * 
 * This page is shown briefly after OAuth redirect from Cognito.
 * AWS Amplify automatically processes the authorization code and
 * exchanges it for tokens.
 * 
 * Note: This component is currently not used since the app doesn't use
 * React Router. The OAuth callback is handled automatically by Amplify
 * and the AuthContext in App.tsx.
 */
export default function Callback() {
  const { isAuthenticated, loading } = useAuth();

  useEffect(() => {
    // Wait for auth state to be determined
    if (!loading) {
      if (isAuthenticated) {
        // Redirect to dashboard after successful authentication
        window.location.href = '/';
      } else {
        // If not authenticated after callback, show error
        console.error('Authentication failed after callback');
      }
    }
  }, [isAuthenticated, loading]);

  return (
    <Box
      minH="100vh"
      bg="gray.900"
      display="flex"
      alignItems="center"
      justifyContent="center"
    >
      <VStack spacing={6}>
        <Spinner
          thickness="4px"
          speed="0.65s"
          emptyColor="gray.700"
          color="orange.400"
          size="xl"
        />
        <VStack spacing={2}>
          <Heading color="orange.400" size="lg">
            Signing you in...
          </Heading>
          <Text color="gray.400" fontSize="md">
            Please wait while we complete your authentication
          </Text>
        </VStack>
      </VStack>
    </Box>
  );
}
