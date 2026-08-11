/**
 * Scan Tab — Media Asset Reconciliation
 *
 * Triggers an async reconciliation scan via POST /api/assets/scan,
 * then subscribes to SSE progress events showing real-time status.
 * When complete, displays results grouped by category.
 *
 * @module components/MediaAssetAdmin/ScanTab
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  Box,
  VStack,
  HStack,
  Button,
  Progress,
  Text,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  Alert,
  AlertIcon,
  Icon,
} from '@chakra-ui/react';
import { MdRefresh, MdCheckCircle } from 'react-icons/md';
import { triggerScan } from '@/services/mediaAssetService';
import { getCurrentAuthTokens } from '@/services/authService';
import { API_BASE_URL } from '@/config/api';
import type { ScanPhase, ScanProgress, ScanSummary } from '@/types/mediaAsset';

// ─── Phase Labels ─────────────────────────────────────────────────────────────

const PHASE_LABELS: Record<ScanPhase, string> = {
  scanning_s3: 'Scanning S3...',
  checking_registry: 'Checking Registry...',
  verifying_references: 'Verifying References...',
  transitioning: 'Transitioning Eligible Assets...',
  complete: 'Scan Complete',
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function ScanTab() {
  const [scanning, setScanning] = useState(false);
  const [phase, setPhase] = useState<ScanPhase | null>(null);
  const [progress, setProgress] = useState(0);
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  const startScan = useCallback(async () => {
    setScanning(true);
    setPhase(null);
    setProgress(0);
    setSummary(null);
    setError(null);

    try {
      // 1. Trigger the scan
      const { scan_id } = await triggerScan();

      // 2. Get auth token for SSE connection
      const tokens = await getCurrentAuthTokens();
      if (!tokens?.idToken) {
        throw new Error('No authentication token available');
      }

      const tenant = localStorage.getItem('selectedTenant') || '';

      // 3. Open SSE connection
      const sseUrl =
        `${API_BASE_URL}/api/assets/scan/${scan_id}/status` +
        `?token=${encodeURIComponent(tokens.idToken)}` +
        `&administration=${encodeURIComponent(tenant)}`;

      const es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const data: ScanProgress = JSON.parse(event.data);
          setPhase(data.phase);
          setProgress(data.progress);

          if (data.phase === 'complete') {
            setSummary(data.summary ?? null);
            setScanning(false);
            es.close();
            eventSourceRef.current = null;
          }
        } catch {
          // Ignore malformed events
        }
      };

      es.onerror = () => {
        es.close();
        eventSourceRef.current = null;
        // Only show error if scan hasn't completed
        if (!summary) {
          setError('Connection lost during scan. Please try again.');
          setScanning(false);
        }
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start scan');
      setScanning(false);
    }
  }, [summary]);

  return (
    <VStack spacing={6} align="stretch">
      {/* ── Controls ────────────────────────────────────────── */}
      <HStack>
        <Button
          colorScheme="orange"
          leftIcon={<Icon as={MdRefresh} />}
          isLoading={scanning}
          loadingText="Scanning..."
          onClick={startScan}
          isDisabled={scanning}
        >
          Start Scan
        </Button>
        {phase && !scanning && (
          <HStack color="green.300" spacing={1}>
            <Icon as={MdCheckCircle} />
            <Text fontSize="sm">Last scan completed</Text>
          </HStack>
        )}
      </HStack>

      {/* ── Error State ─────────────────────────────────────── */}
      {error && (
        <Alert status="error" bg="red.900" borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      {/* ── Progress Bar ────────────────────────────────────── */}
      {scanning && (
        <Box bg="gray.800" p={4} borderRadius="md">
          <Text color="gray.300" fontSize="sm" mb={2}>
            {phase ? PHASE_LABELS[phase] : 'Initializing...'}
          </Text>
          <Progress
            value={progress}
            size="md"
            colorScheme="orange"
            borderRadius="md"
            hasStripe
            isAnimated
          />
          <Text color="gray.500" fontSize="xs" mt={1} textAlign="right">
            {progress}%
          </Text>
        </Box>
      )}

      {/* ── Results ─────────────────────────────────────────── */}
      {summary && <ScanResults summary={summary} />}
    </VStack>
  );
}

// ─── Results Display ──────────────────────────────────────────────────────────

interface ScanResultsProps {
  summary: ScanSummary;
}

function ScanResults({ summary }: ScanResultsProps) {
  return (
    <Box>
      <Text color="gray.200" fontWeight="bold" mb={4}>
        Scan Results
      </Text>
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} spacing={4}>
        <ResultCard
          label="Consistent"
          value={summary.consistent}
          color="green.300"
          bg="green.900"
        />
        <ResultCard
          label="Unregistered"
          value={summary.unregistered}
          color="orange.300"
          bg="orange.900"
        />
        <ResultCard
          label="Missing"
          value={summary.missing}
          color="red.300"
          bg="red.900"
        />
        <ResultCard
          label="Stale References"
          value={summary.stale_references}
          color="orange.300"
          bg="orange.900"
        />
        <ResultCard
          label="Newly Eligible"
          value={summary.newly_eligible}
          color="red.300"
          bg="red.900"
        />
        <ResultCard
          label="Total Scanned"
          value={summary.total}
          color="gray.200"
          bg="gray.700"
        />
      </SimpleGrid>
    </Box>
  );
}

// ─── Result Card ──────────────────────────────────────────────────────────────

interface ResultCardProps {
  label: string;
  value: number;
  color: string;
  bg: string;
}

function ResultCard({ label, value, color, bg }: ResultCardProps) {
  return (
    <Box bg={bg} p={4} borderRadius="md" opacity={0.9}>
      <Stat>
        <StatLabel color="gray.300">{label}</StatLabel>
        <StatNumber color={color} fontSize="2xl">
          {value.toLocaleString()}
        </StatNumber>
      </Stat>
    </Box>
  );
}
