# Google Drive Token Monitoring System

## Quick Start

### 1. Setup Automated Monitoring (Recommended)

```powershell
# Run this once to set up daily health checks
.\scripts\setup_token_monitoring.ps1
```

This creates a Windows scheduled task that runs daily at 9 AM.

### 2. Manual Health Check

```bash
# Check token health anytime
python backend/check_google_token_health.py
```

### 3. Emergency Token Refresh

```bash
# If tokens are expired or folders don't load
python backend/refresh_google_token.py
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
docker-compose restart backend
```

## Files Overview

| File                                       | Purpose                                            |
| ------------------------------------------ | -------------------------------------------------- |
| `check_google_token_health.py`             | Health check script - monitors token expiry        |
| `refresh_google_token.py`                  | Token refresh script - gets new tokens from Google |
| `GOOGLE_DRIVE_TOKEN_MANAGEMENT.md`         | Complete documentation and troubleshooting guide   |
| `../GOOGLE_DRIVE_TOKEN_QUICK_REFERENCE.md` | Quick reference card for operations team           |
| `../scripts/setup_token_monitoring.ps1`    | Setup script for automated monitoring              |

## How It Works

### Token Lifecycle

```
1. OAuth Flow (Initial Setup)
   ↓
2. Access Token (1 hour) + Refresh Token (long-lived)
   ↓
3. Access Token Expires → Auto-refresh using Refresh Token
   ↓
4. Refresh Token Expires → Manual re-authentication required
```

### Prevention System

```
Daily Health Check (9 AM)
   ↓
Check Token Expiry
   ↓
If expires in < 7 days → Warning
   ↓
If expired → Alert + Recovery Steps
```

## Monitoring Schedule

| Task                   | Frequency               | Method                  |
| ---------------------- | ----------------------- | ----------------------- |
| Automated health check | Daily at 9 AM           | Scheduled task          |
| Manual verification    | Weekly                  | Run health check script |
| Proactive refresh      | When warned (< 7 days)  | Run refresh script      |
| Emergency fix          | When folders don't load | Run emergency procedure |

## What Gets Monitored

✅ Token expiry dates (file and database)  
✅ Token validity for all tenants  
✅ Credential presence in database  
✅ Warning for tokens expiring within 7 days

## Alerts and Warnings

### ✅ Healthy

- Token valid for > 7 days
- No action needed

### ⚠️ Warning

- Token expires in ≤ 7 days
- **Action:** Refresh token proactively

### ❌ Critical

- Token expired
- **Action:** Run emergency fix immediately

## Integration with Application

The `GoogleDriveService` class automatically:

1. Attempts to refresh expired tokens
2. Logs detailed error messages
3. Provides recovery instructions
4. Falls back to local folders if Google Drive fails

## Troubleshooting

### Health check shows errors

```bash
# View detailed logs
docker-compose logs backend --tail 100

# Check token file
cat backend/token.json

# Verify database connection
python -c "from database import DatabaseManager; db = DatabaseManager(); print('✅ Connected')"
```

### Scheduled task not running

```powershell
# Check task status
Get-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck"

# View task history
Get-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck" | Get-ScheduledTaskInfo

# Run manually
Start-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck"
```

### Token refresh fails

1. Check internet connection
2. Verify `backend/credentials.json` exists
3. Ensure Google Account access not revoked
4. Check Google Cloud Console for API status

## Best Practices

1. **Set up automated monitoring** - Don't rely on manual checks
2. **Act on warnings** - Refresh tokens when you see 7-day warning
3. **Test recovery procedures** - Practice the emergency fix
4. **Monitor logs** - Check backend logs regularly
5. **Document incidents** - Note when and why tokens expired

## Support

For issues or questions:

1. Check `GOOGLE_DRIVE_TOKEN_MANAGEMENT.md` for detailed guide
2. Check `../GOOGLE_DRIVE_TOKEN_QUICK_REFERENCE.md` for quick fixes
3. Review backend logs for error details
4. Contact system administrator if issues persist

## Maintenance

### Weekly

- [ ] Run health check manually
- [ ] Review backend logs for auth errors

### Monthly

- [ ] Verify scheduled task is running
- [ ] Test token refresh procedure
- [ ] Review token expiry dates

### Quarterly

- [ ] Review and update documentation
- [ ] Test full recovery procedure
- [ ] Verify backup credentials exist

---

**Setup Date:** February 2, 2026  
**Last Updated:** February 2, 2026  
**Maintained By:** System Administrator
