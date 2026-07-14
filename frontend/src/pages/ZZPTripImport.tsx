/**
 * ZZP Trip Import Wizard — multi-step import flow for CSV/Excel trip data.
 * Steps: Upload → Preview → Commit
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.7
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner, Select, VStack, HStack,
  Table, Thead, Tbody, Tr, Th, Td, Badge, Input, Tooltip,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { importTrips, commitImport } from '../services/tripService';
import { getVehicles } from '../services/vehicleService';
import { TripImportStepper } from '../components/zzp/TripImportWizard';
import type { Vehicle, ImportRow } from '../types/zzpTrips';
import type { ColumnMapping } from '../services/tripService';
import { authenticatedGet, buildEndpoint } from '../services/apiService';

/* ─── Constants ─── */
const STEPS = ['Upload', 'Preview', 'Importeren'];
const MAX_PREVIEW_ROWS = 20;

/* ─── Types ─── */
interface ImportValidationResult {
  total_rows: number;
  valid: number;
  warnings: number;
  errors: number;
  preview: ImportRow[];
}

/* ─── Main Page ─── */
const ZZPTripImport: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();

  // Wizard state
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);

  // Step 1 state
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selectedVehicle, setSelectedVehicle] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Step 2 state (preview)
  const [validationResult, setValidationResult] = useState<ImportValidationResult | null>(null);

  // Step 3 state (commit)
  const [importing, setImporting] = useState(false);
  const [importDone, setImportDone] = useState(false);

  // Load vehicles on mount
  useEffect(() => {
    const loadVehicles = async () => {
      try {
        const resp = await getVehicles(true);
        if (resp.success && resp.data.length > 0) {
          setVehicles(resp.data);
          setSelectedVehicle(resp.data[0].id);
        }
      } catch {
        toast({ title: 'Fout bij laden voertuigen', status: 'error', duration: 3000 });
      }
    };
    loadVehicles();
  }, [toast]);

  /* ─── File Handlers ─── */
  const handleUploadClick = () => fileInputRef.current?.click();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setFile(e.target.files[0]);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  /* ─── Template Download ─── */
  const handleDownloadTemplate = async () => {
    try {
      const resp = await authenticatedGet(buildEndpoint('/api/zzp/trips/import/template'));
      if (!resp.ok) throw new Error('Template download failed');
      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'ritten_import_template.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch {
      toast({ title: 'Template downloaden mislukt', status: 'error', duration: 3000 });
    }
  };

  /* ─── Step Navigation ─── */
  const handleNext = async () => {
    if (currentStep === 0) {
      // Validate and upload
      if (!file) {
        toast({ title: 'Selecteer een bestand', status: 'warning', duration: 2000 });
        return;
      }
      if (!selectedVehicle) {
        toast({ title: 'Selecteer een voertuig', status: 'warning', duration: 2000 });
        return;
      }
      setLoading(true);
      try {
        const resp = await importTrips(file, selectedVehicle);
        if (resp.success) {
          setValidationResult(resp.data as unknown as ImportValidationResult);
          setCurrentStep(1);
        } else {
          toast({ title: 'Upload mislukt', status: 'error', duration: 3000 });
        }
      } catch (err) {
        toast({
          title: err instanceof Error ? err.message : 'Upload mislukt',
          status: 'error',
          duration: 3000,
        });
      } finally {
        setLoading(false);
      }
    } else if (currentStep === 1) {
      setCurrentStep(2);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) setCurrentStep(currentStep - 1);
  };

  /* ─── Commit Import ─── */
  const handleCommit = async () => {
    if (!selectedVehicle) return;
    setImporting(true);
    try {
      const mapping: ColumnMapping = {};
      const resp = await commitImport(selectedVehicle, mapping);
      if (resp.success) {
        setImportDone(true);
        toast({
          title: 'Import geslaagd!',
          description: `${validationResult?.valid ?? 0} ritten geïmporteerd.`,
          status: 'success',
          duration: 4000,
        });
      } else {
        toast({
          title: resp.error || 'Import mislukt',
          status: 'error',
          duration: 3000,
        });
      }
    } catch (err) {
      toast({
        title: err instanceof Error ? err.message : 'Import mislukt',
        status: 'error',
        duration: 3000,
      });
    } finally {
      setImporting(false);
    }
  };

  /* ─── Status Badge Helper ─── */
  const getStatusBadge = (row: ImportRow) => {
    const colorMap = { ok: 'green', warning: 'yellow', error: 'red' };
    const labelMap = { ok: 'OK', warning: 'Waarschuwing', error: 'Fout' };
    return (
      <Tooltip
        label={row.messages?.length > 0 ? row.messages.join('\n') : 'Geen opmerkingen'}
        placement="top"
        hasArrow
      >
        <Badge colorScheme={colorMap[row.status]} cursor="pointer">
          {labelMap[row.status]}
        </Badge>
      </Tooltip>
    );
  };

  /* ─── Render Step 1: Upload ─── */
  const renderUploadStep = () => (
    <VStack spacing={6} w="100%" maxW="600px" mx="auto">
      {/* Template download */}
      <Button
        size="sm"
        variant="link"
        color="orange.300"
        onClick={handleDownloadTemplate}
        alignSelf="flex-start"
      >
        📥 Download template (CSV)
      </Button>

      {/* Vehicle selector */}
      <Box w="100%">
        <Text fontSize="sm" color="gray.400" mb={1}>Voertuig</Text>
        <Select
          size="sm"
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={selectedVehicle ?? ''}
          onChange={(e) => setSelectedVehicle(Number(e.target.value) || null)}
        >
          {vehicles.map((v) => (
            <option key={v.id} value={v.id}>
              {v.license_plate} — {v.make} {v.model}
            </option>
          ))}
        </Select>
      </Box>

      {/* File drop zone */}
      <Box
        w="100%"
        p={8}
        border="2px dashed"
        borderColor={dragOver ? 'orange.400' : 'gray.600'}
        borderRadius="md"
        bg={dragOver ? 'gray.700' : 'gray.750'}
        textAlign="center"
        cursor="pointer"
        onClick={handleUploadClick}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        transition="all 0.2s"
        _hover={{ borderColor: 'orange.400', bg: 'gray.700' }}
      >
        <VStack spacing={2}>
          <Text fontSize="2xl">📁</Text>
          <Text color="gray.300">
            {file ? file.name : 'Sleep een CSV/Excel bestand hierheen of klik om te selecteren'}
          </Text>
          {file && (
            <Text fontSize="xs" color="gray.500">
              {(file.size / 1024).toFixed(1)} KB
            </Text>
          )}
        </VStack>
        <Input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          display="none"
          onChange={handleFileChange}
        />
      </Box>
    </VStack>
  );

  /* ─── Render Step 2: Preview ─── */
  const renderPreviewStep = () => {
    if (!validationResult) return null;
    const rows = validationResult.preview.slice(0, MAX_PREVIEW_ROWS);

    return (
      <VStack spacing={4} w="100%">
        {/* Summary badges */}
        <HStack spacing={4} flexWrap="wrap">
          <Badge colorScheme="blue" px={2} py={1} fontSize="sm">
            Totaal: {validationResult.total_rows} rijen
          </Badge>
          <Badge colorScheme="green" px={2} py={1} fontSize="sm">
            Geldig: {validationResult.valid}
          </Badge>
          <Badge colorScheme="yellow" px={2} py={1} fontSize="sm">
            Waarschuwingen: {validationResult.warnings}
          </Badge>
          <Badge colorScheme="red" px={2} py={1} fontSize="sm">
            Fouten: {validationResult.errors}
          </Badge>
        </HStack>

        {/* Preview table */}
        <Box overflowX="auto" w="100%">
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th color="gray.300">#</Th>
                <Th color="gray.300">Datum</Th>
                <Th color="gray.300">Van</Th>
                <Th color="gray.300">Naar</Th>
                <Th color="gray.300" isNumeric>Begin KM</Th>
                <Th color="gray.300" isNumeric>Eind KM</Th>
                <Th color="gray.300">Categorie</Th>
                <Th color="gray.300">Status</Th>
              </Tr>
            </Thead>
            <Tbody>
              {rows.map((row, idx) => (
                <Tr key={idx} _hover={{ bg: 'gray.700' }}>
                  <Td>{row.row_number ?? idx + 1}</Td>
                  <Td>{row.trip_date}</Td>
                  <Td>{row.start_address}</Td>
                  <Td>{row.end_address}</Td>
                  <Td isNumeric>{row.start_odometer}</Td>
                  <Td isNumeric>{row.end_odometer}</Td>
                  <Td>{row.trip_category || '-'}</Td>
                  <Td>{getStatusBadge(row)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>

        {validationResult.total_rows > MAX_PREVIEW_ROWS && (
          <Text fontSize="xs" color="gray.500">
            Toont eerste {MAX_PREVIEW_ROWS} van {validationResult.total_rows} rijen.
          </Text>
        )}
      </VStack>
    );
  };

  /* ─── Render Step 3: Commit ─── */
  const renderCommitStep = () => {
    if (!validationResult) return null;

    return (
      <VStack spacing={6} w="100%" maxW="500px" mx="auto">
        <Text fontSize="lg" fontWeight="bold" color="white">
          Samenvatting Import
        </Text>

        <Box bg="gray.700" p={4} borderRadius="md" w="100%">
          <VStack spacing={3} align="stretch">
            <Flex justify="space-between">
              <Text color="gray.300">Totaal rijen:</Text>
              <Text color="white" fontWeight="bold">{validationResult.total_rows}</Text>
            </Flex>
            <Flex justify="space-between">
              <Text color="gray.300">Geldig (wordt geïmporteerd):</Text>
              <Text color="green.300" fontWeight="bold">{validationResult.valid}</Text>
            </Flex>
            <Flex justify="space-between">
              <Text color="gray.300">Waarschuwingen:</Text>
              <Text color="yellow.300" fontWeight="bold">{validationResult.warnings}</Text>
            </Flex>
            <Flex justify="space-between">
              <Text color="gray.300">Fouten (wordt overgeslagen):</Text>
              <Text color="red.300" fontWeight="bold">{validationResult.errors}</Text>
            </Flex>
            <Flex justify="space-between" pt={2} borderTop="1px" borderColor="gray.600">
              <Text color="gray.300">Voertuig:</Text>
              <Text color="white">
                {vehicles.find(v => v.id === selectedVehicle)?.license_plate ?? '-'}
              </Text>
            </Flex>
          </VStack>
        </Box>

        {validationResult.errors > 0 && (
          <Text fontSize="sm" color="yellow.400">
            ⚠️ Rijen met fouten worden overgeslagen. Alleen geldige rijen worden geïmporteerd.
          </Text>
        )}

        {importDone ? (
          <Badge colorScheme="green" px={4} py={2} fontSize="md">
            ✓ Import voltooid
          </Badge>
        ) : (
          <Button
            colorScheme="orange"
            size="lg"
            onClick={handleCommit}
            isLoading={importing}
            loadingText="Importeren..."
            isDisabled={validationResult.valid === 0}
          >
            Importeer {validationResult.valid} ritten
          </Button>
        )}
      </VStack>
    );
  };

  /* ─── Main Render ─── */
  return (
    <Box p={4} bg="gray.800" color="white" minH="100vh">
      {/* Stepper */}
      <TripImportStepper currentStep={currentStep} steps={STEPS} />

      {/* Content area */}
      <Box mt={6} mb={6} minH="400px">
        {loading ? (
          <Flex justify="center" py={10}>
            <Spinner color="orange.300" size="lg" />
          </Flex>
        ) : (
          <>
            {currentStep === 0 && renderUploadStep()}
            {currentStep === 1 && renderPreviewStep()}
            {currentStep === 2 && renderCommitStep()}
          </>
        )}
      </Box>

      {/* Navigation buttons */}
      <Flex justify="space-between" maxW="600px" mx="auto">
        <Button
          size="sm"
          variant="outline"
          colorScheme="gray"
          onClick={handleBack}
          isDisabled={currentStep === 0 || importing}
        >
          ← Vorige
        </Button>

        {currentStep < 2 && (
          <Button
            size="sm"
            colorScheme="orange"
            onClick={handleNext}
            isLoading={loading}
            isDisabled={currentStep === 0 && (!file || !selectedVehicle)}
          >
            Volgende →
          </Button>
        )}
      </Flex>
    </Box>
  );
};

export default ZZPTripImport;
