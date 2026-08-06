/**
 * AddBlockModal — Modal for selecting a new block type to add.
 *
 * Filters block types based on active tenant modules:
 * - "properties" requires STR module
 * - "services" requires ZZP module
 */

import React from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalCloseButton,
  SimpleGrid, Box, Text, VStack,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { BLOCK_TYPE_DEFINITIONS, BlockTypeDefinition } from './blockTypeDefinitions';

interface AddBlockModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (type: string, layout: string) => void;
  tenantModules: string[];
}

export default function AddBlockModal({ isOpen, onClose, onAdd, tenantModules }: AddBlockModalProps) {
  const { t } = useTypedTranslation('admin');

  // Filter block types by active modules
  const availableTypes = BLOCK_TYPE_DEFINITIONS.filter((bt) => {
    if (bt.requiresModule) {
      return tenantModules.includes(bt.requiresModule);
    }
    return true;
  });

  const handleSelect = (bt: BlockTypeDefinition) => {
    onAdd(bt.type, bt.defaultLayout);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <ModalOverlay />
      <ModalContent bg="gray.800" borderColor="gray.600">
        <ModalHeader color="white">{t('landingPage.editor.selectBlockType')}</ModalHeader>
        <ModalCloseButton color="gray.400" />
        <ModalBody pb={6}>
          <SimpleGrid columns={{ base: 2, md: 3 }} spacing={3}>
            {availableTypes.map((bt) => (
              <Box
                key={bt.type}
                p={4}
                bg="gray.700"
                borderRadius="md"
                cursor="pointer"
                border="2px solid"
                borderColor="transparent"
                _hover={{ borderColor: 'orange.400', bg: 'gray.600' }}
                transition="all 0.15s"
                onClick={() => handleSelect(bt)}
              >
                <VStack spacing={1}>
                  <Text fontSize="2xl">{bt.icon}</Text>
                  <Text color="white" fontSize="sm" fontWeight="medium" textAlign="center">
                    {t(`landingPage.blockTypes.${bt.type}`)}
                  </Text>
                  <Text color="gray.400" fontSize="xs" textAlign="center">
                    {t(`landingPage.blockDescriptions.${bt.type}`)}
                  </Text>
                </VStack>
              </Box>
            ))}
          </SimpleGrid>
        </ModalBody>
      </ModalContent>
    </Modal>
  );
}
