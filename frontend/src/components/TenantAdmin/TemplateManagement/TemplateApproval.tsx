/**
 * Template Approval Component
 * 
 * Provides approve and reject buttons with optional notes/reason.
 * Includes confirmation dialogs and loading states.
 */

import React, { useState } from 'react';
import {
  Box,
  Button,
  VStack,
  HStack,
  Textarea,
  Text,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  useDisclosure,
  FormControl,
  FormLabel,
  FormHelperText,
  Alert,
  AlertIcon,
  AlertDescription,
} from '@chakra-ui/react';
import { CheckIcon, CloseIcon } from '@chakra-ui/icons';

/**
 * Component props
 */
interface TemplateApprovalProps {
  onApprove: (notes?: string) => void;
  onReject: (reason?: string) => void;
  isValid: boolean;
  loading?: boolean;
  disabled?: boolean;
}

/**
 * TemplateApproval Component
 */
export const TemplateApproval: React.FC<TemplateApprovalProps> = ({
  onApprove,
  onReject,
  isValid,
  loading = false,
  disabled = false,
}) => {
  const [approvalNotes, setApprovalNotes] = useState<string>('');
  const [rejectionReason, setRejectionReason] = useState<string>('');

  const {
    isOpen: isApproveOpen,
    onOpen: onApproveOpen,
    onClose: onApproveClose,
  } = useDisclosure();

  const {
    isOpen: isRejectOpen,
    onOpen: onRejectOpen,
    onClose: onRejectClose,
  } = useDisclosure();

  /**
   * Handle approve button click
   */
  const handleApproveClick = () => {
    if (!isValid) {
      return;
    }
    onApproveOpen();
  };

  /**
   * Handle reject button click
   */
  const handleRejectClick = () => {
    onRejectOpen();
  };

  /**
   * Confirm approval
   */
  const handleConfirmApprove = () => {
    onApprove(approvalNotes.trim() || undefined);
    onApproveClose();
    setApprovalNotes('');
  };

  /**
   * Confirm rejection
   */
  const handleConfirmReject = () => {
    onReject(rejectionReason.trim() || undefined);
    onRejectClose();
    setRejectionReason('');
  };

  /**
   * Cancel approval
   */
  const handleCancelApprove = () => {
    onApproveClose();
    setApprovalNotes('');
  };

  /**
   * Cancel rejection
   */
  const handleCancelReject = () => {
    onRejectClose();
    setRejectionReason('');
  };

  return (
    <Box>
      {/* Validation Warning */}
      {!isValid && (
        <Alert status="warning" mb={4} bg="yellow.900" borderRadius="md">
          <AlertIcon />
          <AlertDescription fontSize="sm">
            Template has validation errors. Please fix them before approving.
          </AlertDescription>
        </Alert>
      )}

      {/* Action Buttons */}
      <HStack spacing={4} justify="flex-end">
        <Button
          leftIcon={<CloseIcon />}
          colorScheme="red"
          onClick={handleRejectClick}
          isLoading={loading}
          isDisabled={disabled}
          loadingText="Rejecting..."
        >
          Reject Template
        </Button>
        <Button
          leftIcon={<CheckIcon />}
          colorScheme="green"
          onClick={handleApproveClick}
          isLoading={loading}
          isDisabled={disabled || !isValid}
          loadingText="Approving..."
        >
          Approve Template
        </Button>
      </HStack>

      {/* Approve Confirmation Dialog */}
      <Modal isOpen={isApproveOpen} onClose={handleCancelApprove} size="lg">
        <ModalOverlay />
        <ModalContent bg="brand.gray" borderColor="green.500" borderWidth="2px">
          <ModalHeader>Approve Template</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <Alert status="success" bg="green.900" borderRadius="md">
                <AlertIcon />
                <AlertDescription fontSize="sm">
                  This will save the template to Google Drive and activate it for use.
                </AlertDescription>
              </Alert>

              <FormControl>
                <FormLabel>Approval Notes (Optional)</FormLabel>
                <Textarea
                  value={approvalNotes}
                  onChange={(e) => setApprovalNotes(e.target.value)}
                  placeholder="Add any notes about this approval (e.g., what was changed, why it was approved)"
                  rows={4}
                  bg="gray.800"
                />
                <FormHelperText color="gray.400" fontSize="xs">
                  These notes will be saved in the audit log
                </FormHelperText>
              </FormControl>

              <Box bg="gray.800" p={3} borderRadius="md">
                <Text fontSize="sm" fontWeight="bold" mb={2}>
                  What happens next:
                </Text>
                <VStack align="start" spacing={1} fontSize="xs" color="gray.300">
                  <Text>✓ Template will be saved to your Google Drive</Text>
                  <Text>✓ Previous version will be archived</Text>
                  <Text>✓ Template will become active immediately</Text>
                  <Text>✓ Approval will be logged for audit purposes</Text>
                </VStack>
              </Box>
            </VStack>
          </ModalBody>

          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={handleCancelApprove}>
              Cancel
            </Button>
            <Button colorScheme="green" onClick={handleConfirmApprove}>
              Confirm Approval
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Reject Confirmation Dialog */}
      <Modal isOpen={isRejectOpen} onClose={handleCancelReject} size="lg">
        <ModalOverlay />
        <ModalContent bg="brand.gray" borderColor="red.500" borderWidth="2px">
          <ModalHeader>Reject Template</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <Alert status="warning" bg="red.900" borderRadius="md">
                <AlertIcon />
                <AlertDescription fontSize="sm">
                  This will discard the template without saving. The rejection will be logged.
                </AlertDescription>
              </Alert>

              <FormControl>
                <FormLabel>Rejection Reason (Optional)</FormLabel>
                <Textarea
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  placeholder="Why is this template being rejected? (e.g., doesn't meet brand guidelines, missing required fields)"
                  rows={4}
                  bg="gray.800"
                />
                <FormHelperText color="gray.400" fontSize="xs">
                  Providing a reason helps improve future template submissions
                </FormHelperText>
              </FormControl>

              <Box bg="gray.800" p={3} borderRadius="md">
                <Text fontSize="sm" fontWeight="bold" mb={2}>
                  What happens next:
                </Text>
                <VStack align="start" spacing={1} fontSize="xs" color="gray.300">
                  <Text>✗ Template will NOT be saved</Text>
                  <Text>✗ Current active template remains unchanged</Text>
                  <Text>✓ Rejection will be logged for audit purposes</Text>
                  <Text>✓ You can upload a new template anytime</Text>
                </VStack>
              </Box>
            </VStack>
          </ModalBody>

          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={handleCancelReject}>
              Cancel
            </Button>
            <Button colorScheme="red" onClick={handleConfirmReject}>
              Confirm Rejection
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
};

export default TemplateApproval;
