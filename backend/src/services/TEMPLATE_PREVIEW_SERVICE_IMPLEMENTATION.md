# Template Preview Service Implementation

**Date**: February 1, 2026  
**Status**: ✅ Completed  
**File**: `backend/src/services/template_preview_service.py`

## Overview

Implemented the `TemplatePreviewService` class that provides template preview, validation, and approval functionality for tenant administrators. This service enables safe template customization without requiring SysAdmin intervention.

## Implemented Methods

### Core Methods

1. **`__init__(db_manager, administration)`**
   - Initializes the service with database manager and tenant administration
   - Sets up TemplateService dependency
   - Logs initialization

2. **`generate_preview(template_type, template_content, field_mappings)`**
   - Validates template syntax and structure
   - Fetches sample data for the template type
   - Renders template with sample data
   - Returns preview HTML with validation results
   - Handles errors gracefully with detailed error messages

3. **`validate_template(template_type, template_content)`**
   - Performs HTML syntax validation
   - Checks for required placeholders
   - Runs security scans (scripts, event handlers, external resources)
   - Validates file size (configurable via TEMPLATE_MAX_SIZE_MB env var)
   - Returns structured validation results

4. **`fetch_sample_data(template_type)`**
   - Routes to appropriate sample data fetcher based on template type
   - Supports: STR invoices, BTW aangifte, Aangifte IB, Toeristenbelasting
   - Returns placeholder data if no real data available
   - Includes metadata about data source

5. **`approve_template(template_type, template_content, field_mappings, user_email, notes)`**
   - Validates template before approval
   - Saves template to Google Drive
   - Updates database metadata with versioning
   - Archives previous version
   - Logs approval action
   - Returns success status with file IDs

6. **`_render_template(template_content, sample_data, field_mappings)`**
   - Replaces `{{ placeholder }}` syntax with actual values
   - Formats numbers and dates appropriately
   - Handles missing placeholders gracefully

### Validation Methods

7. **`_validate_html_syntax(template_content)`**
   - Uses HTMLParser to check well-formed HTML
   - Detects unclosed tags
   - Detects mismatched closing tags
   - Tracks line numbers for error reporting
   - Skips self-closing tags (br, hr, img, etc.)

8. **`_validate_placeholders(template_type, template_content)`**
   - Defines required placeholders per template type
   - Extracts all placeholders from template
   - Reports missing required placeholders
   - Supports: str_invoice_nl, str_invoice_en, btw_aangifte, aangifte_ib, toeristenbelasting

9. **`_validate_security(template_content)`**
   - Blocks script tags (security error)
   - Blocks event handlers (onclick, onload, etc.)
   - Warns about external resources (https:// links)
   - Returns structured error/warning list

### Sample Data Methods

10. **`_fetch_str_invoice_sample()`**
    - Queries most recent realized booking
    - Uses `prepare_invoice_data()` from report generator
    - Falls back to placeholder data if no bookings exist

11. **`_fetch_btw_sample()`**
    - Returns placeholder BTW data for current year/quarter
    - TODO: Implement actual BTW data query

12. **`_fetch_aangifte_ib_sample()`**
    - Returns placeholder income tax data for previous year
    - TODO: Implement actual Aangifte IB data query

13. **`_fetch_toeristenbelasting_sample()`**
    - Returns placeholder tourist tax data for current year
    - TODO: Implement actual tourist tax data query

14. **`_fetch_generic_sample()`**
    - Returns generic placeholder data for unknown template types

15. **`_get_placeholder_str_data()`**
    - Provides complete placeholder STR invoice data
    - Includes all required fields for invoice generation

### Approval Helper Methods

16. **`_save_template_to_drive(template_type, template_content, version)`**
    - Uploads template to tenant's Google Drive
    - Creates versioned filename (e.g., str_invoice_nl_v2.html)
    - Returns Google Drive file ID

17. **`_update_template_metadata(template_type, file_id, field_mappings, user_email, notes, previous_file_id, version)`**
    - Updates or inserts template metadata in database
    - Stores version, approval info, and previous file ID
    - Marks template as active

18. **`_log_template_approval(template_type, user_email, notes, validation)`**
    - Logs approval in template_validation_log table
    - Stores validation errors and warnings as JSON
    - Non-blocking (doesn't fail approval if logging fails)

## Features

### Validation Checks

- ✅ HTML syntax validation with line numbers
- ✅ Required placeholder validation per template type
- ✅ Security scanning (scripts, event handlers, external resources)
- ✅ File size validation (configurable limit)

### Sample Data Support

- ✅ STR invoices (with real booking data)
- ✅ BTW aangifte (placeholder)
- ✅ Aangifte IB (placeholder)
- ✅ Toeristenbelasting (placeholder)
- ✅ Generic fallback

### Template Approval

- ✅ Google Drive integration
- ✅ Database metadata management
- ✅ Version tracking
- ✅ Previous version archiving
- ✅ Approval logging

### Error Handling

- ✅ Graceful degradation (placeholder data when real data unavailable)
- ✅ Detailed error messages with types and severity
- ✅ Comprehensive logging
- ✅ Exception handling at all levels

## Database Tables Used

1. **`tenant_template_config`**
   - Stores template metadata
   - Fields: template_file_id, field_mappings, version, approved_by, approved_at, approval_notes, previous_file_id, status, is_active

2. **`template_validation_log`**
   - Logs validation attempts
   - Fields: administration, template_type, validation_result, errors (JSON), warnings (JSON), validated_by, validated_at

3. **`bnb_bookings`**
   - Source for STR invoice sample data
   - Queries most recent realized booking

## Dependencies

- `DatabaseManager` - Database operations
- `TemplateService` - Template operations
- `GoogleDriveService` - Google Drive integration
- `report_generators.str_invoice_generator` - STR invoice data preparation
- Standard library: `re`, `json`, `logging`, `datetime`, `html.parser`

## Configuration

Environment variables:

- `TEMPLATE_MAX_SIZE_MB` - Maximum template size in MB (default: 5)

## Testing

- ✅ Import test passed
- ✅ No syntax errors
- ⏭️ Unit tests to be implemented in next task

## Next Steps

1. Implement HTML Syntax Validation tests
2. Implement Placeholder Validation tests
3. Implement Security Validation tests
4. Implement Sample Data Fetching tests
5. Implement Preview Generation tests
6. Implement Approval Workflow tests

## Notes

- The service is tenant-isolated (all operations scoped to administration)
- Placeholder data is used when real data is unavailable
- Logging is comprehensive for debugging and auditing
- Security validation prevents XSS and script injection
- Version tracking enables rollback if needed
