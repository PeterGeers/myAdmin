# Encryption Key Storage Requirements

## Overview

The `CREDENTIALS_ENCRYPTION_KEY` is used by the CredentialService to encrypt and decrypt tenant-specific credentials stored in the MySQL database. This document outlines the requirements and best practices for storing and managing this critical security key.

## Key Specifications

- **Algorithm**: AES-256 via Fernet (symmetric encryption)
- **Key Length**: 256 bits (32 bytes)
- **Format**: 64-character hexadecimal string
- **Derivation**: PBKDF2-HMAC-SHA256 with 100,000 iterations

## Storage Requirements

### Local Development

**Location**: `backend/.env` file

```env
CREDENTIALS_ENCRYPTION_KEY=<64-character-hex-string>
```

**Requirements**:
- ✅ Add `backend/.env` to `.gitignore` (should already be there)
- ✅ Never commit the key to version control
- ✅ Keep a secure backup of the key (password manager, encrypted file, etc.)
- ✅ Use a different key for each environment (dev, staging, production)

### Railway Production Deployment

**Location**: Railway Environment Variables

**Setup Steps**:
1. Log into Railway dashboard
2. Navigate to your project
3. Go to the "Variables" tab
4. Click "New Variable"
5. Add:
   - **Name**: `CREDENTIALS_ENCRYPTION_KEY`
   - **Value**: `<64-character-hex-string>`
6. Save and redeploy

**Requirements**:
- ✅ Use a different key than development
- ✅ Store a backup of the production key in a secure location
- ✅ Document who has access to the production key
- ✅ Implement key rotation procedures

### Staging/Testing Environments

**Location**: Environment-specific configuration

**Requirements**:
- ✅ Use a unique key for each environment
- ✅ Never use production keys in non-production environments
- ✅ Document which key is used in which environment

## Security Best Practices

### Key Generation

✅ **DO**:
- Use the provided `scripts/generate_encryption_key.py` script
- Generate keys using cryptographically secure random number generators
- Generate a new key for each environment

❌ **DON'T**:
- Use predictable or weak keys
- Reuse keys across environments
- Generate keys manually or with weak tools

### Key Storage

✅ **DO**:
- Store keys in environment variables or secure secrets managers
- Keep encrypted backups of keys in secure locations
- Use password managers for personal key backups
- Document key locations and access procedures

❌ **DON'T**:
- Commit keys to version control (Git, SVN, etc.)
- Store keys in plain text files in the repository
- Share keys via email or unencrypted messaging
- Store keys in application code or configuration files that are committed

### Key Access

✅ **DO**:
- Limit key access to authorized personnel only
- Use role-based access control for production keys
- Audit who has access to keys
- Revoke access when team members leave

❌ **DON'T**:
- Share keys publicly or in team chat
- Give everyone access to production keys
- Store keys in shared documents without encryption

### Key Rotation

✅ **DO**:
- Plan for periodic key rotation (e.g., every 6-12 months)
- Implement a key rotation procedure
- Test key rotation in non-production environments first
- Keep old keys temporarily for decrypting existing data

❌ **DON'T**:
- Rotate keys without a plan
- Delete old keys immediately (existing encrypted data needs them)
- Rotate keys during high-traffic periods

## Key Rotation Procedure

When rotating encryption keys:

1. **Generate New Key**:
   ```bash
   python scripts/generate_encryption_key.py
   ```

2. **Backup Current Key**:
   - Save the current key to a secure backup location
   - Document the rotation date and reason

3. **Decrypt Existing Credentials** (using old key):
   - Export all encrypted credentials from database
   - Decrypt using the old key

4. **Update Environment Variable**:
   - Set `CREDENTIALS_ENCRYPTION_KEY` to the new key
   - Restart the application

5. **Re-encrypt Credentials** (using new key):
   - Encrypt all credentials using the new key
   - Store back in database

6. **Verify**:
   - Test that all credentials can be retrieved
   - Verify tenant functionality (Google Drive access, etc.)

7. **Archive Old Key**:
   - Keep the old key in secure backup for 30 days
   - After verification period, securely delete old key

## Key Loss Recovery

### If Development Key is Lost

**Impact**: Cannot decrypt credentials in local database

**Recovery**:
1. Generate a new key using `scripts/generate_encryption_key.py`
2. Update `backend/.env` with new key
3. Re-run credential migration script to re-encrypt credentials
4. Test all functionality

### If Production Key is Lost

**Impact**: ⚠️ **CRITICAL** - Cannot decrypt any tenant credentials

**Recovery**:
1. **Immediate**: Application will fail to access encrypted credentials
2. **Required Actions**:
   - Generate new encryption key
   - Contact all tenants to re-upload their credentials
   - Re-encrypt all credentials with new key
   - Update Railway environment variables
   - Redeploy application

**Prevention**:
- ✅ Keep multiple secure backups of production key
- ✅ Store in password manager
- ✅ Store in company secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault)
- ✅ Document backup locations
- ✅ Test backup recovery procedures

## Environment-Specific Keys

### Development
- **Purpose**: Local development and testing
- **Storage**: `backend/.env`
- **Access**: Individual developers
- **Rotation**: As needed (low priority)

### Staging
- **Purpose**: Pre-production testing
- **Storage**: Staging environment variables
- **Access**: Development team
- **Rotation**: Every 6 months or after security incidents

### Production
- **Purpose**: Live tenant data
- **Storage**: Railway environment variables + secure backup
- **Access**: System administrators only
- **Rotation**: Every 6-12 months or after security incidents

## Compliance Considerations

### GDPR
- Encryption keys are considered "means of processing" under GDPR
- Must be protected with appropriate technical measures
- Key access should be logged and auditable

### Data Breach Response
- If key is compromised, consider it a data breach
- Rotate key immediately
- Notify affected tenants if required by regulations
- Document incident and response

## Troubleshooting

### Error: "Encryption key not found"
**Cause**: `CREDENTIALS_ENCRYPTION_KEY` not set in environment

**Solution**:
1. Check that key exists in `backend/.env` (local) or Railway variables (production)
2. Verify environment file is being loaded
3. Restart application after adding key

### Error: "Failed to decrypt credential"
**Cause**: Wrong encryption key or corrupted data

**Solution**:
1. Verify correct key is being used
2. Check if key was recently rotated
3. Verify database data integrity
4. If key is lost, follow key loss recovery procedure

### Error: "Invalid encryption key format"
**Cause**: Key is not 64 hex characters

**Solution**:
1. Regenerate key using `scripts/generate_encryption_key.py`
2. Verify key is exactly 64 characters
3. Ensure no extra spaces or newlines in key

## References

- **Credential Service**: `backend/src/services/credential_service.py`
- **Key Generation Script**: `scripts/generate_encryption_key.py`
- **Migration Plan**: `.kiro/specs/Common/Railway migration/IMPACT_ANALYSIS_SUMMARY.md`
- **Cryptography Library**: [Fernet (symmetric encryption)](https://cryptography.io/en/latest/fernet/)

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-01 | Initial documentation | System |

---

**Last Updated**: January 2026
