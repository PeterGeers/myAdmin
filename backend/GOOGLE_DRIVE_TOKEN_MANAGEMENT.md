# Google Drive Token Management Guide

## Overview

This guide explains how Google Drive OAuth tokens work and how to prevent token expiration issues.

## Understanding Google Drive Tokens

### Token Types

1. **OAuth Credentials (`credentials.json`)**
   - Contains client ID and client secret
   - Never expires
   - Used to generate access tokens

2. **Access Token**
   - Short-lived (typically 1 hour)
   - Used for API requests
   - Automatically refreshed using refresh token

3. **Refresh Token**
   - Long-lived (can last months or years)
   - Used to get new access tokens
   - Can expire or be revoked if:
     - Not used for 6 months (Google's policy)
     - User revokes access
     - Security concerns detected
     - OAuth credentials are regenerated

### Token Storage

- **File-based**: `backend/token.json` (local development)
- **Database**: `tenant_credentials` table (production, encrypted)

## Why Tokens Expire

1. **Inactivity**: Google revokes refresh tokens not used for 6 months
2. **Security**: User manually revokes access in Google Account settings
3. **Credential Changes**: OAuth credentials are regenerated
4. **Policy Changes**: Google updates security policies

## Prevention Strategy

### 1. Automated Token Health Monitoring

We've implemented a health check system that monitors token expiry:

```bash
# Check token health manually
python backend/check_google_token_health.py
```

**What it checks:**
- Token expiry dates
- Database token validity
- Warns if tokens expire within 7 days

### 2. Scheduled Monitoring (Recommended)

Set up automated daily checks:

```powershell
# Windows: Setup scheduled task
.\scripts\setup_token_monitoring.ps1
```

This creates a Windows scheduled task that:
- Runs daily at 9:00 AM
- Checks all tenant tokens
- Alerts if tokens are expired or expiring soon

### 3. Improved Error Handling

The `GoogleDriveService` now:
- Automatically attempts to refresh expired tokens
- Provides clear error messages with recovery steps
- Logs detailed information for troubleshooting

### 4. Proactive Token Refresh

Refresh tokens before they expire:

```bash
# Refresh token manually
python backend/refresh_google_token.py

# Update database
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions

# Restart backend
docker-compose restart backend
```

## Recovery Procedures

### If Token Expires

1. **Refresh the token:**
   ```bash
   python backend/refresh_google_token.py
   ```

2. **Update database:**
   ```bash
   python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
   ```

3. **Restart backend:**
   ```bash
   docker-compose restart backend
   ```

### If Refresh Token is Invalid

If the refresh token itself is invalid (revoked or expired):

1. **Re-authenticate with Google:**
   ```bash
   python backend/refresh_google_token.py
   ```
   This will open a browser for OAuth flow.

2. **Follow the prompts** to grant access

3. **Update database and restart** (same as above)

## Best Practices

### For Development

1. **Check token health weekly:**
   ```bash
   python backend/check_google_token_health.py
   ```

2. **Keep tokens active** by using the application regularly

3. **Monitor logs** for authentication warnings

### For Production

1. **Enable scheduled monitoring** (daily checks)

2. **Set up alerts** for token expiration warnings

3. **Document recovery procedures** for operations team

4. **Keep backup credentials** in secure location

5. **Test token refresh** periodically (monthly)

## Monitoring Commands

### Check Current Token Status
```bash
# Check file token
python backend/check_google_token_health.py

# Check database tokens
python -c "
from database import DatabaseManager
from services.credential_service import CredentialService
db = DatabaseManager()
cs = CredentialService(db)
token = cs.get_credential('GoodwinSolutions', 'google_drive_token')
print(f'Token expiry: {token.get(\"expiry\") if token else \"Not found\"}')
"
```

### View Scheduled Task Status (Windows)
```powershell
Get-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck"
```

### Run Health Check Manually
```powershell
Start-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck"
```

## Troubleshooting

### Error: "invalid_grant: Bad Request"

**Cause**: Refresh token is invalid or expired

**Solution**:
```bash
python backend/refresh_google_token.py
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
docker-compose restart backend
```

### Error: "Token not found in database"

**Cause**: Credentials not migrated to database

**Solution**:
```bash
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
docker-compose restart backend
```

### Error: "Credentials file not found"

**Cause**: `backend/credentials.json` is missing

**Solution**:
1. Restore from backup
2. Or download new credentials from Google Cloud Console
3. Run OAuth flow to generate new token

## Security Notes

1. **Never commit tokens to git**
   - `token.json` is in `.gitignore`
   - Database tokens are encrypted

2. **Rotate credentials periodically**
   - Update OAuth credentials annually
   - Re-authenticate all tenants

3. **Monitor access logs**
   - Check for unauthorized access attempts
   - Review Google Account activity

4. **Backup credentials securely**
   - Store encrypted backups
   - Document recovery procedures

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Google Drive API Quickstart](https://developers.google.com/drive/api/quickstart/python)
- [Token Expiration Best Practices](https://developers.google.com/identity/protocols/oauth2#expiration)

## Support

If you encounter issues:

1. Check logs: `docker-compose logs backend --tail 100`
2. Run health check: `python backend/check_google_token_health.py`
3. Review this guide for recovery procedures
4. Contact system administrator if issues persist
