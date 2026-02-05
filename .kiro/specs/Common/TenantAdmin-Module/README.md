# Tenant Admin Module Specification

**Status**: Draft
**Created**: February 5, 2026
**Last Updated**: February 5, 2026

---

## 📖 Overview

The Tenant Admin Module provides tenant-level administration capabilities for managing users, credentials, storage, and settings within a specific tenant. This specification covers the **missing features** that need to be implemented.

---

## ✅ What's Already Implemented

- ✅ **Template Management** (Phase 2.6 - Complete)
  - Upload, preview, validate templates
  - AI-powered template assistance
  - Field mapping configuration
  - Template approval workflow
  - Comprehensive testing (148 unit tests, 11 integration tests)

- ✅ **TenantAdminDashboard** (Navigation)
  - Main dashboard with feature cards
  - Navigation between sections
  - Role-based access control

- ✅ **Backend Routes** (`tenant_admin_routes.py`)
  - Template management endpoints
  - Authentication and authorization

---

## 🚧 What Needs to Be Implemented

This specification focuses on the **missing features**:

1. **User Management** - Create users, assign roles, send invitations
2. **Credentials Management** - Upload and manage Google Drive credentials
3. **Storage Configuration** - Configure folder IDs and storage settings
4. **Tenant Settings** - General tenant preferences and configuration

---

## 📚 Reading Order

### 1. **README.md** (You are here)

- Overview and navigation
- Current status

### 2. **requirements.md** ⭐ START HERE

- User stories for missing features
- Acceptance criteria
- Functional requirements

### 3. **design.md**

- Technical architecture
- API specifications
- Database schema
- Implementation details

### 4. **TASKS.md**

- Detailed implementation tasks
- Phase breakdown
- Progress tracking

---

## 🎯 Key Concepts

### Tenant Administrator Role

- Manages users within their tenant
- Manages tenant-specific credentials
- Configures storage and settings
- Cannot access other tenants
- Cannot access platform-level settings (SysAdmin only)

### User Management

- Create new users in Cognito
- Assign users to tenant
- Assign roles to users (from tenant-allocated roles)
- Send invitation emails
- Remove users from tenant

### Credentials Management

- Upload Google Drive credentials (credentials.json, token.json)
- OAuth flow for Google Drive authentication
- Encrypt and store credentials in MySQL
- Test credential connectivity
- Rotate credentials

### Storage Configuration

- Configure Google Drive folder IDs
- Set default folders for invoices, reports, templates
- Test folder access
- Configure storage quotas

### Tenant Settings

- General tenant preferences
- Contact information
- Notification settings
- Feature toggles

---

## 📊 Current Status

### Implemented (Phase 2.6)

- ✅ Template Management (complete)
- ✅ TenantAdminDashboard (navigation)
- ✅ Backend routes blueprint

### Not Implemented

- ❌ User Management
- ❌ Credentials Management
- ❌ Storage Configuration
- ❌ Tenant Settings

---

## 🔗 Related Specifications

- **Railway Migration**: `.kiro/specs/Common/Railway migration/`
  - Phase 4 implements Tenant Admin features
- **SysAdmin Module**: `.kiro/specs/Common/SysAdmin-Module/`
  - Platform-level administration
  - Tenant creation and role allocation

- **Template Preview & Validation**: `.kiro/specs/Common/template-preview-validation/`
  - Already implemented in Phase 2.6
  - Reference for implementation patterns

---

## 🆘 Quick Reference

**Who is Tenant Administrator?**
→ User with Tenant_Admin role who manages their tenant

**What can Tenant Admin do?**
→ Manage users, credentials, storage, settings for their tenant

**What can't Tenant Admin do?**
→ Access other tenants, create tenants, manage platform settings

**Where is data stored?**
→ MySQL (metadata), Google Drive (tenant files), Cognito (users)

**When to implement?**
→ Phase 4 of Railway migration (after SysAdmin module)

---

## 📝 Document Status

| Document        | Status         | Completion |
| --------------- | -------------- | ---------- |
| README.md       | ✅ Complete    | 100%       |
| requirements.md | 🔄 In Progress | 0%         |
| design.md       | ⏸️ Not Started | 0%         |
| TASKS.md        | ⏸️ Not Started | 0%         |

---

## Next Steps

1. Read `requirements.md` to understand user stories
2. Review `design.md` for technical architecture
3. Follow `TASKS.md` for implementation
4. Reference Template Management implementation as example
