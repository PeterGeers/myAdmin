/**
 * Template API Service
 * 
 * This service provides API calls for template management operations
 * including preview, validation, approval, rejection, and AI assistance.
 */

import { authenticatedRequest } from './apiService';
import type {
  TemplateType,
  ValidationError,
  ValidationResult,
  PreviewResponse,
  AIFixSuggestion,
  AIHelpResponse,
  ApprovalResponse,
  RejectionResponse,
  ApplyFixesResponse,
  FieldMappings,
  CurrentTemplateResponse,
} from '../types/template';

// Re-export types from the types file
export type {
  TemplateType,
  ValidationError,
  ValidationResult,
  PreviewResponse,
  AIFixSuggestion,
  AIHelpResponse,
  ApprovalResponse,
  RejectionResponse,
  ApplyFixesResponse,
  FieldMappings,
  CurrentTemplateResponse,
} from '../types/template';

/**
 * Preview a template with sample data
 * 
 * @param templateType - Type of template
 * @param templateContent - HTML template content
 * @param fieldMappings - Optional field mappings
 * @returns Preview response with HTML and validation results
 */
export async function previewTemplate(
  templateType: TemplateType,
  templateContent: string,
  fieldMappings?: FieldMappings
): Promise<PreviewResponse> {
  const response = await authenticatedRequest('/api/tenant-admin/templates/preview', {
    method: 'POST',
    body: JSON.stringify({
      template_type: templateType,
      template_content: templateContent,
      field_mappings: fieldMappings || {},
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to preview template');
  }

  return response.json();
}

/**
 * Validate a template without generating preview
 * 
 * @param templateType - Type of template
 * @param templateContent - HTML template content
 * @returns Validation results
 */
export async function validateTemplate(
  templateType: TemplateType,
  templateContent: string
): Promise<ValidationResult> {
  const response = await authenticatedRequest('/api/tenant-admin/templates/validate', {
    method: 'POST',
    body: JSON.stringify({
      template_type: templateType,
      template_content: templateContent,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to validate template');
  }

  return response.json();
}

/**
 * Approve a template and save to Google Drive
 * 
 * @param templateType - Type of template
 * @param templateContent - HTML template content
 * @param fieldMappings - Optional field mappings
 * @param notes - Optional approval notes
 * @returns Approval response with template ID and file ID
 */
export async function approveTemplate(
  templateType: TemplateType,
  templateContent: string,
  fieldMappings?: FieldMappings,
  notes?: string
): Promise<ApprovalResponse> {
  const response = await authenticatedRequest('/api/tenant-admin/templates/approve', {
    method: 'POST',
    body: JSON.stringify({
      template_type: templateType,
      template_content: templateContent,
      field_mappings: fieldMappings || {},
      notes: notes || '',
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to approve template');
  }

  return response.json();
}

/**
 * Reject a template with reason
 * 
 * @param templateType - Type of template
 * @param reason - Optional rejection reason
 * @returns Success response
 */
export async function rejectTemplate(
  templateType: TemplateType,
  reason?: string
): Promise<RejectionResponse> {
  const response = await authenticatedRequest('/api/tenant-admin/templates/reject', {
    method: 'POST',
    body: JSON.stringify({
      template_type: templateType,
      reason: reason || '',
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to reject template');
  }

  return response.json();
}

/**
 * Get AI-powered help for fixing template errors
 * 
 * @param templateType - Type of template
 * @param templateContent - HTML template content
 * @param validationErrors - Validation errors to fix
 * @param requiredPlaceholders - Required placeholders for template type
 * @returns AI suggestions for fixing errors
 */
export async function getAIHelp(
  templateType: TemplateType,
  templateContent: string,
  validationErrors: ValidationError[],
  requiredPlaceholders?: string[]
): Promise<AIHelpResponse> {
  const response = await authenticatedRequest('/api/tenant-admin/templates/ai-help', {
    method: 'POST',
    body: JSON.stringify({
      template_type: templateType,
      template_content: templateContent,
      validation_errors: validationErrors,
      required_placeholders: requiredPlaceholders || [],
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to get AI help');
  }

  return response.json();
}

/**
 * Apply AI-suggested fixes to template
 * 
 * @param templateContent - HTML template content
 * @param fixes - AI fix suggestions to apply
 * @returns Fixed template content
 */
export async function applyAIFixes(
  templateContent: string,
  fixes: AIFixSuggestion[]
): Promise<ApplyFixesResponse> {
  const response = await authenticatedRequest('/api/tenant-admin/templates/apply-ai-fixes', {
    method: 'POST',
    body: JSON.stringify({
      template_content: templateContent,
      fixes: fixes,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to apply AI fixes');
  }

  return response.json();
}

/**
 * Get the current active template for a template type
 * 
 * @param templateType - Type of template to retrieve
 * @returns Current template response with content and metadata
 */
export async function getCurrentTemplate(
  templateType: TemplateType
): Promise<CurrentTemplateResponse> {
  const response = await authenticatedRequest(`/api/tenant-admin/templates/${templateType}`, {
    method: 'GET',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to get current template');
  }

  return response.json();
}
