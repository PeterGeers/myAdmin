# Railway Migration - Master Plan

**Last Updated**: January 2026
**Status**: Ready for Implementation

---

## 📋 Quick Start

**Goal**: Move myAdmin from local machine to Railway production

**Current Status**: ✅ Authentication & multi-tenancy implemented (AWS Cognito)

**Cost**: ~$5/month (~€5/month)

**Time**: 3-5 days

---

## 🎯 Critical Decisions (MADE)

### ✅ Decision 1: Credentials Management

**Decision**: Railway for generic secrets, MySQL for tenant-specific secrets

**Local Development**:

```
backend/.env → All secrets (DB, API keys, AWS, Cognito)
frontend/.env → Only REACT_APP_API_URL (NO secrets!)
```

**Railway Production**:

```
Railway Env Vars → Generic secrets (DB password, API keys, encryption key)
MySQL Database → Tenant secrets (encrypted Google Drive credentials)
```

**Why**: $0 cost, zero downtime for tenant changes, unlimited scalability

**Implementation**: 6-8 hours (see Implementation Plan below)

---

### ✅ Decision 2: Template Storage & Management

**Decision**: MySQL metadata + tenant-owned storage

**Structure**:

- **MySQL**: Template metadata (location, type, field mappings)
- **Storage**: Templates stored in tenant's Google Drive
- **Management**: Tenant Administrator via Tenant Admin Module

**Database Tables**:

```sql
tenant_template_config (
    tenant_id, template_type, template_file_id,
    field_mappings, is_active
)
```

**Template Types** (all XML with field mappings):

- Financial reports (template: XML → output: Excel)
- STR invoices (template: XML → output: HTML with logo)
- BTW Aangifte (template: XML → output: XML)
- Toeristenbelasting (template: XML → output: XML)
- IB Aangifte (template: XML → output: XML)

**Why**: Flexible, tenant-controlled, supports custom field mappings

---

### ✅ Decision 3: File Storage Strategy

**Decision**: Tenant-owned storage with myAdmin system tenant

**Principles**:

1. Data storage on storage owned/managed by tenant
2. Generic templates stored centrally in myAdmin tenant
3. No OneDrive dependency

**Storage Options**:

- **Current tenants**: Google Drive
- **New tenants**: Google Drive (default) or AWS S3 (optional)

**Folder Structure**:

**myAdmin Tenant** (System):

```
myAdmin Google Drive/
├── Generic Templates/
│   ├── default_invoice.html
│   ├── default_financial_report.xlsx
│   └── default_str_invoice.html
├── Email Templates/
│   ├── password_recovery.html
│   └── invoice_delivery.html
└── Platform Assets/
    ├── Logos/
    └── Branding/
```

**Client Tenants** (GoodwinSolutions, PeterPrive, etc.):

```
Tenant Google Drive/
├── Templates/
│   ├── financial_report.xlsx (migrated from OneDrive)
│   ├── str_invoice.html
│   ├── btw_aangifte.xml (migrated from hardcoded)
│   ├── toeristenbelasting.xml (migrated from hardcoded)
│   └── ib_aangifte.xml (migrated from hardcoded)
├── Invoices/
└── Reports/
```

**Migration Actions**:

- ✅ Create myAdmin system tenant with Google Drive
- ✅ Migrate OneDrive templates to tenant Google Drive
- ✅ Convert hardcoded tax forms to XML templates
- ✅ Remove OneDrive mount dependency

**Why**: Tenant data sovereignty, scalable, clear separation

---

### ✅ Decision 4: myAdmin System Tenant

**Decision**: Create myAdmin tenant for platform management

**Purpose**:

- Store generic templates
- Platform assets (logos, branding)
- Email templates
- myAdmin invoicing (invoice your clients)
- Cognito management (tenants and roles)
- Other SysAdmin tasks

**Access**: SysAdmin only

**Storage**: Own Google Drive with separate credentials

**Modules**:

- Tenant Admin Module (access to own tenant admin features)
- Cognito Management
- Platform Configuration

**Why**: Clear separation of platform vs client data, professional invoicing

---

### ✅ Decision 5: Tenant Admin Module

**Decision**: Build Tenant Admin Module for tenant-specific management

**Features**:

1. **Tenant Credentials Management**
   - Google Drive credentials
   - AWS S3 credentials (if applicable)
   - Other storage credentials

2. **User & Role Allocation**
   - Manage tenant users
   - Assign roles within tenant
   - View user activity

3. **Storage Configuration**
   - Configure folder IDs
   - Set storage type (Google Drive/S3)
   - Manage storage quotas

4. **Template Management**
   - Upload/update templates
   - Configure field mappings
   - Preview templates
   - Activate/deactivate templates
   - Support for logos/images

**Access**:

- **Tenant Administrators**:
  - ✅ Full access to their own tenant only
  - ✅ Create/manage users within their tenant
  - ✅ Assign users to their tenant
  - ✅ Assign roles to users (from available roles)
  - ✅ Manage tenant credentials, templates, storage
- **SysAdmin**:
  - ✅ Access to myAdmin tenant (platform management)
  - ✅ Tenants: Create, Read, Update, Delete
  - ✅ Roles: Create, Read, Update, Delete (Cognito groups)
  - ✅ Tenant-Role Allocation: Define which roles are available per tenant
  - ✅ View users (for troubleshooting only)
  - ❌ NO access to tenant data (invoices, reports, templates)
  - ❌ NO access to tenant credentials (encrypted, tenant-managed)
  - ❌ NO user creation (tenant administrators do this)
  - ❌ NO user-tenant assignment (tenant administrators do this)

**Why**: Self-service for tenants, data privacy, clear separation of responsibilities

---

### ✅ Decision 6: User Access Control

**Decision**: Tenant Administrator creates user accounts and sends invitations

**Fact**: Tenant Administrator creates user in Cognito, assigns tenant + role, and sends invitation email. User logs in with pre-configured access.

**Why**: Full tenant control, no approval workflow needed, secure by default

---

## 🏗️ Architecture Summary

### System Components

**Frontend (React)**

- Hosted on Railway
- Communicates with Backend API
- Uses AWS Cognito for authentication
- Tenant selection for multi-tenant access

**Backend (Python/Flask)**

- Hosted on Railway
- Reads generic secrets from Railway environment variables
- Reads tenant secrets from MySQL (encrypted)
- Manages all business logic and API endpoints

**Database (MySQL)**

- Hosted on Railway
- Stores all application data
- Stores encrypted tenant credentials
- Stores template metadata and field mappings

**Storage (Google Drive / S3)**

- Tenant-owned storage
- Templates, invoices, reports, logos
- Accessed via tenant-specific credentials from MySQL

**Authentication (AWS Cognito)**

- User management and authentication
- Role-based access control (RBAC)
- Tenant-role allocation

**Notifications (AWS SNS)**

- Email notifications
- System alerts

### Data Flow

**User Login:**

```
User logs in → Cognito authenticates → Backend validates token →
Frontend loads with tenant list in header → User switches tenant from dropdown → Access granted
```

**Template Processing:**

```
User requests report → Backend reads template metadata from MySQL →
Fetches XML template from tenant's Google Drive → Applies field mappings →
Generates output (HTML/Excel/XML) → User chooses:
  - Store in tenant's Google Drive (default)
  - Download to local device
```

**Credentials Access:**

```
Backend needs tenant credentials → Reads from MySQL tenant_credentials table →
Decrypts using CREDENTIALS_ENCRYPTION_KEY from Railway env → Uses credentials
```

### Security Model

**Generic Secrets** (Railway Environment Variables):

- Database password
- API keys (OpenRouter, etc.)
- AWS credentials (Cognito, SNS)
- Encryption key for tenant credentials

**Tenant Secrets** (MySQL Encrypted):

- Google Drive credentials per tenant
- S3 credentials per tenant (if applicable)
- Encrypted with AES-256 using key from Railway

**Access Control**:

- SysAdmin: Platform management, no tenant data access
- Tenant Administrator: Full control of their tenant only
- Users: Access based on assigned roles within tenant

### Tenant Structure

**myAdmin Tenant** (System):

- Generic templates for all tenants
- Platform assets and branding
- Email templates
- SysAdmin access only

**Client Tenants** (GoodwinSolutions, PeterPrive, etc.):

- Tenant-specific templates with field mappings
- Tenant data (invoices, reports, transactions)
- Tenant credentials (encrypted)
- Tenant Administrator + assigned users

---

## 💰 Cost Breakdown

| Item        | Cost          | Notes                         |
| ----------- | ------------- | ----------------------------- |
| Railway     | $5/month      | Minimum (includes $5 credits) |
| AWS SNS     | €0.50/month   | Email notifications           |
| AWS Cognito | €0            | Free tier                     |
| **Total**   | **~€5/month** | **~€60/year**                 |

**Savings**: No more 24/7 computer electricity (~€5-10/month)

---

## 🎓 How It Works

### Local Development (Unchanged)

```
1. docker-compose up
2. Backend reads backend/.env
3. Frontend reads frontend/.env
4. MySQL runs in Docker
```

### Railway Production

```
1. git push origin main
2. Railway auto-deploys
3. Backend reads Railway env vars
4. MySQL managed by Railway
```

**No code changes needed!** `os.getenv()` works in both environments.

---

## 📚 Supporting Documents

**Read These in Order**:

1. **This file** - Master plan (you are here)
2. `TASKS.md` - Implementation tasks (to be created)
3. `OPEN_ISSUES.md` - All issues resolved (reference only)

**Archived** (old analysis files, not needed):

- `archive/Impact Analysis.md` - Original 2500-line analysis
- `archive/TENANT_SPECIFIC_GOOGLE_DRIVE.md` - Options analysis (decision made)
- `archive/CREDENTIALS_FILE_STRUCTURE.md` - Old file structure (cleaned up)

---

## 🆘 Quick Help

**Confused about architecture?**
→ See "Architecture Summary" section above

**Need implementation tasks?**
→ See `TASKS.md` (to be created)

**Have questions?**
→ See `OPEN_ISSUES.md` (all resolved)

**Want to see old analysis?**
→ See `archive/` folder (not needed for implementation)
