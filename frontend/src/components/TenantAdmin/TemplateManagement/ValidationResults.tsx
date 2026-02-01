/**
 * Validation Results Component
 * 
 * Displays validation results including success indicator, errors, and warnings.
 * Features collapsible sections and detailed error information.
 */

import React from 'react';
import {
  Box,
  VStack,
  HStack,
  Text,
  Badge,
  Icon,
  Collapse,
  useDisclosure,
  Divider,
  List,
  ListItem,
  ListIcon,
} from '@chakra-ui/react';
import { CheckCircleIcon, WarningIcon, InfoIcon } from '@chakra-ui/icons';
import type { ValidationResult, ValidationError } from '../../../services/templateApi';

/**
 * Component props
 */
interface ValidationResultsProps {
  validationResult: ValidationResult | null;
}

/**
 * ValidationResults Component
 */
export const ValidationResults: React.FC<ValidationResultsProps> = ({
  validationResult,
}) => {
  const { isOpen: errorsOpen, onToggle: toggleErrors } = useDisclosure({ defaultIsOpen: true });
  const { isOpen: warningsOpen, onToggle: toggleWarnings } = useDisclosure({ defaultIsOpen: true });

  if (!validationResult) {
    return (
      <Box
        p={6}
        border="2px dashed"
        borderColor="gray.700"
        borderRadius="md"
        textAlign="center"
      >
        <Text color="gray.500">No validation results yet</Text>
        <Text fontSize="sm" color="gray.600" mt={2}>
          Upload a template to see validation results
        </Text>
      </Box>
    );
  }

  const { is_valid, errors, warnings, checks_performed } = validationResult;
  const hasErrors = errors && errors.length > 0;
  const hasWarnings = warnings && warnings.length > 0;

  return (
    <VStack spacing={4} align="stretch">
      {/* Overall Status */}
      <Box
        p={4}
        bg={is_valid ? 'green.900' : 'red.900'}
        borderRadius="md"
        border="1px solid"
        borderColor={is_valid ? 'green.700' : 'red.700'}
        data-testid="validation-status-box"
      >
        <HStack spacing={3}>
          <Icon
            as={is_valid ? CheckCircleIcon : WarningIcon}
            boxSize={6}
            color={is_valid ? 'green.400' : 'red.400'}
          />
          <VStack align="start" spacing={0} flex={1}>
            <Text fontWeight="bold" fontSize="lg">
              {is_valid ? 'Template Valid ✓' : 'Validation Failed ✗'}
            </Text>
            <Text fontSize="sm" color="gray.300">
              {is_valid
                ? 'Your template passed all validation checks'
                : 'Please fix the errors below before approving'}
            </Text>
          </VStack>
        </HStack>
      </Box>

      {/* Summary Stats */}
      <HStack spacing={4} justify="space-between">
        <HStack spacing={2}>
          <Badge colorScheme={hasErrors ? 'red' : 'green'} fontSize="md" px={3} py={1}>
            {errors.length} Error{errors.length !== 1 ? 's' : ''}
          </Badge>
          <Badge colorScheme={hasWarnings ? 'yellow' : 'green'} fontSize="md" px={3} py={1}>
            {warnings.length} Warning{warnings.length !== 1 ? 's' : ''}
          </Badge>
        </HStack>
        {checks_performed && checks_performed.length > 0 && (
          <Text fontSize="xs" color="gray.500">
            Checks: {checks_performed.join(', ')}
          </Text>
        )}
      </HStack>

      <Divider borderColor="gray.700" />

      {/* Errors Section */}
      {hasErrors && (
        <Box>
          <HStack
            spacing={3}
            p={3}
            bg="red.900"
            borderRadius="md"
            cursor="pointer"
            onClick={toggleErrors}
            _hover={{ bg: 'red.800' }}
          >
            <Icon as={WarningIcon} color="red.400" />
            <Text fontWeight="bold" flex={1}>
              Errors ({errors.length})
            </Text>
            <Text fontSize="sm" color="gray.400">
              {errorsOpen ? '▼' : '▶'}
            </Text>
          </HStack>
          <Collapse in={errorsOpen} animateOpacity>
            <Box mt={2} pl={4}>
              <List spacing={3}>
                {errors.map((error, index) => (
                  <ValidationErrorItem key={index} error={error} type="error" />
                ))}
              </List>
            </Box>
          </Collapse>
        </Box>
      )}

      {/* Warnings Section */}
      {hasWarnings && (
        <Box>
          <HStack
            spacing={3}
            p={3}
            bg="yellow.900"
            borderRadius="md"
            cursor="pointer"
            onClick={toggleWarnings}
            _hover={{ bg: 'yellow.800' }}
          >
            <Icon as={InfoIcon} color="yellow.400" />
            <Text fontWeight="bold" flex={1}>
              Warnings ({warnings.length})
            </Text>
            <Text fontSize="sm" color="gray.400">
              {warningsOpen ? '▼' : '▶'}
            </Text>
          </HStack>
          <Collapse in={warningsOpen} animateOpacity>
            <Box mt={2} pl={4}>
              <List spacing={3}>
                {warnings.map((warning, index) => (
                  <ValidationErrorItem key={index} error={warning} type="warning" />
                ))}
              </List>
            </Box>
          </Collapse>
        </Box>
      )}

      {/* No Issues Message */}
      {!hasErrors && !hasWarnings && (
        <Box
          p={4}
          bg="green.900"
          borderRadius="md"
          border="1px solid"
          borderColor="green.700"
        >
          <HStack spacing={3}>
            <Icon as={CheckCircleIcon} boxSize={5} color="green.400" />
            <Text>
              No errors or warnings found. Your template is ready to approve!
            </Text>
          </HStack>
        </Box>
      )}
    </VStack>
  );
};

/**
 * Validation Error/Warning Item Component
 */
interface ValidationErrorItemProps {
  error: ValidationError;
  type: 'error' | 'warning';
}

const ValidationErrorItem: React.FC<ValidationErrorItemProps> = ({ error, type }) => {
  const iconColor = type === 'error' ? 'red.400' : 'yellow.400';
  const bgColor = type === 'error' ? 'red.950' : 'yellow.950';

  return (
    <ListItem
      p={3}
      bg={bgColor}
      borderRadius="md"
      border="1px solid"
      borderColor={type === 'error' ? 'red.800' : 'yellow.800'}
    >
      <HStack align="start" spacing={3}>
        <ListIcon as={WarningIcon} color={iconColor} mt={1} />
        <VStack align="start" spacing={1} flex={1}>
          {/* Error Type Badge */}
          {error.type && (
            <Badge
              colorScheme={type === 'error' ? 'red' : 'yellow'}
              fontSize="xs"
              textTransform="uppercase"
            >
              {error.type.replace(/_/g, ' ')}
            </Badge>
          )}

          {/* Error Message */}
          <Text fontSize="sm" fontWeight="medium">
            {error.message}
          </Text>

          {/* Additional Details */}
          <HStack spacing={4} fontSize="xs" color="gray.400">
            {error.line && (
              <Text>
                <Text as="span" fontWeight="bold">
                  Line:
                </Text>{' '}
                {error.line}
              </Text>
            )}
            {error.placeholder && (
              <Text>
                <Text as="span" fontWeight="bold">
                  Placeholder:
                </Text>{' '}
                {error.placeholder}
              </Text>
            )}
          </HStack>
        </VStack>
      </HStack>
    </ListItem>
  );
};

export default ValidationResults;
