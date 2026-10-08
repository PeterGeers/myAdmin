/**
 * Member Sender Identities Tab (R0, design §6.2).
 *
 * Tenant-admin surface to add and see the verification status of a tenant's
 * sender email address(es) for Members mail. A tenant admin can:
 *   - add a sender address (begins SES identity verification),
 *   - see each address with its SES status (pending / verified / failed / expired),
 *   - resend the SES verification email for a not-yet-verified address.
 *
 * The verified sender is what the Members mail worker sends `From` for the tenant.
 * Unlike the single-sender invoice flow (SenderSettingsTab), the Members plane
 * supports MULTIPLE sender addresses per tenant (design §6.2).
 *
 * Steering 32: Chakra modal, Formik+Yup, bilingual NL/EN (no hardcoded strings),
 * action/row patterns. Gate: tenant admin (`members:admin`) — enforced server-side.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Text, Spinner, useToast, Badge,
  Button, Alert, AlertIcon, AlertDescription,
  FormControl, FormErrorMessage, Input,
  Table, Thead, Tbody, Tr, Th, Td, Tooltip,
} from '@chakra-ui/react';
import { AddIcon, RepeatIcon, CheckCircleIcon, WarningIcon } from '@chakra-ui/icons';
import { Formik, Form, Field } from 'formik';
import type { FieldProps } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import {
  getSenderIdentities,
  addSenderIdentity,
  resendSenderIdentity,
} from '../../services/memberSenderIdentityService';
import type {
  MemberSenderIdentity,
  SenderIdentityStatus,
} from '../../types/memberSenderIdentityTypes';

interface MemberSenderIdentitiesTabProps {
  tenant: string;
}

/** Map a sender-identity status to a Chakra badge color scheme. */
function statusColorScheme(status: SenderIdentityStatus): string {
  switch (status) {
    case 'verified':
      return 'green';
    case 'pending':
      return 'yellow';
    case 'failed':
      return 'red';
    case 'expired':
      return 'orange';
    default:
      return 'gray';
  }
}

interface AddFormValues {
  email: string;
}

export default function MemberSenderIdentitiesTab({ tenant }: MemberSenderIdentitiesTabProps) {
  const toast = useToast();
  const { t } = useTypedTranslation('admin');

  const [identities, setIdentities] = useState<MemberSenderIdentity[]>([]);
  const [loading, setLoading] = useState(true);
  // Email currently being resent (drives the per-row button spinner).
  const [resendingEmail, setResendingEmail] = useState<string | null>(null);

  const tt = useCallback(
    (key: string, fallback: string) => t(`memberSenderIdentities.${key}`, fallback),
    [t]
  );

  const loadIdentities = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getSenderIdentities();
      if (response.success && response.data) {
        setIdentities(response.data.identities ?? []);
      } else {
        setIdentities([]);
      }
    } catch (error) {
      toast({
        title: tt('loadError', 'Failed to load sender addresses'),
        description: error instanceof Error ? error.message : tt('unknownError', 'Unknown error'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  }, [toast, tt]);

  useEffect(() => {
    loadIdentities();
  }, [loadIdentities, tenant]);

  // Yup schema with i18n'd messages (steering 32: no hardcoded strings).
  const addSchema = Yup.object().shape({
    email: Yup.string()
      .required(tt('validation.required', 'Email address is required'))
      .matches(
        /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
        tt('validation.invalid', 'Please enter a valid email address')
      ),
  });

  const handleAdd = async (
    values: AddFormValues,
    { setSubmitting, resetForm }: { setSubmitting: (v: boolean) => void; resetForm: () => void }
  ) => {
    try {
      const response = await addSenderIdentity(values.email.trim());
      if (response.success) {
        toast({
          title: tt('addSuccess', 'Verification email sent'),
          description: tt('addSuccessDesc', 'Check the inbox for the AWS SES verification email.'),
          status: 'success',
          duration: 5000,
        });
        resetForm();
        await loadIdentities();
      } else {
        toast({
          title: tt('addError', 'Could not add sender address'),
          description: response.error || tt('tryAgain', 'Please try again later.'),
          status: 'error',
          duration: 5000,
        });
      }
    } catch (error) {
      toast({
        title: tt('addError', 'Could not add sender address'),
        description: error instanceof Error ? error.message : tt('unknownError', 'Unknown error'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async (email: string) => {
    setResendingEmail(email);
    try {
      const response = await resendSenderIdentity(email);
      if (response.success) {
        toast({
          title: tt('resendSuccess', 'Verification email resent'),
          description: tt('resendSuccessDesc', 'Check the inbox for the AWS SES verification email.'),
          status: 'success',
          duration: 5000,
        });
        await loadIdentities();
      } else {
        toast({
          title: tt('resendError', 'Could not resend verification'),
          description: response.error || tt('tryAgain', 'Please try again later.'),
          status: 'error',
          duration: 5000,
        });
      }
    } catch (error) {
      toast({
        title: tt('resendError', 'Could not resend verification'),
        description: error instanceof Error ? error.message : tt('unknownError', 'Unknown error'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setResendingEmail(null);
    }
  };

  if (loading) {
    return (
      <Box p={4}>
        <Spinner color="orange.400" />
        <Text color="gray.400" ml={2} display="inline">
          {tt('loading', 'Loading sender addresses...')}
        </Text>
      </Box>
    );
  }

  return (
    <Box>
      <VStack spacing={5} align="stretch">
        <Box>
          <Text color="gray.300" fontWeight="bold" mb={1}>
            {tt('title', 'Sender Addresses')}
          </Text>
          <Text color="gray.500" fontSize="sm">
            {tt('description', 'Add and verify the email addresses your tenant sends member mail from. Mail is sent from a verified address.')}
          </Text>
        </Box>

        {/* Existing addresses + their SES status */}
        {identities.length === 0 ? (
          <Alert status="info" bg="blue.900" borderRadius="md">
            <AlertIcon />
            <AlertDescription color="gray.100" fontSize="sm">
              {tt('empty', 'No sender addresses yet. Add one below to start verification.')}
            </AlertDescription>
          </Alert>
        ) : (
          <Box bg="gray.800" borderRadius="md" p={4} overflowX="auto">
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="gray.400">{tt('columns.email', 'Email')}</Th>
                  <Th color="gray.400">{tt('columns.status', 'Status')}</Th>
                  <Th color="gray.400">{tt('columns.actions', 'Actions')}</Th>
                </Tr>
              </Thead>
              <Tbody>
                {identities.map((identity) => {
                  const canResend = identity.status !== 'verified';
                  return (
                    <Tr key={identity.email}>
                      <Td color="white">{identity.email}</Td>
                      <Td>
                        <Badge
                          colorScheme={statusColorScheme(identity.status)}
                          fontSize="xs"
                          px={2}
                          py={0.5}
                          borderRadius="md"
                        >
                          {identity.status === 'verified' && <CheckCircleIcon mr={1} boxSize={3} />}
                          {identity.status === 'failed' && <WarningIcon mr={1} boxSize={3} />}
                          {tt(`status.${identity.status}`, identity.status)}
                        </Badge>
                      </Td>
                      <Td>
                        {canResend && (
                          <Tooltip label={tt('resendTooltip', 'Resend the SES verification email')}>
                            <Button
                              leftIcon={<RepeatIcon />}
                              size="xs"
                              colorScheme="orange"
                              variant="outline"
                              onClick={() => handleResend(identity.email)}
                              isLoading={resendingEmail === identity.email}
                              loadingText={tt('resending', 'Sending...')}
                            >
                              {tt('resend', 'Resend')}
                            </Button>
                          </Tooltip>
                        )}
                      </Td>
                    </Tr>
                  );
                })}
              </Tbody>
            </Table>
          </Box>
        )}

        {/* Add a new sender address */}
        <Box bg="gray.800" borderRadius="md" p={5}>
          <Text color="gray.300" fontWeight="bold" mb={3}>
            {tt('addTitle', 'Add Sender Address')}
          </Text>
          <Formik<AddFormValues>
            initialValues={{ email: '' }}
            validationSchema={addSchema}
            onSubmit={handleAdd}
          >
            {({ isSubmitting, errors, touched }) => (
              <Form>
                <HStack spacing={3} align="flex-start">
                  <FormControl isInvalid={!!(errors.email && touched.email)} maxW="400px">
                    <Field name="email">
                      {({ field }: FieldProps) => (
                        <Input
                          {...field}
                          type="email"
                          placeholder={tt('emailPlaceholder', 'sender@example.com')}
                          aria-label={tt('columns.email', 'Email')}
                          size="sm"
                          bg="gray.700"
                          color="white"
                          borderColor="gray.600"
                          _placeholder={{ color: 'gray.500' }}
                        />
                      )}
                    </Field>
                    <FormErrorMessage fontSize="xs">{errors.email}</FormErrorMessage>
                  </FormControl>
                  <Button
                    leftIcon={<AddIcon />}
                    colorScheme="orange"
                    size="sm"
                    type="submit"
                    isLoading={isSubmitting}
                    loadingText={tt('adding', 'Adding...')}
                  >
                    {tt('add', 'Add Address')}
                  </Button>
                </HStack>
              </Form>
            )}
          </Formik>
          <Text color="gray.500" fontSize="xs" mt={2}>
            {tt('addHint', 'Adding an address sends an AWS SES verification email. Click the link in that email to verify it.')}
          </Text>
        </Box>
      </VStack>
    </Box>
  );
}
