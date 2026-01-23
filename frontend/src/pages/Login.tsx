/**
 * Login Page Component
 * 
 * Provides authentication interface for myAdmin application.
 * Supports both email/password login and Cognito Hosted UI.
 */

import React, { useState } from 'react';
import {
  Box,
  VStack,
  Heading,
  Button,
  Image,
  Text,
  useToast,
  Container,
  Divider,
  HStack,
  Link,
  Alert,
  AlertIcon,
  AlertDescription
} from '@chakra-ui/react';
import { signInWithRedirect } from 'aws-amplify/auth';

interface LoginProps {
  onLoginSuccess?: () => void;
}

/**
 * Login Page Component
 * 
 * Features:
 * - Cognito Hosted UI integration
 * - Automatic redirect after successful login
 * - Remember me functionality (via Cognito)
 * - Forgot password link
 * - Error handling and user feedback
 */
export default function Login({ onLoginSuccess }: LoginProps) {
  const [isLoading, setIsLoading] = useState(false);
  const toast = useToast();

  /**
   * Handle Cognito Hosted UI login
   * Redirects to Cognito's hosted authentication page
   */
  const handleCognitoLogin = async () => {
    try {
      setIsLoading(true);
      
      // Redirect to Cognito Hosted UI
      await signInWithRedirect();
      
      // Note: User will be redirected away, so we won't reach here
      // The callback will be handled by the app's routing
    } catch (error) {
      console.error('Login error:', error);
      setIsLoading(false);
      
      toast({
        title: 'Login Failed',
        description: error instanceof Error ? error.message : 'Failed to initiate login. Please try again.',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };

  /**
   * Handle forgot password
   * Redirects to Cognito Hosted UI forgot password page
   */
  const handleForgotPassword = () => {
    const cognitoDomain = process.env.REACT_APP_COGNITO_DOMAIN || 'myadmin.auth.eu-west-1.amazoncognito.com';
    const clientId = process.env.REACT_APP_COGNITO_CLIENT_ID || '6sgh53un5ttsojn7o2aj9hi7en';
    const redirectUri = encodeURIComponent(window.location.origin + '/');
    
    const forgotPasswordUrl = `https://${cognitoDomain}/forgotPassword?client_id=${clientId}&redirect_uri=${redirectUri}`;
    window.location.href = forgotPasswordUrl;
  };

  return (
    <Box
      minH="100vh"
      bg="gray.900"
      display="flex"
      alignItems="center"
      justifyContent="center"
      px={4}
    >
      <Container maxW="md">
        <VStack spacing={8} bg="gray.800" p={8} borderRadius="lg" boxShadow="2xl">
          {/* Logo */}
          <Image
            src="/jabaki-logo.png"
            alt="myAdmin Logo"
            maxW="200px"
            mb={4}
          />

          {/* Title */}
          <VStack spacing={2}>
            <Heading color="orange.400" size="xl">
              Welcome to myAdmin
            </Heading>
            <Text color="gray.300" fontSize="md" textAlign="center">
              Sign in to access your dashboard
            </Text>
          </VStack>

          {/* Login Button */}
          <VStack spacing={4} w="full">
            <Button
              size="lg"
              w="full"
              colorScheme="orange"
              onClick={handleCognitoLogin}
              isLoading={isLoading}
              loadingText="Redirecting..."
            >
              Sign in with Cognito
            </Button>

            <Divider borderColor="gray.600" />

            {/* Forgot Password Link */}
            <HStack spacing={2}>
              <Text color="gray.400" fontSize="sm">
                Forgot your password?
              </Text>
              <Link
                color="orange.400"
                fontSize="sm"
                onClick={handleForgotPassword}
                cursor="pointer"
                _hover={{ textDecoration: 'underline' }}
              >
                Reset it here
              </Link>
            </HStack>
          </VStack>

          {/* Info Alert */}
          <Alert status="info" borderRadius="md" bg="blue.900" borderColor="blue.500" borderWidth="1px">
            <AlertIcon color="blue.400" />
            <AlertDescription color="gray.200" fontSize="sm">
              You will be redirected to a secure login page. After authentication, you'll return to myAdmin.
            </AlertDescription>
          </Alert>

          {/* Footer */}
          <Text color="gray.500" fontSize="xs" textAlign="center">
            Protected by AWS Cognito
          </Text>
        </VStack>
      </Container>
    </Box>
  );
}
