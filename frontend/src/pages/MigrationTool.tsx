import React, { useState } from 'react';
import {
  Box,
  Button,
  Container,
  Heading,
  Text,
  VStack,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  Progress,
  Code,
  useToast,
  Divider,
  Badge,
  HStack,
  Textarea,
} from '@chakra-ui/react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

interface MigrationResult {
  administration: string;
  year: number;
  status: string;
  transaction_number?: string;
  account_count?: number;
  reason?: string;
  error?: string;
}

interface MigrationResponse {
  success: boolean;
  dry_run?: boolean;
  results?: MigrationResult[];
  summary?: {
    total_processed: number;
    successful: number;
    errors: number;
    skipped: number;
  };
  preview?: any[];
  total_years?: number;
  message?: string;
  error?: string;
}

const MigrationTool: React.FC = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [isDryRun, setIsDryRun] = useState(true);
  const [results, setResults] = useState<MigrationResponse | null>(null);
  const [log, setLog] = useState<string>('');
  const toast = useToast();

  const addLog = (message: string) => {
    const timestamp = new Date().toISOString();
    setLog((prev) => `${prev}[${timestamp}] ${message}\n`);
  };

  const downloadLog = () => {
    const blob = new Blob([log], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `migration-log-${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const runMigration = async (dryRun: boolean) => {
    setIsLoading(true);
    setResults(null);
    setLog('');
    
    addLog(`Starting migration (${dryRun ? 'DRY RUN' : 'LIVE RUN'})...`);

    try {
      const response = await axios.post<MigrationResponse>(
        `${API_URL}/api/migration/opening-balances/migrate`,
        {
          secret: 'migrate-opening-balances-2026',
          dry_run: dryRun,
        }
      );

      setResults(response.data);

      if (response.data.success) {
        if (dryRun) {
          addLog('Dry run completed successfully');
          addLog(`Total years to migrate: ${response.data.total_years || 0}`);
          
          if (response.data.preview) {
            response.data.preview.forEach((p: any) => {
              addLog(`  ${p.administration}: ${p.count} years (${p.years.join(', ')})`);
            });
          }
        } else {
          addLog('Migration completed!');
          addLog(`Total processed: ${response.data.summary?.total_processed || 0}`);
          addLog(`Successful: ${response.data.summary?.successful || 0}`);
          addLog(`Errors: ${response.data.summary?.errors || 0}`);
          addLog(`Skipped: ${response.data.summary?.skipped || 0}`);
          
          if (response.data.results) {
            response.data.results.forEach((r: MigrationResult) => {
              if (r.status === 'success') {
                addLog(`✅ ${r.administration} ${r.year}: ${r.transaction_number} (${r.account_count} accounts)`);
              } else if (r.status === 'error') {
                addLog(`❌ ${r.administration} ${r.year}: ${r.error}`);
              } else if (r.status === 'skipped') {
                addLog(`⏭️  ${r.administration} ${r.year}: ${r.reason}`);
              }
            });
          }
        }

        toast({
          title: dryRun ? 'Dry Run Complete' : 'Migration Complete',
          description: response.data.message || 'Operation completed successfully',
          status: 'success',
          duration: 5000,
          isClosable: true,
        });
      } else {
        addLog(`Error: ${response.data.error}`);
        toast({
          title: 'Error',
          description: response.data.error,
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
      }
    } catch (error: any) {
      const errorMsg = error.response?.data?.error || error.message;
      addLog(`Fatal error: ${errorMsg}`);
      
      toast({
        title: 'Migration Failed',
        description: errorMsg,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Container maxW="container.xl" py={8}>
      <VStack spacing={6} align="stretch">
        <Box>
          <Heading size="lg" mb={2}>
            Opening Balance Migration Tool
          </Heading>
          <Text color="gray.600">
            One-time migration to create opening balance records for historical years
          </Text>
        </Box>

        <Alert status="warning">
          <AlertIcon />
          <Box>
            <AlertTitle>One-Time Use Only</AlertTitle>
            <AlertDescription>
              This tool creates opening balance transactions for all historical years.
              Run the dry run first to preview changes, then run the live migration.
              After migration is complete, this page should be removed.
            </AlertDescription>
          </Box>
        </Alert>

        <Divider />

        <HStack spacing={4}>
          <Button
            colorScheme="blue"
            size="lg"
            onClick={() => runMigration(true)}
            isLoading={isLoading}
            loadingText="Running Dry Run..."
          >
            🔍 Run Dry Run (Preview)
          </Button>

          <Button
            colorScheme="red"
            size="lg"
            onClick={() => runMigration(false)}
            isLoading={isLoading}
            loadingText="Running Migration..."
            isDisabled={!results || results.dry_run !== true}
          >
            ⚡ Run Live Migration
          </Button>

          <Button
            colorScheme="green"
            size="lg"
            onClick={downloadLog}
            isDisabled={!log}
          >
            📥 Download Log
          </Button>
        </HStack>

        {isLoading && (
          <Box>
            <Progress size="sm" isIndeterminate colorScheme="blue" />
            <Text mt={2} fontSize="sm" color="gray.600">
              Processing migration... This may take a few minutes.
            </Text>
          </Box>
        )}

        {results && (
          <Box>
            <Heading size="md" mb={4}>
              Results
            </Heading>

            {results.dry_run && (
              <Alert status="info" mb={4}>
                <AlertIcon />
                <Box>
                  <AlertTitle>Dry Run Preview</AlertTitle>
                  <AlertDescription>
                    Found {results.total_years} year(s) needing migration.
                    Review the preview below, then click "Run Live Migration" to apply changes.
                  </AlertDescription>
                </Box>
              </Alert>
            )}

            {results.summary && (
              <HStack spacing={4} mb={4}>
                <Badge colorScheme="blue" fontSize="md" p={2}>
                  Total: {results.summary.total_processed}
                </Badge>
                <Badge colorScheme="green" fontSize="md" p={2}>
                  Success: {results.summary.successful}
                </Badge>
                <Badge colorScheme="red" fontSize="md" p={2}>
                  Errors: {results.summary.errors}
                </Badge>
                <Badge colorScheme="gray" fontSize="md" p={2}>
                  Skipped: {results.summary.skipped}
                </Badge>
              </HStack>
            )}

            {results.preview && (
              <Box mb={4}>
                <Text fontWeight="bold" mb={2}>
                  Preview by Tenant:
                </Text>
                {results.preview.map((p: any, idx: number) => (
                  <Box key={idx} p={3} bg="gray.50" borderRadius="md" mb={2}>
                    <Text fontWeight="bold">{p.administration}</Text>
                    <Text fontSize="sm" color="gray.600">
                      {p.count} years: {p.years.join(', ')}
                    </Text>
                  </Box>
                ))}
              </Box>
            )}
          </Box>
        )}

        {log && (
          <Box>
            <Heading size="md" mb={4}>
              Log Output
            </Heading>
            <Textarea
              value={log}
              readOnly
              fontFamily="monospace"
              fontSize="sm"
              rows={20}
              bg="gray.50"
            />
          </Box>
        )}
      </VStack>
    </Container>
  );
};

export default MigrationTool;
