# Template Preview and Validation - Tasks

**Feature**: Template Preview and Validation System  
**Status**: Ready to Start  
**Created**: January 31, 2026

---

## Task Breakdown

### Phase 1: Backend Foundation (1-2 days)

#### 1.1 Database Schema Updates

- [ ] Add versioning columns to `tenant_template_config` table
  - [ ] `version INT DEFAULT 1`
  - [ ] `approved_by VARCHAR(255)`
  - [ ] `approved_at TIMESTAMP`
  - [ ] `approval_notes TEXT`
  - [ ] `previous_file_id VARCHAR(255)`
  - [ ] `status ENUM('draft', 'active', 'archived')`
- [ ] Create `template_validation_log` table
- [ ] Test schema changes locally
- [ ] Create migration script for Railway

#### 1.2 TemplatePreviewService - Core Structure

- [ ] Create `backend/src/services/template_preview_service.py`
- [ ] Implement `__init__(self, db, administration)`
- [ ] Implement `generate_preview(template_type, template_content, field_mappings)`
- [ ] Implement `validate_template(template_type, template_content)`
- [ ] Implement `fetch_sample_data(template_type)`
- [ ] Implement `approve_template(...)`
- [ ] Add error handling and logging

#### 1.3 HTML Validation

- [ ] Implement `_validate_html_syntax(template_content)`
  - [ ] Use HTMLParser to check well-formed HTML
  - [ ] Detect unclosed tags
  - [ ] Detect mismatched tags
  - [ ] Return structured error messages
- [ ] Write unit tests for HTML validation
  - [ ] Test valid HTML
  - [ ] Test unclosed tags
  - [ ] Test mismatched tags
  - [ ] Test malformed HTML

#### 1.4 Placeholder Validation

- [ ] Define required placeholders per template type
  - [ ] STR Invoice (NL/EN)
  - [ ] BTW Aangifte
  - [ ] Aangifte IB
  - [ ] Toeristenbelasting
  - [ ] Financial Report
- [ ] Implement `_validate_placeholders(template_type, template_content)`
  - [ ] Extract placeholders using regex
  - [ ] Check for missing required placeholders
  - [ ] Return structured error messages
- [ ] Write unit tests for placeholder validation

#### 1.5 Security Validation

- [ ] Implement `_validate_security(template_content)`
  - [ ] Check for `<script>` tags
  - [ ] Check for event handlers (onclick, onload, etc.)
  - [ ] Check for external resources
  - [ ] Check for iframe injection
- [ ] Write unit tests for security validation

### Phase 2: Sample Data & Preview Generation (1 day)

#### 2.1 Sample Data Fetching

- [ ] Implement `_fetch_str_invoice_sample()`
  - [ ] Query most recent booking
  - [ ] Handle no data case (return placeholder)
  - [ ] Return data + metadata
- [ ] Implement `_fetch_btw_sample()`
  - [ ] Query most recent BTW data
  - [ ] Handle no data case
- [ ] Implement `_fetch_aangifte_ib_sample()`
  - [ ] Query most recent IB data
  - [ ] Handle no data case
- [ ] Implement `_fetch_toeristenbelasting_sample()`
  - [ ] Query most recent tourist tax data
  - [ ] Handle no data case
- [ ] Implement `_fetch_generic_sample()`
  - [ ] Return placeholder data for unknown types
- [ ] Write integration tests for sample data fetching

#### 2.2 Preview Rendering

- [ ] Implement `_render_template(template_content, sample_data, field_mappings)`
  - [ ] Apply field mappings
  - [ ] Replace placeholders with sample data
  - [ ] Use existing report generators where applicable
  - [ ] Handle rendering errors gracefully
- [ ] Test preview rendering with all template types
- [ ] Test with missing placeholders
- [ ] Test with invalid data

#### 2.3 Template Approval

- [ ] Implement `approve_template(...)`
  - [ ] Save template to Google Drive
  - [ ] Update database metadata
  - [ ] Archive previous version (if exists)
  - [ ] Log approval action
  - [ ] Return success response with file_id
- [ ] Write integration tests for approval flow
- [ ] Test version archiving
- [ ] Test rollback scenarios

### Phase 3: API Endpoints (1 day)

#### 3.1 Create Routes File

- [ ] Create `backend/src/tenant_admin_routes.py`
- [ ] Register blueprint in main app
- [ ] Add authentication decorator `@require_tenant_admin`
- [ ] Add error handling middleware

#### 3.2 Preview Endpoint

- [ ] Implement `POST /api/tenant-admin/templates/preview`
  - [ ] Validate request body
  - [ ] Call TemplatePreviewService
  - [ ] Return preview HTML + validation results
  - [ ] Handle errors (400, 401, 500)
- [ ] Add request validation
- [ ] Add response formatting
- [ ] Write API tests

#### 3.3 Validate Endpoint

- [ ] Implement `POST /api/tenant-admin/templates/validate`
  - [ ] Validate request body
  - [ ] Call validation only (no preview)
  - [ ] Return validation results
- [ ] Write API tests

#### 3.4 Approve Endpoint

- [ ] Implement `POST /api/tenant-admin/templates/approve`
  - [ ] Validate request body
  - [ ] Call approve_template
  - [ ] Return success response
- [ ] Write API tests

#### 3.5 Reject Endpoint

- [ ] Implement `POST /api/tenant-admin/templates/reject`
  - [ ] Log rejection with reason
  - [ ] Return success response
- [ ] Write API tests

#### 3.6 Security & Authorization

- [ ] Add Content Security Policy headers
- [ ] Verify tenant isolation in all endpoints
- [ ] Add rate limiting
- [ ] Add audit logging
- [ ] Test unauthorized access attempts

### Phase 4: Frontend Components (2 days)

#### 4.1 Component Structure

- [ ] Create `frontend/src/components/TenantAdmin/TemplateManagement/` folder
- [ ] Create component files:
  - [ ] `TemplateManagement.tsx` (main container)
  - [ ] `TemplateUpload.tsx` (file upload form)
  - [ ] `TemplatePreview.tsx` (preview display)
  - [ ] `ValidationResults.tsx` (errors/warnings)
  - [ ] `FieldMappingEditor.tsx` (field mapping UI)
  - [ ] `TemplateApproval.tsx` (approve/reject buttons)

#### 4.2 TemplateUpload Component

- [ ] Create file upload input
- [ ] Add template type selector dropdown
- [ ] Add field mapping editor
- [ ] Add upload button
- [ ] Show loading state during upload
- [ ] Handle file size validation (client-side)
- [ ] Handle file type validation (HTML only)
- [ ] Display upload progress

#### 4.3 TemplatePreview Component

- [ ] Create iframe for preview display
- [ ] Add sandbox attribute for security
- [ ] Add responsive sizing
- [ ] Add zoom controls (optional)
- [ ] Add "Preview with sample data" note
- [ ] Handle preview loading state

#### 4.4 ValidationResults Component

- [ ] Display validation success message
- [ ] Display errors list with details
- [ ] Display warnings list
- [ ] Color-code by severity (error/warning)
- [ ] Show line numbers for syntax errors
- [ ] Add "How to fix" hints for common errors

#### 4.5 FieldMappingEditor Component

- [ ] Create form for field mappings
- [ ] Show required fields per template type
- [ ] Add autocomplete for data fields
- [ ] Validate mapping completeness
- [ ] Save/load mappings
- [ ] Show mapping preview

#### 4.6 TemplateApproval Component

- [ ] Create Approve button
- [ ] Create Reject button
- [ ] Add approval notes textarea
- [ ] Add rejection reason textarea
- [ ] Disable buttons during processing
- [ ] Show confirmation dialog
- [ ] Handle success/error states

#### 4.7 Main TemplateManagement Component

- [ ] Implement state management
- [ ] Connect upload to preview API
- [ ] Connect approval to approve API
- [ ] Connect rejection to reject API
- [ ] Handle loading states
- [ ] Handle error states
- [ ] Add success notifications
- [ ] Add error notifications

#### 4.8 Styling

- [ ] Create CSS/SCSS for all components
- [ ] Ensure responsive design
- [ ] Add loading spinners
- [ ] Add icons for validation results
- [ ] Match existing app theme
- [ ] Test on mobile devices

### Phase 5: Testing & Documentation (1 day)

#### 5.1 Unit Tests

- [ ] Test HTML validation functions
- [ ] Test placeholder validation functions
- [ ] Test security validation functions
- [ ] Test sample data fetching
- [ ] Test preview rendering
- [ ] Test approval logic
- [ ] Achieve 80%+ code coverage

#### 5.2 Integration Tests

- [ ] Test full preview generation flow
- [ ] Test with all template types
- [ ] Test with missing sample data
- [ ] Test approval and archiving
- [ ] Test tenant isolation
- [ ] Test error scenarios

#### 5.3 API Tests

- [ ] Test all endpoints with valid data
- [ ] Test authentication requirements
- [ ] Test authorization (tenant isolation)
- [ ] Test validation error responses
- [ ] Test rate limiting
- [ ] Test concurrent requests

#### 5.4 Frontend Tests

- [ ] Test component rendering
- [ ] Test file upload
- [ ] Test preview display
- [ ] Test validation results display
- [ ] Test approval/rejection flow
- [ ] Test error handling

#### 5.5 E2E Tests

- [ ] Test complete upload-to-approval workflow
- [ ] Test rejection and re-upload
- [ ] Test updating existing template
- [ ] Test with multiple template types
- [ ] Test error recovery

#### 5.6 Documentation

- [ ] Write API documentation (OpenAPI/Swagger)
- [ ] Write user guide for Tenant Administrators
- [ ] Document field mapping reference
- [ ] Document validation rules
- [ ] Create troubleshooting guide
- [ ] Document security considerations
- [ ] Add code comments

### Phase 6: Deployment (0.5 days)

#### 6.1 Database Migration

- [ ] Test migration script locally
- [ ] Run migration on Railway staging
- [ ] Verify schema changes
- [ ] Test rollback procedure

#### 6.2 Environment Configuration

- [ ] Add environment variables to Railway
  - [ ] `TEMPLATE_MAX_SIZE_MB=5`
  - [ ] `TEMPLATE_PREVIEW_TIMEOUT=30`
- [ ] Update configuration documentation

#### 6.3 Deployment

- [ ] Deploy backend to Railway
- [ ] Deploy frontend to Railway
- [ ] Verify all endpoints work
- [ ] Test with production data
- [ ] Monitor logs for errors

#### 6.4 Monitoring

- [ ] Set up error alerts
- [ ] Monitor preview generation time
- [ ] Monitor validation failure rates
- [ ] Set up usage analytics

---

## Progress Tracking

| Phase                            | Tasks   | Completed | Status         |
| -------------------------------- | ------- | --------- | -------------- |
| Phase 1: Backend Foundation      | 15      | 0         | ⏸️ Not Started |
| Phase 2: Sample Data & Preview   | 13      | 0         | ⏸️ Not Started |
| Phase 3: API Endpoints           | 14      | 0         | ⏸️ Not Started |
| Phase 4: Frontend Components     | 28      | 0         | ⏸️ Not Started |
| Phase 5: Testing & Documentation | 23      | 0         | ⏸️ Not Started |
| Phase 6: Deployment              | 8       | 0         | ⏸️ Not Started |
| **Total**                        | **101** | **0**     | **0%**         |

---

## Estimated Timeline

- **Phase 1**: 1-2 days (Backend Foundation)
- **Phase 2**: 1 day (Sample Data & Preview)
- **Phase 3**: 1 day (API Endpoints)
- **Phase 4**: 2 days (Frontend Components)
- **Phase 5**: 1 day (Testing & Documentation)
- **Phase 6**: 0.5 days (Deployment)

**Total**: 6.5-7.5 days

---

## Dependencies

**Upstream** (Must be completed first):

- ✅ Phase 1: Credentials Infrastructure
- ✅ Phase 2.1-2.5: Template Management Infrastructure
- ✅ TemplateService implementation
- ✅ Report generators implementation

**Downstream** (Depends on this):

- Phase 4: Tenant Admin Module (full UI)
- User invitation system
- Template analytics

---

## Success Criteria

- [ ] Tenant Administrators can upload templates
- [ ] System validates templates automatically
- [ ] Previews show accurate representation
- [ ] Approved templates work in production
- [ ] Zero broken templates activated
- [ ] All tests passing (unit, integration, API, E2E)
- [ ] Documentation complete
- [ ] Deployed to Railway successfully

---

## Notes

- Start with backend (Phases 1-3) before frontend
- Test thoroughly with all template types
- Focus on security and tenant isolation
- Keep UI simple and intuitive
- Document validation rules clearly
- Monitor performance in production
