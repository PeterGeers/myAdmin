/**
 * Sender Settings Tab - Email verification status and management
 *
 * Displays the current sender email verification status, allows resending
 * verification emails with a 60s cooldown, shows fallback sender info
 * when the tenant's email is not verified, and provides a form to update
 * the sender email address.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, VStack, HStack, Text, Spinner, useToast, Badge,
  Button, Alert, AlertIcon, AlertDescription,
  FormControl, FormErrorMessage, Input,
} from '@chakra-ui/react';
import { RepeatIcon, CheckCircleIcon, WarningIcon, InfoIcon, EditIcon } from '@chakra-ui/icons';
import { Formik, Form, Field } from 'formik';
import type { FieldProps } from 'formik';
import { getVerificationStatus, resendVerification, updateSenderEmail } from '@/services/verificationApi';
import { emailValidationSchema } from '@/utils/emailVerificationUtils';
import type { VerificationStatus, VerificationStatusValue } from '@/types/VerificationTypes';

interface SenderSettingsTabProps {
  tenant: string;
}

/** Map verification status to badge color scheme */
function getStatusColorScheme(status: VerificationStatusValue): string {
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

/** Map verification status to display label */
function getStatusLabel(status: VerificationStatusValue): string {
  switch (status) {
    case 'verified':
      return 'Verified';
    case 'pending':
      return 'Pending';
    case 'failed':
      return 'Failed';
    case 'expired':
      return 'Expired';
    default:
      return 'Unknown';
  }
}

interface EmailFormValues {
  email: string;
}

export default function SenderSettingsTab({ tenant }: SenderSettingsTabProps) {
  const toast = useToast();

  // Verification status state
  const [verificationData, setVerificationData] = useState<VerificationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [resending, setResending] = useState(false);

  // Cooldown timer state
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load verification status
  const loadStatus = useCallback(async () => {
    try {
      const response = await getVerificationStatus();
      if (response.success && response.data) {
        setVerificationData(response.data);
      }
    } catch (error) {
      toast({
        title: 'Failed to load verification status',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus, tenant]);

  // Cleanup cooldown timer on unmount
  useEffect(() => {
    return () => {
      if (cooldownRef.current) {
        clearInterval(cooldownRef.current);
      }
    };
  }, []);

  // Start cooldown timer
  const startCooldown = () => {
    setCooldownSeconds(60);
    if (cooldownRef.current) {
      clearInterval(cooldownRef.current);
    }
    cooldownRef.current = setInterval(() => {
      setCooldownSeconds((prev) => {
        if (prev <= 1) {
          if (cooldownRef.current) {
            clearInterval(cooldownRef.current);
            cooldownRef.current = null;
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  // Handle resend verification
  const handleResend = async () => {
    setResending(true);
    try {
      const response = await resendVerification();
      if (response.success) {
        toast({
          title: 'Verification email sent',
          description: 'Please check your inbox for the SES verification email.',
          status: 'success',
          duration: 5000,
        });
        startCooldown();
        // Refresh status
        await loadStatus();
      } else {
        toast({
          title: 'Resend failed',
          description: response.error || 'Please try again later.',
          status: 'error',
          duration: 5000,
        });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      // Check if it's a rate limit error
      if (message.includes('60 seconds')) {
        startCooldown();
      }
      toast({
        title: 'Resend failed',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setResending(false);
    }
  };

  // Handle email update form submission
  const handleEmailUpdate = async (
    values: EmailFormValues,
    { setSubmitting, resetForm }: { setSubmitting: (isSubmitting: boolean) => void; resetForm: () => void }
  ) => {
    try {
      const response = await updateSenderEmail(values.email);
      if (response.success) {
        toast({
          title: 'Email updated',
          description: `Verification email sent to ${values.email}. Please check your inbox.`,
          status: 'success',
          duration: 5000,
        });
        resetForm();
        // Refresh status display to show updated email and pending status
        await loadStatus();
      } else {
        toast({
          title: 'Update failed',
          description: response.error || 'Please try again later.',
          status: 'error',
          duration: 5000,
        });
      }
    } catch (error) {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Box p={4}>
        <Spinner color="orange.400" />
        <Text color="gray.400" ml={2} display="inline">
          Loading sender settings...
        </Text>
      </Box>
    );
  }

  if (!verificationData) {
    return (
      <Box p={4}>
        <Alert status="warning" bg="yellow.900" borderRadius="md">
          <AlertIcon />
          <AlertDescription color="gray.100">
            No sender verification data available. The verification may not have been initiated yet.
          </AlertDescription>
        </Alert>
      </Box>
    );
  }

  const { email, status, fallbackSender } = verificationData;
  const isVerified = status === 'verified';
  const showResendButton = status === 'pending' || status === 'failed' || status === 'expired';
  const isCooldownActive = cooldownSeconds > 0;

  return (
    <Box>
      <VStack spacing={5} align="stretch">
        {/* Current sender email and status */}
        <Box bg="gray.800" borderRadius="md" p={5}>
          <Text color="gray.300" fontWeight="bold" mb={3}>
            Sender Email
          </Text>
          <HStack spacing={3} align="center">
            <Text color="white" fontSize="md">
              {email}
            </Text>
            <Badge
              colorScheme={getStatusColorScheme(status)}
              fontSize="sm"
              px={2}
              py={0.5}
              borderRadius="md"
            >
              {status === 'verified' && <CheckCircleIcon mr={1} boxSize={3} />}
              {status === 'failed' && <WarningIcon mr={1} boxSize={3} />}
              {getStatusLabel(status)}
            </Badge>
          </HStack>
        </Box>

        {/* Informational message when pending */}
        {status === 'pending' && (
          <Alert status="info" bg="blue.900" borderRadius="md">
            <InfoIcon color="blue.300" mr={3} />
            <AlertDescription color="gray.100" fontSize="sm">
              A verification email has been sent to <strong>{email}</strong>. Please check your
              inbox (and spam folder) for the AWS SES verification email and click the
              confirmation link to complete verification.
            </AlertDescription>
          </Alert>
        )}

        {/* Fallback sender info when not verified */}
        {!isVerified && (
          <Alert status="warning" bg="yellow.900" borderRadius="md">
            <AlertIcon />
            <AlertDescription color="gray.100" fontSize="sm">
              Your email is not yet verified. Invoice emails are currently sent from the system
              address: <strong>{fallbackSender}</strong>
            </AlertDescription>
          </Alert>
        )}

        {/* Resend Verification button with cooldown */}
        {showResendButton && (
          <Box>
            <HStack spacing={3}>
              <Button
                leftIcon={<RepeatIcon />}
                colorScheme="orange"
                size="sm"
                onClick={handleResend}
                isLoading={resending}
                isDisabled={isCooldownActive}
                loadingText="Sending..."
              >
                {isCooldownActive
                  ? `Resend Verification (${cooldownSeconds}s)`
                  : 'Resend Verification'}
              </Button>
              {isCooldownActive && (
                <Text color="gray.500" fontSize="sm">
                  Please wait before resending.
                </Text>
              )}
            </HStack>
          </Box>
        )}

        {/* Email update form */}
        <Box bg="gray.800" borderRadius="md" p={5}>
          <Text color="gray.300" fontWeight="bold" mb={3}>
            Update Sender Email
          </Text>
          <Formik<EmailFormValues>
            initialValues={{ email: '' }}
            validationSchema={emailValidationSchema}
            onSubmit={handleEmailUpdate}
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
                          placeholder="new-email@example.com"
                          size="sm"
                          bg="gray.700"
                          color="white"
                          borderColor="gray.600"
                          _placeholder={{ color: 'gray.500' }}
                        />
                      )}
                    </Field>
                    <FormErrorMessage fontSize="xs">
                      {errors.email}
                    </FormErrorMessage>
                  </FormControl>
                  <Button
                    leftIcon={<EditIcon />}
                    colorScheme="orange"
                    size="sm"
                    type="submit"
                    isLoading={isSubmitting}
                    loadingText="Updating..."
                  >
                    Update Email
                  </Button>
                </HStack>
              </Form>
            )}
          </Formik>
          <Text color="gray.500" fontSize="xs" mt={2}>
            Changing your sender email will require re-verification via AWS SES.
          </Text>
        </Box>

        {/* Verified success message */}
        {isVerified && (
          <Alert status="success" bg="green.900" borderRadius="md">
            <CheckCircleIcon color="green.300" mr={3} />
            <AlertDescription color="gray.100" fontSize="sm">
              Your email is verified. Invoice emails will be sent from your address.
            </AlertDescription>
          </Alert>
        )}
      </VStack>
    </Box>
  );
}
