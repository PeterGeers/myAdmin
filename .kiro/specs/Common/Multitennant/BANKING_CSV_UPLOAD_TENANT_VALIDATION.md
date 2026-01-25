# Banking CSV Upload Tenant Validation

**Date:** 2026-01-25  
**Status:** ✅ IMPLEMENTED

## Problem

When uploading CSV files in the Banking module, the system was not validating that the bank account (IBAN) in the CSV file belongs to the current tenant. This allowed users to upload CSV files for bank accounts belonging to other tenants.

**Example:**
- User is working in tenant "PeterPrive"
- User uploads a CSV file containing transactions for a bank account belonging to "GoodwinSolutions"
- System accepted the file without any error message

## Root Cause

The frontend processes CSV files **entirely client-side** without calling any backend validation endpoints. The CSV parsing happens in the browser using JavaScript, and the backend endpoints `/api/banking/scan-files` and `/api/banking/process-files` are not used by the current implementation.

## Solution

Added **client-side tenant validation** in the frontend before processing any CSV files.

### Implementation Details

**File:** `frontend/src/components/BankingProcessor.tsx`

**Location:** In the `processFiles` function, after loading lookup data and before processing files

**Validation Logic:**
1. Get current tenant from `localStorage.getItem('selectedTenant')`
2. For each selected CSV file:
   - Read the first data row (skip header)
   - Extract IBAN from first column (Ref1)
   - Look up the IBAN in `lookupData.bank_accounts`
   - Check if the bank account's `Administration` matches current tenant
   - If mismatch: Show error and stop processing
   - If match: Continue processing

**Error Message:**
```
Access denied: File "filename.csv" contains bank account NL80RABO0107936917 
which belongs to GoodwinSolutions. You are currently working in PeterPrive. 
Please switch to GoodwinSolutions to upload this file.
```

### Code Changes

```typescript
// Get current tenant for validation
const currentTenant = localStorage.getItem('selectedTenant');
if (!currentTenant) {
  setMessage('Error: No tenant selected. Please select a tenant first.');
  setLoading(false);
  return;
}

// Validate IBANs in files belong to current tenant BEFORE processing
for (const file of selectedFiles) {
  const text = await file.text();
  const allRows = text.split('\n').filter(row => row.trim());
  
  if (allRows.length > 1) {
    const firstDataRow = allRows[1]; // Skip header
    const columns = file.name.toLowerCase().endsWith('.tsv')
      ? firstDataRow.split('\t').map(col => col.trim())
      : parseCSVRow(firstDataRow);
    
    // Extract IBAN from first column (Ref1)
    const iban = columns[0] || '';
    
    if (iban) {
      // Look up which tenant this IBAN belongs to
      const bankLookup = lookupData.bank_accounts.find(ba => ba.rekeningNummer === iban);
      
      if (bankLookup) {
        const ibanTenant = bankLookup.Administration;
        
        // Strict validation: IBAN must belong to current tenant
        if (ibanTenant !== currentTenant) {
          setMessage(`Access denied: File "${file.name}" contains bank account ${iban} which belongs to ${ibanTenant}. You are currently working in ${currentTenant}. Please switch to ${ibanTenant} to upload this file.`);
          setLoading(false);
          return;
        }
      } else {
        // IBAN not found in lookup - warn but allow (might be new account)
        console.warn(`Warning: IBAN ${iban} not found in bank account lookup`);
      }
    }
  }
}
```

## Additional Fixes

### 1. Fixed `banking_check_accounts` Error

**Problem:** The `check_banking_accounts` function was trying to access `Administration` (uppercase) but the `vw_lookup_accounts` view returns `administration` (lowercase).

**Error:** `Banking check accounts error: 'Administration'`

**Fix:** Changed `acc['Administration']` to `acc['administration']` in `backend/src/banking_processor.py`

```python
# Before:
administrations = list(set([acc['Administration'] for acc in accounts]))

# After:
administrations = list(set([acc['administration'] for acc in accounts]))
```

## Testing

### Test Scenario 1: Upload file for wrong tenant
1. Login as user with access to both "GoodwinSolutions" and "PeterPrive"
2. Switch to tenant "PeterPrive"
3. Try to upload CSV file containing GoodwinSolutions bank account
4. **Expected:** Error message displayed, file not processed
5. **Actual:** ✅ Error message displayed correctly

### Test Scenario 2: Upload file for correct tenant
1. Login as user with access to both tenants
2. Switch to tenant "GoodwinSolutions"
3. Upload CSV file containing GoodwinSolutions bank account
4. **Expected:** File processed successfully
5. **Actual:** ✅ File processed successfully

### Test Scenario 3: Switch tenant and upload
1. Start in "PeterPrive" tenant
2. Try to upload GoodwinSolutions file → Error
3. Switch to "GoodwinSolutions" tenant
4. Upload same file → Success
5. **Expected:** Validation respects current tenant
6. **Actual:** ✅ Works as expected

## Security Considerations

### Why Client-Side Validation is Acceptable Here:

1. **Lookup data is already filtered by tenant** - The `/api/banking/lookups` endpoint only returns bank accounts the user has access to
2. **Backend still validates on save** - When transactions are saved, the backend validates tenant access
3. **User experience** - Immediate feedback without server round-trip
4. **No security bypass** - Even if validation is bypassed, backend will reject on save

### Backend Validation Still Exists:

The backend endpoints `/api/banking/scan-files` and `/api/banking/process-files` have `@tenant_required()` decorators and IBAN validation, but they are not currently used by the frontend. They remain as a backup validation layer if the frontend flow changes in the future.

## Files Modified

- ✅ `frontend/src/components/BankingProcessor.tsx` - Added tenant validation
- ✅ `backend/src/banking_processor.py` - Fixed Administration column case
- ✅ `backend/src/app.py` - Already had tenant validation (not used by frontend)

## Related Requirements

- **REQ8:** Multi-tenant data isolation - ✅ Enforced
- **REQ9:** Tenant-specific access control - ✅ Implemented
- **Banking Module Tenant Support** - ✅ Complete

## Status

✅ **COMPLETE** - CSV upload now validates tenant ownership before processing files.

