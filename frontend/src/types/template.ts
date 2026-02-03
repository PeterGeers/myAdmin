/**
 * Template Management Types
 * 
 * TypeScript type definitions for template management operations.
 * These types are used across components and API services.
 */

/**
 * Template types supported by the system
 */
export type TemplateType = 
  | 'str_invoice_nl'      // Short-term rental invoice (Dutch)
  | 'str_invoice_en'      // Short-term rental invoice (English)
  | 'btw_aangifte'        // VAT declaration
  | 'aangifte_ib'         // Income tax declaration
  | 'toeristenbelasting'  // Tourist tax report
  | 'financial_report';   // General financial report

/**
 * Validation error structure
 * 
 * Represents a single validation error or warning found in a template.
 */
export interface ValidationError {
  /** Type of validation error (e.g., 'missing_placeholder', 'invalid_syntax') */
  type: string;
  
  /** Human-readable error message */
  message: string;
  
  /** Line number where error occurred (optional) */
  line?: number;
  
  /** Placeholder name related to the error (optional) */
  placeholder?: string;
}

/**
 * Validation result structure
 * 
 * Contains the complete validation results for a template.
 */
export interface ValidationResult {
  /** Whether the template passed all validation checks */
  is_valid: boolean;
  
  /** List of validation errors (blocks approval) */
  errors: ValidationError[];
  
  /** List of validation warnings (doesn't block approval) */
  warnings: ValidationError[];
  
  /** List of validation checks that were performed (optional) */
  checks_performed?: string[];
}

/**
 * Sample data information
 * 
 * Information about the sample data used for preview generation.
 */
export interface SampleDataInfo {
  /** Source of sample data ('database' or 'placeholder') */
  source: 'database' | 'placeholder';
  
  /** Number of records used for sample data (optional) */
  record_count?: number;
}

/**
 * Preview response structure
 * 
 * Response from template preview API endpoint.
 */
export interface PreviewResponse {
  /** Whether the preview generation was successful */
  success: boolean;
  
  /** Generated HTML preview (optional, only if successful) */
  preview_html?: string;
  
  /** Validation results for the template */
  validation: ValidationResult;
  
  /** Information about sample data used (optional) */
  sample_data_info?: SampleDataInfo;
  
  /** Additional message (optional) */
  message?: string;
}

/**
 * AI fix suggestion structure
 * 
 * Represents a single AI-suggested fix for a template error.
 */
export interface AIFixSuggestion {
  /** Description of the issue */
  issue: string;
  
  /** Suggested fix for the issue */
  suggestion: string;
  
  /** Code example showing the fix */
  code_example: string;
  
  /** Location in template where fix should be applied */
  location: string;
  
  /** Confidence level of the suggestion */
  confidence: 'high' | 'medium' | 'low';
  
  /** Whether this fix can be applied automatically */
  auto_fixable: boolean;
}

/**
 * AI suggestions structure
 * 
 * Contains AI analysis and fix suggestions.
 */
export interface AISuggestions {
  /** AI analysis of the template issues */
  analysis: string;
  
  /** List of suggested fixes */
  fixes: AIFixSuggestion[];
  
  /** Whether any fixes are auto-fixable */
  auto_fixable: boolean;
}

/**
 * AI help response structure
 * 
 * Response from AI help API endpoint.
 */
export interface AIHelpResponse {
  /** Whether the AI help request was successful */
  success: boolean;
  
  /** AI suggestions (optional, only if successful) */
  ai_suggestions?: AISuggestions;
  
  /** Number of tokens used by AI (optional) */
  tokens_used?: number;
  
  /** Estimated cost of AI request (optional) */
  cost_estimate?: number;
  
  /** Whether fallback mode was used (AI unavailable) */
  fallback?: boolean;
  
  /** Additional message (optional) */
  message?: string;
}

/**
 * Template approval response structure
 * 
 * Response from template approval API endpoint.
 */
export interface ApprovalResponse {
  /** Whether the approval was successful */
  success: boolean;
  
  /** Unique template ID */
  template_id: string;
  
  /** Google Drive file ID */
  file_id: string;
  
  /** Success message */
  message: string;
}

/**
 * Template rejection response structure
 * 
 * Response from template rejection API endpoint.
 */
export interface RejectionResponse {
  /** Whether the rejection was successful */
  success: boolean;
  
  /** Success message */
  message: string;
}

/**
 * Apply AI fixes response structure
 * 
 * Response from apply AI fixes API endpoint.
 */
export interface ApplyFixesResponse {
  /** Whether the fixes were applied successfully */
  success: boolean;
  
  /** Fixed template content */
  fixed_template: string;
  
  /** Number of fixes that were applied */
  fixes_applied: number;
  
  /** Success message */
  message: string;
}

/**
 * Template metadata
 * 
 * Metadata about a template (for future use).
 */
export interface TemplateMetadata {
  /** Template ID */
  id: string;
  
  /** Template type */
  type: TemplateType;
  
  /** Template name */
  name: string;
  
  /** Template version */
  version: string;
  
  /** Creation date */
  created_at: string;
  
  /** Last modified date */
  updated_at: string;
  
  /** Created by user */
  created_by: string;
  
  /** Approval status */
  status: 'draft' | 'pending' | 'approved' | 'rejected';
  
  /** Google Drive file ID (if approved) */
  file_id?: string;
}

/**
 * Field mapping type
 * 
 * Custom field mappings for template placeholders.
 */
export type FieldMappings = Record<string, any>;

/**
 * Template upload request
 * 
 * Request payload for template upload/preview.
 */
export interface TemplateUploadRequest {
  /** Template type */
  template_type: TemplateType;
  
  /** Template HTML content */
  template_content: string;
  
  /** Optional field mappings */
  field_mappings?: FieldMappings;
}

/**
 * Template validation request
 * 
 * Request payload for template validation.
 */
export interface TemplateValidationRequest {
  /** Template type */
  template_type: TemplateType;
  
  /** Template HTML content */
  template_content: string;
}

/**
 * Template approval request
 * 
 * Request payload for template approval.
 */
export interface TemplateApprovalRequest {
  /** Template type */
  template_type: TemplateType;
  
  /** Template HTML content */
  template_content: string;
  
  /** Optional field mappings */
  field_mappings?: FieldMappings;
  
  /** Optional approval notes */
  notes?: string;
}

/**
 * Template rejection request
 * 
 * Request payload for template rejection.
 */
export interface TemplateRejectionRequest {
  /** Template type */
  template_type: TemplateType;
  
  /** Optional rejection reason */
  reason?: string;
}

/**
 * AI help request
 * 
 * Request payload for AI help.
 */
export interface AIHelpRequest {
  /** Template type */
  template_type: TemplateType;
  
  /** Template HTML content */
  template_content: string;
  
  /** Validation errors to fix */
  validation_errors: ValidationError[];
  
  /** Required placeholders for template type */
  required_placeholders?: string[];
}

/**
 * Apply AI fixes request
 * 
 * Request payload for applying AI fixes.
 */
export interface ApplyAIFixesRequest {
  /** Template HTML content */
  template_content: string;
  
  /** AI fix suggestions to apply */
  fixes: AIFixSuggestion[];
}

/**
 * Current template response structure
 * 
 * Response from get current template API endpoint.
 */
export interface CurrentTemplateResponse {
  /** Whether the request was successful */
  success: boolean;
  
  /** Template type */
  template_type: TemplateType;
  
  /** Template HTML content */
  template_content: string;
  
  /** Custom field mappings (if any) */
  field_mappings?: FieldMappings;
  
  /** Template metadata */
  metadata: {
    /** Template version */
    version: string;
    
    /** Approval date */
    approved_at: string;
    
    /** Approved by user */
    approved_by: string;
    
    /** Google Drive file ID */
    file_id: string;
    
    /** Template status */
    status: string;
    
    /** Optional approval notes */
    notes?: string;
  };
  
  /** Success message */
  message: string;
}

/**
 * Template type labels
 * 
 * Human-readable labels for template types.
 */
export const TEMPLATE_TYPE_LABELS: Record<TemplateType, string> = {
  str_invoice_nl: 'STR Invoice (Dutch)',
  str_invoice_en: 'STR Invoice (English)',
  btw_aangifte: 'BTW Aangifte',
  aangifte_ib: 'Aangifte IB',
  toeristenbelasting: 'Toeristenbelasting',
  financial_report: 'Financial Report',
};

/**
 * Template type descriptions
 * 
 * Descriptions for each template type.
 */
export const TEMPLATE_TYPE_DESCRIPTIONS: Record<TemplateType, string> = {
  str_invoice_nl: 'Short-term rental invoice in Dutch',
  str_invoice_en: 'Short-term rental invoice in English',
  btw_aangifte: 'VAT declaration report',
  aangifte_ib: 'Income tax declaration report',
  toeristenbelasting: 'Tourist tax report',
  financial_report: 'General financial report',
};

/**
 * Required placeholders for each template type
 * 
 * List of required placeholders that must be present in each template type.
 */
export const REQUIRED_PLACEHOLDERS: Record<TemplateType, string[]> = {
  str_invoice_nl: ['invoice_number', 'invoice_date', 'company_name', 'total_amount'],
  str_invoice_en: ['invoice_number', 'invoice_date', 'company_name', 'total_amount'],
  btw_aangifte: ['period', 'year', 'quarter', 'btw_total'],
  aangifte_ib: ['year', 'administration', 'total_income', 'total_expenses'],
  toeristenbelasting: ['year', 'accommodation_name', 'total_nights', 'tourist_tax'],
  financial_report: ['year', 'administration', 'report_type'],
};

/**
 * Type guard to check if a string is a valid TemplateType
 * 
 * @param value - String to check
 * @returns True if value is a valid TemplateType
 */
export function isTemplateType(value: string): value is TemplateType {
  return [
    'str_invoice_nl',
    'str_invoice_en',
    'btw_aangifte',
    'aangifte_ib',
    'toeristenbelasting',
    'financial_report',
  ].includes(value);
}

/**
 * Get required placeholders for a template type
 * 
 * @param templateType - Template type
 * @returns Array of required placeholder names
 */
export function getRequiredPlaceholders(templateType: TemplateType): string[] {
  return REQUIRED_PLACEHOLDERS[templateType] || [];
}

/**
 * Get template type label
 * 
 * @param templateType - Template type
 * @returns Human-readable label
 */
export function getTemplateTypeLabel(templateType: TemplateType): string {
  return TEMPLATE_TYPE_LABELS[templateType] || templateType;
}

/**
 * Get template type description
 * 
 * @param templateType - Template type
 * @returns Description
 */
export function getTemplateTypeDescription(templateType: TemplateType): string {
  return TEMPLATE_TYPE_DESCRIPTIONS[templateType] || '';
}
