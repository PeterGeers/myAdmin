# CSV Export Fix - Filtered Data

## Issues Fixed

### Issue 1: Line Breaks Not Working

**Problem**: CSV exports showed all data in one long line with literal `\n` text
**Cause**: Used `'\\n'` (escaped) instead of `'\n'` (actual newline)
**Fix**: Changed `.join('\\n')` to `.join('\n')`

### Issue 2: Export Ignores Filters

**Problem**: When filtering records in the UI, the CSV export still exported ALL records
**Cause**: Export functions used raw data (`mutatiesData`, `bnbData`) instead of filtered data
**Fix**: Changed to use `filteredMutatiesData` and `filteredBnbData`

## Changes Made

### Mutaties (P&L) Export

```typescript
// Before
const exportMutatiesCsv = React.useCallback(() => {
  const csvContent = [
    ['Date', 'Reference', 'Description', 'Amount', 'Debet', 'Credit', 'Administration'],
    ...mutatiesData.map(row => [...])  // ❌ All data
  ].map(row => row.join(',')).join('\\n');  // ❌ Literal \n
  // ...
}, [mutatiesData, ...]);

// After
const exportMutatiesCsv = React.useCallback(() => {
  const csvContent = [
    ['Date', 'Reference', 'Description', 'Amount', 'Debet', 'Credit', 'Administration'],
    ...filteredMutatiesData.map(row => [...])  // ✅ Filtered data
  ].map(row => row.join(',')).join('\n');  // ✅ Actual newline
  // ...
}, [filteredMutatiesData, ...]);
```

### BNB Revenue Export

```typescript
// Before
const exportBnbCsv = React.useCallback(() => {
  const csvContent = [
    ['Check-in Date', 'Check-out Date', ...],
    ...bnbData.map(row => [...])  // ❌ All data
  ].map(row => row.join(',')).join('\\n');  // ❌ Literal \n
  // ...
}, [bnbData, ...]);

// After
const exportBnbCsv = React.useCallback(() => {
  const csvContent = [
    ['Check-in Date', 'Check-out Date', ...],
    ...filteredBnbData.map(row => [...])  // ✅ Filtered data
  ].map(row => row.join(',')).join('\n');  // ✅ Actual newline
  // ...
}, [filteredBnbData, ...]);
```

## How Filtering Works

The filtered data is calculated based on search filters:

```typescript
const filteredMutatiesData = mutatiesData.filter((row) => {
  return Object.entries(searchFilters).every(([key, value]) => {
    if (!value) return true; // No filter = include all
    const fieldValue = row[key]?.toString().toLowerCase() || "";
    return fieldValue.includes(value.toLowerCase());
  });
});
```

### Available Filters (Mutaties):

- **TransactionDescription**: Filter by description text
- **Reknum**: Filter by account number (Debet)
- **AccountName**: Filter by account name (Credit)
- **ReferenceNumber**: Filter by reference

### Available Filters (BNB):

- **channel**: Filter by booking channel
- **listing**: Filter by property listing
- **guestName**: Filter by guest name
- **reservationCode**: Filter by reservation code

## Result

Now when you:

1. **Filter records** in the UI (e.g., search for "Booking.com")
2. **Click Export CSV**

The exported file will contain:

- ✅ Only the filtered/visible records
- ✅ Proper line breaks (one record per line)
- ✅ UTF-8 encoding for special characters
- ✅ Ready to open in Excel, Google Sheets, etc.

## Testing

### Test Case 1: No Filters

1. Load data with date range
2. Don't apply any search filters
3. Export CSV
4. **Expected**: All records exported

### Test Case 2: With Filters

1. Load data with date range
2. Apply search filter (e.g., Description = "Booking.com")
3. Verify table shows only filtered records
4. Export CSV
5. **Expected**: Only filtered records exported

### Test Case 3: Multiple Filters

1. Load data with date range
2. Apply multiple filters (e.g., Description = "AIRBNB", Account = "1002")
3. Verify table shows only matching records
4. Export CSV
5. **Expected**: Only records matching ALL filters exported

## Additional Improvements

1. **Better MIME type**: `text/csv;charset=utf-8;` for proper encoding
2. **Memory cleanup**: Added `URL.revokeObjectURL(url)` to prevent memory leaks
3. **Consistent behavior**: Both Mutaties and BNB exports work the same way

## Files Modified

- `frontend/src/components/myAdminReports.tsx`
  - Line ~1358: `exportMutatiesCsv` function
  - Line ~1378: `exportBnbCsv` function

## No Breaking Changes

- ✅ Existing functionality preserved
- ✅ No API changes
- ✅ No UI changes
- ✅ Backward compatible
