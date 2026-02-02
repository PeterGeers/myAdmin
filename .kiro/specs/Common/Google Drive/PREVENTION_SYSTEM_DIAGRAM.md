# Google Drive Token Prevention System - Visual Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PREVENTION SYSTEM                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  1. AUTOMATED MONITORING (Daily at 9 AM)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Windows Scheduled Task                                         │
│         ↓                                                        │
│  check_google_token_health.py                                   │
│         ↓                                                        │
│  Check token expiry for all tenants                             │
│         ↓                                                        │
│  ┌──────────────┬──────────────┬──────────────┐                │
│  │   Healthy    │   Warning    │   Expired    │                │
│  │   (> 7 days) │  (≤ 7 days)  │  (< 0 days)  │                │
│  │      ✅      │      ⚠️       │      ❌      │                │
│  └──────────────┴──────────────┴──────────────┘                │
│         │              │              │                          │
│         │              │              └─→ Alert + Recovery Steps│
│         │              └─→ Warning + Recommendation             │
│         └─→ No action needed                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  2. RUNTIME PROTECTION (Every API Call)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User requests Google Drive folders                             │
│         ↓                                                        │
│  GoogleDriveService._authenticate()                             │
│         ↓                                                        │
│  Check token validity                                           │
│         ↓                                                        │
│  ┌──────────────┬──────────────┐                               │
│  │    Valid     │   Expired    │                               │
│  │      ✅      │      ❌      │                               │
│  └──────────────┴──────────────┘                               │
│         │              │                                         │
│         │              └─→ Attempt auto-refresh                 │
│         │                        ↓                               │
│         │              ┌──────────────┬──────────────┐          │
│         │              │   Success    │    Failed    │          │
│         │              │      ✅      │      ❌      │          │
│         │              └──────────────┴──────────────┘          │
│         │                      │              │                  │
│         │                      │              └─→ Error + Steps │
│         │                      └─→ Update DB                    │
│         │                                                        │
│         └─→ Continue normally                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  3. MANUAL MONITORING (On-Demand)                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Admin runs health check                                        │
│         ↓                                                        │
│  python backend/check_google_token_health.py                    │
│         ↓                                                        │
│  View detailed status report                                    │
│         ↓                                                        │
│  Take action if needed                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  4. API MONITORING (Frontend Integration)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Frontend calls API                                             │
│         ↓                                                        │
│  GET /api/google-drive/token-health                             │
│         ↓                                                        │
│  Returns JSON with status                                       │
│         ↓                                                        │
│  Frontend displays warnings/errors                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Token Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                      TOKEN LIFECYCLE                             │
└─────────────────────────────────────────────────────────────────┘

Day 0: OAuth Flow
   ↓
   ├─→ Access Token (expires in 1 hour)
   └─→ Refresh Token (long-lived)

Hour 1: Access Token Expires
   ↓
   Auto-refresh using Refresh Token
   ↓
   New Access Token (expires in 1 hour)

Day 30: Token Still Valid
   ↓
   Continue auto-refreshing

Day 60: Token Still Valid
   ↓
   Continue auto-refreshing

Day 90: Token Approaching Expiry
   ↓
   ⚠️  Warning: 7 days until expiry
   ↓
   Proactive refresh recommended

Day 97: Token Expires
   ↓
   ❌ Token expired
   ↓
   Manual refresh required
   ↓
   Run: python backend/refresh_google_token.py
```

## Prevention vs Recovery

```
┌─────────────────────────────────────────────────────────────────┐
│                    BEFORE (No Prevention)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Token expires → No warning → Folders don't load →              │
│  User reports issue → Admin investigates → Finds expired token →│
│  Searches for solution → Fixes manually → 30+ minutes downtime  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    AFTER (With Prevention)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Day -7: ⚠️  Warning: Token expires in 7 days                   │
│         ↓                                                        │
│  Admin refreshes proactively                                    │
│         ↓                                                        │
│  Token refreshed → No downtime → Users unaffected               │
│                                                                  │
│  OR (if warning missed):                                        │
│                                                                  │
│  Token expires → Auto-refresh attempts → Success → No downtime  │
│                                                                  │
│  OR (if auto-refresh fails):                                    │
│                                                                  │
│  Token expires → Auto-refresh fails → Clear error message →     │
│  Admin follows steps → Fixed in 2 minutes → Minimal downtime    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Recovery Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    EMERGENCY RECOVERY                            │
└─────────────────────────────────────────────────────────────────┘

Issue Detected: Folders not loading
         ↓
Check backend logs
         ↓
See "invalid_grant" error
         ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Refresh Token (30 seconds)                             │
│  $ python backend/refresh_google_token.py                       │
│  ✅ Token refreshed successfully!                               │
└─────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Update Database (30 seconds)                           │
│  $ python scripts/credentials/migrate_credentials_to_db.py \    │
│    --tenant GoodwinSolutions                                    │
│  ✅ Migration completed successfully!                           │
└─────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Restart Backend (60 seconds)                           │
│  $ docker-compose restart backend                               │
│  ✅ Backend restarted!                                          │
└─────────────────────────────────────────────────────────────────┘
         ↓
Test: Load folders in UI
         ↓
✅ RESOLVED - Total time: 2 minutes
```

## Monitoring Schedule

```
┌─────────────────────────────────────────────────────────────────┐
│                    MONITORING SCHEDULE                           │
└─────────────────────────────────────────────────────────────────┘

Daily (Automated):
   09:00 AM → Scheduled task runs health check
            → Logs results
            → Alerts if issues found

Weekly (Manual):
   Monday → Admin runs health check manually
          → Reviews results
          → Takes action if needed

Monthly (Maintenance):
   1st of month → Test emergency recovery
                → Verify scheduled task
                → Review documentation

As Needed (Reactive):
   When warned → Proactive token refresh
   When error → Emergency recovery
```

## File Structure

```
myAdmin/
├── backend/
│   ├── check_google_token_health.py      ← Health monitoring
│   ├── refresh_google_token.py           ← Token refresh
│   ├── GOOGLE_DRIVE_TOKEN_MANAGEMENT.md  ← Complete guide
│   ├── TOKEN_MONITORING_README.md        ← System overview
│   └── src/
│       ├── google_drive_service.py       ← Improved error handling
│       └── app.py                        ← API health endpoint
├── scripts/
│   ├── setup_token_monitoring.ps1        ← Setup automation
│   └── credentials/
│       └── migrate_credentials_to_db.py  ← Database migration
├── GOOGLE_DRIVE_TOKEN_QUICK_REFERENCE.md ← Emergency procedures
├── GOOGLE_DRIVE_TOKEN_PREVENTION_SUMMARY.md ← System summary
├── SETUP_CHECKLIST.md                    ← Setup guide
└── PREVENTION_SYSTEM_DIAGRAM.md          ← This file
```

## Success Metrics

```
┌─────────────────────────────────────────────────────────────────┐
│                      BEFORE vs AFTER                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Metric              │  Before    │  After                      │
│  ────────────────────┼────────────┼──────────────────────       │
│  Warning Time        │  0 days    │  7 days                     │
│  Detection Method    │  Manual    │  Automated                  │
│  Recovery Time       │  30+ min   │  2 minutes                  │
│  Downtime            │  High      │  Minimal/None               │
│  Manual Checks       │  Required  │  Optional                   │
│  Documentation       │  None      │  Comprehensive              │
│  Visibility          │  Low       │  High                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Key Takeaways

1. **Prevention is Better than Cure**
   - 7-day advance warning prevents issues
   - Automated monitoring reduces manual work
   - Proactive refresh avoids downtime

2. **Multiple Layers of Protection**
   - Automated daily checks
   - Runtime auto-refresh
   - Manual monitoring tools
   - API health endpoints

3. **Quick Recovery When Needed**
   - Clear error messages
   - Step-by-step instructions
   - 2-minute recovery time

4. **Comprehensive Documentation**
   - Quick reference for emergencies
   - Complete guide for deep dives
   - System diagrams for understanding

5. **Minimal Maintenance Required**
   - Setup once, runs automatically
   - Only act when warned
   - Monthly verification recommended

---

**Created:** February 2, 2026  
**Purpose:** Visual guide to prevention system  
**Audience:** Developers and system administrators
