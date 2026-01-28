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

### ✅ Credentials Management

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

## ⏸️ Pending Decisions

### 1. Template Storage (STR Invoices)

**Options**: Database | Railway Volumes | Google Drive
**Impact**: MEDIUM
**Needed By**: Before Railway migration

### 2. File Storage (Reports/Uploads)

**Options**: Railway Volumes | S3 | Google Cloud Storage  
**Impact**: MEDIUM
**Needed By**: Before Railway migration

---

## 🚀 Implementation Plan

### Phase 1: Credentials Setup (Day 1)

**1.1 Generate Encryption Key**

```bash
python scripts/generate_encryption_key.py
# Output: CREDENTIALS_ENCRYPTION_KEY=...
```

**1.2 Create Database Table**

```sql
CREATE TABLE tenant_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_cred (tenant_id, credential_type)
);
```

**1.3 Implement Encryption Service**

- Create `backend/src/services/credential_service.py`
- Methods: `store_credential()`, `get_credential()`, `delete_credential()`

**1.4 Update GoogleDriveService**

- Change `__init__()` to accept `tenant_id`
- Read credentials from database instead of files

**1.5 Migrate Existing Credentials**

```bash
python scripts/migrate_credentials_to_db.py
```

**1.6 Test Locally**

```bash
docker-compose up
# Test Google Drive access for both tenants
```

### Phase 2: Railway Setup (Day 2)

**2.1 Create Railway Account**

- Sign up at railway.app
- Create new project "myadmin-production"

**2.2 Create MySQL Database**

- Add MySQL service in Railway
- Note connection details

**2.3 Configure Environment Variables**

```bash
# In Railway dashboard, add:
DB_HOST=<railway-mysql-host>
DB_PASSWORD=<railway-generated>
OPENROUTER_API_KEY=<your-key>
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
COGNITO_CLIENT_SECRET=<your-secret>
CREDENTIALS_ENCRYPTION_KEY=<generated-key>
```

**2.4 Import Database**

```bash
# Export local
mysqldump finance > production_backup.sql

# Import to Railway
mysql -h <railway-host> -u root -p railway < production_backup.sql
```

### Phase 3: Deploy Application (Day 3)

**3.1 Connect GitHub**

- Link Railway to your GitHub repo
- Set deploy branch to `main`

**3.2 Configure Build**

- Railway auto-detects Dockerfile
- Verify build settings

**3.3 Deploy**

- Push to main branch
- Railway auto-deploys

**3.4 Test**

- Test all endpoints
- Verify Google Drive access
- Check tenant isolation

### Phase 4: Go Live (Day 4)

**4.1 Update DNS**

```
admin.pgeers.nl → Railway URL
```

**4.2 Monitor**

- Check Railway logs
- Verify all features working

**4.3 Backup**

- Keep local database for 1 week

---

## 📁 File Cleanup (Before Migration)

### Delete These Files:

```
❌ backend/data/credentials.json (duplicate)
❌ backend/data/token.json (duplicate)
```

### Clean Up frontend/.env:

```bash
# REMOVE all backend secrets, keep only:
REACT_APP_API_URL=http://localhost:5000
```

### Keep These Files:

```
✅ backend/.env (all secrets for local dev)
✅ backend/credentials.json (until migrated to DB)
✅ backend/token.json (until migrated to DB)
```

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
2. `CREDENTIALS_IMPLEMENTATION.md` - Detailed code examples
3. `OPEN_ISSUES.md` - Track pending decisions

**Reference Only** (don't read unless needed):

- `Impact Analysis.md` - Full 2500-line analysis
- `TENANT_SPECIFIC_GOOGLE_DRIVE.md` - Options analysis
- `CREDENTIALS_FILE_STRUCTURE.md` - Current file locations

---

## ✅ Checklist

### Before Starting

- [ ] Read this master plan
- [ ] Decide on template storage
- [ ] Decide on file storage
- [ ] Backup current database

### Phase 1 (Credentials)

- [ ] Generate encryption key
- [ ] Create database table
- [ ] Implement CredentialService
- [ ] Update GoogleDriveService
- [ ] Migrate credentials
- [ ] Test locally

### Phase 2 (Railway Setup)

- [ ] Create Railway account
- [ ] Create MySQL database
- [ ] Configure env vars
- [ ] Import database

### Phase 3 (Deploy)

- [ ] Connect GitHub
- [ ] Deploy application
- [ ] Test all features

### Phase 4 (Go Live)

- [ ] Update DNS
- [ ] Monitor production
- [ ] Verify everything works

---

## 🆘 Quick Help

**Confused about credentials?**
→ See "How It Works" section above

**Need code examples?**
→ See `CREDENTIALS_IMPLEMENTATION.md`

**Have questions?**
→ See `OPEN_ISSUES.md`

**Want full details?**
→ See `Impact Analysis.md` (warning: 2500 lines)
