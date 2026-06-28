/**
 * Current Template Info Component
 *
 * Displays the current active template status with actions:
 * download, load & modify, delete, or download default.
 */

import React from 'react';
import {
  Box,
  Button,
  HStack,
  Text,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  Spinner,
  Badge,
} from '@chakra-ui/react';
import { CurrentTemplateResponse } from '../../../services/templateApi';

interface CurrentTemplateInfoProps {
  currentTemplate: CurrentTemplateResponse | null;
  loadingCurrent: boolean;
  downloadingDefault: boolean;
  disabled: boolean;
  loading: boolean;
  onDownloadCurrent: () => void;
  onLoadCurrent: () => void;
  onDeleteOpen: () => void;
  onDownloadDefault: () => void;
}

export const CurrentTemplateInfo: React.FC<CurrentTemplateInfoProps> = ({
  currentTemplate,
  loadingCurrent,
  downloadingDefault,
  disabled,
  loading,
  onDownloadCurrent,
  onLoadCurrent,
  onDeleteOpen,
  onDownloadDefault,
}) => {
  if (loadingCurrent) {
    return (
      <HStack spacing={2} p={3} bg="gray.800" borderRadius="md">
        <Spinner size="sm" />
        <Text fontSize="sm" color="gray.400">Loading current template...</Text>
      </HStack>
    );
  }

  if (currentTemplate && currentTemplate.success && currentTemplate.metadata) {
    return (
      <Alert status="info" variant="left-accent" bg="blue.900" borderColor="blue.500">
        <AlertIcon />
        <Box flex="1">
          <AlertTitle fontSize="sm">Current Active Template</AlertTitle>
          <AlertDescription fontSize="xs" color="gray.300">
            Version {currentTemplate.metadata.version} •{' '}
            Approved {new Date(currentTemplate.metadata.approved_at).toLocaleDateString()} by {currentTemplate.metadata.approved_by}
            {currentTemplate.field_mappings && Object.keys(currentTemplate.field_mappings).length > 0 && (
              <Badge ml={2} colorScheme="purple" fontSize="xs">Custom Mappings</Badge>
            )}
          </AlertDescription>
          <HStack spacing={2} mt={2}>
            <Button
              size="xs"
              colorScheme="orange"
              onClick={onDownloadCurrent}
              isDisabled={disabled || loading}
            >
              Download
            </Button>
            <Button
              size="xs"
              colorScheme="orange"
              onClick={onLoadCurrent}
              isDisabled={disabled || loading}
            >
              Load & Modify
            </Button>
            <Button
              size="xs"
              colorScheme="red"
              onClick={onDeleteOpen}
              isDisabled={disabled || loading}
            >
              Delete Template
            </Button>
          </HStack>
        </Box>
      </Alert>
    );
  }

  return (
    <Alert status="warning" variant="left-accent" bg="yellow.900" borderColor="yellow.500">
      <AlertIcon />
      <Box flex="1">
        <AlertDescription fontSize="xs">
          No active template found for this type. You'll be creating the first one.
        </AlertDescription>
        <Button
          size="xs"
          colorScheme="orange"
          mt={2}
          onClick={onDownloadDefault}
          isLoading={downloadingDefault}
          isDisabled={disabled || loading}
          loadingText="Downloading..."
        >
          Download Default Template
        </Button>
      </Box>
    </Alert>
  );
};

export default CurrentTemplateInfo;
