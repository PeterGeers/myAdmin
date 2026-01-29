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

- [ ] Create `tenant_template_config` table
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
- [ ] Test table creation locally
- [ ] Document field_mappings JSON structure

#### 2.2 Template Service

- [ ] Create `backend/src/services/template_service.py`
- [ ] Implement `get_template_metadata(administration, template_type)` method
- [ ] Implement `fetch_template_from_drive(file_id, administration)` method
- [ ] Implement `apply_field_mappings(template_xml, data, mappings)` method
- [ ] Implement `generate_output(template, data, output_format)` method
- [ ] Write unit tests

#### 2.3 Convert Existing Templates to XML

- [ ] Convert financial report template to XML with field mappings
- [ ] Convert STR invoice template to XML with field mappings
- [ ] Convert BTW Aangifte (currently hardcoded) to XML template
- [ ] Convert Toeristenbelasting (currently hardcoded) to XML template
- [ ] Convert IB Aangifte (currently hardcoded) to XML template
- [ ] Document field mapping structure for each template

#### 2.4 Migrate Templates to Google Drive

- [ ] Create template folders in each tenant's Google Drive
- [ ] Upload XML templates to tenant Google Drives
- [ ] Store template metadata in `tenant_template_config` table
- [ ] Verify templates are accessible

#### 2.5 Update Report Generation Routes

- [ ] Update financial report generation to use TemplateService
- [ ] Update STR invoice generation to use TemplateService
- [ ] Update tax form generation to use TemplateService
- [ ] Add option to download vs store in Drive
- [ ] Test all report types

#### 2.6 Testing

- [ ] Test each template type generation
- [ ] Verify field mappings work correctly
- [ ] Test download to local device
- [ ] Test store to Google Drive
- [ ] Run integration tests

**Deliverables**:

- ✅ All templates converted to XML
- ✅ Template metadata in database
- ✅ Working TemplateService
- ✅ Updated report generation routes
- ✅ All tests passing

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
