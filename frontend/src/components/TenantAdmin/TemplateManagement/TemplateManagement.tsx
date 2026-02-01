/**
 * Template Management Component
 * 
 * Main container component for template management.
 * Allows Tenant Administrators to upload, preview, validate, and manage custom report templates.
 */

import React, { useState } from 'react';
import {
  Box,
  Button,
  Container,
  Heading,
  Text,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  CloseButton,
  VStack,
  HStack,
  Grid,
  GridItem,
  Progress,
  useToast,
} from '@chakra-ui/react';
import * as templateApi from '../../../services/templateApi';
import type {
  TemplateType,
  ValidationResult,
  AIHelpResponse,
  AIFixSuggestion,
} from '../../../services/templateApi';
import { TemplateUpload } from './TemplateUpload';
import { TemplatePreview } from './TemplatePreview';
import { ValidationResults } from './ValidationResults';
import { TemplateApproval } from './TemplateApproval';
import { AIHelpButton } from './AIHelpButton';

/**
 * Component state interface
 */
interface TemplateManagementState {
  // Template data
  templateContent: string;
  templateType: TemplateType | '';
  fieldMappings: Record<string, any>;
  
  // Validation and preview
  validationResult: ValidationResult | null;
  previewHtml: string;
  sampleDataInfo: { source: string; record_count?: number } | null;
  
  // AI assistance
  aiSuggestions: AIHelpResponse | null;
  
  // UI state
  loading: boolean;
  error: string;
  success: string;
  
  // Step tracking
  currentStep: 'upload' | 'preview' | 'approval';
}

/**
 * Initial state
 */
const initialState: TemplateManagementState = {
  templateContent: '',
  templateType: '',
  fieldMappings: {},
  validationResult: null,
  previewHtml: '',
  sampleDataInfo: null,
  aiSuggestions: null,
  loading: false,
  error: '',
  success: '',
  currentStep: 'upload',
};

/**
 * TemplateManagement Component
 */
export const TemplateManagement: React.FC = () => {
  const [state, setState] = useState<TemplateManagementState>(initialState);
  const toast = useToast();

  /**
   * Update state helper
   */
  const updateState = (updates: Partial<TemplateManagementState>) => {
    setState((prev) => ({ ...prev, ...updates }));
  };

  /**
   * Clear messages
   */
  const clearMessages = () => {
    updateState({ error: '', success: '' });
  };

  /**
   * Handle file upload and preview generation
   */
  const handleUpload = async (
    file: File,
    templateType: TemplateType,
    fieldMappings?: Record<string, any>
  ) => {
    clearMessages();
    updateState({ loading: true });

    try {
      // Read file content
      const content = await readFileAsText(file);

      // Validate file size (max 5MB)
      if (file.size > 5 * 1024 * 1024) {
        throw new Error('File size exceeds 5MB limit');
      }

      // Validate file type
      if (!file.name.endsWith('.html') && !file.name.endsWith('.htm')) {
        throw new Error('Only HTML files are allowed');
      }

      // Call preview API
      const result = await templateApi.previewTemplate(
        templateType,
        content,
        fieldMappings
      );

      // Update state with results
      updateState({
        templateContent: content,
        templateType,
        fieldMappings: fieldMappings || {},
        validationResult: result.validation,
        previewHtml: result.preview_html || '',
        sampleDataInfo: result.sample_data_info || null,
        currentStep: 'preview',
        loading: false,
      });

      // Show success or validation errors
      if (result.validation.is_valid) {
        updateState({ success: 'Template validated successfully!' });
        toast({
          title: 'Template validated',
          description: 'Your template passed all validation checks',
          status: 'success',
          duration: 5000,
          isClosable: true,
        });
      } else {
        updateState({
          error: `Template has ${result.validation.errors.length} error(s). Please review and fix.`,
        });
        toast({
          title: 'Validation failed',
          description: `Found ${result.validation.errors.length} error(s) in your template`,
          status: 'error',
          duration: 7000,
          isClosable: true,
        });
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to upload template';
      updateState({
        loading: false,
        error: errorMessage,
      });
      toast({
        title: 'Upload failed',
        description: errorMessage,
        status: 'error',
        duration: 7000,
        isClosable: true,
      });
    }
  };

  /**
   * Handle template approval
   */
  const handleApprove = async (notes?: string) => {
    if (!state.templateType || !state.templateContent) {
      updateState({ error: 'No template to approve' });
      return;
    }

    if (!state.validationResult?.is_valid) {
      updateState({ error: 'Cannot approve template with validation errors' });
      return;
    }

    clearMessages();
    updateState({ loading: true });

    try {
      const result = await templateApi.approveTemplate(
        state.templateType,
        state.templateContent,
        state.fieldMappings,
        notes
      );

      updateState({
        loading: false,
        success: `Template approved successfully! Template ID: ${result.template_id}`,
        currentStep: 'approval',
      });

      toast({
        title: 'Template approved',
        description: `Template has been saved and activated. ID: ${result.template_id}`,
        status: 'success',
        duration: 5000,
        isClosable: true,
      });

      // Reset form after 3 seconds
      setTimeout(() => {
        setState(initialState);
      }, 3000);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to approve template';
      updateState({
        loading: false,
        error: errorMessage,
      });
      toast({
        title: 'Approval failed',
        description: errorMessage,
        status: 'error',
        duration: 7000,
        isClosable: true,
      });
    }
  };

  /**
   * Handle template rejection
   */
  const handleReject = async (reason?: string) => {
    if (!state.templateType) {
      updateState({ error: 'No template to reject' });
      return;
    }

    clearMessages();
    updateState({ loading: true });

    try {
      const result = await templateApi.rejectTemplate(state.templateType, reason);

      updateState({
        loading: false,
        success: result.message,
      });

      toast({
        title: 'Template rejected',
        description: 'Template has been discarded. You can upload a new one.',
        status: 'info',
        duration: 5000,
        isClosable: true,
      });

      // Reset form after 2 seconds
      setTimeout(() => {
        setState(initialState);
      }, 2000);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to reject template';
      updateState({
        loading: false,
        error: errorMessage,
      });
      toast({
        title: 'Rejection failed',
        description: errorMessage,
        status: 'error',
        duration: 7000,
        isClosable: true,
      });
    }
  };

  /**
   * Handle AI help request
   */
  const handleAIHelp = async () => {
    if (!state.templateType || !state.templateContent || !state.validationResult) {
      updateState({ error: 'No template or validation errors to analyze' });
      return;
    }

    if (state.validationResult.errors.length === 0) {
      updateState({ error: 'No validation errors to fix' });
      return;
    }

    clearMessages();
    updateState({ loading: true });

    try {
      const result = await templateApi.getAIHelp(
        state.templateType,
        state.templateContent,
        state.validationResult.errors,
        getRequiredPlaceholders(state.templateType)
      );

      updateState({
        loading: false,
        aiSuggestions: result,
        success: result.fallback
          ? 'AI service unavailable. Showing generic help.'
          : 'AI analysis complete!',
      });

      toast({
        title: result.fallback ? 'AI unavailable' : 'AI analysis complete',
        description: result.fallback
          ? 'Showing generic help suggestions'
          : `Found ${result.ai_suggestions?.fixes.length || 0} suggested fixes`,
        status: result.fallback ? 'warning' : 'success',
        duration: 5000,
        isClosable: true,
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to get AI help';
      updateState({
        loading: false,
        error: errorMessage,
      });
      toast({
        title: 'AI help failed',
        description: errorMessage,
        status: 'error',
        duration: 7000,
        isClosable: true,
      });
    }
  };

  /**
   * Handle applying AI fixes
   */
  const handleApplyAIFixes = async (fixes: AIFixSuggestion[]) => {
    if (!state.templateContent) {
      updateState({ error: 'No template to fix' });
      return;
    }

    clearMessages();
    updateState({ loading: true });

    try {
      const result = await templateApi.applyAIFixes(state.templateContent, fixes);

      // Re-validate with fixed template
      if (state.templateType) {
        const previewResult = await templateApi.previewTemplate(
          state.templateType,
          result.fixed_template,
          state.fieldMappings
        );

        updateState({
          templateContent: result.fixed_template,
          validationResult: previewResult.validation,
          previewHtml: previewResult.preview_html || '',
          loading: false,
          success: `Applied ${result.fixes_applied} fix(es). Please review the updated template.`,
          aiSuggestions: null, // Clear AI suggestions after applying
        });

        toast({
          title: 'Fixes applied',
          description: `Applied ${result.fixes_applied} fix(es). Template has been updated and re-validated.`,
          status: 'success',
          duration: 5000,
          isClosable: true,
        });
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to apply AI fixes';
      updateState({
        loading: false,
        error: errorMessage,
      });
      toast({
        title: 'Failed to apply fixes',
        description: errorMessage,
        status: 'error',
        duration: 7000,
        isClosable: true,
      });
    }
  };

  /**
   * Handle starting over
   */
  const handleStartOver = () => {
    setState(initialState);
  };

  return (
    <Container maxW="container.xl" py={8}>
      {/* Header */}
      <VStack spacing={2} align="start" mb={8}>
        <Heading size="xl">Template Management</Heading>
        <Text color="gray.400">Upload and customize report templates for your organization</Text>
      </VStack>

      {/* Error and Success Messages */}
      {state.error && (
        <Alert status="error" mb={4} bg="red.900" borderRadius="md">
          <AlertIcon />
          <Box flex="1">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{state.error}</AlertDescription>
          </Box>
          <CloseButton onClick={clearMessages} />
        </Alert>
      )}

      {state.success && (
        <Alert status="success" mb={4} bg="green.900" borderRadius="md">
          <AlertIcon />
          <Box flex="1">
            <AlertTitle>Success</AlertTitle>
            <AlertDescription>{state.success}</AlertDescription>
          </Box>
          <CloseButton onClick={clearMessages} />
        </Alert>
      )}

      {/* Loading Progress */}
      {state.loading && (
        <Box mb={4}>
          <Progress size="xs" isIndeterminate colorScheme="orange" />
          <Text mt={2} fontSize="sm" color="gray.400">Processing template...</Text>
        </Box>
      )}

      {/* Step Indicator */}
      <HStack spacing={4} mb={8} justify="center" role="navigation" aria-label="Template upload progress">
        <Box role="group" aria-label="Step 1: Upload" aria-current={state.currentStep === 'upload' ? 'step' : undefined}>
          <StepIndicator
            number={1}
            label="Upload"
            isActive={state.currentStep === 'upload'}
            isCompleted={state.currentStep !== 'upload'}
          />
        </Box>
        <Box w="50px" h="2px" bg={state.currentStep !== 'upload' ? 'brand.orange' : 'gray.700'} aria-hidden="true" />
        <Box role="group" aria-label="Step 2: Preview and Validate" aria-current={state.currentStep === 'preview' ? 'step' : undefined}>
          <StepIndicator
            number={2}
            label="Preview & Validate"
            isActive={state.currentStep === 'preview'}
            isCompleted={state.currentStep === 'approval'}
          />
        </Box>
        <Box w="50px" h="2px" bg={state.currentStep === 'approval' ? 'brand.orange' : 'gray.700'} aria-hidden="true" />
        <Box role="group" aria-label="Step 3: Approve" aria-current={state.currentStep === 'approval' ? 'step' : undefined}>
          <StepIndicator
            number={3}
            label="Approve"
            isActive={state.currentStep === 'approval'}
            isCompleted={false}
          />
        </Box>
      </HStack>

      {/* Main Content */}
      <Box bg="brand.gray" borderRadius="lg" p={8}>
        {/* Upload Step */}
        {state.currentStep === 'upload' && (
          <TemplateUpload
            onUpload={handleUpload}
            loading={state.loading}
            disabled={state.loading}
          />
        )}

        {/* Preview Step */}
        {state.currentStep === 'preview' && (
          <VStack spacing={6} align="stretch">
            <Grid 
              templateColumns={{ base: "1fr", lg: "1fr 2fr" }} 
              gap={6}
            >
              {/* Left Column: Validation Results */}
              <GridItem>
                <VStack spacing={4} align="stretch">
                  <Heading size="md">Validation Results</Heading>
                  <ValidationResults validationResult={state.validationResult} />

                  {/* AI Help Button */}
                  <AIHelpButton
                    onRequestHelp={handleAIHelp}
                    onApplyFixes={handleApplyAIFixes}
                    aiSuggestions={state.aiSuggestions}
                    hasErrors={(state.validationResult?.errors?.length ?? 0) > 0}
                    loading={state.loading}
                    disabled={state.loading}
                  />
                </VStack>
              </GridItem>

              {/* Right Column: Preview */}
              <GridItem>
                <VStack spacing={4} align="stretch">
                  <Heading size="md">Template Preview</Heading>
                  <TemplatePreview
                    previewHtml={state.previewHtml}
                    loading={state.loading}
                    sampleDataInfo={state.sampleDataInfo}
                  />
                </VStack>
              </GridItem>
            </Grid>

            {/* Action Buttons */}
            <Box pt={6} borderTop="1px solid" borderColor="gray.700">
              <HStack spacing={4} mb={4}>
                <Button
                  variant="outline"
                  onClick={handleStartOver}
                  isDisabled={state.loading}
                >
                  Start Over
                </Button>
              </HStack>
              <TemplateApproval
                onApprove={handleApprove}
                onReject={handleReject}
                isValid={state.validationResult?.is_valid || false}
                loading={state.loading}
                disabled={state.loading}
              />
            </Box>
          </VStack>
        )}

        {/* Approval Step */}
        {state.currentStep === 'approval' && (
          <VStack spacing={6} align="center" py={12}>
            <Heading size="lg">Template Approved! ✅</Heading>
            <Text color="gray.400">Your template has been saved and is now active.</Text>
            <Button colorScheme="orange" onClick={handleStartOver}>
              Upload Another Template
            </Button>
          </VStack>
        )}
      </Box>
    </Container>
  );
};

/**
 * Helper function to read file as text
 */
function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      if (e.target?.result) {
        resolve(e.target.result as string);
      } else {
        reject(new Error('Failed to read file'));
      }
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsText(file);
  });
}

/**
 * Get required placeholders for template type
 */
function getRequiredPlaceholders(templateType: TemplateType): string[] {
  const placeholders: Record<TemplateType, string[]> = {
    str_invoice_nl: ['invoice_number', 'invoice_date', 'company_name', 'total_amount'],
    str_invoice_en: ['invoice_number', 'invoice_date', 'company_name', 'total_amount'],
    btw_aangifte: ['period', 'year', 'quarter', 'btw_total'],
    aangifte_ib: ['year', 'administration', 'total_income', 'total_expenses'],
    toeristenbelasting: ['year', 'accommodation_name', 'total_nights', 'tourist_tax'],
    financial_report: ['year', 'administration', 'report_type'],
  };

  return placeholders[templateType] || [];
}

/**
 * Step Indicator Component
 */
interface StepIndicatorProps {
  number: number;
  label: string;
  isActive: boolean;
  isCompleted: boolean;
}

const StepIndicator: React.FC<StepIndicatorProps> = ({ number, label, isActive, isCompleted }) => {
  const status = isCompleted ? 'completed' : isActive ? 'current' : 'upcoming';
  
  return (
    <VStack spacing={2}>
      <Box
        w="40px"
        h="40px"
        borderRadius="full"
        bg={isActive ? 'brand.orange' : isCompleted ? 'green.500' : 'gray.700'}
        color="white"
        display="flex"
        alignItems="center"
        justifyContent="center"
        fontWeight="bold"
        aria-label={`Step ${number}: ${label}, ${status}`}
      >
        {number}
      </Box>
      <Text
        fontSize="sm"
        color={isActive ? 'brand.orange' : 'gray.400'}
        fontWeight={isActive ? 'bold' : 'normal'}
        aria-hidden="true"
      >
        {label}
      </Text>
    </VStack>
  );
};

export default TemplateManagement;
