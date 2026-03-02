# Phase 1 Testing Guide

**Purpose**: Verify Phase 1 implementation before proceeding to Phase 2  
**Status**: Ready for testing  
**Estimated time**: 1-2 hours

## Overview

Phase 1 implemented:

- ✅ Database schema (tables and columns)
- ✅ Configuration service (backend)
- ✅ API endpoints
- ✅ UI components (Year-End Settings, Chart of Accounts)
- ✅ Role-based access control

This guide will help you test each component systematically.

## Pre-Testing Checklist

Before starting tests:

- [ ] Backend is running (`python src/app.py`)
- [ ] Frontend is running (`npm start`)
- [ ] You have access to a test tenant
- [ ] You have `Tenant_Admin` role for the test tenant
- [ ] Database is accessible

## Test Plan

### 1. Database Migration (5 minutes)

**Purpose**: Verify database schema was created correctly

**Steps**:

1. Run migration in dry-run mode:

   ```bash
   cd backend
   python scripts/database/create_year_closure_tables.py --dry-run
   ```

2. Review output - should show:
   - ✅ Would create `year_closure_status` table
   - ✅ Would add `parameters` column to `rekeningschema`
   - ✅ Would create indexes

3. Run actual migration:

   ```bash
   python scripts/database/create_year_closure_tables.py
   ```

   - Type `yes` when prompted

4. Verify in database:

   ```sql
   -- Check table exists
   SHOW TABLES LIKE 'year_closure_status';

   -- Check table structure
   DESCRIBE year_closure_status;

   -- Check parameters column exists
   DESCRIBE rekeningschema;
   ```

**Expected Results**:

- ✅ `year_closure_status` table exists with correct columns
- ✅ `parameters` column exists in `rekeningschema` (type: JSON)
- ✅ Indexes created successfully

**If it fails**:

- Check database connection in `.env`
- Verify user has CREATE/ALTER permissions
- Check migration script output for errors

---

### 2. Backend Configuration Service (10 minutes)

**Purpose**: Test the configuration service directly

**Steps**:

1. Open Python shell in backend directory:

   ```bash
   cd backend/src
   python
   ```

2. Test service initialization:

   ```python
   from services.year_end_config import YearEndConfigService

   service = YearEndConfigService(test_mode=True)
   print("✅ Service initialized")
   ```

3. Test getting required purposes:

   ```python
   purposes = service.REQUIRED_PURPOSES
   print(f"Required purposes: {list(purposes.keys())}")
   # Should show: ['equity_result', 'pl_closing', 'interim_opening_balance']
   ```

4. Test validation (should fail - nothing configured yet):

   ```python
   validation = service.validate_configuration('YourTestTenant')
   print(f"Valid: {validation['valid']}")
   print(f"Errors: {validation['errors']}")
   # Should show: Valid: False, with 3 errors (missing purposes)
   ```

5. Test getting available accounts:
   ```python
   accounts = service.get_available_accounts('YourTestTenant', vw_filter='N')
   print(f"Found {len(accounts)} balance sheet accounts")
   ```

**Expected Results**:

- ✅ Service initializes without errors
- ✅ REQUIRED_PURPOSES has 3 entries
- ✅ Validation fails with missing purpose errors
- ✅ Available accounts query returns results

**If it fails**:

- Check database connection
- Verify tenant exists in database
- Check `rekeningschema` table has accounts

---

### 3. Backend API Endpoints (15 minutes)

**Purpose**: Test API endpoints with curl or Postman

**Prerequisites**:

- Get JWT token from browser (DevTools → Application → Local Storage → authToken)
- Replace `YOUR_TOKEN` in commands below

**Steps**:

1. Test validation endpoint:

   ```bash
   curl -X GET http://localhost:5000/api/tenant-admin/year-end-config/validate \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

   **Expected**: JSON with `valid: false` and 3 errors

2. Test get purposes endpoint:

   ```bash
   curl -X GET http://localhost:5000/api/tenant-admin/year-end-config/purposes \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

   **Expected**: JSON with `purposes: {}` and `required_purposes: {...}`

3. Test get available accounts:

   ```bash
   curl -X GET "http://localhost:5000/api/tenant-admin/year-end-config/available-accounts?vw=N" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

   **Expected**: JSON with array of balance sheet accounts

4. Test set purpose (pick an account from step 3):

   ```bash
   curl -X POST http://localhost:5000/api/tenant-admin/year-end-config/accounts \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"account_code": "3080", "purpose": "equity_result"}'
   ```

   **Expected**: JSON with `success: true`

5. Verify in database:

   ```sql
   SELECT Reknum, AccountName, parameters
   FROM rekeningschema
   WHERE administration = 'YourTestTenant'
   AND JSON_EXTRACT(parameters, '$.purpose') IS NOT NULL;
   ```

   **Expected**: Shows account 3080 with `{"purpose": "equity_result"}`

**Expected Results**:

- ✅ All endpoints return 200 status
- ✅ Validation endpoint shows errors
- ✅ Purpose assignment works
- ✅ Database updated correctly

**If it fails**:

- Check backend is running
- Verify JWT token is valid
- Check user has `Tenant_Admin` role
- Review backend logs for errors

---

### 4. Chart of Accounts - Purpose Column (10 minutes)

**Purpose**: Verify purpose column displays correctly

**Steps**:

1. Navigate to Chart of Accounts:
   - Login to frontend
   - Go to Tenant Admin section
   - Click "Chart of Accounts"

2. Check table columns:
   - [ ] "Purpose" column exists (last column)
   - [ ] Column header says "Purpose" (not "Role")

3. Check purpose display:
   - [ ] Account 3080 shows green badge with "equity_result"
   - [ ] Other accounts show "-" (no purpose)

4. Test purpose filter:
   - Type "equity" in Purpose filter box
   - [ ] Only account 3080 shows
   - Clear filter
   - [ ] All accounts show again

5. Test clear all filters:
   - Add some filters
   - Click "Clear All Filters"
   - [ ] Purpose filter is cleared too

**Expected Results**:

- ✅ Purpose column visible
- ✅ Configured purposes show as green badges
- ✅ Filter works correctly
- ✅ Clear filters includes purpose

**If it fails**:

- Check frontend console for errors
- Verify backend API returns purpose field
- Check TypeScript types are updated

---

### 5. Year-End Settings Screen (20 minutes)

**Purpose**: Test the main configuration UI

**Steps**:

1. Navigate to Year-End Settings:
   - Go to Tenant Admin section
   - Click "Year-End Settings" (or navigate directly)

2. Check access control:
   - [x] Screen loads without errors
   - [x] No "Access Denied" message (you have Tenant_Admin role)

   **Test with non-admin user** (if possible):
   - [ ] Shows "Access Denied" alert
   - [ ] Cannot configure purposes

3. Check initial state:
   - [x] Shows "Configuration Incomplete" warning (orange/yellow)
   - [x] Lists missing purposes in errors
   - [x] Shows 3 purpose configuration boxes

4. Check purpose boxes:
   - [x] Each box has clear label (Equity Result Account, etc.)
   - [x] Each box shows VW badge (N or Y)
   - [x] Each box has description text
   - [x] Each box has example (e.g., "Example: 3080")

5. Test account selection:
   - Click "Equity Result Account" dropdown
   - [x] Only shows VW='N' accounts (balance sheet)
   - [x] Shows account code and name
   - Select account 3080
   - Click "P&L Closing Account" dropdown
   - [x] Only shows VW='Y' accounts (P&L)
   - Select account 8099
   - Click "Interim Opening Balance Account" dropdown
   - [x] Only shows VW='N' accounts (balance sheet)
   - Select account 2001

6. Test save:
   - Click "Save Configuration"
   - [x] Shows loading state
   - [x] Shows success toast message
   - [x] Page reloads with updated data

7. Check validation after save:
   - [x] Shows "Configuration Complete" success message (green)
   - [x] No errors listed
   - [x] All three dropdowns show selected accounts

8. Test reload:
   - Refresh page
   - [x] Configuration persists
   - [x] All three accounts still selected

**Expected Results**:

- ✅ Access control works
- ✅ VW filtering works correctly
- ✅ Save functionality works
- ✅ Validation updates correctly
- ✅ Configuration persists

**If it fails**:

- Check browser console for errors
- Verify API endpoints work (test #3)
- Check network tab for failed requests
- Review backend logs

---

### 6. Integration Test (15 minutes)

**Purpose**: Test complete workflow end-to-end

**Steps**:

1. Start fresh (clear configuration):

   ```sql
   UPDATE rekeningschema
   SET parameters = NULL
   WHERE administration = 'YourTestTenant';
   ```

2. Open Year-End Settings:
   - [x] Shows "Configuration Incomplete"
   - [x] Lists 3 missing purposes

3. Configure all three purposes:
   - Equity Result: 3080
   - P&L Closing: 8099
   - Interim Opening Balance: 2001
   - Click Save

4. Verify in Chart of Accounts:
   - [x] Account 3080 shows "equity_result" badge
   - [x] Account 8099 shows "pl_closing" badge
   - [x] Account 2001 shows "interim_opening_balance" badge

5. Filter by purpose:
   - Type "equity" in Purpose filter
   - [x] Only 3080 shows
   - Type "pl_closing"
   - [x] Only 8099 shows

6. Test validation API:

   ```bash
   curl -X GET http://localhost:5000/api/tenant-admin/year-end-config/validate \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

   - [ ] Returns `valid: true`
   - [ ] No errors
   - [ ] Shows all 3 configured purposes

7. Check database:
   ```sql
   SELECT Reknum, AccountName,
          JSON_EXTRACT(parameters, '$.purpose') as purpose
   FROM rekeningschema
   WHERE administration = 'YourTestTenant'
   AND JSON_EXTRACT(parameters, '$.purpose') IS NOT NULL;
   ```

   - [ ] Shows 3 accounts with purposes

**Expected Results**:

- ✅ Complete workflow works smoothly
- ✅ All components work together
- ✅ Data persists correctly
- ✅ Validation reflects actual state

---

### 7. Error Handling (10 minutes)

**Purpose**: Test error scenarios

**Steps**:

1. Test invalid purpose:

   ```bash
   curl -X POST http://localhost:5000/api/tenant-admin/year-end-config/accounts \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"account_code": "3080", "purpose": "invalid_purpose"}'
   ```

   - [ ] Returns 400 error
   - [ ] Error message mentions invalid purpose

2. Test wrong VW classification:

   ```bash
   # Try to assign P&L account to equity_result (needs VW='N')
   curl -X POST http://localhost:5000/api/tenant-admin/year-end-config/accounts \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"account_code": "8000", "purpose": "equity_result"}'
   ```

   - [ ] Returns 400 error
   - [ ] Error message mentions VW mismatch

3. Test duplicate purpose:
   - Configure equity_result to 3080
   - Try to configure equity_result to 3090
   - [ ] Returns error about purpose already assigned

4. Test missing account:
   ```bash
   curl -X POST http://localhost:5000/api/tenant-admin/year-end-config/accounts \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"account_code": "9999", "purpose": "equity_result"}'
   ```

   - [ ] Returns 400 error
   - [ ] Error message mentions account not found

**Expected Results**:

- ✅ All error scenarios handled gracefully
- ✅ Clear error messages
- ✅ No crashes or 500 errors

---

## Test Results Summary

After completing all tests, fill in:

### Database

- [ ] Migration successful
- [ ] Tables created correctly
- [ ] Columns added correctly

### Backend

- [ ] Configuration service works
- [ ] API endpoints respond correctly
- [ ] Validation logic works
- [ ] Error handling works

### Frontend

- [ ] Chart of Accounts shows purpose column
- [ ] Purpose filter works
- [ ] Year-End Settings loads
- [ ] Access control works
- [ ] Configuration can be saved
- [ ] VW filtering works

### Integration

- [ ] End-to-end workflow works
- [ ] Data persists correctly
- [ ] All components work together

## Common Issues and Solutions

### Issue: Migration fails with "Table already exists"

**Solution**: This is normal if you ran it before. The script uses `IF NOT EXISTS`.

### Issue: API returns 403 Forbidden

**Solution**: Check you have `Tenant_Admin` role in JWT token.

### Issue: Purpose column doesn't show in Chart of Accounts

**Solution**:

- Check backend query includes purpose field
- Verify frontend types are updated
- Clear browser cache and reload

### Issue: Year-End Settings shows "Access Denied"

**Solution**: Verify you have `Tenant_Admin` role for the current tenant.

### Issue: Dropdowns are empty

**Solution**:

- Check accounts exist in `rekeningschema`
- Verify VW values are 'Y' or 'N'
- Check tenant filter is correct

### Issue: Save doesn't persist

**Solution**:

- Check browser console for errors
- Verify API endpoint works (curl test)
- Check database permissions

## Next Steps

After all tests pass:

1. ✅ Phase 1 is verified and working
2. Document any issues found
3. Fix any bugs discovered
4. Ready to proceed to Phase 2

If tests fail:

1. Document which tests failed
2. Check error messages and logs
3. Review implementation
4. Fix issues before Phase 2

## Quick Smoke Test (5 minutes)

If you're short on time, run this minimal test:

1. Run migration: `python scripts/database/create_year_closure_tables.py`
2. Open Year-End Settings in browser
3. Configure all 3 purposes
4. Click Save
5. Check Chart of Accounts shows purpose badges
6. Refresh page - configuration persists

If these 6 steps work, Phase 1 is likely working correctly!
