# Google Drive Token - Quick Reference Card

## 🚨 Emergency Fix (When Folders Don't Load)

If Google Drive folders are not showing in the UI:

```bash
# 1. Refresh the token
python backend/refresh_google_token.py

# 2. Update database
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions

# 3. Restart backend
docker-compose restart backend
```

**Time to fix: ~2 minutes**

---

## 🔍 Check Token Health

```bash
python backend/check_google_token_health.py
```

**Run this weekly or when you see authentication errors**

---

## 📅 Setup Automated Monitoring (One-time)

```powershell
.\scripts\setup_token_monitoring.ps1
```

This creates a daily scheduled task that checks token health automatically.

---

## 🎯 Common Scenarios

### Scenario 1: "No folders showing in dropdown"

**Symptoms:**

- Upload Invoices → Select folder shows no Google Drive folders
- Backend logs show "invalid_grant" error

**Fix:**

```bash
python backend/refresh_google_token.py
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
docker-compose restart backend
```

---

### Scenario 2: "Token expires in X days" warning

**Symptoms:**

- Health check shows warning about upcoming expiry

**Fix (Proactive):**

```bash
python backend/refresh_google_token.py
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
docker-compose restart backend
```

---

### Scenario 3: Multiple tenants affected

**Fix all tenants:**

```bash
# Refresh token (shared across tenants)
python backend/refresh_google_token.py

# Update each tenant
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
python scripts/credentials/migrate_credentials_to_db.py --tenant PeterPrive

# Restart backend
docker-compose restart backend
```

---

## 📊 Monitoring Commands

### Check if scheduled task is running

```powershell
Get-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck"
```

### Run health check manually

```powershell
Start-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck"
```

### View backend logs

```bash
docker-compose logs backend --tail 50
```

### Check for authentication errors

```bash
docker-compose logs backend | findstr "invalid_grant"
```

---

## 🛡️ Prevention Checklist

- [ ] Automated monitoring is set up (scheduled task)
- [ ] Health check runs weekly (manual or automated)
- [ ] Tokens are refreshed before expiry (7-day warning)
- [ ] Recovery procedures are documented
- [ ] Team knows how to run emergency fix

---

## 📞 When to Escalate

Contact system administrator if:

1. Token refresh fails repeatedly
2. OAuth flow doesn't open browser
3. "Credentials file not found" error
4. Multiple authentication errors in logs
5. Google Account access was revoked

---

## 🔗 Full Documentation

See `backend/GOOGLE_DRIVE_TOKEN_MANAGEMENT.md` for detailed information.

---

## 💡 Pro Tips

1. **Bookmark this page** for quick access during incidents
2. **Run health check on Mondays** to catch weekend issues
3. **Refresh tokens proactively** when you see 7-day warning
4. **Keep backend logs open** when testing fixes
5. **Test the emergency fix** in a non-critical time to familiarize yourself

---

**Last Updated:** February 2, 2026
