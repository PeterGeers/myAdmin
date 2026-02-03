# Google Drive Token Prevention - Setup Checklist

## ✅ Completed (Already Done)

- [x] Token refreshed and working
- [x] Error handling improved in `google_drive_service.py`
- [x] Health check script created (`backend/check_google_token_health.py`)
- [x] Token refresh script created (`backend/refresh_google_token.py`)
- [x] Automated monitoring script created (`scripts/setup_token_monitoring.ps1`)
- [x] API health endpoint added (`/api/google-drive/token-health`)
- [x] Documentation created (3 comprehensive guides)
- [x] Backend restarted with new changes

## 🔲 To Do (Next Steps)

### Step 1: Setup Automated Monitoring (5 minutes)

```powershell
# Run this command to create the scheduled task
.\scripts\setup_token_monitoring.ps1
```

**What it does:**
- Creates a Windows scheduled task
- Runs daily at 9:00 AM
- Checks token health automatically
- No manual intervention needed

**Verification:**
```powershell
# Check if task was created
Get-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck"
```

---

### Step 2: Test the Health Check (2 minutes)

```bash
# Run the health check manually
python backend/check_google_token_health.py
```

**Expected output:**
- Status for each tenant (GoodwinSolutions, PeterPrive)
- Days until token expiry
- Warnings if tokens expire soon
- Errors if tokens are expired

**Current status:**
- GoodwinSolutions: Token expires today (needs refresh)
- PeterPrive: Token already expired (needs refresh)

---

### Step 3: Refresh All Tenant Tokens (3 minutes)

Since both tenants need token refresh:

```bash
# 1. Refresh the token
python backend/refresh_google_token.py

# 2. Update GoodwinSolutions
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions

# 3. Update PeterPrive
python scripts/credentials/migrate_credentials_to_db.py --tenant PeterPrive

# 4. Restart backend
docker-compose restart backend
```

---

### Step 4: Verify Everything Works (2 minutes)

```bash
# 1. Check token health again
python backend/check_google_token_health.py
```

**Expected:** All tokens should show "healthy" status

```bash
# 2. Check backend logs
docker-compose logs backend --tail 50
```

**Expected:** No authentication errors

```bash
# 3. Test in UI
# Go to: Import Invoices → Upload Invoices → Select folder
```

**Expected:** Google Drive folders should load

---

### Step 5: Share Documentation with Team (5 minutes)

Share these files with your team:

1. **Quick Reference** (for emergencies)
   - `GOOGLE_DRIVE_TOKEN_QUICK_REFERENCE.md`

2. **Complete Guide** (for detailed info)
   - `backend/GOOGLE_DRIVE_TOKEN_MANAGEMENT.md`

3. **System Overview** (for understanding)
   - `backend/TOKEN_MONITORING_README.md`

---

## 📅 Ongoing Maintenance

### Weekly Tasks
- [ ] Run health check manually: `python backend/check_google_token_health.py`
- [ ] Review backend logs for auth errors
- [ ] Verify scheduled task ran successfully

### Monthly Tasks
- [ ] Test emergency recovery procedure
- [ ] Verify scheduled task is still active
- [ ] Review token expiry dates

### When Warned (< 7 days to expiry)
- [ ] Run token refresh proactively
- [ ] Update database
- [ ] Restart backend

---

## 🎯 Success Criteria

You'll know the system is working when:

1. ✅ Scheduled task runs daily at 9 AM
2. ✅ Health check shows all tokens healthy
3. ✅ Google Drive folders load in UI
4. ✅ No authentication errors in logs
5. ✅ Team knows emergency procedures

---

## 📞 Quick Commands Reference

### Check Token Health
```bash
python backend/check_google_token_health.py
```

### Emergency Fix
```bash
python backend/refresh_google_token.py
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
docker-compose restart backend
```

### Check Scheduled Task
```powershell
Get-ScheduledTask -TaskName "GoogleDriveTokenHealthCheck"
```

### View Backend Logs
```bash
docker-compose logs backend --tail 50
```

---

## ⏱️ Time Estimate

- **Initial Setup:** ~15 minutes
- **Weekly Maintenance:** ~5 minutes
- **Emergency Fix:** ~2 minutes

---

## 📝 Notes

- The scheduled task only needs to be set up once
- Health checks are automatic after setup
- Only act when you see warnings or errors
- Keep this checklist for reference

---

**Created:** February 2, 2026  
**Status:** Ready for setup  
**Priority:** High (prevents future downtime)
