/**
 * Template Upload Component
 * 
 * Allows users to upload HTML template files with validation.
 * Includes template type selection and optional field mappings editor.
 */

import React, { useState, useRef, useEffect } from 'react';
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
  useToast,
} from '@chakra-ui/react';
import { TemplateType, getCurrentTemplate, CurrentTemplateResponse, downloadDefaultTemplate, deleteTenantTemplate } from '../../../services/templateApi';
import { CurrentTemplateInfo } from './CurrentTemplateInfo';
import { DeleteTemplateDialog } from './DeleteTemplateDialog';
import { UploadInstructions } from './UploadInstructions';

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
  { value: 'zzp_invoice', label: 'ZZP Invoice', description: 'ZZP freelancer invoice template' },
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
  const [currentTemplate, setCurrentTemplate] = useState<CurrentTemplateResponse | null>(null);
  const [loadingCurrent, setLoadingCurrent] = useState(false);
  const [downloadingDefault, setDownloadingDefault] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const { isOpen: showMappings, onToggle: toggleMappings } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const toast = useToast();

  /**
   * Load current template when template type changes
   */
  useEffect(() => {
    if (!templateType) {
      setCurrentTemplate(null);
      setFieldMappings('{}');
      return;
    }

    const loadCurrentTemplate = async () => {
      setLoadingCurrent(true);
      try {
        const response = await getCurrentTemplate(templateType);
        if (response.success && response.template_content) {
          setCurrentTemplate(response);
          if (response.field_mappings && Object.keys(response.field_mappings).length > 0) {
            setFieldMappings(JSON.stringify(response.field_mappings, null, 2));
          } else {
            setFieldMappings('{}');
          }
        } else {
          setCurrentTemplate(null);
          setFieldMappings('{}');
        }
      } catch {
        setCurrentTemplate(null);
        setFieldMappings('{}');
      } finally {
        setLoadingCurrent(false);
      }
    };

    loadCurrentTemplate();
  }, [templateType]);

  const clearErrors = () => setErrors({});

  const validateFile = (file: File): string | null => {
    if (!file.name.endsWith('.html') && !file.name.endsWith('.htm')) {
      return 'Only HTML files (.html, .htm) are allowed';
    }
    if (file.size > MAX_FILE_SIZE) {
      return `File size exceeds 5MB limit (${(file.size / 1024 / 1024).toFixed(2)}MB)`;
    }
    return null;
  };

  const validateFieldMappings = (jsonString: string): string | null => {
    if (!jsonString.trim() || jsonString.trim() === '{}') return null;
    try {
      JSON.parse(jsonString);
      return null;
    } catch {
      return 'Invalid JSON format';
    }
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    clearErrors();
    const file = event.target.files?.[0];
    if (!file) {
      setSelectedFile(null);
      return;
    }
    const error = validateFile(file);
    if (error) {
      setErrors({ file: error });
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  };

  const handleTemplateTypeChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    clearErrors();
    setTemplateType(event.target.value as TemplateType);
  };

  const handleDownloadCurrent = () => {
    if (!currentTemplate || !currentTemplate.success || !currentTemplate.template_content) return;
    const blob = new Blob([currentTemplate.template_content], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${currentTemplate.template_type}_current.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadDefault = async () => {
    if (!templateType) return;
    setDownloadingDefault(true);
    try {
      const response = await downloadDefaultTemplate(templateType as TemplateType);
      const blob = new Blob([response.template_content], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = response.filename || `${templateType}_default.html`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast({ title: 'Default template downloaded', description: `Downloaded ${response.filename}`, status: 'success', duration: 3000 });
    } catch (error) {
      toast({ title: 'Failed to download default template', description: error instanceof Error ? error.message : 'An error occurred', status: 'error', duration: 5000 });
    } finally {
      setDownloadingDefault(false);
    }
  };

  const handleDeleteTemplate = async () => {
    if (!templateType) return;
    setDeleting(true);
    try {
      await deleteTenantTemplate(templateType as TemplateType);
      onDeleteClose();
      setCurrentTemplate(null);
      toast({ title: 'Template deleted', description: 'Tenant template removed. The system will use the default template.', status: 'success', duration: 3000 });
    } catch (error) {
      toast({ title: 'Failed to delete template', description: error instanceof Error ? error.message : 'An error occurred', status: 'error', duration: 5000 });
    } finally {
      setDeleting(false);
    }
  };

  const handleFieldMappingsChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setFieldMappings(event.target.value);
    const error = validateFieldMappings(event.target.value);
    if (!error) {
      setErrors((prev) => ({ ...prev, fieldMappings: undefined }));
    }
  };

  const handleUpload = () => {
    clearErrors();
    const newErrors: typeof errors = {};
    if (!selectedFile) newErrors.file = 'Please select a file';
    if (!templateType) newErrors.templateType = 'Please select a template type';
    const mappingsError = validateFieldMappings(fieldMappings);
    if (mappingsError) newErrors.fieldMappings = mappingsError;

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    let parsedMappings: Record<string, any> = {};
    if (fieldMappings.trim() && fieldMappings.trim() !== '{}') {
      try {
        parsedMappings = JSON.parse(fieldMappings);
      } catch {
        setErrors({ fieldMappings: 'Invalid JSON format' });
        return;
      }
    }

    if (selectedFile && templateType) {
      onUpload(selectedFile, templateType, parsedMappings);
    }
  };

  const handleBrowseClick = () => fileInputRef.current?.click();

  const handleLoadCurrent = async () => {
    if (!templateType) {
      toast({ title: 'Select template type first', description: 'Please select a template type before loading the current template', status: 'warning', duration: 3000 });
      return;
    }
    setLoadingCurrent(true);
    try {
      const response = await getCurrentTemplate(templateType as TemplateType);
      if (!response.success || !response.template_content) {
        throw new Error('No active template found');
      }
      const blob = new Blob([response.template_content], { type: 'text/html' });
      const file = new File([blob], `${templateType}_current.html`, { type: 'text/html' });
      setSelectedFile(file);
      if (response.field_mappings && Object.keys(response.field_mappings).length > 0) {
        setFieldMappings(JSON.stringify(response.field_mappings, null, 2));
      }
      toast({ title: 'Template loaded', description: `Current ${templateType} template loaded. Modify and upload when ready.`, status: 'success', duration: 3000 });
    } catch (error) {
      toast({ title: 'Failed to load template', description: error instanceof Error ? error.message : 'No active template found', status: 'error', duration: 5000 });
    } finally {
      setLoadingCurrent(false);
    }
  };

  const selectedTemplateDescription = TEMPLATE_TYPES.find((t) => t.value === templateType)?.description;
  const templateLabel = TEMPLATE_TYPES.find((t) => t.value === templateType)?.label ?? templateType;

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

      {/* Current Template Info */}
      {templateType && (
        <Box>
          <CurrentTemplateInfo
            currentTemplate={currentTemplate}
            loadingCurrent={loadingCurrent}
            downloadingDefault={downloadingDefault}
            disabled={disabled}
            loading={loading}
            onDownloadCurrent={handleDownloadCurrent}
            onLoadCurrent={handleLoadCurrent}
            onDeleteOpen={onDeleteOpen}
            onDownloadDefault={handleDownloadDefault}
          />
        </Box>
      )}

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
              rows={25}
              minHeight="500px"
              fontFamily="monospace"
              fontSize="xs"
              isDisabled={disabled || loading}
              bg="gray.800"
              aria-label="Field Mappings (JSON)"
              resize="vertical"
              whiteSpace="pre"
              overflowX="auto"
            />
            <HStack spacing={2} mt={2}>
              <Button
                size="xs"
                variant="outline"
                onClick={() => {
                  try {
                    const parsed = JSON.parse(fieldMappings);
                    setFieldMappings(JSON.stringify(parsed, null, 2));
                    setErrors((prev) => ({ ...prev, fieldMappings: undefined }));
                  } catch {
                    setErrors((prev) => ({ ...prev, fieldMappings: 'Invalid JSON format' }));
                  }
                }}
                isDisabled={disabled || loading}
              >
                Format JSON
              </Button>
              <Button
                size="xs"
                variant="outline"
                onClick={() => {
                  setFieldMappings('{}');
                  setErrors((prev) => ({ ...prev, fieldMappings: undefined }));
                }}
                isDisabled={disabled || loading}
              >
                Clear
              </Button>
            </HStack>
            <FormHelperText color="gray.400" fontSize="xs">
              Optional: Customize field mappings in JSON format. Leave empty to auto-generate from template placeholders.
              The textarea is resizable - drag the bottom-right corner to expand.
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
      <UploadInstructions />

      {/* Delete Confirmation Dialog */}
      <DeleteTemplateDialog
        isOpen={isDeleteOpen}
        onClose={onDeleteClose}
        onConfirm={handleDeleteTemplate}
        deleting={deleting}
        templateLabel={templateLabel}
        cancelRef={cancelRef as React.RefObject<HTMLButtonElement>}
      />
    </VStack>
  );
};

export default TemplateUpload;
