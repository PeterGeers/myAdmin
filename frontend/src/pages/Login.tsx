/**
 * Login Page Component
 *
 * Custom authentication form supporting both email/password
 * and passkey (WebAuthn) sign-in via AWS Cognito.
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
  AlertDescription,
  Input,
  FormControl,
  FormLabel,
} from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import { LockIcon } from '@chakra-ui/icons';
import {
  signInWithPassword,
  signInWithPasskey,
  isPasskeySupported,
} from '../services/authService';

interface LoginProps {
  onLoginSuccess?: () => void;
}

export default function Login({ onLoginSuccess }: LoginProps) {
  const { t } = useTranslation('auth');
  const toast = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isPasswordLoading, setIsPasswordLoading] = useState(false);
  const [isPasskeyLoading, setIsPasskeyLoading] = useState(false);

  const isLoading = isPasswordLoading || isPasskeyLoading;

  /**
   * Handle forgot password — redirect to Cognito hosted forgot-password page
   */
  const handleForgotPassword = () => {
    const cognitoDomain =
      process.env.REACT_APP_COGNITO_DOMAIN ||
      'myadmin.auth.eu-west-1.amazoncognito.com';
    const clientId =
      process.env.REACT_APP_COGNITO_CLIENT_ID || '6sgh53un5ttsojn7o2aj9hi7en';
    const redirectUri = encodeURIComponent(window.location.origin + '/');
    const forgotPasswordUrl = `https://${cognitoDomain}/forgotPassword?client_id=${clientId}&redirect_uri=${redirectUri}`;
    window.location.href = forgotPasswordUrl;
  };

  /**
   * Handle email/password sign-in
   */
  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;

    try {
      setIsPasswordLoading(true);
      const result = await signInWithPassword(email, password);

      if (result.isSignedIn) {
        onLoginSuccess?.();
      }
    } catch (error: any) {
      const code = error?.name || '';
      let description = t('login.loginFailedDescription');

      if (code === 'NotAuthorizedException' || code === 'UserNotFoundException') {
        description = t('login.loginFailedDescription');
      }

      toast({
        title: t('login.loginFailed'),
        description,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsPasswordLoading(false);
    }
  };

  /**
   * Handle passkey (WebAuthn) sign-in
   */
  const handlePasskeyLogin = async () => {
    if (!email) {
      toast({
        title: t('login.loginFailed'),
        description: t('login.emailLabel') + ' is required.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      setIsPasskeyLoading(true);
      const result = await signInWithPasskey(email);

      if (result.isSignedIn) {
        onLoginSuccess?.();
      }
    } catch (error: any) {
      const code = error?.name || '';
      let description = t('login.passkeyFailed');

      if (code === 'NotAuthorizedException') {
        description = t('login.noPasskeyRegistered');
      } else if (error?.message?.includes('cancelled') || error?.message?.includes('AbortError')) {
        description = t('login.passkeyCancelled');
      }

      toast({
        title: t('login.loginFailed'),
        description,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsPasskeyLoading(false);
    }
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
            src={`${process.env.PUBLIC_URL}/jabaki-logo.png`}
            alt="myAdmin Logo"
            maxW="200px"
            mb={4}
          />

          {/* Title */}
          <VStack spacing={2}>
            <Heading color="orange.400" size="xl">
              {t('login.title')}
            </Heading>
            <Text color="gray.300" fontSize="md" textAlign="center">
              {t('login.subtitle')}
            </Text>
          </VStack>

          {/* Email / Password Form */}
          <Box as="form" w="full" onSubmit={handlePasswordLogin}>
            <VStack spacing={4}>
              <FormControl isRequired>
                <FormLabel color="gray.300">{t('login.emailLabel')}</FormLabel>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="user@example.com"
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                  _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                  disabled={isLoading}
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel color="gray.300">{t('login.passwordLabel')}</FormLabel>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                  _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                  disabled={isLoading}
                />
              </FormControl>

              <Button
                type="submit"
                size="lg"
                w="full"
                colorScheme="orange"
                isLoading={isPasswordLoading}
                loadingText={t('login.signingIn')}
                isDisabled={isPasskeyLoading}
              >
                {t('login.signInButton')}
              </Button>
            </VStack>
          </Box>

          {/* Passkey section */}
          {isPasskeySupported() && (
            <>
              <HStack w="full" spacing={4}>
                <Divider borderColor="gray.600" />
                <Text color="gray.400" fontSize="sm" whiteSpace="nowrap">
                  {t('login.or')}
                </Text>
                <Divider borderColor="gray.600" />
              </HStack>

              <Button
                size="lg"
                w="full"
                variant="outline"
                colorScheme="orange"
                leftIcon={<LockIcon />}
                onClick={handlePasskeyLogin}
                isLoading={isPasskeyLoading}
                loadingText={t('login.signingIn')}
                isDisabled={isPasswordLoading}
              >
                {t('login.signInWithPasskey')}
              </Button>
            </>
          )}

          {/* Forgot Password Link */}
          <HStack spacing={2}>
            <Text color="gray.400" fontSize="sm">
              {t('login.forgotPassword')}
            </Text>
            <Link
              color="orange.400"
              fontSize="sm"
              onClick={handleForgotPassword}
              cursor="pointer"
              _hover={{ textDecoration: 'underline' }}
            >
              {t('login.resetPassword')}
            </Link>
          </HStack>

          {/* Info Alert */}
          <Alert status="info" borderRadius="md" bg="blue.900" borderColor="blue.500" borderWidth="1px">
            <AlertIcon color="blue.400" />
            <AlertDescription color="gray.200" fontSize="sm">
              {t('login.secureLoginInfo')}
            </AlertDescription>
          </Alert>

          {/* Footer */}
          <Text color="gray.500" fontSize="xs" textAlign="center">
            {t('login.protectedBy')}
          </Text>
        </VStack>
      </Container>
    </Box>
  );
}
