/**
 * Template Upload Component
 * 
 * Allows users to upload HTML template files with validation.
 * Includes template type selection and optional field mappings editor.
 */

import React, { useState, useRef } from 'react';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  FormErrorMessage,
  FormHelperText,
  Select,
  VStack,
  HStack,
  Input,
  Text,
  Textarea,
  Collapse,
  useDisclosure,
} from '@chakra-ui/react';
import { TemplateType } from '../../../services/templateApi';

/**
 * Component props
 */
interface TemplateUploadProps {
  onUpload: (file: File, templateType: TemplateType, fieldMappings?: Record<string, any>) => void;
  loading?: boolean;
  disabled?: boolean;
}

/**
 * Template type options
 */
const TEMPLATE_TYPES: Array<{ value: TemplateType; label: string; description: string }> = [
  { value: 'str_invoice_nl', label: 'STR Invoice (Dutch)', description: 'Short-term rental invoice in Dutch' },
  { value: 'str_invoice_en', label: 'STR Invoice (English)', description: 'Short-term rental invoice in English' },
  { value: 'btw_aangifte', label: 'BTW Aangifte', description: 'VAT declaration report' },
  { value: 'aangifte_ib', label: 'Aangifte IB', description: 'Income tax declaration report' },
  { value: 'toeristenbelasting', label: 'Toeristenbelasting', description: 'Tourist tax report' },
  { value: 'financial_report', label: 'Financial Report', description: 'General financial report' },
];

/**
 * Max file size (5MB)
 */
const MAX_FILE_SIZE = 5 * 1024 * 1024;

/**
 * TemplateUpload Component
 */
export const TemplateUpload: React.FC<TemplateUploadProps> = ({
  onUpload,
  loading = false,
  disabled = false,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [templateType, setTemplateType] = useState<TemplateType | ''>('');
  const [fieldMappings, setFieldMappings] = useState<string>('{}');
  const [errors, setErrors] = useState<{
    file?: string;
    templateType?: string;
    fieldMappings?: string;
  }>({});

  const fileInputRef = useRef<HTMLInputElement>(null);
  const { isOpen: showMappings, onToggle: toggleMappings } = useDisclosure();

  /**
   * Clear all errors
   */
  const clearErrors = () => {
    setErrors({});
  };

  /**
   * Validate file
   */
  const validateFile = (file: File): string | null => {
    // Check file type
    if (!file.name.endsWith('.html') && !file.name.endsWith('.htm')) {
      return 'Only HTML files (.html, .htm) are allowed';
    }

    // Check file size
    if (file.size > MAX_FILE_SIZE) {
      return `File size exceeds 5MB limit (${(file.size / 1024 / 1024).toFixed(2)}MB)`;
    }

    return null;
  };

  /**
   * Validate field mappings JSON
   */
  const validateFieldMappings = (jsonString: string): string | null => {
    if (!jsonString.trim() || jsonString.trim() === '{}') {
      return null; // Empty is valid (optional)
    }

    try {
      JSON.parse(jsonString);
      return null;
    } catch (err) {
      return 'Invalid JSON format';
    }
  };

  /**
   * Handle file selection
   */
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    clearErrors();
    const file = event.target.files?.[0];

    if (!file) {
      setSelectedFile(null);
      return;
    }

    // Validate file
    const error = validateFile(file);
    if (error) {
      setErrors({ file: error });
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  /**
   * Handle template type change
   */
  const handleTemplateTypeChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    clearErrors();
    setTemplateType(event.target.value as TemplateType);
  };

  /**
   * Handle field mappings change
   */
  const handleFieldMappingsChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setFieldMappings(event.target.value);
    
    // Clear field mappings error if valid
    const error = validateFieldMappings(event.target.value);
    if (!error) {
      setErrors((prev) => ({ ...prev, fieldMappings: undefined }));
    }
  };

  /**
   * Handle upload button click
   */
  const handleUpload = () => {
    clearErrors();

    // Validate all fields
    const newErrors: typeof errors = {};

    if (!selectedFile) {
      newErrors.file = 'Please select a file';
    }

    if (!templateType) {
      newErrors.templateType = 'Please select a template type';
    }

    const mappingsError = validateFieldMappings(fieldMappings);
    if (mappingsError) {
      newErrors.fieldMappings = mappingsError;
    }

    // If there are errors, show them and return
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    // Parse field mappings
    let parsedMappings: Record<string, any> = {};
    if (fieldMappings.trim() && fieldMappings.trim() !== '{}') {
      try {
        parsedMappings = JSON.parse(fieldMappings);
      } catch {
        // Should not happen due to validation above
        setErrors({ fieldMappings: 'Invalid JSON format' });
        return;
      }
    }

    // Call onUpload callback
    if (selectedFile && templateType) {
      onUpload(selectedFile, templateType, parsedMappings);
    }
  };

  /**
   * Handle browse button click
   */
  const handleBrowseClick = () => {
    fileInputRef.current?.click();
  };

  /**
   * Get selected template description
   */
  const selectedTemplateDescription = TEMPLATE_TYPES.find(
    (t) => t.value === templateType
  )?.description;

  return (
    <VStack spacing={6} align="stretch">
      {/* Template Type Selection */}
      <FormControl isInvalid={!!errors.templateType} isRequired>
        <FormLabel>Template Type</FormLabel>
        <Select
          placeholder="Select template type"
          value={templateType}
          onChange={handleTemplateTypeChange}
          isDisabled={disabled || loading}
          aria-label="Template Type"
        >
          {TEMPLATE_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </Select>
        {selectedTemplateDescription && (
          <FormHelperText color="gray.400">{selectedTemplateDescription}</FormHelperText>
        )}
        {errors.templateType && (
          <FormErrorMessage>{errors.templateType}</FormErrorMessage>
        )}
      </FormControl>

      {/* File Upload */}
      <FormControl isInvalid={!!errors.file} isRequired>
        <FormLabel>Template File</FormLabel>
        <Input
          ref={fileInputRef}
          type="file"
          accept=".html,.htm"
          onChange={handleFileChange}
          display="none"
          aria-label="Upload HTML template file"
        />
        <HStack spacing={4}>
          <Button
            onClick={handleBrowseClick}
            isDisabled={disabled || loading}
            variant="outline"
            flex={1}
          >
            {selectedFile ? 'Change File' : 'Browse Files'}
          </Button>
          {selectedFile && (
            <Box flex={2}>
              <Text fontSize="sm" color="gray.300">
                {selectedFile.name}
              </Text>
              <Text fontSize="xs" color="gray.500">
                {(selectedFile.size / 1024).toFixed(2)} KB
              </Text>
            </Box>
          )}
        </HStack>
        <FormHelperText color="gray.400">
          HTML files only, max 5MB
        </FormHelperText>
        {errors.file && <FormErrorMessage>{errors.file}</FormErrorMessage>}
      </FormControl>

      {/* Field Mappings (Optional) */}
      <Box>
        <Button
          size="sm"
          variant="ghost"
          onClick={toggleMappings}
          isDisabled={disabled || loading}
          mb={2}
        >
          {showMappings ? '▼' : '▶'} Advanced: Field Mappings (Optional)
        </Button>
        <Collapse in={showMappings} animateOpacity>
          <FormControl isInvalid={!!errors.fieldMappings}>
            <FormLabel fontSize="sm">Field Mappings (JSON)</FormLabel>
            <Textarea
              value={fieldMappings}
              onChange={handleFieldMappingsChange}
              placeholder='{"field_name": "custom_value"}'
              rows={6}
              fontFamily="monospace"
              fontSize="sm"
              isDisabled={disabled || loading}
              bg="gray.800"
              aria-label="Field Mappings (JSON)"
            />
            <FormHelperText color="gray.400" fontSize="xs">
              Optional: Customize field mappings in JSON format. Leave empty to use defaults.
            </FormHelperText>
            {errors.fieldMappings && (
              <FormErrorMessage>{errors.fieldMappings}</FormErrorMessage>
            )}
          </FormControl>
        </Collapse>
      </Box>

      {/* Upload Button */}
      <Button
        colorScheme="orange"
        size="lg"
        onClick={handleUpload}
        isLoading={loading}
        isDisabled={disabled || !selectedFile || !templateType}
        loadingText="Uploading..."
      >
        Upload & Preview Template
      </Button>

      {/* Help Text */}
      <Box bg="blue.900" p={4} borderRadius="md">
        <Text fontSize="sm" fontWeight="bold" mb={2}>
          📝 Upload Instructions
        </Text>
        <VStack align="start" spacing={1} fontSize="xs" color="gray.300">
          <Text>1. Select the template type from the dropdown</Text>
          <Text>2. Choose your HTML template file (max 5MB)</Text>
          <Text>3. Optionally configure field mappings</Text>
          <Text>4. Click "Upload & Preview Template" to validate</Text>
        </VStack>
      </Box>
    </VStack>
  );
};

export default TemplateUpload;
