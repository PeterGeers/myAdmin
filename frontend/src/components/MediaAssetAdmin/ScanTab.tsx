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
import { useTypedTranslation } from '@/hooks/useTypedTranslation';
import type { ScanPhase, ScanProgress, ScanSummary } from '@/types/mediaAsset';

// ─── Component ────────────────────────────────────────────────────────────────

export default function ScanTab() {
  const { t } = useTypedTranslation('admin');

  const PHASE_LABELS: Record<ScanPhase, string> = {
    scanning_s3: t('mediaAssets.scan.phases.scanningS3'),
    checking_registry: t('mediaAssets.scan.phases.checkingRegistry'),
    verifying_references: t('mediaAssets.scan.phases.verifyingReferences'),
    transitioning: t('mediaAssets.scan.phases.transitioning'),
    complete: t('mediaAssets.scan.phases.complete'),
  };
  const [scanning, setScanning] = useState(false);
  const [phase, setPhase] = useState<ScanPhase | null>(null);
  const [progress, setProgress] = useState(0);
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const scanCompleteRef = useRef(false);

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
    scanCompleteRef.current = false;

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
        `${API_BASE_URL}/api/media-assets/scan/${scan_id}/status` +
        `?token=${encodeURIComponent(tokens.idToken)}` +
        `&administration=${encodeURIComponent(tenant)}`;

      const es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const data: ScanProgress = JSON.parse(event.data);

          if (data.type === 'error') {
            setError(data.error || t('mediaAssets.scan.errors.startFailed'));
            setScanning(false);
            es.close();
            eventSourceRef.current = null;
            return;
          }

          setPhase(data.phase);
          setProgress(data.progress ?? 0);

          if (data.phase === 'complete') {
            setSummary(data.summary ?? null);
            setScanning(false);
            scanCompleteRef.current = true;
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
        if (!scanCompleteRef.current) {
          setError(t('mediaAssets.scan.errors.connectionLost'));
          setScanning(false);
        }
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : t('mediaAssets.scan.errors.startFailed'));
      setScanning(false);
    }
  }, [t]);

  return (
    <VStack spacing={6} align="stretch">
      {/* ── Controls ────────────────────────────────────────── */}
      <HStack>
        <Button
          colorScheme="orange"
          leftIcon={<Icon as={MdRefresh} />}
          isLoading={scanning}
          loadingText={t('mediaAssets.scan.scanning')}
          onClick={startScan}
          isDisabled={scanning}
        >
          {t('mediaAssets.scan.startScan')}
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
            {phase ? PHASE_LABELS[phase] : t('mediaAssets.scan.scanning')}
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
  const { t } = useTypedTranslation('admin');

  return (
    <Box>
      <Text color="gray.200" fontWeight="bold" mb={4}>
        {t('mediaAssets.scan.results.title')}
      </Text>
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} spacing={4}>
        <ResultCard
          label={t('mediaAssets.scan.results.consistent')}
          value={summary.consistent}
          color="green.300"
          bg="green.900"
        />
        <ResultCard
          label={t('mediaAssets.scan.results.unregistered')}
          value={summary.unregistered}
          color="orange.300"
          bg="orange.900"
        />
        <ResultCard
          label={t('mediaAssets.scan.results.missing')}
          value={summary.missing}
          color="red.300"
          bg="red.900"
        />
        <ResultCard
          label={t('mediaAssets.scan.results.staleReferences')}
          value={summary.stale_references}
          color="orange.300"
          bg="orange.900"
        />
        <ResultCard
          label={t('mediaAssets.scan.results.newlyEligible')}
          value={summary.newly_eligible}
          color="red.300"
          bg="red.900"
        />
        <ResultCard
          label={t('mediaAssets.scan.results.totalScanned')}
          value={summary.total_assets}
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
          {(value ?? 0).toLocaleString()}
        </StatNumber>
      </Stat>
    </Box>
  );
}
