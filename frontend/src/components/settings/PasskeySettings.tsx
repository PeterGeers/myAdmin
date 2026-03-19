/**
 * Passkey Settings Component
 *
 * Allows users to register, view, and delete passkeys (WebAuthn credentials).
 * Integrates with AWS Cognito via Amplify v6.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Heading,
  Text,
  Button,
  useToast,
  Alert,
  AlertIcon,
  AlertDescription,
  Spinner,
  IconButton,
  useDisclosure,
  AlertDialog,
  AlertDialogOverlay,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogBody,
  AlertDialogFooter,
} from '@chakra-ui/react';
import { DeleteIcon, AddIcon } from '@chakra-ui/icons';
import { useTranslation } from 'react-i18next';
import {
  registerPasskey,
  listPasskeys,
  deletePasskey,
  isPasskeySupported,
} from '../../services/authService';

interface PasskeyCredential {
  credentialId: string;
  friendlyName?: string;
  createdAt?: Date;
  lastUsedAt?: Date;
}

export default function PasskeySettings() {
  const { t } = useTranslation();
  const toast = useToast();

  const [passkeys, setPasskeys] = useState<PasskeyCredential[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isRegistering, setIsRegistering] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Confirmation dialog state
  const { isOpen, onOpen, onClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const supported = isPasskeySupported();

  const loadPasskeys = useCallback(async () => {
    try {
      setIsLoadingList(true);
      const credentials = await listPasskeys();
      setPasskeys(credentials as PasskeyCredential[]);
    } catch (error) {
      console.error('Failed to load passkeys:', error);
    } finally {
      setIsLoadingList(false);
    }
  }, []);

  useEffect(() => {
    if (supported) {
      loadPasskeys();
    } else {
      setIsLoadingList(false);
    }
  }, [supported, loadPasskeys]);

  const handleRegister = async () => {
    try {
      setIsRegistering(true);
      await registerPasskey();
      toast({
        title: t('auth:passkey.registerSuccess', 'Passkey registered'),
        description: t('auth:passkey.registerSuccessDesc', 'You can now sign in with this passkey.'),
        status: 'success',
        duration: 5000,
        isClosable: true,
      });
      await loadPasskeys();
    } catch (error: any) {
      const msg = error?.message?.includes('cancelled') || error?.message?.includes('AbortError')
        ? t('auth:login.passkeyCancelled')
        : t('auth:passkey.registerFailed', 'Failed to register passkey. Please try again.');
      toast({
        title: t('auth:login.loginFailed'),
        description: msg,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsRegistering(false);
    }
  };

  const confirmDelete = (credentialId: string) => {
    setPendingDeleteId(credentialId);
    onOpen();
  };

  const handleDelete = async () => {
    if (!pendingDeleteId) return;
    onClose();

    try {
      setDeletingId(pendingDeleteId);
      await deletePasskey(pendingDeleteId);
      toast({
        title: t('auth:passkey.deleteSuccess', 'Passkey removed'),
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
      await loadPasskeys();
    } catch (error) {
      toast({
        title: t('auth:passkey.deleteFailed', 'Failed to remove passkey'),
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setDeletingId(null);
      setPendingDeleteId(null);
    }
  };

  if (!supported) {
    return (
      <Box bg="gray.800" p={6} borderRadius="lg">
        <Alert status="warning" bg="yellow.900" borderRadius="md">
          <AlertIcon />
          <AlertDescription color="gray.200">
            {t('auth:login.passkeyNotSupported')}
          </AlertDescription>
        </Alert>
      </Box>
    );
  }

  return (
    <Box bg="gray.800" p={6} borderRadius="lg">
      <VStack spacing={5} align="stretch">
        <HStack justify="space-between">
          <Heading size="md" color="orange.400">
            {t('auth:passkey.title', 'Passkeys')}
          </Heading>
          <Button
            leftIcon={<AddIcon />}
            colorScheme="orange"
            size="sm"
            onClick={handleRegister}
            isLoading={isRegistering}
            loadingText={t('auth:passkey.registering', 'Registering...')}
          >
            {t('auth:passkey.register', 'Register new passkey')}
          </Button>
        </HStack>

        {isLoadingList ? (
          <HStack justify="center" py={4}>
            <Spinner color="orange.400" />
            <Text color="gray.400">{t('auth:passkey.loading', 'Loading passkeys...')}</Text>
          </HStack>
        ) : passkeys.length === 0 ? (
          <Text color="gray.400" fontSize="sm">
            {t('auth:passkey.noPasskeys', 'No passkeys registered yet. Register one for faster, more secure sign-in.')}
          </Text>
        ) : (
          <VStack spacing={3} align="stretch">
            {passkeys.map((pk) => (
              <HStack
                key={pk.credentialId}
                bg="gray.700"
                p={4}
                borderRadius="md"
                justify="space-between"
              >
                <VStack align="start" spacing={0}>
                  <Text color="white" fontSize="sm" fontWeight="medium">
                    {pk.friendlyName || t('auth:passkey.unnamed', 'Passkey')}
                  </Text>
                  {pk.createdAt && (
                    <Text color="gray.400" fontSize="xs">
                      {t('auth:passkey.created', 'Created')}: {new Date(pk.createdAt).toLocaleDateString()}
                    </Text>
                  )}
                </VStack>
                <IconButton
                  aria-label={t('auth:passkey.remove', 'Remove passkey')}
                  icon={<DeleteIcon />}
                  size="sm"
                  colorScheme="red"
                  variant="ghost"
                  onClick={() => confirmDelete(pk.credentialId)}
                  isLoading={deletingId === pk.credentialId}
                />
              </HStack>
            ))}
          </VStack>
        )}
      </VStack>

      {/* Delete confirmation dialog */}
      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800">
            <AlertDialogHeader color="white">
              {t('auth:passkey.confirmDeleteTitle', 'Remove passkey?')}
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300">
              {t('auth:passkey.confirmDeleteBody', 'This passkey will no longer work for sign-in. You can register a new one later.')}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onClose} variant="ghost" color="gray.300">
                {t('auth:passkey.cancel', 'Cancel')}
              </Button>
              <Button colorScheme="red" onClick={handleDelete} ml={3}>
                {t('auth:passkey.remove', 'Remove')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
