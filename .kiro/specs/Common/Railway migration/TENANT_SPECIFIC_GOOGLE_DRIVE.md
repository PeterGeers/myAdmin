# Tenant-Specific Google Drive Integration

## Problem

Currently, Google Drive integration uses a single set of credentials (`credentials.json` and `token.json`) for all tenants. This is problematic because:

1. Each tenant should have their own Google Drive folders
2. Different tenants may use different Google accounts
3. Security: One tenant shouldn't access another tenant's Drive
4. Railway deployment: Single credentials don't scale for multi-tenant

## Current Implementation

```python
# backend/src/google_drive_service.py
credentials_path = '/app/credentials.json'  # Single file for all tenants
token_path = '/app/token.json'              # Single token for all tenants
```

## Proposed Solutions

### Option 1: Database-Stored Credentials (Recommended)

Store encrypted Google Drive credentials per tenant in the database.

**Pros:**
- Fully multi-tenant
- No file system dependencies
- Easy to manage via UI
- Works perfectly on Railway

**Cons:**
- Requires encryption/decryption
- More complex implementation

**Implementation:**

```sql
-- Add to database schema
CREATE TABLE tenant_google_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_name VARCHAR(100) NOT NULL UNIQUE,
    credentials_json TEXT NOT NULL,  -- Encrypted
    token_json TEXT,                 -- Encrypted
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tenant (tenant_name)
);
```

```python
# backend/src/google_drive_service.py
class GoogleDriveService:
    def __init__(self, tenant_name):
        self.tenant_name = tenant_name
        self.service = self._authenticate()
    
    def _authenticate(self):
        # Get credentials from database
        creds_data = self._get_tenant_credentials(self.tenant_name)
        
        if not creds_data:
            raise Exception(f"No Google Drive credentials for tenant: {self.tenant_name}")
        
        # Decrypt and use credentials
        credentials_json = decrypt(creds_data['credentials_json'])
        token_json = decrypt(creds_data['token_json']) if creds_data['token_json'] else None
        
        # ... rest of authentication logic
```

**Admin UI:**
- Add "Google Drive Settings" to Tenant Management
- Upload credentials.json per tenant
- OAuth flow per tenant
- Store encrypted in database

---

### Option 2: Environment Variables per Tenant

Use Railway environment variables with tenant prefixes.

**Pros:**
- Simple implementation
- Uses Railway's secret management
- No database changes needed

**Cons:**
- Limited scalability (max ~50 tenants)
- Manual configuration per tenant
- Harder to manage

**Implementation:**

```bash
# Railway environment variables
TENANT_PETERPRIVE_GOOGLE_CREDENTIALS={"type":"service_account",...}
TENANT_PETERPRIVE_GOOGLE_TOKEN={"token":"..."}
TENANT_GOODWIN_GOOGLE_CREDENTIALS={"type":"service_account",...}
TENANT_GOODWIN_GOOGLE_TOKEN={"token":"..."}
```

```python
def _authenticate(self):
    tenant_key = self.tenant_name.upper().replace(' ', '_')
    credentials_env = f"TENANT_{tenant_key}_GOOGLE_CREDENTIALS"
    token_env = f"TENANT_{tenant_key}_GOOGLE_TOKEN"
    
    credentials_json = os.getenv(credentials_env)
    token_json = os.getenv(token_env)
    
    if not credentials_json:
        raise Exception(f"No credentials for tenant: {self.tenant_name}")
    
    # Parse and use credentials
```

---

### Option 3: Service Account per Tenant

Use Google Service Accounts instead of OAuth tokens.

**Pros:**
- No token refresh needed
- More secure
- Better for automation
- Can be stored as environment variables

**Cons:**
- Requires Google Workspace admin setup
- Each tenant needs service account
- More complex initial setup

**Implementation:**

```python
from google.oauth2 import service_account

def _authenticate(self):
    # Get service account JSON from database or env var
    service_account_info = self._get_tenant_service_account(self.tenant_name)
    
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES
    )
    
    return build('drive', 'v3', credentials=credentials)
```

---

### Option 4: Hybrid Approach (Best for Railway)

Combine database storage with Railway secrets for encryption keys.

**Implementation:**

1. **Database**: Store encrypted credentials per tenant
2. **Railway Secret**: Single encryption key (`GOOGLE_CREDS_ENCRYPTION_KEY`)
3. **Admin UI**: Manage credentials per tenant
4. **Fallback**: Environment variables for initial setup

```python
class GoogleDriveService:
    def __init__(self, tenant_name):
        self.tenant_name = tenant_name
        self.service = self._authenticate()
    
    def _authenticate(self):
        # Try database first
        creds = self._get_from_database(self.tenant_name)
        
        if not creds:
            # Fallback to environment variables
            creds = self._get_from_env(self.tenant_name)
        
        if not creds:
            raise Exception(f"No Google Drive credentials for: {self.tenant_name}")
        
        return self._build_service(creds)
    
    def _get_from_database(self, tenant_name):
        # Query database for encrypted credentials
        # Decrypt using GOOGLE_CREDS_ENCRYPTION_KEY from Railway
        pass
    
    def _get_from_env(self, tenant_name):
        # Fallback to environment variables
        tenant_key = tenant_name.upper().replace(' ', '_')
        return os.getenv(f"TENANT_{tenant_key}_GOOGLE_CREDENTIALS")
```

---

## Recommended Solution

**Use Option 4: Hybrid Approach**

### Phase 1: Quick Fix for Railway (Environment Variables)
- Use environment variables per tenant
- Works immediately on Railway
- No code changes to database

```bash
# Railway secrets
TENANT_PETERPRIVE_GOOGLE_CREDENTIALS=<json>
TENANT_PETERPRIVE_GOOGLE_TOKEN=<json>
TENANT_GOODWIN_GOOGLE_CREDENTIALS=<json>
TENANT_GOODWIN_GOOGLE_TOKEN=<json>
```

### Phase 2: Long-term Solution (Database + Encryption)
- Add database table for tenant credentials
- Build admin UI for credential management
- Encrypt credentials with Railway secret key
- Migrate from environment variables to database

---

## Migration Steps

### Step 1: Update GoogleDriveService to accept tenant_name

```python
# Before
drive_service = GoogleDriveService()

# After
drive_service = GoogleDriveService(tenant_name=current_tenant)
```

### Step 2: Update all routes that use Google Drive

```python
@app.route('/api/invoices/upload')
@cognito_required()
def upload_invoice(user_email, user_roles, user_tenants):
    current_tenant = get_current_tenant(user_tenants)
    drive_service = GoogleDriveService(tenant_name=current_tenant)
    # ... rest of code
```

### Step 3: Configure Railway secrets

For each tenant, add:
```bash
TENANT_<NAME>_GOOGLE_CREDENTIALS
TENANT_<NAME>_GOOGLE_TOKEN
TENANT_<NAME>_FACTUREN_FOLDER_ID
```

### Step 4: (Future) Build Admin UI

Add to Tenant Management:
- Upload Google credentials per tenant
- OAuth flow per tenant
- Test connection
- View/revoke access

---

## Security Considerations

1. **Encryption**: Always encrypt credentials in database
2. **Access Control**: Only SysAdmin can manage credentials
3. **Audit Log**: Track who accesses/modifies credentials
4. **Token Refresh**: Handle token expiration gracefully
5. **Fallback**: Graceful degradation if Drive unavailable

---

## Testing Strategy

1. **Unit Tests**: Mock Google Drive API per tenant
2. **Integration Tests**: Test with test Google accounts
3. **Manual Testing**: Verify each tenant accesses only their folders
4. **Security Testing**: Attempt cross-tenant access

---

## Impact on Railway Migration

**Before this fix:**
- Risk: HIGH (single credentials for all tenants)
- Complexity: HIGH (manual configuration per deployment)

**After this fix:**
- Risk: LOW (proper multi-tenant isolation)
- Complexity: MEDIUM (environment variables per tenant)

**Future (with database storage):**
- Risk: LOW (encrypted, managed via UI)
- Complexity: LOW (self-service tenant setup)

---

## Related Files

- `backend/src/google_drive_service.py` - Main service file
- `backend/src/invoice_routes.py` - Uses Google Drive
- `.env` - Current credentials location
- `docker-compose.yml` - Mounts credentials files

---

## Next Steps

1. ✅ Document the problem and solutions
2. ⬜ Implement Phase 1 (environment variables)
3. ⬜ Update all routes to pass tenant_name
4. ⬜ Test with multiple tenants
5. ⬜ Plan Phase 2 (database storage)
6. ⬜ Build admin UI for credential management
