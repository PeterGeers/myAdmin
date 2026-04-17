# Template Preview and Validation - Requirements

**Feature**: Template Preview and Validation System  
**Status**: Draft  
**Created**: January 31, 2026  
**Owner**: Development Team

---

## 1. Overview

### 1.1 Purpose

Enable Tenant Administrators to safely upload, preview, and validate custom report templates before activating them in production. This prevents broken templates from affecting report generation and gives administrators confidence that their customizations work correctly.

### 1.2 Context

As part of the Railway migration (Phase 2.6), we're implementing a self-service template management system. Tenant Administrators need the ability to:

- Upload custom HTML templates for reports (invoices, tax forms, financial reports)
- Preview templates with real sample data before activation
- Validate templates for syntax errors and missing placeholders
- Approve or reject templates based on preview results

### 1.3 Goals

1. **Safety**: Prevent broken templates from being activated
2. **Confidence**: Show administrators exactly how their template will look with real data
3. **Self-service**: Enable tenants to manage templates without developer intervention
4. **Quality**: Catch errors early through automated validation

---

## 2. User Stories

### 2.1 As a Tenant Administrator

**Story 1: Upload and Preview Template**

```
As a Tenant Administrator
I want to upload a custom invoice template and see a preview with real data
So that I can verify it looks correct before activating it
```

**Acceptance Criteria**:

- 1.1: I can upload an HTML template file through the UI
- 1.2: I can specify field mappings for the template
- 1.3: The system generates a preview using recent sample data from my tenant
- 1.4: The preview shows exactly how the template will render with real data
- 1.5: I can see any validation errors or warnings before approval

**Story 2: Validate Template Syntax**

```
As a Tenant Administrator
I want the system to validate my template for errors
So that I don't activate a broken template
```

**Acceptance Criteria**:

- 2.1: The system checks that HTML is well-formed
- 2.2: The system verifies all required placeholders are present
- 2.3: The system tests that the template renders without errors
- 2.4: I receive clear error messages if validation fails
- 2.5: I can fix errors and re-upload without losing my progress

**Story 3: Approve or Reject Template**

```
As a Tenant Administrator
I want to approve a template after reviewing the preview
So that it becomes active for report generation
```

**Acceptance Criteria**:

- 3.1: I can approve a template after reviewing the preview
- 3.2: Approved templates are saved to my Google Drive
- 3.3: Template metadata is stored in the database
- 3.4: I can reject a template and upload a modified version
- 3.5: Only approved templates are used for report generation

**Story 4: Update Existing Template**

```
As a Tenant Administrator
I want to update an existing template
So that I can improve or fix my customizations
```

**Acceptance Criteria**:

- 4.1: I can upload a new version of an existing template
- 4.2: The system shows a preview of the new version
- 4.3: I can compare the new version with the current version
- 4.4: Approving the new version replaces the old one
- 4.5: The old version is archived (not deleted)

### 2.2 As a Tenant Administrator (AI Assistance)

**Story 5: Get AI Help with Template Errors**

```
As a Tenant Administrator
I want AI assistance to fix my template validation errors
So that I can resolve issues quickly without developer help
```

**Acceptance Criteria**:

- 5.1: When validation fails, I can click "Get AI Help"
- 5.2: AI analyzes my template and validation errors
- 5.3: AI suggests specific fixes with code examples
- 5.4: AI can optionally auto-fix common issues
- 5.5: All AI analysis happens within my tenant context (no data sharing)
- 5.6: I can accept or reject AI suggestions
- 5.7: AI suggestions are logged for quality improvement

---

## 3. Functional Requirements

### 3.1 Template Upload

**FR-1.1**: System shall accept HTML template files via API endpoint  
**FR-1.2**: System shall validate file size (max 5MB)  
**FR-1.3**: System shall validate file type (HTML only)  
**FR-1.4**: System shall accept field mappings as JSON  
**FR-1.5**: System shall associate uploaded template with authenticated tenant

### 3.2 Sample Data Retrieval

**FR-2.1**: System shall fetch most recent report data for the template type  
**FR-2.2**: System shall use tenant-specific data only (tenant isolation)  
**FR-2.3**: System shall handle cases where no sample data exists  
**FR-2.4**: System shall support all report types:

- Aangifte IB (Income Tax)
- BTW Aangifte (VAT)
- STR Invoice (Rental)
- Toeristenbelasting (Tourist Tax)
- Financial Report (XLSX)

### 3.3 Template Validation

**FR-3.1**: System shall validate HTML syntax (well-formed)  
**FR-3.2**: System shall check for required placeholders per template type  
**FR-3.3**: System shall verify template renders without errors  
**FR-3.4**: System shall check for security issues (XSS, script injection)  
**FR-3.5**: System shall return detailed validation results

### 3.4 Preview Generation

**FR-4.1**: System shall generate preview using sample data  
**FR-4.2**: System shall apply field mappings to template  
**FR-4.3**: System shall return rendered HTML preview  
**FR-4.4**: System shall handle rendering errors gracefully  
**FR-4.5**: System shall include validation warnings in preview response

### 3.5 Template Approval

**FR-5.1**: System shall save approved templates to tenant's Google Drive  
**FR-5.2**: System shall store template metadata in database  
**FR-5.3**: System shall mark template as active upon approval  
**FR-5.4**: System shall archive previous version (if updating)  
**FR-5.5**: System shall log approval action with timestamp and user

### 3.6 Template Rejection

**FR-6.1**: System shall allow rejection without saving to Google Drive  
**FR-6.2**: System shall preserve uploaded template for modification  
**FR-6.3**: System shall allow re-upload after rejection  
**FR-6.4**: System shall log rejection action with reason

### 3.7 AI-Powered Template Assistance

**FR-7.1**: System shall integrate with OpenRouter AI API  
**FR-7.2**: System shall send validation errors + template code to AI (within tenant context)  
**FR-7.3**: System shall receive AI-generated fix suggestions  
**FR-7.4**: System shall present suggestions to user with code diff  
**FR-7.5**: System shall allow user to accept or reject AI suggestions  
**FR-7.6**: System shall apply accepted suggestions to template  
**FR-7.7**: System shall not share tenant data with external AI (only template code + errors)  
**FR-7.8**: System shall log AI interactions for quality monitoring

---

## 4. Non-Functional Requirements

### 4.1 Security

**NFR-1.1**: Only Tenant Administrators can upload templates for their tenant  
**NFR-1.2**: Templates must be validated for XSS and injection attacks  
**NFR-1.3**: Sample data must be filtered by tenant (no data leakage)  
**NFR-1.4**: File uploads must be scanned for malicious content  
**NFR-1.5**: API endpoints must require authentication and authorization

### 4.2 Performance

**NFR-2.1**: Preview generation shall complete within 5 seconds  
**NFR-2.2**: Validation shall complete within 3 seconds  
**NFR-2.3**: File upload shall support up to 5MB files  
**NFR-2.4**: System shall handle concurrent uploads from multiple tenants

### 4.3 Reliability

**NFR-3.1**: Validation errors shall not crash the system  
**NFR-3.2**: Failed uploads shall not corrupt existing templates  
**NFR-3.3**: System shall maintain template version history  
**NFR-3.4**: Rollback shall be possible if new template causes issues

### 4.4 Usability

**NFR-4.1**: Error messages shall be clear and actionable  
**NFR-4.2**: Preview shall accurately represent final output  
**NFR-4.3**: UI shall provide visual feedback during upload/validation  
**NFR-4.4**: System shall support common HTML editors' output

### 4.5 Maintainability

**NFR-5.1**: Validation rules shall be configurable per template type  
**NFR-5.2**: New template types shall be easy to add  
**NFR-5.3**: Code shall follow existing project patterns  
**NFR-5.4**: API shall be versioned for future changes

---

## 5. Constraints

### 5.1 Technical Constraints

- Must integrate with existing TemplateService
- Must use existing Google Drive authentication
- Must work with current database schema (can extend)
- Must support existing report generators
- Must work in Railway deployment environment

### 5.2 Business Constraints

- Tenant Administrators only (not regular users)
- Templates are tenant-owned (stored in tenant's Google Drive)
- Must maintain backward compatibility with existing templates
- Must not require developer intervention for template changes

### 5.3 Time Constraints

- Part of Phase 2.6 of Railway migration
- Should be completed before Phase 4 (Tenant Admin Module UI)
- Estimated: 2-3 days for backend, 2-3 days for frontend

---

## 6. Dependencies

### 6.1 Upstream Dependencies

- Phase 1: Credentials Infrastructure (completed)
- Phase 2.1-2.5: Template Management Infrastructure (completed)
- TemplateService implementation
- Report generators implementation
- Google Drive integration

### 6.2 Downstream Dependencies

- Phase 4: Tenant Admin Module UI (will use this API)
- Template management frontend components
- User invitation system (for notifying about template changes)

---

## 7. Success Criteria

### 7.1 Functional Success

- ✅ Tenant Administrators can upload templates
- ✅ System validates templates automatically
- ✅ Previews show accurate representation of final output
- ✅ Approved templates work correctly in production
- ✅ Validation catches common errors before activation

### 7.2 Quality Success

- ✅ Zero broken templates activated in production
- ✅ 95%+ of validation errors caught before approval
- ✅ Clear error messages for all validation failures
- ✅ Preview matches final output 100%

### 7.3 User Success

- ✅ Tenant Administrators can manage templates without developer help
- ✅ Template upload and approval takes < 5 minutes
- ✅ Users understand validation errors and how to fix them
- ✅ Confidence in template customization increases

---

## 8. Out of Scope

The following are explicitly **not** included in this feature:

- ❌ Visual template editor (WYSIWYG)
- ❌ Template marketplace or sharing between tenants
- ❌ Automated template generation from data
- ❌ PDF conversion (handled separately)
- ❌ Email delivery of templates
- ❌ Template versioning UI (basic versioning only)
- ❌ A/B testing of templates
- ❌ Template analytics or usage tracking

---

## 9. Future Enhancements

Potential future additions (not in current scope):

1. **Template Library**: Pre-built templates for common use cases
2. **Visual Editor**: Drag-and-drop template builder
3. **Version Comparison**: Side-by-side diff of template versions
4. **Template Testing**: Automated tests for templates
5. **Template Metrics**: Track which templates perform best
6. **Collaborative Editing**: Multiple admins working on same template
7. **Template Inheritance**: Base templates with tenant-specific overrides

---

## 10. Risks and Mitigations

### 10.1 Risk: Malicious Template Upload

**Impact**: High - Could lead to XSS attacks or data leakage  
**Probability**: Medium  
**Mitigation**:

- Strict HTML validation
- Content Security Policy enforcement
- Sanitize all user input
- Sandbox preview rendering

### 10.2 Risk: Template Breaks Production Reports

**Impact**: High - Users cannot generate reports  
**Probability**: Low (with validation)  
**Mitigation**:

- Comprehensive validation before approval
- Preview with real data
- Easy rollback to previous version
- Monitoring and alerts

### 10.3 Risk: Sample Data Privacy

**Impact**: High - Sample data could leak between tenants  
**Probability**: Low  
**Mitigation**:

- Strict tenant filtering in queries
- Test tenant isolation thoroughly
- Audit logs for data access
- Regular security reviews

### 10.4 Risk: Performance Issues with Large Templates

**Impact**: Medium - Slow preview generation  
**Probability**: Medium  
**Mitigation**:

- File size limits (5MB)
- Timeout on preview generation
- Async processing for large templates
- Caching of sample data

---

## 11. Acceptance Testing

### 11.1 Test Scenarios

**Scenario 1: Happy Path - Upload and Approve**

1. Tenant Admin uploads valid HTML template
2. System validates template (passes)
3. System generates preview with sample data
4. Admin reviews preview
5. Admin approves template
6. Template saved to Google Drive
7. Template marked as active in database

**Scenario 2: Validation Failure**

1. Tenant Admin uploads template with missing placeholder
2. System validates template (fails)
3. System returns error: "Missing required placeholder: {{ invoice_number }}"
4. Admin fixes template
5. Admin re-uploads
6. System validates (passes)
7. Preview generated successfully

**Scenario 3: No Sample Data**

1. Tenant Admin uploads template for new report type
2. System attempts to fetch sample data (none exists)
3. System generates preview with placeholder data
4. System warns: "No sample data available, using placeholder values"
5. Admin can still approve template

**Scenario 4: Update Existing Template**

1. Tenant Admin uploads new version of existing template
2. System shows preview of new version
3. Admin approves
4. Old version archived
5. New version becomes active

---

## 12. Documentation Requirements

### 12.1 User Documentation

- Template upload guide for Tenant Administrators
- Field mapping reference for each template type
- Troubleshooting guide for common validation errors
- Best practices for template customization

### 12.2 Technical Documentation

- API documentation (endpoints, request/response schemas)
- Validation rules reference
- Integration guide for new template types
- Security considerations

### 12.3 Developer Documentation

- Code architecture overview
- Adding new validation rules
- Extending to new template types
- Testing guide

---

## 13. Glossary

- **Template**: HTML file with placeholders for dynamic data
- **Field Mapping**: JSON configuration mapping data fields to template placeholders
- **Preview**: Rendered HTML showing how template looks with sample data
- **Validation**: Automated checks for template correctness
- **Approval**: Action by Tenant Admin to activate a template
- **Sample Data**: Recent real data used for preview generation
- **Tenant Administrator**: User role with permission to manage templates for their tenant
- **Template Type**: Category of template (e.g., "str_invoice_nl", "btw_aangifte")

---

## Next Steps

1. ✅ Requirements approved
2. ⏭️ Create design document
3. ⏭️ Create task breakdown
4. ⏭️ Implement backend API
5. ⏭️ Implement frontend UI
6. ⏭️ Integration testing
7. ⏭️ User acceptance testing
