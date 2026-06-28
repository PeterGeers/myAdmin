/**
 * AISuggestionsModal — AI-powered budget line adjustment suggestions.
 *
 * Allows the user to provide context notes, request AI suggestions,
 * then accept or reject individual recommendations.
 */

import React from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack, HStack, Box,
  Flex, Button, Text, Textarea, Badge, FormControl, FormLabel,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { AISuggestionsModalProps } from './types';

const AISuggestionsModal: React.FC<AISuggestionsModalProps> = ({
  isOpen,
  onClose,
  suggestions,
  loading,
  contextNotes,
  onContextNotesChange,
  onGetSuggestions,
  onAccept,
  onReject,
}) => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" scrollBehavior="inside" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent maxW="750px" bg="gray.800" color="white">
        <ModalHeader>{t('buttons.aiSuggestions')}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={4} align="stretch">
            <FormControl>
              <FormLabel>{t('labels.contextNotes')}</FormLabel>
              <Textarea
                value={contextNotes}
                onChange={(e) => onContextNotesChange(e.target.value)}
                placeholder="e.g. Huur stijgt 5% vanaf juni. Platform Booking.com is gestopt."
                rows={3}
              />
            </FormControl>
            <Button
              colorScheme="orange"
              onClick={onGetSuggestions}
              isLoading={loading}
              loadingText={tc('status.processing')}
              isDisabled={!contextNotes.trim()}
            >
              {t('buttons.aiSuggestions')}
            </Button>

            {/* Suggestions list */}
            {suggestions.length > 0 && (
              <VStack spacing={3} align="stretch" mt={2}>
                <Text fontWeight="semibold" color="gray.300">
                  {suggestions.length} suggestion{suggestions.length !== 1 ? 's' : ''}
                </Text>
                {suggestions.map((suggestion, idx) => (
                  <Box key={idx} p={3} borderWidth="1px" borderRadius="md" bg="gray.700">
                    <Flex justify="space-between" align="start" mb={2}>
                      <Box>
                        <Text fontWeight="bold" color="white">
                          {suggestion.account_code} — {suggestion.account_name}
                        </Text>
                        <Text fontSize="sm" color="gray.300">
                          Months affected: {suggestion.affected_months.join(', ')}
                        </Text>
                      </Box>
                      <Badge colorScheme="blue" fontSize="xs">AI</Badge>
                    </Flex>
                    <Text fontSize="sm" mb={2} color="gray.200">{suggestion.reasoning}</Text>
                    <HStack spacing={2}>
                      <Button
                        size="xs"
                        colorScheme="orange"
                        onClick={() => onAccept(suggestion)}
                      >
                        {t('buttons.accept')}
                      </Button>
                      <Button
                        size="xs"
                        colorScheme="red"
                        variant="outline"
                        onClick={() => onReject(idx)}
                      >
                        {t('buttons.reject')}
                      </Button>
                    </HStack>
                  </Box>
                ))}
              </VStack>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>{tc('buttons.close')}</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default AISuggestionsModal;
