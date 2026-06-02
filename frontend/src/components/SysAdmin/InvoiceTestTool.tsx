import React, { useState, useRef } from 'react';
import {
  Box,
  VStack,
  HStack,
  Button,
  Text,
  Input,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Alert,
  AlertIcon,
  AlertDescription,
  Spinner,
  Icon,
} from '@chakra-ui/react';
import { AttachmentIcon } from '@chakra-ui/icons';
import { processFile } from '../../services/invoiceTestToolService';
import { PipelineResultsPanel } from './PipelineResultsPanel';
import { CustomPromptEditor } from './CustomPromptEditor';
import { VendorHistoryPanel } from './VendorHistoryPanel';
import type { ProcessResponse } from '../../types/invoiceTestTool';

/** Allowed file extensions for invoice upload. */
const ALLOWED_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'csv', 'eml', 'mhtml'];

/** Accept string for the file input element. */
const FILE_ACCEPT = '.pdf,.jpg,.jpeg,.png,.csv,.eml,.mhtml';

/** Maximum file size in bytes (20 MB). */
const MAX_FILE_SIZE = 20 * 1024 * 1024;

/** Regex for vendor name validation. */
const VENDOR_NAME_REGEX = /^[a-zA-Z0-9_ -]{1,100}$/;

/**
 * Validates the file extension against allowed types.
 * Returns an error message or null if valid.
 */
export function validateFileExtension(fileName: string): string | null {
  const ext = fileName.split('.').pop()?.toLowerCase();
  if (!ext || !ALLOWED_EXTENSIONS.includes(ext)) {
    return `Unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ').toUpperCase()}`;
  }
  return null;
}

/**
 * Validates file size against the 20 MB limit.
 * Returns an error message or null if valid.
 */
export function validateFileSize(fileSize: number): string | null {
  if (fileSize > MAX_FILE_SIZE) {
    const sizeMB = (fileSize / (1024 * 1024)).toFixed(1);
    return `File size (${sizeMB} MB) exceeds the 20 MB limit`;
  }
  return null;
}

/**
 * Validates the vendor name against the allowed pattern.
 * Returns an error message or null if valid.
 */
export function validateVendorName(name: string): string | null {
  if (!name) return null; // Empty is allowed — defaults to "TestVendor"
  if (!VENDOR_NAME_REGEX.test(name)) {
    return 'Reference number must be 1–100 characters: letters, numbers, spaces, hyphens, underscores only';
  }
  return null;
}

/**
 * InvoiceTestTool — Top-level tab component for the Invoice Processing Test Tool.
 *
 * Contains the upload form (inline TestToolUploadForm section) and manages
 * the state flow: Upload File → Loading → Display Results.
 * Sub-components (PipelineResultsPanel, CustomPromptEditor, VendorHistoryPanel)
 * will be added in subsequent tasks.
 */
export function InvoiceTestTool() {
  // Form state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [vendorName, setVendorName] = useState('');
  const [administration, setAdministration] = useState('');

  // Validation errors
  const [fileError, setFileError] = useState<string | null>(null);
  const [vendorError, setVendorError] = useState<string | null>(null);

  // Submission state
  const [isLoading, setIsLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Result state (for sub-components to use in later tasks)
  const [result, setResult] = useState<ProcessResponse | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setFileError(null);
    setSubmitError(null);

    if (!file) {
      setSelectedFile(null);
      return;
    }

    // Validate extension
    const extError = validateFileExtension(file.name);
    if (extError) {
      setFileError(extError);
      setSelectedFile(null);
      return;
    }

    // Validate size
    const sizeError = validateFileSize(file.size);
    if (sizeError) {
      setFileError(sizeError);
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  const handleVendorNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setVendorName(value);
    setVendorError(validateVendorName(value));
  };

  const handleAdministrationChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setAdministration(e.target.value);
  };

  const isFormValid = (): boolean => {
    return !!selectedFile && !fileError && !vendorError;
  };

  const handleSubmit = async () => {
    if (!selectedFile || !isFormValid()) return;

    setIsLoading(true);
    setSubmitError(null);
    setResult(null);

    try {
      const response = await processFile(
        selectedFile,
        vendorName || undefined,
        administration || undefined
      );
      setResult(response);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'An unexpected error occurred';
      setSubmitError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box>
      <VStack spacing={6} align="stretch">
        {/* Header */}
        <Text fontSize="2xl" fontWeight="bold" color="orange.400">
          Invoice Processing Test Tool
        </Text>
        <Text fontSize="sm" color="gray.400">
          Upload an invoice file to test the processing pipeline in dry-run mode.
          No data will be written to the database or uploaded to external storage.
        </Text>

        {/* Upload Form */}
        <Box
          p={6}
          bg="gray.700"
          borderRadius="lg"
          borderWidth="1px"
          borderColor="gray.600"
        >
          <VStack spacing={5} align="stretch">
            {/* File Input */}
            <FormControl isInvalid={!!fileError}>
              <FormLabel color="gray.300" fontSize="sm">
                Invoice File *
              </FormLabel>
              <HStack spacing={3}>
                <Button
                  size="sm"
                  colorScheme="orange"
                  variant="outline"
                  leftIcon={<Icon as={AttachmentIcon} />}
                  onClick={() => fileInputRef.current?.click()}
                  isDisabled={isLoading}
                >
                  Choose File
                </Button>
                <Text fontSize="sm" color="gray.400" noOfLines={1}>
                  {selectedFile ? selectedFile.name : 'No file selected'}
                </Text>
                <Input
                  ref={fileInputRef}
                  type="file"
                  accept={FILE_ACCEPT}
                  onChange={handleFileChange}
                  display="none"
                  aria-label="Invoice file upload"
                />
              </HStack>
              {fileError && (
                <FormErrorMessage>{fileError}</FormErrorMessage>
              )}
              <Text fontSize="xs" color="gray.500" mt={1}>
                Accepted: PDF, JPG, JPEG, PNG, CSV, EML, MHTML (max 20 MB)
              </Text>
            </FormControl>

            {/* Vendor Name Input */}
            <FormControl isInvalid={!!vendorError}>
              <FormLabel color="gray.300" fontSize="sm">
                Reference Number
              </FormLabel>
              <Input
                value={vendorName}
                onChange={handleVendorNameChange}
                placeholder="TestVendor"
                size="sm"
                bg="gray.800"
                color="white"
                borderColor="gray.600"
                _placeholder={{ color: 'gray.500' }}
                isDisabled={isLoading}
                maxLength={100}
              />
              {vendorError && (
                <FormErrorMessage>{vendorError}</FormErrorMessage>
              )}
              <Text fontSize="xs" color="gray.500" mt={1}>
                Optional. Letters, numbers, spaces, hyphens, underscores. Defaults to "TestVendor".
              </Text>
            </FormControl>

            {/* Administration Input */}
            <FormControl>
              <FormLabel color="gray.300" fontSize="sm">
                Administration
              </FormLabel>
              <Input
                value={administration}
                onChange={handleAdministrationChange}
                placeholder="Optional tenant identifier"
                size="sm"
                bg="gray.800"
                color="white"
                borderColor="gray.600"
                _placeholder={{ color: 'gray.500' }}
                isDisabled={isLoading}
              />
              <Text fontSize="xs" color="gray.500" mt={1}>
                Optional. Used for vendor history lookup across tenants.
              </Text>
            </FormControl>

            {/* Submit Button */}
            <Button
              colorScheme="orange"
              onClick={handleSubmit}
              isDisabled={!isFormValid() || isLoading}
              isLoading={isLoading}
              loadingText="Processing..."
              spinner={<Spinner size="sm" />}
              size="md"
              width="fit-content"
            >
              Process File
            </Button>
          </VStack>
        </Box>

        {/* Submit Error Display */}
        {submitError && (
          <Alert status="error" bg="red.900" borderRadius="md">
            <AlertIcon />
            <AlertDescription color="gray.200">
              {submitError}
            </AlertDescription>
          </Alert>
        )}

        {/* Pipeline Results */}
        {result && !submitError && (
          <PipelineResultsPanel response={result} />
        )}

        {/* Custom Prompt Editor — shown when AI was used and raw text is available */}
        {result && !submitError && result.pipeline_result.parser_used !== 'csv_rule' && (
          <CustomPromptEditor
            originalPrompt={result.prompt_used || ''}
            originalResult={result.pipeline_result.extraction_result}
            textContent={result.pipeline_result.raw_text}
            vendorHint={vendorName || undefined}
          />
        )}

        {/* Vendor History Panel — shown after results for context lookup */}
        {result && !submitError && (
          <VendorHistoryPanel
            vendorName={vendorName || result.pipeline_result.folder_name}
            administration={administration || undefined}
          />
        )}
      </VStack>
    </Box>
  );
}

export default InvoiceTestTool;
