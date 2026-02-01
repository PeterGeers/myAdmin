/**
 * Template Management Components
 * 
 * This module exports all components related to template management
 * for Tenant Administrators.
 * 
 * Components:
 * - TemplateManagement: Main container component
 * - TemplateUpload: File upload and template type selection
 * - TemplatePreview: Iframe preview of template with sample data
 * - ValidationResults: Display validation errors and warnings
 * - FieldMappingEditor: JSON editor for field mappings
 * - TemplateApproval: Approve/reject buttons with notes
 * - AIHelpButton: AI-powered template assistance
 */

// Main container
export { TemplateManagement, default } from './TemplateManagement';

// Sub-components
export { TemplateUpload } from './TemplateUpload';
export { TemplatePreview } from './TemplatePreview';
export { ValidationResults } from './ValidationResults';
export { FieldMappingEditor } from './FieldMappingEditor';
export { TemplateApproval } from './TemplateApproval';
export { AIHelpButton } from './AIHelpButton';
