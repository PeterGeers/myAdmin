# Services Package

This package contains business logic services for the myAdmin application.

## CredentialService

The `CredentialService` provides secure storage and retrieval of tenant-specific credentials using AES-256 encryption.

### Features

- **Encryption**: AES-256 encryption using Fernet (symmetric encryption)
- **Key Derivation**: PBKDF2-HMAC-SHA256 with 100,000 iterations
- **Multi-tenant**: Isolated credential storage per tenant
- **Flexible Storage**: Supports strings, dictionaries, and JSON-serializable objects
- **CRUD Operations**: Complete create, read, update, delete functionality

### Setup

1. **Install Dependencies**:

   ```bash
   pip install cryptography==41.0.7
   ```

2. **Create Database Table**:

   ```sql
   CREATE TABLE tenant_credentials (
       id INT AUTO_INCREMENT PRIMARY KEY,
       tenant_id VARCHAR(100) NOT NULL,
       credential_type VARCHAR(50) NOT NULL,
       encrypted_value TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
       UNIQUE KEY unique_tenant_cred (tenant_id, credential_type),
       INDEX idx_tenant (tenant_id)
   );
   ```

3. **Set Encryption Key**:

   ```bash
   # In .env file
   CREDENTIALS_ENCRYPTION_KEY=your_secure_encryption_key_here
   ```

   Or generate a secure key:

   ```python
   import secrets
   key = secrets.token_urlsafe(32)
   print(f"CREDENTIALS_ENCRYPTION_KEY={key}")
   ```

### Usage

#### Basic Usage

```python
from database import DatabaseManager
from services.credential_service import CredentialService

# Initialize
db = DatabaseManager()
service = CredentialService(db)

# Store credentials
google_creds = {
    "client_id": "123.apps.googleusercontent.com",
    "client_secret": "secret_key",
    "refresh_token": "refresh_token_value"
}
service.store_credential("GoodwinSolutions", "google_drive", google_creds)

# Retrieve credentials
creds = service.get_credential("GoodwinSolutions", "google_drive")
print(creds["client_id"])  # 123.apps.googleusercontent.com

# List all credential types for a tenant
credentials = service.list_credential_types("GoodwinSolutions")
for cred in credentials:
    print(f"{cred['type']} - created: {cred['created_at']}")

# Check if credential exists
exists = service.credential_exists("GoodwinSolutions", "google_drive")

# Delete credential
service.delete_credential("GoodwinSolutions", "google_drive")
```

#### Storing Different Types

```python
# String credential (API key)
service.store_credential("tenant1", "api_key", "sk_live_123456789")

# Dictionary credential (OAuth)
oauth_creds = {
    "access_token": "ya29.xxx",
    "refresh_token": "1//xxx",
    "expires_in": 3599
}
service.store_credential("tenant1", "oauth", oauth_creds)

# Complex nested object
service_account = {
    "type": "service_account",
    "project_id": "my-project",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "service@project.iam.gserviceaccount.com"
}
service.store_credential("tenant1", "service_account", service_account)
```

#### Error Handling

```python
try:
    creds = service.get_credential("tenant1", "google_drive")
    if creds is None:
        print("Credentials not found")
except Exception as e:
    print(f"Error retrieving credentials: {e}")
```

### API Reference

#### `__init__(db_manager, encryption_key=None)`

Initialize the credential service.

- `db_manager`: DatabaseManager instance
- `encryption_key`: Optional encryption key (reads from env if not provided)

#### `encrypt_credential(value) -> str`

Encrypt a credential value.

- `value`: String, dict, or JSON-serializable object
- Returns: Base64-encoded encrypted string

#### `decrypt_credential(encrypted_value) -> Any`

Decrypt an encrypted credential.

- `encrypted_value`: Base64-encoded encrypted string
- Returns: Decrypted value (string or dict)

#### `store_credential(tenant_id, credential_type, value) -> bool`

Store or update a credential.

- `tenant_id`: Tenant identifier
- `credential_type`: Type of credential (e.g., 'google_drive', 's3')
- `value`: Credential value to store
- Returns: True if successful

#### `get_credential(tenant_id, credential_type) -> Optional[Any]`

Retrieve a credential.

- `tenant_id`: Tenant identifier
- `credential_type`: Type of credential
- Returns: Decrypted credential or None if not found

#### `delete_credential(tenant_id, credential_type) -> bool`

Delete a credential.

- `tenant_id`: Tenant identifier
- `credential_type`: Type of credential
- Returns: True if deleted, False if not found

#### `list_credential_types(tenant_id) -> list`

List all credential types for a tenant.

- `tenant_id`: Tenant identifier
- Returns: List of dicts with 'type', 'created_at', 'updated_at'

#### `credential_exists(tenant_id, credential_type) -> bool`

Check if a credential exists.

- `tenant_id`: Tenant identifier
- `credential_type`: Type of credential
- Returns: True if exists, False otherwise

### Security Considerations

1. **Encryption Key**: Store the encryption key securely in environment variables, never in code
2. **Key Rotation**: If you need to rotate the encryption key, decrypt all credentials with the old key and re-encrypt with the new key
3. **Access Control**: Ensure only authorized services can access the CredentialService
4. **Tenant Isolation**: The service enforces tenant isolation - credentials are never shared between tenants
5. **Logging**: Credential values are never logged, only metadata (tenant_id, credential_type)

### Testing

Run unit tests:

```bash
pytest tests/test_credential_service.py -v
```

Run integration tests (requires database):

```bash
pytest tests/test_credential_service_integration.py -v -m integration
```

Run example script:

```bash
python src/services/credential_service_example.py
```

### Migration from File-Based Credentials

To migrate existing file-based credentials (e.g., `credentials.json`, `token.json`):

```python
import json
from database import DatabaseManager
from services.credential_service import CredentialService

# Initialize service
db = DatabaseManager()
service = CredentialService(db)

# Read existing credentials
with open('credentials.json', 'r') as f:
    google_creds = json.load(f)

with open('token.json', 'r') as f:
    google_token = json.load(f)

# Store in database
service.store_credential("GoodwinSolutions", "google_drive_credentials", google_creds)
service.store_credential("GoodwinSolutions", "google_drive_token", google_token)

# Verify
retrieved = service.get_credential("GoodwinSolutions", "google_drive_credentials")
print("Migration successful!" if retrieved else "Migration failed!")
```

### Railway Deployment

For Railway deployment:

1. Set the encryption key in Railway environment variables:

   ```
   CREDENTIALS_ENCRYPTION_KEY=your_secure_key_here
   ```

2. Ensure the `tenant_credentials` table exists in the Railway MySQL database

3. The service will automatically use the Railway environment variables

### Troubleshooting

**Error: "Encryption key not found"**

- Solution: Set `CREDENTIALS_ENCRYPTION_KEY` in your `.env` file or environment variables

**Error: "Failed to decrypt credential"**

- Solution: Ensure you're using the same encryption key that was used to encrypt the data

**Error: "Table 'tenant_credentials' doesn't exist"**

- Solution: Run the CREATE TABLE statement to create the table

**Credentials not found**

- Solution: Verify the tenant_id and credential_type are correct
- Check if the credential was actually stored using `credential_exists()`

### Future Enhancements

- [ ] Key rotation support
- [ ] Credential versioning
- [ ] Audit logging for credential access
- [ ] Automatic credential expiration
- [ ] Support for credential metadata (tags, descriptions)
