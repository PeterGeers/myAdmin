# Bug Report: Failed to Generate BTW Report - SOLVED ✅

**Date**: 2026-02-07 12:00  
**Severity**: High  
**Component**: Backend - Google Drive Integration  
**Status**: ✅ **FIXED & VERIFIED**  
**Solved**: 2026-02-07

## Problem Description

BTW report generation failed with error:

```
POST http://localhost:5000/api/btw/generate-report 500 (INTERNAL SERVER ERROR)
BTW report generation failed: Template not found
```

**Template URL**: https://drive.google.com/file/d/1NIXR3HnlnAcSX6TAQd7Oy5R8OVjt8FtQ/view?usp=drive_link

### Error from Docker Logs

```
ERROR:google_drive_service:❌ Token refresh failed for GoodwinSolutions:
  invalid_grant: Bad Request
ERROR:google_drive_service:⚠️  The refresh token may have expired or been revoked.
ERROR:services.template_service:Failed to fetch template from Google Drive
```

## Root Cause Analysis

### Initial Assumption (Incorrect)

Initially thought the Google Drive OAuth refresh token had expired or been revoked.

### Actual Root Cause (Discovered)

The database contained **fake/test tokens** instead of real Google Drive OAuth tokens:

- **Database token**: `refresh_token: "refresh_token_123..."` (test/placeholder data)
- **File token**: `refresh_token: "1//097OGBEz2IK4s..."` (real Google OAuth token)

When the system tried to refresh the expired access token, Google rejected the fake refresh token with `invalid_grant: Bad Request`.

### Why Import Invoices Still Worked

Import Invoices was able to list Google Drive folders because:

- The access token wasn't completely expired for all API calls
- OR it was using a cached connection
- The issue only surfaced when fetching templates, which triggered a token refresh

### Diagnostic Process

Created diagnostic script (`backend/diagnose_google_token.py`) which revealed:

```
COMPARISON
❌ Refresh tokens DIFFER
   File:     1//097OGBEz2IK4sCgYIARAAGAkSNw...
   Database: refresh_token_123...

💡 SOLUTION: Database token is outdated. Run migration
```

## Solution Applied

### Step 1: Diagnosed the Issue

```bash
cd backend
python diagnose_google_token.py
```

**Result**: Confirmed database had fake tokens while file had real tokens.

### Step 2: Migrated Real Tokens to Database

```bash
# From project root
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
python scripts/credentials/migrate_credentials_to_db.py --tenant PeterPrive
```

**Result**:

- ✅ Successfully migrated real tokens for both tenants
- ✅ Database now contains valid Google OAuth refresh tokens

### Step 3: Verified Fix

```bash
cd backend
python diagnose_google_token.py
```

**Result**: ✅ Refresh tokens MATCH between file and database

### Step 4: Tested BTW Report

**User confirmed**: "Yes it works again" ✅

## Technical Details

### OAuth Token Structure

**Access Token**:

- Short-lived (1 hour)
- Used for API calls
- Has expiry date
- ⚠️ Expiry is NORMAL - gets auto-refreshed

**Refresh Token**:

- Long-lived (no expiration under normal use)
- Used to get new access tokens
- Should NOT expire unless revoked
- Must be valid for auto-refresh to work

### Why This Happened

The database was likely populated with test/placeholder data during development, and the real tokens were never migrated from the file-based storage to the database.

### Files Involved

- `backend/token.json` - File-based token storage (real tokens)
- `backend/credentials.json` - OAuth client credentials
- Database table: `tenant_credentials` - Encrypted credential storage
- Migration script: `scripts/credentials/migrate_credentials_to_db.py`

## Prevention

### Diagnostic Tool Created

Created `backend/diagnose_google_token.py` to check token health:

```bash
cd backend
python diagnose_google_token.py
```

This tool:

- ✅ Checks file-based tokens
- ✅ Checks database-stored tokens
- ✅ Compares refresh tokens
- ✅ Provides actionable recommendations

### Recommendations

1. **Run diagnostic periodically** to ensure tokens are in sync
2. **Monitor token refresh errors** in logs
3. **Ensure migration runs** after any token refresh
4. **Document token management** for team

## Lessons Learned

1. **Don't assume token expiration** - investigate the actual cause
2. **Verify database contents** - don't trust that migrations ran correctly
3. **Create diagnostic tools** - they save hours of debugging
4. **Test both file and database** - ensure they're in sync
5. **User feedback is valuable** - "Import Invoices works" was the key clue

## Files Modified/Created

### Created

- `backend/diagnose_google_token.py` - Diagnostic tool for token health

### Modified

- Database: `tenant_credentials` table - Updated with real tokens for both tenants

### No Code Changes Required

The code was working correctly - it was a **data/configuration issue**, not a code bug.

## Verification

✅ BTW report generation works  
✅ Template fetching from Google Drive works  
✅ Tokens match between file and database  
✅ Automatic token refresh will work  
✅ Both tenants (GoodwinSolutions, PeterPrive) fixed

---

**Fixed By**: Kiro AI Assistant  
**Verified By**: User  
**Date**: 2026-02-07  
**Resolution**: Migrated real Google OAuth tokens from file to database

---

## Quick Reference

### If This Happens Again

1. **Diagnose**:

   ```bash
   cd backend
   python diagnose_google_token.py
   ```

2. **If tokens don't match, migrate**:

   ```bash
   python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
   python scripts/credentials/migrate_credentials_to_db.py --tenant PeterPrive
   ```

3. **Verify**:

   ```bash
   cd backend
   python diagnose_google_token.py
   ```

4. **Test**: Try generating BTW report

### If Token Actually Expired (Rare)

Only if Google actually revoked the refresh token:

```bash
cd backend
python refresh_google_token.py  # Opens browser for re-authentication
python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions
```
