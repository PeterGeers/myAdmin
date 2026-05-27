# Bug Report: Aangifte IB Expand Failure in Table - SOLVED ✅

**Date**: 2026-02-07 15:21  
**Severity**: High  
**Component**: Backend & Frontend - AangifteIbReport  
**Status**: ✅ **FIXED & VERIFIED**  
**Solved**: 2026-02-07

## Problem Description

In the Aangifte IB Summary table:

1. Clicking the + sign before **Parent** correctly expands to show **Aangifte** items ✅
2. Clicking the + sign before **Aangifte** items failed with a 500 error ❌

**Error Message**:

```
GET http://localhost:3000/api/reports/aangifte-ib-details?administration=GoodwinSolutions&year=2025&parent=2000&aangifte=BTW 500 (INTERNAL SERVER ERROR)
```

**User Note**: "If I press export HTML all details on account level are shown" - indicating the data exists and export works.

## Root Cause

**Column Name Case Sensitivity Error** in `backend/src/app.py` line ~2596:

The code was trying to filter by `df['Administration']` (capital A), but the actual column name from the `vw_mutaties` view is `administration` (lowercase a).

```python
# WRONG (caused KeyError)
df = df[df['Administration'].isin(user_tenants)]

# CORRECT
df = df[df['administration'].isin(user_tenants)]
```

The `vw_mutaties` view defines columns as:

- `Aangifte` (capital A) ✅
- `Parent` (capital P) ✅
- `administration` (lowercase a) ✅

## Fix Applied

### Backend Changes (`backend/src/app.py`)

1. **Fixed column name case** in `/api/reports/aangifte-ib-details` endpoint:

   ```python
   # SECURITY: Filter by user's accessible tenants
   # Note: Column name is 'administration' (lowercase) from vw_mutaties view
   df = df[df['administration'].isin(user_tenants)]
   ```

2. **Added detailed error logging** for debugging:
   ```python
   except Exception as e:
       import traceback
       error_details = traceback.format_exc()
       print(f"Error in aangifte_ib_details: {error_details}", flush=True)
       return jsonify({'success': False, 'error': str(e), 'details': error_details if flag else None}), 500
   ```

## Verification

✅ Column name corrected to match database schema  
✅ Error logging improved for future debugging  
✅ TypeScript compilation passes  
✅ **User confirmed: "It works now TOP"** 🎉

## Testing Results

1. ✅ Click + on Parent row → shows Aangifte items
2. ✅ Click + on Aangifte item → shows account details (Reknum, AccountName, Amount)
3. ✅ No 500 errors in console
4. ✅ Account details display correctly with amounts
5. ✅ HTML export continues to work

## Technical Details

**Endpoint**: `/api/reports/aangifte-ib-details`  
**Method**: GET  
**Parameters**: `year`, `administration`, `parent`, `aangifte`  
**Returns**: Account details grouped by Reknum and AccountName

**Cache Method**: `mutaties_cache.query_aangifte_ib_details()`  
**View**: `vw_mutaties` (with VW logic applied)

## Additional Notes

- The HTML export worked because it uses a different code path without this bug
- All other usages of the cache in the codebase already use correct column names
- This was an isolated issue in the aangifte-ib-details endpoint only
- The frontend filtering logic (removing zero amounts) works correctly

---

**Fixed By**: Kiro AI Assistant  
**Date**: 2026-02-07  
**Verified By**: User  
**Files Modified**:

- `backend/src/app.py` - Fixed column name case and added error logging

---

## Impact

**Before Fix**:

- ❌ 500 Internal Server Error when expanding Aangifte items
- ❌ No account details visible
- ❌ Poor error messages for debugging

**After Fix**:

- ✅ Expand functionality works perfectly
- ✅ Account details display correctly
- ✅ Better error logging for future issues
- ✅ User confirmed working

## Lessons Learned

1. **Column name consistency**: Always verify column names match the database schema exactly
2. **Case sensitivity**: Python/Pandas is case-sensitive for column names
3. **Error logging**: Detailed error logging with stack traces helps debug issues quickly
4. **Testing**: Test both API endpoints and export functionality to ensure consistency
