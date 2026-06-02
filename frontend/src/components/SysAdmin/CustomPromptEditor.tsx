import React, { useState, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Button,
  Text,
  Textarea,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Alert,
  AlertIcon,
  AlertDescription,
  Spinner,
  Badge,
  Divider,
  Grid,
  GridItem,
  Code,
} from '@chakra-ui/react';
import { rerunPrompt } from '../../services/invoiceTestToolService';
import type {
  ExtractionResult,
  RerunPromptResponse,
} from '../../types/invoiceTestTool';

/** Maximum allowed characters for the custom prompt. */
const MAX_PROMPT_LENGTH = 10_000;

interface CustomPromptEditorProps {
  /** The original prompt used for extraction (displayed read-only). */
  originalPrompt: string;
  /** The original extraction result for comparison. */
  originalResult: ExtractionResult | null;
  /** The raw text content from the processed file (used for re-run). */
  textContent: string;
  /** Optional vendor hint for context during re-run. */
  vendorHint?: string;
}

/**
 * Validates custom prompt length.
 * Returns an error message or null if valid.
 */
export function validatePromptLength(prompt: string): string | null {
  if (prompt.length === 0) {
    return 'Prompt cannot be empty (minimum 1 character)';
  }
  if (prompt.length > MAX_PROMPT_LENGTH) {
    return `Prompt exceeds maximum length of ${MAX_PROMPT_LENGTH.toLocaleString()} characters`;
  }
  return null;
}

/**
 * CustomPromptEditor — Allows editing the AI extraction prompt and re-running
 * extraction to compare results with the original.
 *
 * Displays original prompt (read-only), editable textarea, character count,
 * submit with loading state, and side-by-side comparison of results.
 */
export function CustomPromptEditor({
  originalPrompt,
  originalResult,
  textContent,
  vendorHint,
}: CustomPromptEditorProps) {
  const [customPrompt, setCustomPrompt] = useState(originalPrompt);
  const [promptError, setPromptError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [rerunResult, setRerunResult] = useState<RerunPromptResponse | null>(null);
  const [rerunError, setRerunError] = useState<string | null>(null);

  const handlePromptChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setCustomPrompt(value);
    setPromptError(validatePromptLength(value));
  }, []);

  const isSubmitDisabled = (): boolean => {
    return isLoading || !!promptError || customPrompt.length === 0;
  };

  const handleRerun = async () => {
    const error = validatePromptLength(customPrompt);
    if (error) {
      setPromptError(error);
      return;
    }

    setIsLoading(true);
    setRerunError(null);

    try {
      const response = await rerunPrompt(textContent, customPrompt, vendorHint);
      setRerunResult(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred during re-run';
      setRerunError(message);
      // Preserve original result and prompt text on failure (state unchanged)
    } finally {
      setIsLoading(false);
    }
  };

  const charCount = customPrompt.length;
  const charCountColor = charCount > MAX_PROMPT_LENGTH ? 'red.400' : charCount > 9000 ? 'yellow.400' : 'gray.400';

  return (
    <Box p={5} bg="gray.700" borderRadius="lg" borderWidth="1px" borderColor="gray.600">
      <VStack spacing={5} align="stretch">
        <Text fontSize="lg" fontWeight="semibold" color="orange.400">
          Custom Prompt Editor
        </Text>

        {/* Original Prompt (read-only) */}
        <FormControl>
          <FormLabel color="gray.300" fontSize="sm">
            Original Prompt (read-only)
          </FormLabel>
          <Textarea
            value={originalPrompt}
            isReadOnly
            size="sm"
            bg="gray.800"
            color="gray.300"
            borderColor="gray.600"
            minH="120px"
            resize="vertical"
            fontFamily="mono"
            fontSize="xs"
            cursor="default"
            _focus={{ borderColor: 'gray.600' }}
          />
        </FormControl>

        {/* Editable Custom Prompt */}
        <FormControl isInvalid={!!promptError}>
          <FormLabel color="gray.300" fontSize="sm">
            Custom Prompt
          </FormLabel>
          <Textarea
            value={customPrompt}
            onChange={handlePromptChange}
            size="sm"
            bg="gray.800"
            color="white"
            borderColor="gray.600"
            minH="200px"
            resize="vertical"
            fontFamily="mono"
            fontSize="xs"
            maxLength={MAX_PROMPT_LENGTH}
            isDisabled={isLoading}
            placeholder="Enter your modified extraction prompt..."
            _placeholder={{ color: 'gray.500' }}
          />
          <HStack justify="space-between" mt={1}>
            {promptError ? (
              <FormErrorMessage mt={0}>{promptError}</FormErrorMessage>
            ) : (
              <Text fontSize="xs" color="gray.500">
                Modify the prompt and re-run to compare results
              </Text>
            )}
            <Text fontSize="xs" color={charCountColor}>
              {charCount.toLocaleString()} / {MAX_PROMPT_LENGTH.toLocaleString()}
            </Text>
          </HStack>
        </FormControl>

        {/* Submit Button */}
        <Button
          colorScheme="orange"
          onClick={handleRerun}
          isDisabled={isSubmitDisabled()}
          isLoading={isLoading}
          loadingText="Re-running extraction..."
          spinner={<Spinner size="sm" />}
          size="md"
          width="fit-content"
        >
          Re-run with Custom Prompt
        </Button>

        {/* Re-run Error */}
        {rerunError && (
          <Alert status="error" bg="red.900" borderRadius="md">
            <AlertIcon />
            <AlertDescription color="gray.200">
              Re-run failed: {rerunError}
            </AlertDescription>
          </Alert>
        )}

        {/* Re-run Results Comparison */}
        {rerunResult && !rerunError && (
          <Box>
            <Divider borderColor="gray.600" my={2} />

            {/* Timing & Token Usage */}
            <HStack spacing={4} mb={4} flexWrap="wrap">
              {rerunResult.performance.ai_duration_ms != null && (
                <Badge colorScheme="blue" px={2} py={1}>
                  Duration: {rerunResult.performance.ai_duration_ms} ms
                </Badge>
              )}
              {rerunResult.performance.ai_model && (
                <Badge colorScheme="purple" px={2} py={1}>
                  Model: {rerunResult.performance.ai_model}
                </Badge>
              )}
              {rerunResult.performance.ai_tokens && (
                <>
                  <Badge colorScheme="green" px={2} py={1}>
                    Prompt: {rerunResult.performance.ai_tokens.prompt_tokens}
                  </Badge>
                  <Badge colorScheme="green" px={2} py={1}>
                    Completion: {rerunResult.performance.ai_tokens.completion_tokens}
                  </Badge>
                  <Badge colorScheme="green" px={2} py={1}>
                    Total: {rerunResult.performance.ai_tokens.total_tokens}
                  </Badge>
                </>
              )}
            </HStack>

            {/* Side-by-side Comparison */}
            <Text fontSize="sm" fontWeight="medium" color="gray.300" mb={3}>
              Extraction Result Comparison
            </Text>
            <Grid templateColumns={{ base: '1fr', md: '1fr 1fr' }} gap={4}>
              <GridItem>
                <ExtractionResultCard
                  title="Original Result"
                  result={originalResult}
                  colorScheme="gray"
                />
              </GridItem>
              <GridItem>
                <ExtractionResultCard
                  title="Re-run Result"
                  result={rerunResult.extraction_result}
                  colorScheme="orange"
                />
              </GridItem>
            </Grid>
          </Box>
        )}
      </VStack>
    </Box>
  );
}

/** Renders a single extraction result in a card layout for comparison. */
function ExtractionResultCard({
  title,
  result,
  colorScheme,
}: {
  title: string;
  result: ExtractionResult | null;
  colorScheme: string;
}) {
  if (!result) {
    return (
      <Box p={3} bg="gray.800" borderRadius="md" borderWidth="1px" borderColor="gray.600">
        <Text fontSize="sm" fontWeight="medium" color={`${colorScheme}.400`} mb={2}>
          {title}
        </Text>
        <Text fontSize="xs" color="gray.500" fontStyle="italic">
          No extraction result available
        </Text>
      </Box>
    );
  }

  return (
    <Box p={3} bg="gray.800" borderRadius="md" borderWidth="1px" borderColor="gray.600">
      <Text fontSize="sm" fontWeight="medium" color={`${colorScheme}.400`} mb={2}>
        {title}
      </Text>
      <VStack spacing={1} align="stretch">
        <FieldRow label="Date" value={result.date} />
        <FieldRow label="Total Amount" value={result.total_amount?.toString() ?? '0'} />
        <FieldRow label="VAT Amount" value={result.vat_amount?.toString() ?? '0'} />
        <FieldRow label="Description" value={result.description} />
        <FieldRow label="Vendor" value={result.vendor} />
      </VStack>
    </Box>
  );
}

/** Renders a single label-value row for extraction fields. */
function FieldRow({ label, value }: { label: string; value: string }) {
  const displayValue = value || '(empty)';
  const isEmpty = !value;

  return (
    <HStack justify="space-between" spacing={2}>
      <Text fontSize="xs" color="gray.400" minW="100px">
        {label}:
      </Text>
      <Code
        fontSize="xs"
        bg="gray.700"
        color={isEmpty ? 'gray.500' : 'white'}
        fontStyle={isEmpty ? 'italic' : 'normal'}
        px={2}
        py={0.5}
        borderRadius="sm"
        maxW="200px"
        noOfLines={1}
      >
        {displayValue}
      </Code>
    </HStack>
  );
}

export default CustomPromptEditor;
