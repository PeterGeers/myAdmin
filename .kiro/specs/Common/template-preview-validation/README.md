# Template Preview and Validation - Specification

**Feature**: Template Preview and Validation System  
**Status**: Ready for Implementation  
**Created**: January 31, 2026  
**Part of**: Railway Migration Phase 2.6

---

## 📋 Overview

This specification defines the Template Preview and Validation system that enables Tenant Administrators to safely upload, preview, and validate custom report templates before activating them in production.

### Purpose

- **Safety**: Prevent broken templates from being activated
- **Confidence**: Show administrators exactly how templates will look with real data
- **Self-service**: Enable tenants to manage templates without developer intervention
- **Quality**: Catch errors early through automated validation

---

## 📁 Specification Documents

### 1. [Requirements](./requirements.md)

Defines what the system must do:

- User stories and acceptance criteria
- Functional and non-functional requirements
- Success criteria and constraints
- Out of scope items

**Read this first** to understand the business requirements.

### 2. [Design](./design.md)

Defines how the system will work:

- Architecture and data flow
- API specifications (endpoints, request/response schemas)
- Database schema changes
- Backend implementation (TemplatePreviewService)
- Frontend implementation (React components)
- Security considerations
- Error handling and performance optimization

**Read this second** to understand the technical approach.

### 3. [Tasks](./tasks.md)

Defines the implementation plan:

- Detailed task breakdown (101 tasks across 6 phases)
- Estimated timeline (6.5-7.5 days)
- Progress tracking
- Dependencies

**Use this** during implementation to track progress.

---

## 🎯 Quick Start

### For Product Owners

1. Read [Requirements](./requirements.md) - Sections 1-2 (Overview, User Stories)
2. Review success criteria (Section 7)
3. Approve or provide feedback

### For Developers

1. Read [Requirements](./requirements.md) - All sections
2. Read [Design](./design.md) - All sections
3. Review [Tasks](./tasks.md) - Understand phases
4. Start with Phase 1 (Backend Foundation)

### For QA/Testers

1. Read [Requirements](./requirements.md) - Section 11 (Acceptance Testing)
2. Read [Design](./design.md) - Section 9 (Testing Strategy)
3. Review [Tasks](./tasks.md) - Phase 5 (Testing)

---

## 🏗️ Architecture Summary

```
Frontend (React)
    ↓ Upload template + field mappings
Backend API (Flask)
    ↓ Validate & generate preview
TemplatePreviewService
    ├─→ Validate HTML syntax
    ├─→ Check required placeholders
    ├─→ Scan for security issues
    ├─→ Fetch sample data (MySQL)
    └─→ Generate preview (report generators)
    ↓ Return preview HTML + validation results
Frontend
    ↓ Display preview in iframe
User reviews and approves
    ↓ Approve
Backend
    ├─→ Save to Google Drive
    ├─→ Update database metadata
    └─→ Archive previous version
```

---

## 🔑 Key Features

### Template Upload

- Upload HTML template files (max 5MB)
- Specify field mappings (JSON)
- Support for all report types

### Validation

- ✅ HTML syntax validation
- ✅ Required placeholder checking
- ✅ Security scanning (XSS, injection)
- ✅ File size and type validation

### Preview Generation

- Uses real sample data from tenant's database
- Renders exactly as final output will look
- Shows validation errors and warnings
- Handles missing sample data gracefully

### Approval Workflow

- Review preview before activation
- Approve → saves to Google Drive + activates
- Reject → allows modification and re-upload
- Version history and archiving

---

## 📊 Implementation Phases

| Phase                      | Duration | Description                                                   |
| -------------------------- | -------- | ------------------------------------------------------------- |
| 1. Backend Foundation      | 1-2 days | Database schema, TemplatePreviewService, validation functions |
| 2. Sample Data & Preview   | 1 day    | Sample data fetching, preview rendering, approval logic       |
| 3. API Endpoints           | 1 day    | REST API endpoints, authentication, error handling            |
| 4. Frontend Components     | 2 days   | React components, file upload, preview display, approval UI   |
| 5. Testing & Documentation | 1 day    | Unit, integration, API, E2E tests, documentation              |
| 6. Deployment              | 0.5 days | Database migration, Railway deployment, monitoring            |

**Total**: 6.5-7.5 days

---

## 🔒 Security Highlights

- **Authentication**: All endpoints require Tenant Administrator role
- **Tenant Isolation**: Sample data filtered by authenticated tenant
- **Content Sanitization**: Strip dangerous tags and attributes
- **XSS Prevention**: Sandbox iframe for preview display
- **Audit Logging**: Track all template operations

---

## 📈 Success Metrics

- ✅ Zero broken templates activated in production
- ✅ 95%+ of validation errors caught before approval
- ✅ Preview matches final output 100%
- ✅ Template upload and approval takes < 5 minutes
- ✅ Tenant Administrators can manage templates without developer help

---

## 🔗 Related Documentation

### Railway Migration

- [TASKS.md](../Railway%20migration/TASKS.md) - Phase 2.6
- [IMPACT_ANALYSIS_SUMMARY.md](../Railway%20migration/IMPACT_ANALYSIS_SUMMARY.md) - Decision 2 & 5

### Templates

- [analysis.md](../templates/analysis.md) - Template system decisions
- [FIELD_MAPPINGS_INDEX.md](../../templates/FIELD_MAPPINGS_INDEX.md) - Field mapping reference

### Existing Services

- `backend/src/services/template_service.py` - Template management
- `backend/src/report_generators/` - Report generation logic

---

## 🚀 Getting Started

### Prerequisites

- Phase 1 (Credentials Infrastructure) completed
- Phase 2.1-2.5 (Template Management) completed
- TemplateService implemented
- Report generators implemented
- Google Drive integration working

### Implementation Order

1. **Backend First**: Implement Phases 1-3 (backend, API)
2. **Test Backend**: Write and run unit + integration tests
3. **Frontend**: Implement Phase 4 (React components)
4. **E2E Testing**: Test complete workflow
5. **Deploy**: Phase 6 (Railway deployment)

### Development Workflow

1. Create feature branch: `feature/template-preview-validation`
2. Implement one phase at a time
3. Write tests as you go
4. Review and test thoroughly
5. Merge to main when complete

---

## 📝 Change Log

| Date       | Version | Changes                       |
| ---------- | ------- | ----------------------------- |
| 2026-01-31 | 1.0     | Initial specification created |

---

## 👥 Stakeholders

- **Product Owner**: Approves requirements
- **Development Team**: Implements features
- **QA Team**: Tests functionality
- **Tenant Administrators**: End users
- **System Administrators**: Monitor and support

---

## ❓ Questions or Feedback?

For questions about this specification:

1. Review the relevant document (Requirements, Design, or Tasks)
2. Check the [IMPACT_ANALYSIS_SUMMARY.md](../Railway%20migration/IMPACT_ANALYSIS_SUMMARY.md)
3. Consult with the development team

---

## ✅ Approval

- [ ] Requirements approved by Product Owner
- [ ] Design approved by Tech Lead
- [ ] Tasks reviewed by Development Team
- [ ] Ready for implementation

---

**Next Steps**: Review requirements document and provide approval to proceed with implementation.
