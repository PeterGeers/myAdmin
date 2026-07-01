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
  Divider,
} from '@chakra-ui/react';
import { ChevronDownIcon, ChevronRightIcon } from '@chakra-ui/icons';
import type {
  ProcessResponse,
  PipelineResult,
  PerformanceMetrics,
  AIUsagePreview,
  PipelineError,
  ExtractionResult,
  Transaction,
  PreparedTransaction,
} from '../../types/invoiceTestTool';
import { SectionBox, MetricItem, EmptyState } from './PipelineSharedComponents';
import { ExecutionLogSection, ErrorDisplaySection } from './PipelineLogAndErrors';

// ─── Props ───────────────────────────────────────────────────────────────────

interface PipelineResultsPanelProps {
  response: ProcessResponse;
}

// ─── Main Component ──────────────────────────────────────────────────────────

/**
 * PipelineResultsPanel displays the full pipeline execution results
 * in sequential pipeline order with inline sub-sections for metrics,
 * AI usage, execution log, and errors.
 */
export function PipelineResultsPanel({ response }: PipelineResultsPanelProps) {
  const { pipeline_result, performance, ai_usage_preview, execution_log, errors } = response;

  return (
    <Box>
      <VStack spacing={4} align="stretch">
        <Text fontSize="xl" fontWeight="bold" color="orange.400">
          Pipeline Results
        </Text>

        {/* Stage 1: Parser Used & Vendor Info */}
        <PipelineMetaSection pipelineResult={pipeline_result} />

        {/* Stage 2: Raw Text */}
        <RawTextSection
          rawText={pipeline_result.raw_text}
          truncated={pipeline_result.raw_text_truncated}
        />

        {/* Stage 3: Extraction Result */}
        <ExtractionResultSection result={pipeline_result.extraction_result} />

        {/* Stage 4: Formatted Transactions */}
        <FormattedTransactionsSection transactions={pipeline_result.formatted_transactions} />

        {/* Stage 5: Prepared Transactions */}
        <PreparedTransactionsSection transactions={pipeline_result.prepared_transactions} />

        <Divider borderColor="gray.600" />

        {/* Performance Metrics */}
        <PerformanceMetricsSection performance={performance} />

        {/* AI Usage Preview */}
        {ai_usage_preview && <AIUsagePreviewSection preview={ai_usage_preview} />}

        {/* Execution Log */}
        <ExecutionLogSection log={execution_log} />

        {/* Errors */}
        {errors.length > 0 && <ErrorDisplaySection errors={errors} />}
      </VStack>
    </Box>
  );
}

// ─── Pipeline Meta Section ───────────────────────────────────────────────────

function PipelineMetaSection({ pipelineResult }: { pipelineResult: PipelineResult }) {
  const parserColorScheme = {
    ai: 'green',
    csv_rule: 'blue',
    ai_failed: 'red',
  };

  return (
    <SectionBox title="Pipeline Overview">
      <HStack spacing={6} wrap="wrap">
        <Box>
          <Text fontSize="xs" color="gray.400" mb={1}>Parser Used</Text>
          <Badge colorScheme={parserColorScheme[pipelineResult.parser_used]} fontSize="sm">
            {pipelineResult.parser_used}
          </Badge>
        </Box>
        <Box>
          <Text fontSize="xs" color="gray.400" mb={1}>Vendor / Folder Name</Text>
          <Text fontSize="sm" color="white" fontWeight="medium">
            {pipelineResult.folder_name}
          </Text>
        </Box>
      </HStack>
    </SectionBox>
  );
}

// ─── Raw Text Section ────────────────────────────────────────────────────────

function RawTextSection({ rawText, truncated }: { rawText: string; truncated: boolean }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const previewLength = 500;
  const showToggle = rawText.length > previewLength;
  const displayText = isExpanded ? rawText : rawText.slice(0, previewLength);

  return (
    <SectionBox title="Raw Extracted Text">
      {truncated && (
        <Badge colorScheme="yellow" mb={2} fontSize="xs">
          Truncated — original text exceeds 50,000 characters
        </Badge>
      )}
      <Box
        bg="gray.900"
        p={3}
        borderRadius="md"
        maxH={isExpanded ? '400px' : '150px'}
        overflow="auto"
        borderWidth="1px"
        borderColor="gray.700"
      >
        <Code
          display="block"
          whiteSpace="pre-wrap"
          wordBreak="break-word"
          bg="transparent"
          color="gray.300"
          fontSize="xs"
        >
          {displayText}
          {!isExpanded && showToggle && '...'}
        </Code>
      </Box>
      {showToggle && (
        <Button
          size="xs"
          variant="ghost"
          colorScheme="orange"
          mt={1}
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? 'Show Less' : 'Show More'}
        </Button>
      )}
      <Text fontSize="xs" color="gray.500" mt={1}>
        {rawText.length.toLocaleString()} characters
      </Text>
    </SectionBox>
  );
}

// ─── Extraction Result Section ───────────────────────────────────────────────

function ExtractionResultSection({ result }: { result: ExtractionResult | null }) {
  if (!result) {
    return (
      <SectionBox title="Extraction Result">
        <EmptyState message="No extraction result available" />
      </SectionBox>
    );
  }

  const fields: { label: string; value: string | number }[] = [
    { label: 'Date', value: result.date || '(empty)' },
    { label: 'Total Amount', value: result.total_amount ?? 0 },
    { label: 'VAT Amount', value: result.vat_amount ?? 0 },
    { label: 'Description', value: result.description || '(empty)' },
    { label: 'Vendor', value: result.vendor || '(empty)' },
  ];

  return (
    <SectionBox title="Extraction Result">
      <Table size="sm" variant="simple">
        <Tbody>
          {fields.map((field) => (
            <Tr key={field.label}>
              <Td color="gray.400" borderColor="gray.700" py={2} px={3} width="150px">
                {field.label}
              </Td>
              <Td color="white" borderColor="gray.700" py={2} px={3} fontFamily="mono" fontSize="sm">
                {typeof field.value === 'number' ? field.value.toFixed(2) : field.value}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </SectionBox>
  );
}

// ─── Formatted Transactions Section ──────────────────────────────────────────

function FormattedTransactionsSection({ transactions }: { transactions: Transaction[] }) {
  if (!transactions || transactions.length === 0) {
    return (
      <SectionBox title="Formatted Transactions">
        <EmptyState message="No formatted transactions produced" />
      </SectionBox>
    );
  }

  return (
    <SectionBox title="Formatted Transactions">
      <Box overflow="auto">
        <Table size="sm" variant="simple">
          <Thead>
            <Tr>
              <Th color="gray.400" borderColor="gray.700">Date</Th>
              <Th color="gray.400" borderColor="gray.700" isNumeric>Amount</Th>
              <Th color="gray.400" borderColor="gray.700">Description</Th>
              <Th color="gray.400" borderColor="gray.700">Debet</Th>
              <Th color="gray.400" borderColor="gray.700">Credit</Th>
            </Tr>
          </Thead>
          <Tbody>
            {transactions.map((tx, idx) => (
              <Tr key={idx}>
                <Td color="white" borderColor="gray.700" fontSize="sm">{tx.date}</Td>
                <Td color="white" borderColor="gray.700" fontSize="sm" isNumeric>
                  {Number(tx.amount).toFixed(2)}
                </Td>
                <Td color="white" borderColor="gray.700" fontSize="sm">{tx.description}</Td>
                <Td color="gray.300" borderColor="gray.700" fontSize="sm">{tx.debet || '-'}</Td>
                <Td color="gray.300" borderColor="gray.700" fontSize="sm">{tx.credit || '-'}</Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </Box>
      <Text fontSize="xs" color="gray.500" mt={2}>
        {transactions.length} transaction{transactions.length !== 1 ? 's' : ''}
      </Text>
    </SectionBox>
  );
}

// ─── Prepared Transactions Section ───────────────────────────────────────────

function PreparedTransactionsSection({ transactions }: { transactions: PreparedTransaction[] }) {
  if (!transactions || transactions.length === 0) {
    return (
      <SectionBox title="Prepared Transactions">
        <EmptyState message="No prepared transactions produced" />
      </SectionBox>
    );
  }

  return (
    <SectionBox title="Prepared Transactions">
      <Box overflow="auto">
        <Table size="sm" variant="simple">
          <Thead>
            <Tr>
              <Th color="gray.400" borderColor="gray.700">Date</Th>
              <Th color="gray.400" borderColor="gray.700" isNumeric>Amount</Th>
              <Th color="gray.400" borderColor="gray.700">Description</Th>
              <Th color="gray.400" borderColor="gray.700">Debet</Th>
              <Th color="gray.400" borderColor="gray.700">Credit</Th>
              <Th color="gray.400" borderColor="gray.700">Reference</Th>
              <Th color="gray.400" borderColor="gray.700">Administration</Th>
            </Tr>
          </Thead>
          <Tbody>
            {transactions.map((tx, idx) => (
              <Tr key={idx}>
                <Td color="white" borderColor="gray.700" fontSize="sm">{tx.TransactionDate}</Td>
                <Td color="white" borderColor="gray.700" fontSize="sm" isNumeric>
                  {Number(tx.TransactionAmount).toFixed(2)}
                </Td>
                <Td color="white" borderColor="gray.700" fontSize="sm" noOfLines={1} maxW="200px">
                  {tx.TransactionDescription}
                </Td>
                <Td color="gray.300" borderColor="gray.700" fontSize="sm">{tx.Debet}</Td>
                <Td color="gray.300" borderColor="gray.700" fontSize="sm">{tx.Credit}</Td>
                <Td color="gray.300" borderColor="gray.700" fontSize="sm">{tx.ReferenceNumber}</Td>
                <Td color="gray.300" borderColor="gray.700" fontSize="sm">{tx.Administration}</Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </Box>
      <Text fontSize="xs" color="gray.500" mt={2}>
        {transactions.length} prepared transaction{transactions.length !== 1 ? 's' : ''}
      </Text>
    </SectionBox>
  );
}

// ─── Performance Metrics (Inline) ────────────────────────────────────────────

function PerformanceMetricsSection({ performance }: { performance: PerformanceMetrics }) {
  return (
    <SectionBox title="Performance Metrics">
      <HStack spacing={8} wrap="wrap">
        <MetricItem label="Total Duration" value={`${performance.total_duration_ms} ms`} />
        {performance.ai_duration_ms != null && (
          <MetricItem label="AI Duration" value={`${performance.ai_duration_ms} ms`} />
        )}
        {performance.ai_model && (
          <MetricItem label="Model" value={performance.ai_model} />
        )}
      </HStack>
      {performance.ai_tokens && (
        <HStack spacing={6} mt={3} wrap="wrap">
          <MetricItem label="Prompt Tokens" value={String(performance.ai_tokens.prompt_tokens)} />
          <MetricItem
            label="Completion Tokens"
            value={String(performance.ai_tokens.completion_tokens)}
          />
          <MetricItem label="Total Tokens" value={String(performance.ai_tokens.total_tokens)} />
        </HStack>
      )}
    </SectionBox>
  );
}

// ─── AI Usage Preview (Inline) ───────────────────────────────────────────────

function AIUsagePreviewSection({ preview }: { preview: AIUsagePreview }) {
  return (
    <SectionBox title="AI Usage Preview">
      <Text fontSize="xs" color="gray.500" mb={2}>
        Preview of the usage log entry (not written in dry-run mode)
      </Text>
      <Table size="sm" variant="simple">
        <Tbody>
          <Tr>
            <Td color="gray.400" borderColor="gray.700" py={1} px={3}>Administration</Td>
            <Td color="white" borderColor="gray.700" py={1} px={3}>{preview.administration}</Td>
          </Tr>
          <Tr>
            <Td color="gray.400" borderColor="gray.700" py={1} px={3}>Feature</Td>
            <Td color="white" borderColor="gray.700" py={1} px={3}>{preview.feature}</Td>
          </Tr>
          <Tr>
            <Td color="gray.400" borderColor="gray.700" py={1} px={3}>Tokens Used</Td>
            <Td color="white" borderColor="gray.700" py={1} px={3}>{preview.tokens_used}</Td>
          </Tr>
          <Tr>
            <Td color="gray.400" borderColor="gray.700" py={1} px={3}>Cost Estimate</Td>
            <Td color="white" borderColor="gray.700" py={1} px={3}>€{preview.cost_estimate}</Td>
          </Tr>
        </Tbody>
      </Table>

      {/* Cost Breakdown */}
      <Box mt={3} p={3} bg="gray.900" borderRadius="md" borderWidth="1px" borderColor="gray.700">
        <Text fontSize="xs" color="gray.400" mb={2} fontWeight="medium">
          Cost Breakdown
        </Text>
        <VStack align="stretch" spacing={1}>
          <HStack justify="space-between">
            <Text fontSize="xs" color="gray.500">Model</Text>
            <Text fontSize="xs" color="white">{preview.cost_breakdown.model}</Text>
          </HStack>
          <HStack justify="space-between">
            <Text fontSize="xs" color="gray.500">Rate per 1M tokens</Text>
            <Text fontSize="xs" color="white">{preview.cost_breakdown.rate_per_million}</Text>
          </HStack>
          <HStack justify="space-between">
            <Text fontSize="xs" color="gray.500">Total Tokens</Text>
            <Text fontSize="xs" color="white">{preview.cost_breakdown.total_tokens}</Text>
          </HStack>
          <HStack justify="space-between">
            <Text fontSize="xs" color="gray.500">Formula</Text>
            <Text fontSize="xs" color="green.300" fontFamily="mono">
              {preview.cost_breakdown.formula}
            </Text>
          </HStack>
        </VStack>
      </Box>
    </SectionBox>
  );
}

export default PipelineResultsPanel;

