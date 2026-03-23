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
import { resetPassword, confirmResetPassword, confirmSignIn } from 'aws-amplify/auth';

interface LoginProps {
  onLoginSuccess?: () => void;
}

export default function Login({ onLoginSuccess }: LoginProps) {
  const { t } = useTranslation();
  const toast = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isPasswordLoading, setIsPasswordLoading] = useState(false);
  const [isPasskeyLoading, setIsPasskeyLoading] = useState(false);

  // Forgot password flow state
  type ViewType = 'login' | 'forgotPassword' | 'resetPassword' | 'newPasswordRequired';
  const [view, setView] = useState<ViewType>('login');
  const [resetCode, setResetCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [isResetLoading, setIsResetLoading] = useState(false);

  const isLoading = isPasswordLoading || isPasskeyLoading;

  /**
   * Handle forgot password — send reset code via Cognito
   */
  const handleForgotPassword = async () => {
    if (!email) {
      toast({ title: t('auth:login.emailLabel') + ' is required.', status: 'warning', duration: 3000 });
      return;
    }
    try {
      setIsResetLoading(true);
      await resetPassword({ username: email });
      toast({ title: t('auth:forgotPassword.codeSent'), status: 'success', duration: 5000, isClosable: true });
      setView('resetPassword');
    } catch (error: any) {
      toast({ title: t('auth:forgotPassword.sendFailed'), description: error?.message || '', status: 'error', duration: 5000, isClosable: true });
    } finally {
      setIsResetLoading(false);
    }
  };

  /**
   * Handle confirm reset — verify code and set new password
   */
  const handleConfirmReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !resetCode || !newPassword) return;
    try {
      setIsResetLoading(true);
      await confirmResetPassword({ username: email, confirmationCode: resetCode, newPassword });
      toast({ title: t('auth:forgotPassword.resetSuccess'), status: 'success', duration: 5000, isClosable: true });
      setView('login');
      setResetCode('');
      setNewPassword('');
    } catch (error: any) {
      toast({ title: t('auth:forgotPassword.resetFailed'), description: error?.message || '', status: 'error', duration: 5000, isClosable: true });
    } finally {
      setIsResetLoading(false);
    }
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
      } else if (result.nextStep?.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        // First-time login with temporary password — user must set a new password
        setView('newPasswordRequired');
        setNewPassword('');
        setConfirmNewPassword('');
      }
    } catch (error: any) {
      const code = error?.name || '';
      let description = t('auth:login.loginFailedDescription');

      if (code === 'NotAuthorizedException' || code === 'UserNotFoundException') {
        description = t('auth:login.loginFailedDescription');
      }

      toast({
        title: t('auth:login.loginFailed'),
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
        title: t('auth:login.loginFailed'),
        description: t('auth:login.emailLabel') + ' is required.',
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
      let description = t('auth:login.passkeyFailed');

      if (code === 'NotAuthorizedException') {
        description = t('auth:login.noPasskeyRegistered');
      } else if (error?.message?.includes('cancelled') || error?.message?.includes('AbortError')) {
        description = t('auth:login.passkeyCancelled');
      }

      toast({
        title: t('auth:login.loginFailed'),
        description,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsPasskeyLoading(false);
    }
  };

  /**
   * Handle new password required challenge — first-time login
   */
  const handleNewPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPassword || !confirmNewPassword) return;

    if (newPassword !== confirmNewPassword) {
      toast({
        title: t('auth:newPassword.mismatch'),
        status: 'error',
        duration: 4000,
        isClosable: true,
      });
      return;
    }

    try {
      setIsResetLoading(true);
      const result = await confirmSignIn({ challengeResponse: newPassword });

      if (result.isSignedIn) {
        toast({
          title: t('auth:newPassword.success'),
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
        onLoginSuccess?.();
      }
    } catch (error: any) {
      toast({
        title: t('auth:newPassword.failed'),
        description: error?.message || '',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsResetLoading(false);
    }
  };

  // Shared wrapper for all views
  const renderWrapper = (children: React.ReactNode) => (
    <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center" px={4}>
      <Container maxW="md">
        <VStack spacing={8} bg="gray.800" p={8} borderRadius="lg" boxShadow="2xl">
          <Image src={`${process.env.PUBLIC_URL}/jabaki-logo.png`} alt="myAdmin Logo" maxW="200px" mb={4} />
          {children}
          <Text color="gray.500" fontSize="xs" textAlign="center">{t('auth:login.protectedBy')}</Text>
        </VStack>
      </Container>
    </Box>
  );

  // Forgot password view — enter email to receive code
  if (view === 'forgotPassword') {
    return renderWrapper(
      <>
        <VStack spacing={2}>
          <Heading color="orange.400" size="lg">{t('auth:forgotPassword.title')}</Heading>
          <Text color="gray.300" fontSize="sm" textAlign="center">{t('auth:forgotPassword.subtitle')}</Text>
        </VStack>
        <VStack spacing={4} w="full">
          <FormControl isRequired>
            <FormLabel color="gray.300">{t('auth:login.emailLabel')}</FormLabel>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@example.com"
              bg="gray.700" color="white" borderColor="gray.600" _hover={{ borderColor: 'gray.500' }}
              _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }} disabled={isResetLoading} />
          </FormControl>
          <Button size="lg" w="full" colorScheme="orange" onClick={handleForgotPassword} isLoading={isResetLoading}
            loadingText={t('auth:forgotPassword.sending')}>{t('auth:forgotPassword.sendCode')}</Button>
          <Link color="orange.400" fontSize="sm" onClick={() => setView('login')} cursor="pointer">
            ← {t('auth:forgotPassword.backToLogin')}
          </Link>
        </VStack>
      </>
    );
  }

  // Reset password view — enter code + new password
  if (view === 'resetPassword') {
    return renderWrapper(
      <>
        <VStack spacing={2}>
          <Heading color="orange.400" size="lg">{t('auth:forgotPassword.resetTitle')}</Heading>
          <Text color="gray.300" fontSize="sm" textAlign="center">{t('auth:forgotPassword.resetSubtitle')}</Text>
        </VStack>
        <Box as="form" w="full" onSubmit={handleConfirmReset}>
          <VStack spacing={4}>
            <FormControl isRequired>
              <FormLabel color="gray.300">{t('auth:forgotPassword.codeLabel')}</FormLabel>
              <Input value={resetCode} onChange={(e) => setResetCode(e.target.value)} placeholder="123456"
                bg="gray.700" color="white" borderColor="gray.600" _hover={{ borderColor: 'gray.500' }}
                _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }} disabled={isResetLoading} />
            </FormControl>
            <FormControl isRequired>
              <FormLabel color="gray.300">{t('auth:forgotPassword.newPasswordLabel')}</FormLabel>
              <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                bg="gray.700" color="white" borderColor="gray.600" _hover={{ borderColor: 'gray.500' }}
                _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }} disabled={isResetLoading} />
            </FormControl>
            <Button type="submit" size="lg" w="full" colorScheme="orange" isLoading={isResetLoading}
              loadingText={t('auth:forgotPassword.resetting')}>{t('auth:forgotPassword.resetButton')}</Button>
            <Link color="orange.400" fontSize="sm" onClick={() => setView('login')} cursor="pointer">
              ← {t('auth:forgotPassword.backToLogin')}
            </Link>
          </VStack>
        </Box>
      </>
    );
  }

  // New password required view — first-time login with temporary password
  if (view === 'newPasswordRequired') {
    return renderWrapper(
      <>
        <VStack spacing={2}>
          <Heading color="orange.400" size="lg">{t('auth:newPassword.title')}</Heading>
          <Text color="gray.300" fontSize="sm" textAlign="center">{t('auth:newPassword.subtitle')}</Text>
        </VStack>
        <Box as="form" w="full" onSubmit={handleNewPasswordSubmit}>
          <VStack spacing={4}>
            <FormControl isRequired>
              <FormLabel color="gray.300">{t('auth:newPassword.newPasswordLabel')}</FormLabel>
              <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                bg="gray.700" color="white" borderColor="gray.600" _hover={{ borderColor: 'gray.500' }}
                _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }} disabled={isResetLoading} />
            </FormControl>
            <FormControl isRequired>
              <FormLabel color="gray.300">{t('auth:newPassword.confirmPasswordLabel')}</FormLabel>
              <Input type="password" value={confirmNewPassword} onChange={(e) => setConfirmNewPassword(e.target.value)}
                bg="gray.700" color="white" borderColor="gray.600" _hover={{ borderColor: 'gray.500' }}
                _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }} disabled={isResetLoading} />
            </FormControl>
            <Alert status="info" borderRadius="md" bg="blue.900" borderColor="blue.500" borderWidth="1px">
              <AlertIcon color="blue.400" />
              <AlertDescription color="gray.200" fontSize="sm">{t('auth:newPassword.requirements')}</AlertDescription>
            </Alert>
            <Button type="submit" size="lg" w="full" colorScheme="orange" isLoading={isResetLoading}
              loadingText={t('auth:newPassword.saving')}>{t('auth:newPassword.saveButton')}</Button>
          </VStack>
        </Box>
      </>
    );
  }

  // Default: login view
  return renderWrapper(
    <>
      {/* Title */}
      <VStack spacing={2}>
        <Heading color="orange.400" size="xl">{t('auth:login.title')}</Heading>
        <Text color="gray.300" fontSize="md" textAlign="center">{t('auth:login.subtitle')}</Text>
      </VStack>

      {/* Email / Password Form */}
      <Box as="form" w="full" onSubmit={handlePasswordLogin}>
        <VStack spacing={4}>
          <FormControl isRequired>
            <FormLabel color="gray.300">{t('auth:login.emailLabel')}</FormLabel>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@example.com"
              bg="gray.700" color="white" borderColor="gray.600" _hover={{ borderColor: 'gray.500' }}
              _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }} disabled={isLoading} />
          </FormControl>
          <FormControl isRequired>
            <FormLabel color="gray.300">{t('auth:login.passwordLabel')}</FormLabel>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              bg="gray.700" color="white" borderColor="gray.600" _hover={{ borderColor: 'gray.500' }}
              _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }} disabled={isLoading} />
          </FormControl>
          <Button type="submit" size="lg" w="full" colorScheme="orange" isLoading={isPasswordLoading}
            loadingText={t('auth:login.signingIn')} isDisabled={isPasskeyLoading}>
            {t('auth:login.signInButton')}
          </Button>
        </VStack>
      </Box>

      {/* Passkey section */}
      {isPasskeySupported() && (
        <>
          <HStack w="full" spacing={4}>
            <Divider borderColor="gray.600" />
            <Text color="gray.400" fontSize="sm" whiteSpace="nowrap">{t('auth:login.or')}</Text>
            <Divider borderColor="gray.600" />
          </HStack>
          <Button size="lg" w="full" variant="outline" colorScheme="orange" leftIcon={<LockIcon />}
            onClick={handlePasskeyLogin} isLoading={isPasskeyLoading} loadingText={t('auth:login.signingIn')} isDisabled={isPasswordLoading}>
            {t('auth:login.signInWithPasskey')}
          </Button>
        </>
      )}

      {/* Forgot Password Link */}
      <HStack spacing={2}>
        <Text color="gray.400" fontSize="sm">{t('auth:login.forgotPassword')}</Text>
        <Link color="orange.400" fontSize="sm" onClick={() => setView('forgotPassword')} cursor="pointer" _hover={{ textDecoration: 'underline' }}>
          {t('auth:login.resetPassword')}
        </Link>
      </HStack>

      {/* Info Alert */}
      <Alert status="info" borderRadius="md" bg="blue.900" borderColor="blue.500" borderWidth="1px">
        <AlertIcon color="blue.400" />
        <AlertDescription color="gray.200" fontSize="sm">{t('auth:login.secureLoginInfo')}</AlertDescription>
      </Alert>
    </>
  );
}
