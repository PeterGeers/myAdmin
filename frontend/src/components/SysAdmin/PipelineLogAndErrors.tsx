import React, { useState } from 'react';
import {
  Box,
  VStack,
  HStack,
  Text,
  Badge,
  Code,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Collapse,
  Button,
  Icon,
} from '@chakra-ui/react';
import { ChevronDownIcon, ChevronRightIcon, WarningIcon } from '@chakra-ui/icons';
import type { PipelineError, ModelFailure, CsvRuleDebug } from '../../types/invoiceTestTool';
import { SectionBox } from './PipelineSharedComponents';

// ─── Execution Log (Collapsible) ─────────────────────────────────────────────

export function ExecutionLogSection({ log }: { log: string }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!log) {
    return null;
  }

  return (
    <SectionBox title="Execution Log">
      <Button
        size="xs"
        variant="ghost"
        colorScheme="orange"
        leftIcon={<Icon as={isOpen ? ChevronDownIcon : ChevronRightIcon} />}
        onClick={() => setIsOpen(!isOpen)}
        mb={isOpen ? 2 : 0}
      >
        {isOpen ? 'Hide Log' : 'Show Log'} ({log.length.toLocaleString()} chars)
      </Button>
      <Collapse in={isOpen} animateOpacity>
        <Box
          bg="gray.900"
          p={3}
          borderRadius="md"
          maxH="300px"
          overflow="auto"
          borderWidth="1px"
          borderColor="gray.700"
        >
          <Code
            display="block"
            whiteSpace="pre-wrap"
            wordBreak="break-word"
            bg="transparent"
            color="green.300"
            fontSize="xs"
          >
            {log}
          </Code>
        </Box>
      </Collapse>
    </SectionBox>
  );
}

// ─── Error Display ───────────────────────────────────────────────────────────

export function ErrorDisplaySection({ errors }: { errors: PipelineError[] }) {
  return (
    <SectionBox title="Errors" titleColor="red.400">
      <VStack spacing={3} align="stretch">
        {errors.map((error, idx) => (
          <ErrorItem key={idx} error={error} />
        ))}
      </VStack>
    </SectionBox>
  );
}

function ErrorItem({ error }: { error: PipelineError }) {
  const [showTrace, setShowTrace] = useState(false);

  return (
    <Box
      bg="red.900"
      p={3}
      borderRadius="md"
      borderWidth="1px"
      borderColor="red.700"
      borderLeftWidth="4px"
      borderLeftColor="red.400"
    >
      <HStack spacing={2} mb={1}>
        <Icon as={WarningIcon} color="red.300" boxSize={3} />
        <Badge colorScheme="red" fontSize="xs">{error.stage}</Badge>
        <Text fontSize="xs" color="red.300" fontFamily="mono">{error.error_type}</Text>
      </HStack>
      <Text fontSize="sm" color="white" mb={2}>
        {error.message}
      </Text>

      {error.stack_trace && (
        <>
          <Button
            size="xs"
            variant="ghost"
            colorScheme="red"
            leftIcon={<Icon as={showTrace ? ChevronDownIcon : ChevronRightIcon} />}
            onClick={() => setShowTrace(!showTrace)}
            mb={showTrace ? 2 : 0}
          >
            {showTrace ? 'Hide' : 'Show'} Stack Trace
          </Button>
          <Collapse in={showTrace} animateOpacity>
            <Box
              bg="gray.900"
              p={2}
              borderRadius="md"
              maxH="200px"
              overflow="auto"
            >
              <Code
                display="block"
                whiteSpace="pre-wrap"
                bg="transparent"
                color="red.200"
                fontSize="xs"
              >
                {error.stack_trace}
              </Code>
            </Box>
          </Collapse>
        </>
      )}

      {error.model_failures && error.model_failures.length > 0 && (
        <ModelFailuresDisplay failures={error.model_failures} />
      )}

      {error.csv_rule_details && (
        <CsvRuleDebugDisplay details={error.csv_rule_details} />
      )}
    </Box>
  );
}

function ModelFailuresDisplay({ failures }: { failures: ModelFailure[] }) {
  return (
    <Box mt={2}>
      <Text fontSize="xs" color="red.300" fontWeight="medium" mb={1}>
        Model Failures ({failures.length})
      </Text>
      <Table size="sm" variant="simple">
        <Thead>
          <Tr>
            <Th color="gray.400" borderColor="gray.700" fontSize="xs" py={1}>Model</Th>
            <Th color="gray.400" borderColor="gray.700" fontSize="xs" py={1}>Reason</Th>
            <Th color="gray.400" borderColor="gray.700" fontSize="xs" py={1}>Details</Th>
          </Tr>
        </Thead>
        <Tbody>
          {failures.map((failure, idx) => (
            <Tr key={idx}>
              <Td color="white" borderColor="gray.700" fontSize="xs" py={1}>
                {failure.model}
              </Td>
              <Td borderColor="gray.700" fontSize="xs" py={1}>
                <Badge
                  colorScheme={failure.failure_reason === 'timeout' ? 'yellow' : 'red'}
                  fontSize="xs"
                >
                  {failure.failure_reason}
                </Badge>
              </Td>
              <Td color="gray.300" borderColor="gray.700" fontSize="xs" py={1}>
                {failure.details}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
}

function CsvRuleDebugDisplay({ details }: { details: CsvRuleDebug }) {
  return (
    <Box mt={2}>
      <Text fontSize="xs" color="red.300" fontWeight="medium" mb={1}>
        CSV Rule Debug
      </Text>
      <VStack align="stretch" spacing={1}>
        <HStack>
          <Text fontSize="xs" color="gray.400">Pattern Matched:</Text>
          <Badge colorScheme={details.pattern_matched ? 'green' : 'red'} fontSize="xs">
            {details.pattern_matched ? 'Yes' : 'No'}
          </Badge>
        </HStack>
        <Box>
          <Text fontSize="xs" color="gray.400">Failure Reason:</Text>
          <Text fontSize="xs" color="white">{details.failure_reason}</Text>
        </Box>
        {details.rules_evaluated.length > 0 && (
          <Box>
            <Text fontSize="xs" color="gray.400">Rules Evaluated:</Text>
            <HStack spacing={1} wrap="wrap" mt={1}>
              {details.rules_evaluated.map((rule, idx) => (
                <Badge key={idx} colorScheme="gray" fontSize="xs" variant="outline">
                  {rule}
                </Badge>
              ))}
            </HStack>
          </Box>
        )}
      </VStack>
    </Box>
  );
}
