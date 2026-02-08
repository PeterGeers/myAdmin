npm test -- --watchAll=false --coverage

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

**Status**: ✅ Basic functionality complete. Additional work needed post-migration for full usability (see Phase 5 tasks).

#### 2.4 Migrate Templates to Google Drive

- [x] Create template folders in each tenant's Google Drive
- [x] Upload templates to tenant Google Drives
- [x] Store template metadata in `tenant_template_config` table
- [x] Verify templates are accessible in line with .kiro\specs\Common\CICD\TEST_ORGANIZATION.md

**Known Issue**: Google Drive may have duplicate templates with same name but different file IDs. The file IDs are unique identifiers in Google Drive. Need to implement deduplication logic or use specific file ID references. This will be addressed in Phase 5 template cleanup tasks.

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

- [x] Extend `tenant_template_config` table for versioning
  - [x] Add `version` column (INT, default 1)
  - [x] Add `approved_by` column (VARCHAR(255))
  - [x] Add `approved_at` column (TIMESTAMP)
  - [x] Add `approval_notes` column (TEXT)
  - [x] Add `previous_file_id` column (VARCHAR(255))
  - [x] Add `status` column (ENUM: 'draft', 'active', 'archived', default 'active')
  - [x] Test schema changes locally
  - [x] Create migration script

- [x] Create `template_validation_log` table
  - [x] Create table with columns: id, administration, template_type, validation_result, errors (JSON), warnings (JSON), validated_by, validated_at
  - [x] Add indexes: (administration, template_type), (validated_at)
  - [x] Test table creation locally
  - [x] Document table structure

- [x] Create `ai_usage_log` table (for cost tracking)
  - [x] Create table with columns: id, administration, feature, tokens_used, cost_estimate, created_at
  - [x] Add indexes: (administration), (created_at)
  - [x] Test table creation locally

##### 2.6.2 Backend - TemplatePreviewService

- [x] Create `backend/src/services/template_preview_service.py`
  - [x] Implement `__init__(db, administration)` constructor
  - [x] Implement `generate_preview(template_type, template_content, field_mappings)` method
  - [x] Implement `validate_template(template_type, template_content)` method
  - [x] Implement `fetch_sample_data(template_type)` method
  - [x] Implement `approve_template(template_type, template_content, field_mappings, user_email, notes)` method
  - [x] Implement `_render_template(template_content, sample_data, field_mappings)` method

- [x] Implement HTML Syntax Validation
  - [x] Create `_validate_html_syntax(template_content)` method
  - [x] Use HTMLParser to check for well-formed HTML
  - [x] Detect unclosed tags
  - [x] Detect mismatched closing tags
  - [x] Return structured error list

- [x] Implement Placeholder Validation
  - [x] Create `_validate_placeholders(template_type, template_content)` method
  - [x] Define required placeholders per template type (str_invoice_nl, btw_aangifte, aangifte_ib, toeristenbelasting, financial_report)
  - [x] Extract placeholders from template using regex
  - [x] Check for missing required placeholders
  - [x] Return structured error list

- [x] Implement Security Validation
  - [x] Create `_validate_security(template_content)` method
  - [x] Check for script tags (not allowed)
  - [x] Check for event handlers (onclick, onload, etc. - not allowed)
  - [x] Check for external resources (warn if present)
  - [x] Return structured error/warning list

- [x] Implement Sample Data Fetching
  - [x] Create `_fetch_str_invoice_sample()` method (most recent booking)
  - [x] Create `_fetch_btw_sample()` method (most recent quarter data)
  - [x] Create `_fetch_aangifte_ib_sample()` method (most recent year data)
  - [x] Create `_fetch_toeristenbelasting_sample()` method (most recent year data)
  - [x] Create `_fetch_generic_sample()` method (placeholder data)
  - [x] Handle cases where no sample data exists

- [x] Write unit tests for TemplatePreviewService
  - [x] Test HTML syntax validation (valid HTML, unclosed tags, mismatched tags)
  - [x] Test placeholder validation (all present, missing required)
  - [x] Test security validation (script tags, event handlers, external resources)
  - [x] Test sample data fetching for each template type
  - [x] Test preview generation (success and failure cases)
  - [x] Test validation logging

##### 2.6.3 Backend - AI Template Assistant

- [x] Setup OpenRouter API Integration (This is already available and used. It is stored in .env)
  - [x] Create OpenRouter account and get API key
  - [x] Add `OPENROUTER_API_KEY` to environment variables
  - [x] Document API key setup in README

- [x] Create `backend/src/services/ai_template_assistant.py`
  - [x] Implement `__init__()` constructor (load API key, set model)
  - [x] Implement `get_fix_suggestions(template_type, template_content, validation_errors, required_placeholders)` method
  - [x] Implement `_build_prompt(template_type, template_content, validation_errors, required_placeholders)` method
  - [x] Implement `_sanitize_template(template_content)` method (remove PII: emails, phones, addresses)
  - [x] Implement `_format_errors(errors)` method
  - [x] Implement `_parse_ai_response(response_text)` method (extract JSON from AI response)
  - [x] Implement `apply_auto_fixes(template_content, fixes)` method
  - [x] Implement `_add_placeholder(template, code_to_add, location)` method

- [x] Create AI Usage Tracking
  - [x] Create `AIUsageTracker` class
  - [x] Implement `log_ai_request(administration, template_type, tokens_used)` method
  - [x] Calculate cost estimates based on token usage
  - [x] Store in `ai_usage_log` table

- [x] Write unit tests for AITemplateAssistant
  - [x] Test prompt building
  - [x] Test template sanitization (removes emails, phones, addresses)
  - [x] Test AI response parsing (JSON extraction)
  - [x] Test auto-fix application
  - [x] Mock OpenRouter API calls

##### 2.6.4 Backend - API Routes

- [x] Create `backend/src/tenant_admin_routes.py` blueprint
  - [x] Setup blueprint with prefix `/api/tenant-admin`
  - [x] Import required services and decorators

- [x] Implement POST `/api/tenant-admin/templates/preview`
  - [x] Add `@require_tenant_admin` decorator
  - [x] Validate request (template_type, template_content required)
  - [x] Call TemplatePreviewService.generate_preview()
  - [x] Return preview HTML + validation results
  - [x] Handle errors (400 for validation failures, 500 for server errors)

- [x] Implement POST `/api/tenant-admin/templates/validate`
  - [x] Add `@require_tenant_admin` decorator
  - [x] Validate request
  - [x] Call TemplatePreviewService.validate_template()
  - [x] Return validation results only (faster than full preview)

- [x] Implement POST `/api/tenant-admin/templates/approve`
  - [x] Add `@require_tenant_admin` decorator
  - [x] Validate request
  - [x] Call TemplatePreviewService.approve_template()
  - [x] Save template to Google Drive
  - [x] Update database metadata
  - [x] Archive previous version
  - [x] Return success with template_id and file_id

- [x] Implement POST `/api/tenant-admin/templates/reject`
  - [x] Add `@require_tenant_admin` decorator
  - [x] Log rejection with reason
  - [x] Return success message

- [x] Implement POST `/api/tenant-admin/templates/ai-help`
  - [x] Add `@require_tenant_admin` decorator
  - [x] Validate request
  - [x] Call AITemplateAssistant.get_fix_suggestions()
  - [x] Log AI usage for cost tracking
  - [x] Return AI suggestions with fixes
  - [x] Handle AI service unavailable (fallback to generic help)

- [x] Implement POST `/api/tenant-admin/templates/apply-ai-fixes`
  - [x] Add `@require_tenant_admin` decorator
  - [x] Validate request
  - [x] Call AITemplateAssistant.apply_auto_fixes()
  - [x] Return fixed template content
  - [x] Log fix application

- [x] Add Content Security Policy headers
  - [x] Implement `@after_request` handler
  - [x] Add CSP headers (no scripts, self-only styles, no external resources)
  - [x] Test CSP enforcement

- [x] Register blueprint in main app
  - [x] Import tenant_admin_bp in `backend/src/app.py`
  - [x] Register blueprint with app
  - [x] Test all endpoints are accessible

- [x] Write API integration tests
  - [x] Test preview endpoint (auth required, success, validation failure)
  - [x] Test validate endpoint
  - [x] Test approve endpoint (saves to Drive, updates DB)
  - [x] Test reject endpoint
  - [x] Test AI help endpoint (with mocked OpenRouter)
  - [x] Test apply fixes endpoint
  - [x] Test tenant isolation (cannot access other tenant's templates)Handle the tenant isolation exception (one user can access multiple tenants and they share Google Drive)

##### 2.6.5 Frontend - Template Management Components

- [x] Create component structure
  - [x] Create `frontend/src/components/TenantAdmin/TemplateManagement/` directory
  - [x] Create component index file

- [x] Create `TemplateManagement.tsx` (main container)
  - [x] Setup state management (template content, validation, preview, loading)
  - [x] Implement `handleUpload()` function (read file, call preview API)
  - [x] Implement `handleApprove()` function (call approve API)
  - [x] Implement `handleReject()` function (call reject API)
  - [x] Compose child components
  - [x] Add error handling and loading states

- [x] Create `TemplateUpload.tsx` component
  - [x] File input for HTML template upload
  - [x] Template type selector dropdown (str_invoice_nl, btw_aangifte, etc.)
  - [x] Field mappings editor (optional)
  - [x] Upload button with loading state
  - [x] File size validation (max 5MB)
  - [x] File type validation (HTML only)

- [x] Create `TemplatePreview.tsx` component
  - [x] Iframe for displaying preview HTML
  - [x] Sandbox iframe (allow-same-origin only, no scripts)
  - [x] Responsive sizing
  - [x] Loading skeleton
  - [x] Preview note ("This shows how your template will look with sample data")

- [x] Create `ValidationResults.tsx` component
  - [x] Success indicator (green checkmark)
  - [x] Error list (red, with icons)
  - [x] Warning list (yellow, with icons)
  - [x] Display error type, message, line number (if available)
  - [x] Collapsible sections for errors/warnings

- [x] Create `FieldMappingEditor.tsx` component
  - [x] JSON editor for field mappings
  - [x] Syntax highlighting
  - [x] Validation for JSON format
  - [x] Help text with examples
  - [x] Optional (can use default mappings)

- [x] Create `TemplateApproval.tsx` component
  - [x] Approve button (green, enabled only if valid)
  - [x] Reject button (red, always enabled)
  - [x] Notes textarea (optional, for approval)
  - [x] Reason textarea (optional, for rejection)
  - [x] Confirmation dialogs
  - [x] Loading states

- [x] Create `AIHelpButton.tsx` component
  - [x] "Get AI Help" button (robot icon)
  - [x] Disabled if no validation errors
  - [x] Loading state while AI analyzes
  - [x] Display AI suggestions in modal/panel
  - [x] Show analysis text
  - [x] Show list of fixes with code examples
  - [x] "Apply All Auto-Fixes" button
  - [x] Individual fix accept/reject buttons
  - [x] Confidence indicator
  - [x] Fallback message if AI unavailable

- [x] Add routing and navigation
  - [x] Add route `/tenant-admin/templates` in React Router
  - [x] Add navigation link in Tenant Admin menu
  - [x] Add breadcrumbs

- [x] Check styling
  - [x] Check styling defined and used in the existing code base
  - [x] Responsive design (mobile, tablet, desktop)
  - [x] Consistent with existing UI theme
  - [x] Accessibility (ARIA labels, keyboard navigation)

##### 2.6.6 Frontend - API Integration

- [x] Create API service file
  - [x] Create `frontend/src/services/templateApi.ts`
  - [x] Implement `previewTemplate(templateType, content, mappings)` function
  - [x] Implement `validateTemplate(templateType, content)` function
  - [x] Implement `approveTemplate(templateType, content, mappings, notes)` function
  - [x] Implement `rejectTemplate(templateType, reason)` function
  - [x] Implement `getAIHelp(templateType, content, errors)` function
  - [x] Implement `applyAIFixes(content, fixes)` function
  - [x] Add authentication headers
  - [x] Add error handling

- [x] Add TypeScript types
  - [x] Create `frontend/src/types/template.ts`
  - [x] Define `TemplateType` enum
  - [x] Define `ValidationError` interface
  - [x] Define `ValidationResult` interface
  - [x] Define `PreviewResponse` interface
  - [x] Define `AIFixSuggestion` interface
  - [x] Define `AIHelpResponse` interface

##### 2.6.7 Testing

- [x] Backend Unit Tests
  - [x] Test TemplatePreviewService (all validation methods)
  - [x] Test AITemplateAssistant (sanitization, prompt building, parsing)
  - [x] Test sample data fetching for all template types
  - [x] Test template rendering with field mappings
  - [x] Achieve 80%+ code coverage

- [x] Backend Integration Tests
  - [x] Test full preview generation flow (upload → validate → preview)
  - [x] Test approval workflow (approve → save to Drive → update DB)
  - [x] Test AI help flow (request → sanitize → call API → parse response)
  - [x] Test tenant isolation (cannot access other tenant's data)
  - [x] Test with real database and Google Drive (test environment)

- [x] API Tests
  - [x] Test all endpoints with authentication
  - [x] Test all endpoints without authentication (should fail)
  - [x] Test request validation (missing fields, invalid types)
  - [x] Test error responses (400, 401, 500)
  - [x] Test rate limiting (if implemented)
  - **Status**: ✅ **COMPLETE** - 29/29 tests passing, 2 skipped (rate limiting). Security audit fixed (TEST_MODE). All test classes updated with proper mocking. Comprehensive coverage of authentication, validation, error handling, and edge cases.

- [x] Frontend Unit Tests
  - [x] Test TemplateManagement component (state management, handlers)
  - [x] Test TemplateUpload component (file validation, upload)
  - [x] Test ValidationResults component (error/warning display)
  - [x] Test AIHelpButton component (AI interaction)
  - [x] Test TemplatePreview component (iframe rendering, security sandbox)
  - [x] Test TemplateApproval component (approve/reject buttons, confirmation dialogs)
  - [x] Mock API calls
  - **Status**: ✅ **COMPLETE** - 148 unit tests created covering all Template Management components. Tests include state management, user interactions, API mocking, loading states, error handling, and edge cases. All tests follow React Testing Library best practices with accessible queries and realistic user interactions.

- [x] Frontend Integration Tests
  - [x] Test upload → validation flow
  - [x] Test validation → preview flow
  - [x] Test validation error display
  - [x] Test AI help button states and interaction
  - [x] Test approval button states
  - [x] Test rejection button states
  - [x] Test complete approval workflow
  - [x] Test complete rejection workflow
  - [x] Use React Testing Library
  - **Status**: ✅ **COMPLETE** - All 11 integration tests passing. Core integration flows validated: upload, validation, preview, AI help, approval, and rejection workflows.

- [x] End-to-End Tests
  - [x] Test complete workflow from UI to database
  - [x] Test with real templates for each type
  - [x] Test AI assistance with real OpenRouter API (staging)
  - [x] Test error scenarios (invalid template, no sample data, AI unavailable)
  - [x] Test on different browsers (Chrome, Firefox, Safari)

##### 2.6.8 Documentation

- [x] Update API documentation
  - [x] Document all new endpoints in OpenAPI/Swagger
  - [x] Include request/response schemas
  - [x] Include authentication requirements
  - [x] Include error codes and messages

##### 2.6.9 Deployment

- [x] Environment Configuration (stll local not on railway as it does not exists yet)
  - For later Add `OPENROUTER_API_KEY` to Railway environment (phase 5)
  - [x] Add `TEMPLATE_MAX_SIZE_MB=5` to environment
  - [x] Add `TEMPLATE_PREVIEW_TIMEOUT=30` to environment
  - [x] Document all new environment variables

**Deliverables**:

- ✅ Template preview and validation system
- ✅ AI-powered template assistance (privacy-first)
- ✅ Complete frontend UI for template management
- ✅ Comprehensive testing (unit, integration, E2E)
- ✅ User and developer documentation
- ✅ Deployed to production with monitoring

**Deliverables**:

- ✅ All templates converted to HTML
- ✅ Template metadata in database
- ✅ Working TemplateService
- ✅ Updated report generation routes
- ✅ All tests passing

**Note**: Official XBRL tax forms (IB Aangifte XBRL, BTW Aangifte XBRL) have been moved to a separate specification at `.kiro/specs/FIN/AANGIFTE_XBRL/` and will be implemented post-Railway migration. Research and documentation are complete.

---

## Phase 3: myAdmin System Tenant (1 day)

**Goal**: Create myAdmin tenant for platform management (database and Cognito only)

**Prerequisites**:

- Phase 1 completed
- Phase 2 completed

**Note**: Storage setup (Google Drive folders, template migration) will be done in Phase 5 after Railway deployment.

### Tasks

#### 3.1 Create myAdmin Tenant

- [x] Add myAdmin tenant to database
- [x] Create myAdmin Google Drive account (or use existing)
- [x] Store myAdmin Google Drive credentials in database
- [x] Configure myAdmin tenant in Cognito

**Verification**: myAdmin tenant exists in database and Cognito, credentials stored.

#### 3.2 Configure SysAdmin Access

**Important**: SysAdmin role is for platform management functions only (user management, system configuration, monitoring). It does NOT grant access to any tenant data, including myAdmin tenant. A user can have multiple roles: TenantAdmin for their tenant(s) + SysAdmin for platform functions.

- [x] Verify SysAdmin role exists in Cognito
- [x] Verify SysAdmin cannot access tenant data (GoodwinSolutions, PeterPrive, myAdmin)
- [x] Test that users with combined roles (TenantAdmin + SysAdmin):
  - [x] Can access their tenant data via TenantAdmin role
  - [x] Can access platform management functions via SysAdmin role
  - [x] Cannot access other tenants' data
- [x] Document role separation and combination behavior

**Test Results**: ✅ All 6 tests passed

- SysAdmin role exists with correct description
- SysAdmin correctly denied access to all tenants
- Combined roles work correctly with proper isolation
- Documentation created: `.kiro/specs/Common/Role based access/ROLE_SEPARATION_AND_COMBINATION.md`
- Test script: `.kiro/specs/Common/Role based access/test_sysadmin_role_config.py`

#### 3.3 Testing (Database & Cognito Only)

- [ ] Test SysAdmin role has NO direct tenant data access
- [ ] Verify tenant isolation (SysAdmin cannot query any tenant data)
- [ ] Test user with TenantAdmin role can access their tenant data
- [ ] Test user with combined roles (TenantAdmin + SysAdmin) can access both functions
- [ ] Run security tests for role-based access control

#### 3.4 Create Tenant Admin & SysAdmin Specifications

**Prerequisites**: Phase 3.1-3.3 completed

**Purpose**: Document requirements and design before implementing Phase 4

- [ ] Create `.kiro/specs/Common/TenantAdmin-Module/` folder
- [ ] Create `requirements.md` (user stories, acceptance criteria)
  - Credential management requirements
  - User management requirements
  - Template management requirements (reference Phase 2.6)
  - Storage configuration requirements
- [ ] Create `design.md` (technical design)
  - API endpoint specifications
  - Database schema (if new tables needed)
  - Frontend component architecture
  - Authentication and authorization design
- [ ] Create `TASKS.md` (detailed implementation tasks)
  - Break down Phase 4 into granular tasks
  - Add time estimates
  - Add dependencies
- [ ] Review and approve specifications
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Deliverables**:

- ✅ myAdmin tenant created in database
- ✅ myAdmin tenant configured in Cognito
- ✅ SysAdmin role access configured
- ✅ Tenant isolation verified
- ✅ Complete requirements documentation
- ✅ Complete technical design
- ✅ Detailed implementation tasks
- ✅ All tests passing

**Note**: Google Drive storage setup, template migration, and template access testing will be done in Phase 5 (tasks 5.12-5.16). This keeps the Railway migration TASKS.md focused on execution while detailed module specifications live in their own folder.

---

## Phase 4: Tenant Admin Module (4-5 days)

**Goal**: Build UI for tenant administrators to manage their tenant

**Prerequisites**:

- Phase 1, 2, 3 completed (including 3.4 - specifications)
- Frontend development environment ready

### Tasks

#### 4.1 Backend API Endpoints

**Note**: Many template-related endpoints already exist from Phase 2.6 (Template Preview and Validation). Review `backend/src/tenant_admin_routes.py` to avoid duplication. Focus on credential management and user management endpoints.

- [ ] Review existing `backend/src/tenant_admin_routes.py` from Phase 2.6
- [ ] Implement credential management endpoints:
  - POST `/api/tenant-admin/credentials` (upload Google Drive credentials)
  - GET `/api/tenant-admin/credentials` (list credential types)
  - DELETE `/api/tenant-admin/credentials/:type` (remove credentials)
- [ ] Implement user management endpoints:
  - POST `/api/tenant-admin/users` (create user with invitation)
  - GET `/api/tenant-admin/users` (list tenant users)
  - PUT `/api/tenant-admin/users/:id/roles` (assign roles)
  - DELETE `/api/tenant-admin/users/:id` (remove user from tenant)
- [ ] Review existing template management endpoints from Phase 2.6:
  - POST `/api/tenant-admin/templates/preview` (already exists)
  - POST `/api/tenant-admin/templates/validate` (already exists)
  - POST `/api/tenant-admin/templates/approve` (already exists)
  - POST `/api/tenant-admin/templates/reject` (already exists)
- [ ] Add any missing template endpoints:
  - GET `/api/tenant-admin/templates` (list templates)
  - PUT `/api/tenant-admin/templates/:id/mappings` (configure field mappings)
  - PUT `/api/tenant-admin/templates/:id/activate` (activate/deactivate)
- [ ] Implement storage configuration endpoints:
  - GET `/api/tenant-admin/storage` (get storage config)
  - PUT `/api/tenant-admin/storage` (update folder IDs, storage type)
- [ ] Add authentication and authorization checks
- [ ] Write API tests
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 4.2 Frontend Components

**Note**: Template Management components already exist from Phase 2.6. Review `frontend/src/components/TenantAdmin/TemplateManagement/` before creating new components. Focus on credentials and user management UI.

- [x] Create `frontend/src/components/TenantAdmin/` folder
- [x] Create TenantAdminDashboard component
- [x] Review existing TemplateManagement components from Phase 2.6:
  - TemplateManagement.tsx (main container)
  - TemplateUpload.tsx
  - TemplatePreview.tsx
  - ValidationResults.tsx
  - TemplateApproval.tsx
  - AIHelpButton.tsx
- [ ] Create CredentialsManagement component
  - Upload credentials.json
  - OAuth flow for Google Drive (reference: diagnose_google_token.py)
  - Display credential status
  - Test connection button
- [ ] Create UserManagement component
  - Create user form (email, name)
  - Role assignment dropdown
  - Send invitation button
  - User list with roles
  - Edit/delete user actions
- [ ] Enhance existing TemplateManagement component (if needed):
  - Add template list view
  - Add activate/deactivate toggle
  - Add field mappings editor
- [ ] Create StorageConfiguration component
  - Folder ID inputs
  - Storage type selector (Google Drive/S3)
  - Test connection button
  - Display current configuration
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 4.3 User Invitation System

- [ ] Create email template for user invitation
- [ ] Implement invitation email sending (via AWS SNS)
- [ ] Generate temporary password or magic link
- [ ] Create invitation acceptance flow (frontend)
- [ ] Test invitation flow end-to-end
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 4.4 Access Control

- [ ] Verify Tenant Administrator can only access their tenant
- [ ] Verify SysAdmin cannot access tenant data (except myAdmin tenant)
- [ ] Test users with combined roles (TenantAdmin + SysAdmin) can access both their tenant and myAdmin
- [ ] Document role combination behavior and access patterns
- [ ] Test role-based permissions for all endpoints
- [ ] Add audit logging for admin actions
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 4.5 Testing

- [ ] Test all CRUD operations
- [ ] Test user invitation flow
- [ ] Test template upload and configuration
- [ ] Test credential management
- [ ] Run E2E tests
- [ ] Test on multiple browsers
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1
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

#### 5.3 Google Drive Tenant Integration Fixes

**Context**: GoogleDriveService was updated to require tenant-specific credentials, but several endpoints were not passing the tenant parameter, causing files to be stored locally instead of in Google Drive.
Note PG: Check what we really have

- [x] Fix `/api/folders` endpoint (Line 325 in app.py)
  - [x] Add tenant extraction from `X-Tenant` header
  - [x] Pass tenant to `GoogleDriveService(administration=tenant)`
  - [x] Add error handling for missing tenant
  - [x] Test folder loading for both tenants (GoodwinSolutions, PeterPrive)

- [x] Fix `/api/upload` endpoint (Line 768 in app.py)
  - [x] Pass tenant to `GoogleDriveService(administration=tenant)` during file upload
  - [x] Ensure files are uploaded to correct tenant's Google Drive
  - [x] Verify Google Drive URLs are returned (not local URLs)
  - [x] Test file upload for both tenants

- [x] Fix `/api/create-folder` endpoint (Line 686 in app.py)
  - [x] Add `@tenant_required()` decorator
  - [x] Update function signature to include tenant parameters
  - [x] Pass tenant to `GoogleDriveService(administration=tenant)`
  - [x] Test folder creation in correct tenant's Google Drive

- [x] Verify all other GoogleDriveService instantiations
  - [x] Search codebase for `GoogleDriveService()` calls
  - [x] Ensure all pass `administration=tenant` parameter
  - [x] Update any remaining instances

- [x] Test complete Google Drive integration
  - [x] Test folder loading (dropdown populates correctly)
  - [x] Test file upload (files go to Google Drive, not local storage)
  - [x] Test folder creation (new folders appear in correct Drive)
  - [x] Test with multiple tenants (verify isolation)
  - [x] Verify Google Drive URLs are returned in all cases

**Impact**: These fixes ensure that:

- Files are uploaded to the correct tenant's Google Drive account
- Folder lists are loaded from the correct tenant's Google Drive
- New folders are created in the correct tenant's Google Drive
- Tenant data isolation is maintained
- No files are stored locally in production

**Testing Checklist**:

- [x] Local testing completed (January 31, 2026)
- [ ] Staging environment testing
- [ ] Production deployment verification
- [ ] Monitor logs for Google Drive errors
- [ ] Verify no local file storage in production

#### 5.4 Database Migration

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

#### 5.4 Database Migration

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

#### 5.5 GitHub Integration

- [ ] Connect Railway to GitHub repository
- [ ] Set deploy branch to `main`
- [ ] Configure build settings (Railway auto-detects Dockerfile)
- [ ] Verify build configuration

#### 5.6 Initial Deployment

- [ ] Push to main branch
- [ ] Monitor Railway deployment logs
- [ ] Wait for successful deployment
- [ ] Note Railway application URL

#### 5.7 Testing on Railway

- [ ] Test frontend loads correctly
- [ ] Test user login (Cognito)
- [ ] Test tenant selection
- [ ] Test Google Drive access for both tenants
- [ ] Test report generation
- [ ] Test template management
- [ ] Test user creation and invitation
- [ ] Run smoke tests on all modules

#### 5.8 DNS Configuration

- [ ] Update DNS record:
  ```
  admin.pgeers.nl → Railway URL
  ```
- [ ] Wait for DNS propagation (5-30 minutes)
- [ ] Test access via custom domain
- [ ] Verify SSL certificate

#### 5.9 Monitoring Setup

- [ ] Configure Railway logging
- [ ] Set up error alerts
- [ ] Monitor application performance
- [ ] Check database connection pool

#### 5.10 Go Live Checklist

- [ ] Verify all features working on production
- [ ] Test with real user accounts
- [ ] Verify email notifications working
- [ ] Check AWS costs (Cognito, SNS)
- [ ] Check Railway costs
- [ ] Keep local database backup for 1 week
- [ ] Document production URLs and credentials

#### 5.11 Post-Deployment

- [ ] Monitor logs for 24 hours
- [ ] Fix any issues that arise
- [ ] Optimize performance if needed
- [ ] Update documentation with production details
- [ ] Celebrate! 🎉

#### 5.12 Setup myAdmin Storage Structure

**Prerequisites**: Railway deployed, myAdmin tenant created

- [ ] Create folder structure in myAdmin Google Drive:
  - Generic Templates/
  - Email Templates/
  - Platform Assets/Logos/
  - Platform Assets/Branding/
- [ ] Upload generic templates to myAdmin Drive
- [ ] Store folder IDs in configuration
- [ ] Verify folder access from Railway application
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 5.13 Migrate Generic Templates

**Prerequisites**: 5.12 completed

- [ ] Identify generic templates (used by all tenants)
- [ ] Move to myAdmin Google Drive
- [ ] Update template references in code
- [ ] Test template access from myAdmin tenant
- [ ] Verify tenant-specific templates still work
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 5.14 Test myAdmin Storage Access

**Prerequisites**: 5.12, 5.13 completed

**Note**: myAdmin storage is for generic templates shared across all tenants. Access is controlled by TenantAdmin role for myAdmin tenant, NOT by SysAdmin role.

- [ ] Test users with TenantAdmin role for myAdmin can access myAdmin Google Drive
- [ ] Test SysAdmin role alone CANNOT access myAdmin Google Drive
- [ ] Test SysAdmin role cannot access tenant Google Drives (GoodwinSolutions, PeterPrive)
- [ ] Test users with combined roles (TenantAdmin for myAdmin + SysAdmin) can access myAdmin storage
- [ ] Verify folder permissions are correct
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 5.15 Test Generic Template Access

**Prerequisites**: 5.13 completed

- [ ] Test generic template loading from myAdmin Drive
- [ ] Test tenant-specific template loading from tenant Drives
- [ ] Verify template fallback logic (tenant → generic)
- [ ] Test template rendering with both generic and tenant templates
- [ ] Run E2E tests for all report types
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 5.16 Template Deduplication Cleanup

**Prerequisites**: 5.15 completed

**Purpose**: Address duplicate templates in Google Drive (same name, different file IDs)

- [ ] Audit all templates in Google Drive (list all file IDs and names)
- [ ] Identify duplicates (same name, different IDs)
- [ ] Determine which file ID to keep (most recent or explicitly chosen)
- [ ] Update `tenant_template_config` table with correct file IDs
- [ ] Delete duplicate template files from Google Drive
- [ ] Verify all reports still work with deduplicated templates
- [ ] Document template file ID management process
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Deliverables**:

- ✅ Application running on Railway
- ✅ Custom domain configured
- ✅ All features tested and working
- ✅ Monitoring in place
- ✅ Documentation updated
- ✅ myAdmin storage structure created
- ✅ Generic templates migrated
- ✅ Template access verified
- ✅ Duplicate templates cleaned up

---

## 📊 Progress Tracking

| Phase                        | Status         | Duration | Start Date | End Date | Notes                                                    |
| ---------------------------- | -------------- | -------- | ---------- | -------- | -------------------------------------------------------- |
| Phase 1: Credentials         | ✅ Completed   | 4 days   | -          | -        | All tasks complete                                       |
| Phase 2: Templates           | ✅ Completed   | 3 days   | -          | -        | Basic functionality complete, post-migration work needed |
| Phase 3: myAdmin Tenant      | 🔄 In Progress | 1 day    | -          | -        | Database & Cognito only                                  |
| Phase 4: Tenant Admin Module | ⏸️ Not Started | 4-5 days | -          | -        | Requires Phase 3.4 (specs) first                         |
| Phase 5: Railway Deployment  | ⏸️ Not Started | 2-3 days | -          | -        | Includes storage setup (5.12-5.16)                       |

**Legend**:

- ⏸️ Not Started
- 🔄 In Progress
- ✅ Completed
- ⚠️ Blocked
- 🔍 Under Review

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
- **Git uploads**: Each major task group includes `git-upload.ps1` step for version control
- **Specifications**: Detailed module specs (TenantAdmin, SysAdmin) are in separate folders under `.kiro/specs/` to keep this TASKS.md focused on execution
