# Railway Migration - Implementation Tasks

**Last Updated**: January 2026
**Status**: Ready to Start

---

## 📋 Overview

This document breaks down the Railway migration into manageable phases with detailed tasks. Each phase builds on the previous one and can be tested independently.

**Total Estimated Time**: 2-3 weeks
**Phases**: 5 phases

---

## Phase 1: Credentials Infrastructure (3-4 days)

**Goal**: Implement encrypted tenant-specific credentials in MySQL

**Prerequisites**:

- [x] Backup current database
- [x] Backup current credential files:
  - [x] Copy `backend/credentials.json` to `backend/credentials_backup/`
  - [x] Copy `backend/token.json` to `backend/credentials_backup/`
  - These are your Google Drive OAuth credentials (needed for rollback if migration fails)

### Tasks

#### 1.1 Database Schema

- [x] Create `tenant_credentials` table
  ```sql
  CREATE TABLE tenant_credentials (
      id INT AUTO_INCREMENT PRIMARY KEY,
      administration VARCHAR(100) NOT NULL,
      credential_type VARCHAR(50) NOT NULL,
      encrypted_value TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY unique_tenant_cred (administration, credential_type),
      INDEX idx_tenant (administration)
  );
  ```
- [x] Test table creation locally
- [x] Document table structure

#### 1.2 Encryption Service

- [x] Create `backend/src/services/credential_service.py`
- [x] Implement `encrypt_credential(value)` method (key set during service initialization - more secure design pattern)
- [x] Implement `decrypt_credential(encrypted_value)` method (key set during service initialization)
- [x] Implement `store_credential(administration, type, value)` method
- [x] Implement `get_credential(administration, type)` method
- [x] Implement `delete_credential(administration, type)` method
- [x] Write unit tests for encryption/decryption
- [x] Test with sample data

#### 1.3 Generate Encryption Key

- [x] Create `scripts/generate_encryption_key.py`
- [x] Generate secure 256-bit encryption key
- [x] Document key storage requirements
- [x] Add key to local `backend\.env` as `CREDENTIALS_ENCRYPTION_KEY`

#### 1.4 Migration Script

- [x] Create `scripts/migrate_credentials_to_db.py`
- [x] Read existing `credentials.json` and `token.json` files
- [x] Encrypt and store in database for each tenant
- [x] Verify migration success
- [x] Create rollback script (if needed)

#### 1.5 Update GoogleDriveService

- [x] Modify `__init__(self, administration)` to accept administration
- [x] Update `_authenticate()` to read from database
- [x] Remove hardcoded file paths
- [x] Add error handling for missing credentials
- [x] Test with both tenants (GoodwinSolutions, PeterPrive) Use of .kiro\specs\Common\CICD\TEST_ORGANIZATION.md

#### 1.6 Testing

- [x] Test Google Drive access for each tenant Use of .kiro\specs\Common\CICD\TEST_ORGANIZATION.md
- [x] Verify credential access isolation (tenants can only access their own credentials, not other tenants' credentials)
- [x] Test credential rotation (update and verify) Use of .kiro\specs\Common\CICD\TEST_ORGANIZATION.md
- [x] Run existing integration tests Use of .kiro\specs\Common\CICD\TEST_ORGANIZATION.md
- [x] Document any issues

**Deliverables**:

- ✅ Encrypted credentials in MySQL
- ✅ Working CredentialService
- ✅ Updated GoogleDriveService
- ✅ Migration script
- ✅ All tests passing

---

## Phase 2: Template Management Infrastructure (2-3 days)

**Goal**: Implement XML template storage with field mappings

**Prerequisites**:

- Phase 1 completed
- Identify all current templates

### Tasks

#### 2.1 Database Schema

- [x] Create `tenant_template_config` table
  ```sql
  CREATE TABLE tenant_template_config (
      id INT AUTO_INCREMENT PRIMARY KEY,
      administration VARCHAR(100) NOT NULL,
      template_type VARCHAR(50) NOT NULL,
      template_file_id VARCHAR(255) NOT NULL,
      field_mappings JSON,
      is_active BOOLEAN DEFAULT TRUE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY unique_tenant_template (administration, template_type),
      INDEX idx_tenant (administration)
  );
  ```
- [x] Test table creation locally
- [x] Document field_mappings JSON structure

#### 2.2 Template Service

- [x] Create `backend/src/services/template_service.py`
- [x] Implement `get_template_metadata(administration, template_type)` method
- [x] Implement `fetch_template_from_drive(file_id, administration)` method
- [x] Implement `apply_field_mappings(template_xml, data, mappings)` method
- [x] Implement `generate_output(template, data, output_format)` method
- [x] Write and or update unit and integration tests in line with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md
- [x] consolidate the Template Service related .md files in backend\src\services

#### 2.3 Convert Existing Templates to XML/HTML

**Architecture Documentation Review**:

- [x] Review and update template system architecture documentation
  - [x] `.kiro/specs/Common/Railway migration/IMPACT_ANALYSIS_SUMMARY.md` - Update template approach section
  - [x] `.kiro/specs/Common/templates/analysis.md` - Verify all decisions are documented
  - [x] `backend/src/services/template_service.py` - Confirm it remains simple (no changes needed)
  - [x] `backend/templates/README.md` - Document template structure and architecture
  - [x] `backend/templates/xml/IMPLEMENTATION_SUMMARY.md` - Track implementation status

**HTML Reports (Viewing/Analysis - Customizable per tenant)**:

- [x] Convert Aangifte IB HTML Report template (hierarchical view of income/expenses)
  - [x] Create HTML template with placeholders (`backend/templates/html/aangifte_ib_template.html`)
  - [x] Create `backend/src/report_generators/` module structure
    - [x] Create `backend/src/report_generators/__init__.py`
    - [x] Create `backend/src/report_generators/common_formatters.py` (shared utilities for formatting)
    - [x] Create `backend/src/report_generators/README.md` (document module purpose, patterns, and usage)
    - [x] Create unit tests `backend/tests/unit/test_common_formatters.py` (73 tests, all passing)
  - [x] Create Aangifte IB generator
    - [x] Create `backend/src/report_generators/aangifte_ib_generator.py`
    - [x] Implement `generate_table_rows(report_data, cache, year, administration, user_tenants)` function
    - [x] Implement hierarchical row generation (parent → aangifte → accounts)
    - [x] Implement amount formatting and CSS class assignment
    - [x] Export function in `__init__.py`
  - [x] Update `backend/src/app.py` route `aangifte_ib_export()`
    - [x] Import report_generators module
    - [x] Replace hardcoded HTML generation with generator + TemplateService
    - [x] Pass generated table_rows to TemplateService
  - [x] Test end-to-end with real data
    - [x] Test with GoodwinSolutions tenant
    - [x] Test with PeterPrive tenant
    - [x] Verify output matches expected format
    - [x] Compare with example output (`backend/templates/xml/Aangifte_IB_GoodwinSolutions_2025.html`)
- [x] Convert STR invoices (NL/UK) template to HTML with field mappings
  - [x] Create HTML templates with placeholders
    - [x] `backend/templates/html/str_invoice_nl_template.html` (Dutch version)
    - [x] `backend/templates/html/str_invoice_en_template.html` (English version)
  - [x] Create STR invoice generator
    - [x] Create `backend/src/report_generators/str_invoice_generator.py`
    - [x] Implement `generate_table_rows(invoice_data, language)` function
    - [x] Implement `prepare_invoice_data(booking_data, custom_billing)` function
    - [x] Support both Dutch (NL) and English (EN) languages
    - [x] Handle conditional line items (VAT, tourist tax)
    - [x] Export functions in `__init__.py`
  - [x] Update `backend/src/str_invoice_routes.py` route `generate_invoice()`
    - [x] Import str_invoice_generator module
    - [x] Replace old invoice generation with generator + template approach
    - [x] Use template files from `backend/templates/html/`
  - [x] Document field mappings
    - [x] Create `backend/templates/html/STR_INVOICE_FIELD_MAPPINGS.md`
    - [x] Document all placeholder fields
    - [x] Document company information fields
    - [x] Document booking and billing fields
    - [x] Document financial fields and calculations
    - [x] Document conditional logic (VAT, tourist tax)
    - [x] Document language support (NL/EN)
  - [x] Create unit tests
    - [x] Create `backend/tests/unit/test_str_invoice_generator.py`
    - [x] Test `generate_table_rows()` with various scenarios (12 tests)
    - [x] Test `prepare_invoice_data()` with various inputs
    - [x] Test language support (NL and EN)
    - [x] Test conditional line items
    - [x] All tests passing (12/12)
- [x] Convert BTW Aangifte HTML Report (VAT calculations and breakdowns)
  - [x] Create HTML template with placeholders (`backend/templates/html/btw_aangifte_template.html`)
  - [x] Create BTW Aangifte generator
    - [x] Create `backend/src/report_generators/btw_aangifte_generator.py`
    - [x] Implement `generate_btw_report(cache, db, administration, year, quarter)` function
    - [x] Implement balance data retrieval (accounts 2010, 2020, 2021)
    - [x] Implement quarter data retrieval (BTW + revenue accounts)
    - [x] Implement BTW calculations (total balance, received BTW, prepaid BTW)
    - [x] Implement table row formatting
    - [x] Export function in `__init__.py`
  - [x] Update `backend/src/app.py` route `btw_generate_report()`
    - [x] Import btw_aangifte_generator module
    - [x] Replace BTWProcessor hardcoded HTML with generator + template approach
    - [x] Use template file from `backend/templates/html/`
  - [x] Document field mappings
    - [x] Create `backend/templates/html/BTW_AANGIFTE_FIELD_MAPPINGS.md`
    - [x] Document all placeholder fields
    - [x] Document balance and quarter data structure
    - [x] Document calculation logic
    - [x] Document data sources and queries
  - [x] Create unit tests
    - [x] Create `backend/tests/unit/test_btw_aangifte_generator.py`
    - [x] Test quarter end date calculation (5 tests)
    - [x] Test BTW calculations (4 tests)
    - [x] Test table row formatting (3 tests)
    - [x] Test template data preparation (2 tests)
    - [x] Test data retrieval functions (3 tests)
    - [x] Test main report generation (1 test)
    - [x] All tests passing (18/18)
- [x] Convert Toeristenbelasting HTML Report (tourist tax calculations)
  - [x] Create HTML template with placeholders (`backend/templates/html/toeristenbelasting_template.html`)
  - [x] Create Toeristenbelasting generator
    - [x] Create `backend/src/report_generators/toeristenbelasting_generator.py`
    - [x] Implement `generate_toeristenbelasting_report(cache, bnb_cache, db, year)` function
    - [x] Implement configuration retrieval (contact info, accommodation details)
    - [x] Implement BNB data retrieval (bookings, cancellations, realised)
    - [x] Implement rental statistics calculation (nights, occupancy rates)
    - [x] Implement financial data retrieval (tourist tax, revenue, service fees)
    - [x] Implement taxable revenue calculation
    - [x] Implement template data preparation with formatting
    - [x] Export function in `__init__.py`
  - [x] Update `backend/src/toeristenbelasting_processor.py`
    - [x] Import report_generators module
    - [x] Replace hardcoded HTML generation with generator + TemplateService
    - [x] Use template file from `backend/templates/html/`
    - [x] Remove old helper methods (\_get_bnb_data, \_get_tourist_tax_from_account, etc.)
    - [x] Remove old \_generate_html_report method
  - [x] Document field mappings
    - [x] Create `backend/templates/html/TOERISTENBELASTING_FIELD_MAPPINGS.md`
    - [x] Document all placeholder fields
    - [x] Document contact and accommodation fields
    - [x] Document rental statistics fields
    - [x] Document financial calculation fields
    - [x] Document data sources (BNB cache, mutaties cache)
    - [x] Document calculation logic (tourist tax formula, taxable revenue)
  - [x] Create unit tests
    - [x] Create `backend/tests/unit/test_toeristenbelasting_generator.py`
    - [x] Test configuration retrieval (1 test)
    - [x] Test rental statistics calculation (2 tests)
    - [x] Test financial data retrieval (3 tests)
    - [x] Test taxable revenue calculation (1 test)
    - [x] Test financial data aggregation (1 test)
    - [x] Test template data preparation (1 test)
    - [x] Test main report generation (2 tests)
    - [x] All tests passing (11/11)

**Other**:

- [x] Manage financial report generate XLSX template to be used with variable storage of template and local storage of output
- [x] Document field mapping structure for each template

- [x] Validate all tests created in section 2.3 comply with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md

**Note**: HTML Reports are customizable per tenant and stored in their Google Drive. Official XBRL/XML tax forms have been moved to a separate specification at `.kiro/specs/FIN/AANGIFTE_XBRL/` and will be implemented post-Railway migration.

#### 2.4 Migrate Templates to Google Drive

- [x] Create template folders in each tenant's Google Drive
- [x] Upload templates to tenant Google Drives
- [x] Store template metadata in `tenant_template_config` table
- [x] Verify templates are accessible in line with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md

#### 2.5 Update Report Generation Routes

- [x] Update financial report generation to use TemplateService
- [x] Update STR invoice generation to use TemplateService
- [x] Update tax form generation to use TemplateService
- [x] Add output destination options
  - [x] Implement download to local filesystem (return to frontend)
  - [x] Implement upload to Google Drive (save to tenant's Drive)
  - [x] Add `output_destination` parameter to report endpoints (`download`, `gdrive`, `s3`)
  - [x] Implement S3 upload (future option)
- [x] Test all report types in line with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md

#### 2.6 Template Preview and Validation

**Reference Documentation**:

- Requirements: `.kiro/specs/Common/template-preview-validation/requirements.md`
- Design: `.kiro/specs/Common/template-preview-validation/design.md`
- AI Assistance Approach: `.kiro/specs/Common/template-preview-validation/AI_ASSISTANCE_APPROACH.md`
- Testing: `.kiro\specs\Common\CICD\TEST_ORGANIZATION.md`

**Estimated Time**: 6.5-7.5 days

**Overview**: Enable Tenant Administrators to safely upload, preview, and validate custom report templates before activating them. Includes AI-powered assistance for fixing template errors (privacy-first approach - no SysAdmin access to tenant data).

##### 2.6.1 Database Schema Updates

- [ ] Extend `tenant_template_config` table for versioning
  - [ ] Add `version` column (INT, default 1)
  - [ ] Add `approved_by` column (VARCHAR(255))
  - [ ] Add `approved_at` column (TIMESTAMP)
  - [ ] Add `approval_notes` column (TEXT)
  - [ ] Add `previous_file_id` column (VARCHAR(255))
  - [ ] Add `status` column (ENUM: 'draft', 'active', 'archived', default 'active')
  - [ ] Test schema changes locally
  - [ ] Create migration script

- [ ] Create `template_validation_log` table
  - [ ] Create table with columns: id, administration, template_type, validation_result, errors (JSON), warnings (JSON), validated_by, validated_at
  - [ ] Add indexes: (administration, template_type), (validated_at)
  - [ ] Test table creation locally
  - [ ] Document table structure

- [ ] Create `ai_usage_log` table (for cost tracking)
  - [ ] Create table with columns: id, administration, feature, tokens_used, cost_estimate, created_at
  - [ ] Add indexes: (administration), (created_at)
  - [ ] Test table creation locally

##### 2.6.2 Backend - TemplatePreviewService

- [ ] Create `backend/src/services/template_preview_service.py`
  - [ ] Implement `__init__(db, administration)` constructor
  - [ ] Implement `generate_preview(template_type, template_content, field_mappings)` method
  - [ ] Implement `validate_template(template_type, template_content)` method
  - [ ] Implement `fetch_sample_data(template_type)` method
  - [ ] Implement `approve_template(template_type, template_content, field_mappings, user_email, notes)` method
  - [ ] Implement `_render_template(template_content, sample_data, field_mappings)` method

- [ ] Implement HTML Syntax Validation
  - [ ] Create `_validate_html_syntax(template_content)` method
  - [ ] Use HTMLParser to check for well-formed HTML
  - [ ] Detect unclosed tags
  - [ ] Detect mismatched closing tags
  - [ ] Return structured error list

- [ ] Implement Placeholder Validation
  - [ ] Create `_validate_placeholders(template_type, template_content)` method
  - [ ] Define required placeholders per template type (str_invoice_nl, btw_aangifte, aangifte_ib, toeristenbelasting, financial_report)
  - [ ] Extract placeholders from template using regex
  - [ ] Check for missing required placeholders
  - [ ] Return structured error list

- [ ] Implement Security Validation
  - [ ] Create `_validate_security(template_content)` method
  - [ ] Check for script tags (not allowed)
  - [ ] Check for event handlers (onclick, onload, etc. - not allowed)
  - [ ] Check for external resources (warn if present)
  - [ ] Return structured error/warning list

- [ ] Implement Sample Data Fetching
  - [ ] Create `_fetch_str_invoice_sample()` method (most recent booking)
  - [ ] Create `_fetch_btw_sample()` method (most recent quarter data)
  - [ ] Create `_fetch_aangifte_ib_sample()` method (most recent year data)
  - [ ] Create `_fetch_toeristenbelasting_sample()` method (most recent year data)
  - [ ] Create `_fetch_generic_sample()` method (placeholder data)
  - [ ] Handle cases where no sample data exists

- [ ] Write unit tests for TemplatePreviewService
  - [ ] Test HTML syntax validation (valid HTML, unclosed tags, mismatched tags)
  - [ ] Test placeholder validation (all present, missing required)
  - [ ] Test security validation (script tags, event handlers, external resources)
  - [ ] Test sample data fetching for each template type
  - [ ] Test preview generation (success and failure cases)
  - [ ] Test validation logging

##### 2.6.3 Backend - AI Template Assistant

- [ ] Setup OpenRouter API Integration
  - [ ] Create OpenRouter account and get API key
  - [ ] Add `OPENROUTER_API_KEY` to environment variables
  - [ ] Document API key setup in README

- [ ] Create `backend/src/services/ai_template_assistant.py`
  - [ ] Implement `__init__()` constructor (load API key, set model)
  - [ ] Implement `get_fix_suggestions(template_type, template_content, validation_errors, required_placeholders)` method
  - [ ] Implement `_build_prompt(template_type, template_content, validation_errors, required_placeholders)` method
  - [ ] Implement `_sanitize_template(template_content)` method (remove PII: emails, phones, addresses)
  - [ ] Implement `_format_errors(errors)` method
  - [ ] Implement `_parse_ai_response(response_text)` method (extract JSON from AI response)
  - [ ] Implement `apply_auto_fixes(template_content, fixes)` method
  - [ ] Implement `_add_placeholder(template, code_to_add, location)` method

- [ ] Create AI Usage Tracking
  - [ ] Create `AIUsageTracker` class
  - [ ] Implement `log_ai_request(administration, template_type, tokens_used)` method
  - [ ] Calculate cost estimates based on token usage
  - [ ] Store in `ai_usage_log` table

- [ ] Write unit tests for AITemplateAssistant
  - [ ] Test prompt building
  - [ ] Test template sanitization (removes emails, phones, addresses)
  - [ ] Test AI response parsing (JSON extraction)
  - [ ] Test auto-fix application
  - [ ] Mock OpenRouter API calls

##### 2.6.4 Backend - API Routes

- [ ] Create `backend/src/tenant_admin_routes.py` blueprint
  - [ ] Setup blueprint with prefix `/api/tenant-admin`
  - [ ] Import required services and decorators

- [ ] Implement POST `/api/tenant-admin/templates/preview`
  - [ ] Add `@require_tenant_admin` decorator
  - [ ] Validate request (template_type, template_content required)
  - [ ] Call TemplatePreviewService.generate_preview()
  - [ ] Return preview HTML + validation results
  - [ ] Handle errors (400 for validation failures, 500 for server errors)

- [ ] Implement POST `/api/tenant-admin/templates/validate`
  - [ ] Add `@require_tenant_admin` decorator
  - [ ] Validate request
  - [ ] Call TemplatePreviewService.validate_template()
  - [ ] Return validation results only (faster than full preview)

- [ ] Implement POST `/api/tenant-admin/templates/approve`
  - [ ] Add `@require_tenant_admin` decorator
  - [ ] Validate request
  - [ ] Call TemplatePreviewService.approve_template()
  - [ ] Save template to Google Drive
  - [ ] Update database metadata
  - [ ] Archive previous version
  - [ ] Return success with template_id and file_id

- [ ] Implement POST `/api/tenant-admin/templates/reject`
  - [ ] Add `@require_tenant_admin` decorator
  - [ ] Log rejection with reason
  - [ ] Return success message

- [ ] Implement POST `/api/tenant-admin/templates/ai-help`
  - [ ] Add `@require_tenant_admin` decorator
  - [ ] Validate request
  - [ ] Call AITemplateAssistant.get_fix_suggestions()
  - [ ] Log AI usage for cost tracking
  - [ ] Return AI suggestions with fixes
  - [ ] Handle AI service unavailable (fallback to generic help)

- [ ] Implement POST `/api/tenant-admin/templates/apply-ai-fixes`
  - [ ] Add `@require_tenant_admin` decorator
  - [ ] Validate request
  - [ ] Call AITemplateAssistant.apply_auto_fixes()
  - [ ] Return fixed template content
  - [ ] Log fix application

- [ ] Add Content Security Policy headers
  - [ ] Implement `@after_request` handler
  - [ ] Add CSP headers (no scripts, self-only styles, no external resources)
  - [ ] Test CSP enforcement

- [ ] Register blueprint in main app
  - [ ] Import tenant_admin_bp in `backend/src/app.py`
  - [ ] Register blueprint with app
  - [ ] Test all endpoints are accessible

- [ ] Write API integration tests
  - [ ] Test preview endpoint (auth required, success, validation failure)
  - [ ] Test validate endpoint
  - [ ] Test approve endpoint (saves to Drive, updates DB)
  - [ ] Test reject endpoint
  - [ ] Test AI help endpoint (with mocked OpenRouter)
  - [ ] Test apply fixes endpoint
  - [ ] Test tenant isolation (cannot access other tenant's templates)

##### 2.6.5 Frontend - Template Management Components

- [ ] Create component structure
  - [ ] Create `frontend/src/components/TenantAdmin/TemplateManagement/` directory
  - [ ] Create component index file

- [ ] Create `TemplateManagement.tsx` (main container)
  - [ ] Setup state management (template content, validation, preview, loading)
  - [ ] Implement `handleUpload()` function (read file, call preview API)
  - [ ] Implement `handleApprove()` function (call approve API)
  - [ ] Implement `handleReject()` function (call reject API)
  - [ ] Compose child components
  - [ ] Add error handling and loading states

- [ ] Create `TemplateUpload.tsx` component
  - [ ] File input for HTML template upload
  - [ ] Template type selector dropdown (str_invoice_nl, btw_aangifte, etc.)
  - [ ] Field mappings editor (optional)
  - [ ] Upload button with loading state
  - [ ] File size validation (max 5MB)
  - [ ] File type validation (HTML only)

- [ ] Create `TemplatePreview.tsx` component
  - [ ] Iframe for displaying preview HTML
  - [ ] Sandbox iframe (allow-same-origin only, no scripts)
  - [ ] Responsive sizing
  - [ ] Loading skeleton
  - [ ] Preview note ("This shows how your template will look with sample data")

- [ ] Create `ValidationResults.tsx` component
  - [ ] Success indicator (green checkmark)
  - [ ] Error list (red, with icons)
  - [ ] Warning list (yellow, with icons)
  - [ ] Display error type, message, line number (if available)
  - [ ] Collapsible sections for errors/warnings

- [ ] Create `FieldMappingEditor.tsx` component
  - [ ] JSON editor for field mappings
  - [ ] Syntax highlighting
  - [ ] Validation for JSON format
  - [ ] Help text with examples
  - [ ] Optional (can use default mappings)

- [ ] Create `TemplateApproval.tsx` component
  - [ ] Approve button (green, enabled only if valid)
  - [ ] Reject button (red, always enabled)
  - [ ] Notes textarea (optional, for approval)
  - [ ] Reason textarea (optional, for rejection)
  - [ ] Confirmation dialogs
  - [ ] Loading states

- [ ] Create `AIHelpButton.tsx` component
  - [ ] "Get AI Help" button (robot icon)
  - [ ] Disabled if no validation errors
  - [ ] Loading state while AI analyzes
  - [ ] Display AI suggestions in modal/panel
  - [ ] Show analysis text
  - [ ] Show list of fixes with code examples
  - [ ] "Apply All Auto-Fixes" button
  - [ ] Individual fix accept/reject buttons
  - [ ] Confidence indicator
  - [ ] Fallback message if AI unavailable

- [ ] Add routing and navigation
  - [ ] Add route `/tenant-admin/templates` in React Router
  - [ ] Add navigation link in Tenant Admin menu
  - [ ] Add breadcrumbs

- [ ] Add styling
  - [ ] Create CSS/SCSS for all components
  - [ ] Responsive design (mobile, tablet, desktop)
  - [ ] Consistent with existing UI theme
  - [ ] Accessibility (ARIA labels, keyboard navigation)

##### 2.6.6 Frontend - API Integration

- [ ] Create API service file
  - [ ] Create `frontend/src/services/templateApi.ts`
  - [ ] Implement `previewTemplate(templateType, content, mappings)` function
  - [ ] Implement `validateTemplate(templateType, content)` function
  - [ ] Implement `approveTemplate(templateType, content, mappings, notes)` function
  - [ ] Implement `rejectTemplate(templateType, reason)` function
  - [ ] Implement `getAIHelp(templateType, content, errors)` function
  - [ ] Implement `applyAIFixes(content, fixes)` function
  - [ ] Add authentication headers
  - [ ] Add error handling

- [ ] Add TypeScript types
  - [ ] Create `frontend/src/types/template.ts`
  - [ ] Define `TemplateType` enum
  - [ ] Define `ValidationError` interface
  - [ ] Define `ValidationResult` interface
  - [ ] Define `PreviewResponse` interface
  - [ ] Define `AIFixSuggestion` interface
  - [ ] Define `AIHelpResponse` interface

##### 2.6.7 Testing

- [ ] Backend Unit Tests
  - [ ] Test TemplatePreviewService (all validation methods)
  - [ ] Test AITemplateAssistant (sanitization, prompt building, parsing)
  - [ ] Test sample data fetching for all template types
  - [ ] Test template rendering with field mappings
  - [ ] Achieve 80%+ code coverage

- [ ] Backend Integration Tests
  - [ ] Test full preview generation flow (upload → validate → preview)
  - [ ] Test approval workflow (approve → save to Drive → update DB)
  - [ ] Test AI help flow (request → sanitize → call API → parse response)
  - [ ] Test tenant isolation (cannot access other tenant's data)
  - [ ] Test with real database and Google Drive (test environment)

- [ ] API Tests
  - [ ] Test all endpoints with authentication
  - [ ] Test all endpoints without authentication (should fail)
  - [ ] Test request validation (missing fields, invalid types)
  - [ ] Test error responses (400, 401, 500)
  - [ ] Test rate limiting (if implemented)

- [ ] Frontend Unit Tests
  - [ ] Test TemplateManagement component (state management, handlers)
  - [ ] Test TemplateUpload component (file validation, upload)
  - [ ] Test ValidationResults component (error/warning display)
  - [ ] Test AIHelpButton component (AI interaction)
  - [ ] Mock API calls

- [ ] Frontend Integration Tests
  - [ ] Test full user flow (upload → preview → approve)
  - [ ] Test validation error display
  - [ ] Test AI help interaction
  - [ ] Test rejection flow
  - [ ] Use React Testing Library

- [ ] End-to-End Tests
  - [ ] Test complete workflow from UI to database
  - [ ] Test with real templates for each type
  - [ ] Test AI assistance with real OpenRouter API (staging)
  - [ ] Test error scenarios (invalid template, no sample data, AI unavailable)
  - [ ] Test on different browsers (Chrome, Firefox, Safari)

##### 2.6.8 Documentation

- [ ] Update API documentation
  - [ ] Document all new endpoints in OpenAPI/Swagger
  - [ ] Include request/response schemas
  - [ ] Include authentication requirements
  - [ ] Include error codes and messages

- [ ] Create user guide for Tenant Administrators
  - [ ] How to upload a template
  - [ ] Understanding validation errors
  - [ ] Using AI assistance
  - [ ] Field mapping reference for each template type
  - [ ] Best practices for template customization
  - [ ] Troubleshooting common issues

- [ ] Create developer documentation
  - [ ] Architecture overview
  - [ ] Adding new template types
  - [ ] Adding new validation rules
  - [ ] Extending AI assistance
  - [ ] Testing guide

- [ ] Update README files
  - [ ] Update main README with new feature
  - [ ] Update backend README with new services
  - [ ] Update frontend README with new components

##### 2.6.9 Deployment

- [ ] Environment Configuration
  - [ ] Add `OPENROUTER_API_KEY` to Railway environment
  - [ ] Add `TEMPLATE_MAX_SIZE_MB=5` to environment
  - [ ] Add `TEMPLATE_PREVIEW_TIMEOUT=30` to environment
  - [ ] Document all new environment variables

- [ ] Database Migration
  - [ ] Create migration script for schema changes
  - [ ] Test migration on staging database
  - [ ] Run migration on production database
  - [ ] Verify data integrity after migration

- [ ] Deploy Backend
  - [ ] Deploy new services and routes to Railway
  - [ ] Verify all endpoints are accessible
  - [ ] Test with staging data
  - [ ] Monitor logs for errors

- [ ] Deploy Frontend
  - [ ] Build production bundle
  - [ ] Deploy to hosting (Railway/Vercel)
  - [ ] Verify all components load correctly
  - [ ] Test user flows in production

- [ ] Monitoring and Alerts
  - [ ] Setup logging for template operations
  - [ ] Setup alerts for high validation failure rates
  - [ ] Setup alerts for AI API errors
  - [ ] Monitor AI usage costs
  - [ ] Track preview generation times

**Deliverables**:

- ✅ Template preview and validation system
- ✅ AI-powered template assistance (privacy-first)
- ✅ Complete frontend UI for template management
- ✅ Comprehensive testing (unit, integration, E2E)
- ✅ User and developer documentation
- ✅ Deployed to production with monitoring

#### 2.7 Testing

- [ ] Test each template type generation inline with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md
- [ ] Verify field mappings work correctly
- [ ] Test download to local device inline with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md
- [ ] Test store to Google Drive inline with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md
- [ ] Run integration tests inline with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md

**Deliverables**:

- ✅ All templates converted to HTML
- ✅ Template metadata in database
- ✅ Working TemplateService
- ✅ Updated report generation routes
- ✅ All tests passing

**Note**: Official XBRL tax forms (IB Aangifte XBRL, BTW Aangifte XBRL) have been moved to a separate specification at `.kiro/specs/FIN/AANGIFTE_XBRL/` and will be implemented post-Railway migration. Research and documentation are complete.

---

## Phase 3: myAdmin System Tenant (1-2 days)

**Goal**: Create myAdmin tenant for platform management

**Prerequisites**:

- Phase 1 completed
- Phase 2 completed

### Tasks

#### 3.1 Create myAdmin Tenant

- [ ] Add myAdmin tenant to database
- [ ] Create myAdmin Google Drive account (or use existing)
- [ ] Store myAdmin Google Drive credentials in database
- [ ] Configure myAdmin tenant in Cognito

#### 3.2 Setup myAdmin Storage Structure

- [ ] Create folder structure in myAdmin Google Drive:
  - Generic Templates/
  - Email Templates/
  - Platform Assets/Logos/
  - Platform Assets/Branding/
- [ ] Upload generic templates to myAdmin Drive
- [ ] Store folder IDs in configuration

#### 3.3 Migrate Generic Templates

- [ ] Identify generic templates (used by all tenants)
- [ ] Move to myAdmin Google Drive
- [ ] Update template references in code
- [ ] Test template access from myAdmin tenant

#### 3.4 Configure SysAdmin Access

- [ ] Ensure SysAdmin role has access to myAdmin tenant
- [ ] Verify SysAdmin cannot access other tenant data
- [ ] Test myAdmin tenant isolation

#### 3.5 Testing

- [ ] Test SysAdmin access to myAdmin tenant
- [ ] Test generic template access
- [ ] Verify tenant isolation
- [ ] Run security tests

**Deliverables**:

- ✅ myAdmin tenant created
- ✅ Generic templates in myAdmin Drive
- ✅ SysAdmin access configured
- ✅ All tests passing

---

## Phase 4: Tenant Admin Module (4-5 days)

**Goal**: Build UI for tenant administrators to manage their tenant

**Prerequisites**:

- Phase 1, 2, 3 completed
- Frontend development environment ready

### Tasks

#### 4.1 Backend API Endpoints

- [ ] Create `backend/src/tenant_admin_routes.py`
- [ ] Implement credential management endpoints:
  - POST `/api/tenant-admin/credentials` (upload Google Drive credentials)
  - GET `/api/tenant-admin/credentials` (list credential types)
  - DELETE `/api/tenant-admin/credentials/:type` (remove credentials)
- [ ] Implement user management endpoints:
  - POST `/api/tenant-admin/users` (create user with invitation)
  - GET `/api/tenant-admin/users` (list tenant users)
  - PUT `/api/tenant-admin/users/:id/roles` (assign roles)
  - DELETE `/api/tenant-admin/users/:id` (remove user from tenant)
- [ ] Implement template management endpoints:
  - POST `/api/tenant-admin/templates` (upload template)
  - GET `/api/tenant-admin/templates` (list templates)
  - PUT `/api/tenant-admin/templates/:id/mappings` (configure field mappings)
  - PUT `/api/tenant-admin/templates/:id/activate` (activate/deactivate)
- [ ] Implement storage configuration endpoints:
  - GET `/api/tenant-admin/storage` (get storage config)
  - PUT `/api/tenant-admin/storage` (update folder IDs, storage type)
- [ ] Add authentication and authorization checks
- [ ] Write API tests

#### 4.2 Frontend Components

- [ ] Create `frontend/src/components/TenantAdmin/` folder
- [ ] Create TenantAdminDashboard component
- [ ] Create CredentialsManagement component
  - Upload credentials.json
  - OAuth flow for Google Drive
  - Display credential status
- [ ] Create UserManagement component
  - Create user form (email, name)
  - Role assignment dropdown
  - Send invitation button
  - User list with roles
- [ ] Create TemplateManagement component
  - Upload template file
  - Configure field mappings UI
  - Logo upload/selection
  - Template preview
  - Activate/deactivate toggle
- [ ] Create StorageConfiguration component
  - Folder ID inputs
  - Storage type selector (Google Drive/S3)
  - Test connection button

#### 4.3 User Invitation System

- [ ] Create email template for user invitation
- [ ] Implement invitation email sending (via AWS SNS)
- [ ] Generate temporary password or magic link
- [ ] Test invitation flow end-to-end

#### 4.4 Access Control

- [ ] Verify Tenant Administrator can only access their tenant
- [ ] Verify SysAdmin cannot access tenant data
- [ ] Test role-based permissions
- [ ] Add audit logging for admin actions

#### 4.5 Testing

- [ ] Test all CRUD operations
- [ ] Test user invitation flow
- [ ] Test template upload and configuration
- [ ] Test credential management
- [ ] Run E2E tests
- [ ] Test on multiple browsers

**Deliverables**:

- ✅ Tenant Admin Module UI
- ✅ All backend APIs working
- ✅ User invitation system
- ✅ Template management working
- ✅ All tests passing

---

## Phase 5: Railway Deployment (2-3 days)

**Goal**: Deploy to Railway and go live

**Prerequisites**:

- All phases 1-4 completed and tested locally
- Railway account created
- DNS ready to update

### Tasks

#### 5.1 Railway Setup

- [ ] Create Railway account (if not exists)
- [ ] Create new project "myadmin-production"
- [ ] Add MySQL service in Railway
- [ ] Note MySQL connection details

#### 5.2 Environment Variables

- [ ] Configure Railway environment variables:
  - `DB_HOST` (from Railway MySQL)
  - `DB_PASSWORD` (from Railway MySQL)
  - `DB_NAME` (from Railway MySQL)
  - `DB_USER` (from Railway MySQL)
  - `OPENROUTER_API_KEY`
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_REGION`
  - `COGNITO_USER_POOL_ID`
  - `COGNITO_CLIENT_ID`
  - `COGNITO_CLIENT_SECRET`
  - `CREDENTIALS_ENCRYPTION_KEY`
- [ ] Verify all variables are set correctly

#### 5.3 Database Migration

- [ ] Export local database:
  ```bash
  mysqldump finance > production_backup.sql
  ```
- [ ] Import to Railway MySQL:
  ```bash
  mysql -h <railway-host> -u root -p railway < production_backup.sql
  ```
- [ ] Verify all tables and data migrated
- [ ] Test database connection from Railway

#### 5.4 GitHub Integration

- [ ] Connect Railway to GitHub repository
- [ ] Set deploy branch to `main`
- [ ] Configure build settings (Railway auto-detects Dockerfile)
- [ ] Verify build configuration

#### 5.5 Initial Deployment

- [ ] Push to main branch
- [ ] Monitor Railway deployment logs
- [ ] Wait for successful deployment
- [ ] Note Railway application URL

#### 5.6 Testing on Railway

- [ ] Test frontend loads correctly
- [ ] Test user login (Cognito)
- [ ] Test tenant selection
- [ ] Test Google Drive access for both tenants
- [ ] Test report generation
- [ ] Test template management
- [ ] Test user creation and invitation
- [ ] Run smoke tests on all modules

#### 5.7 DNS Configuration

- [ ] Update DNS record:
  ```
  admin.pgeers.nl → Railway URL
  ```
- [ ] Wait for DNS propagation (5-30 minutes)
- [ ] Test access via custom domain
- [ ] Verify SSL certificate

#### 5.8 Monitoring Setup

- [ ] Configure Railway logging
- [ ] Set up error alerts
- [ ] Monitor application performance
- [ ] Check database connection pool

#### 5.9 Go Live Checklist

- [ ] Verify all features working on production
- [ ] Test with real user accounts
- [ ] Verify email notifications working
- [ ] Check AWS costs (Cognito, SNS)
- [ ] Check Railway costs
- [ ] Keep local database backup for 1 week
- [ ] Document production URLs and credentials

#### 5.10 Post-Deployment

- [ ] Monitor logs for 24 hours
- [ ] Fix any issues that arise
- [ ] Optimize performance if needed
- [ ] Update documentation with production details
- [ ] Celebrate! 🎉

**Deliverables**:

- ✅ Application running on Railway
- ✅ Custom domain configured
- ✅ All features tested and working
- ✅ Monitoring in place
- ✅ Documentation updated

---

## 📊 Progress Tracking

| Phase                        | Status         | Start Date | End Date | Notes |
| ---------------------------- | -------------- | ---------- | -------- | ----- |
| Phase 1: Credentials         | ⏸️ Not Started | -          | -        | -     |
| Phase 2: Templates           | ⏸️ Not Started | -          | -        | -     |
| Phase 3: myAdmin Tenant      | ⏸️ Not Started | -          | -        | -     |
| Phase 4: Tenant Admin Module | ⏸️ Not Started | -          | -        | -     |
| Phase 5: Railway Deployment  | ⏸️ Not Started | -          | -        | -     |

**Legend**:

- ⏸️ Not Started
- 🔄 In Progress
- ✅ Completed
- ⚠️ Blocked

---

## 🆘 Troubleshooting

### Common Issues

**Issue**: Encryption key not found
**Solution**: Ensure `CREDENTIALS_ENCRYPTION_KEY` is set in `.env` (local) or Railway environment variables (production)

**Issue**: Google Drive authentication fails
**Solution**: Verify credentials are correctly encrypted and stored in database. Check administration matches.

**Issue**: Template not found
**Solution**: Verify template file_id is correct in `tenant_template_config` table. Check Google Drive permissions.

**Issue**: Railway deployment fails
**Solution**: Check Railway logs. Verify Dockerfile is correct. Ensure all environment variables are set.

**Issue**: Database connection fails on Railway
**Solution**: Verify Railway MySQL connection details. Check if database was imported correctly.

---

## 📚 Reference

- **Master Plan**: `IMPACT_ANALYSIS_SUMMARY.md`
- **Architecture**: See Architecture Summary in master plan
- **Decisions**: See 6 Critical Decisions in master plan
- **Issues**: `OPEN_ISSUES.md` (all resolved)

---

## Notes

- Each phase should be completed and tested before moving to the next
- Keep local backups until production is stable for 1 week
- Test thoroughly in local environment before Railway deployment
- Document any deviations from the plan
- Update this file as tasks are completed
