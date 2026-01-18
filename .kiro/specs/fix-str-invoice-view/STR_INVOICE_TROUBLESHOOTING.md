# STR Invoice Generator Troubleshooting Guide

## Current Status

✅ **Backend API is working correctly**

- Database has 3,191 booking records
- API endpoint `/api/str-invoice/search-booking` is responding
- Test searches return correct data

❌ **Frontend is not displaying search results**

## Verified Working Components

1. **Database View**: `vw_bnb_total` exists and contains 3,191 records
2. **Backend Routes**: `str_invoice_bp` is properly registered at `/api/str-invoice`
3. **API Responses**: Search queries return correct JSON data
4. **Error Handling**: Empty queries return appropriate 400 errors

## Frontend Debugging Steps

### Step 1: Check Browser Console

1. Open the STR Invoice Generator page
2. Press F12 to open Developer Tools
3. Go to the "Console" tab
4. Look for any JavaScript errors (red text)
5. Common errors to look for:
   - CORS errors
   - Network errors
   - React component errors

### Step 2: Check Network Requests

1. In Developer Tools, go to "Network" tab
2. Try searching for a guest name (e.g., "Davies")
3. Look for a request to `/api/str-invoice/search-booking`
4. Check:
   - Is the request being made?
   - What is the response status code?
   - What data is being returned?

### Step 3: Verify Frontend-Backend Connection

**Expected behavior:**

- When you type "Davies" and click Search
- A GET request should be made to: `http://localhost:5000/api/str-invoice/search-booking?query=Davies`
- Response should be: `{"success": true, "bookings": [...]}`

**If no request is made:**

- Check if the Search button click handler is working
- Check browser console for React errors

**If request fails:**

- Check if backend server is running on port 5000
- Check CORS configuration
- Check if frontend is proxying requests correctly

## Quick Tests

### Test 1: Direct API Call

Open browser and navigate to:

```
http://localhost:5000/api/str-invoice/search-booking?query=Davies
```

**Expected result:** JSON response with booking data

### Test 2: Frontend Search

1. Go to STR Invoice Generator page
2. Type "Davies" in search box
3. Click "Search" button
4. Check Network tab for API call

### Test 3: Check Frontend Proxy

If frontend is running on a different port (e.g., 3000), check if it's configured to proxy API requests to backend (port 5000).

Look for `proxy` configuration in `frontend/package.json`:

```json
{
  "proxy": "http://localhost:5000"
}
```

## Common Issues and Solutions

### Issue 1: CORS Error

**Symptom:** Console shows "CORS policy" error

**Solution:** Backend already has CORS enabled in `app.py`. If still seeing errors:

1. Restart backend server
2. Clear browser cache
3. Check if CORS is configured for your frontend URL

### Issue 2: Wrong API URL

**Symptom:** 404 errors in Network tab

**Solution:** Verify frontend is calling `/api/str-invoice/search-booking` (not `/str-invoice/search-booking`)

### Issue 3: Backend Not Running

**Symptom:** "Failed to fetch" or connection refused errors

**Solution:** Start backend server:

```bash
cd backend
python src/app.py
```

### Issue 4: Frontend Not Updating State

**Symptom:** API returns data but UI doesn't update

**Solution:** Check React component state management:

- Verify `setSearchResults(data.bookings)` is being called
- Check if `searchResults` state is being used in render
- Look for conditional rendering issues

## Test Results

### Backend API Tests (✅ All Passing)

```
✓ Search for 'Davies' returns 2 bookings
✓ Search for reservation '1089888747' returns 1 booking
✓ Empty search returns 400 error
✓ Non-existent reservation returns empty list
✓ Invoice generation returns 404 for non-existent booking
```

### Database Tests (✅ All Passing)

```
✓ vw_bnb_total view exists
✓ View contains 3,191 records
✓ Sample records retrieved successfully
```

## Next Steps for User

1. **Open Browser Developer Tools** (F12)
2. **Go to STR Invoice Generator page**
3. **Try searching for "Davies"**
4. **Check Console tab** for any errors
5. **Check Network tab** to see if API request is made
6. **Report findings:**
   - Are there any console errors?
   - Is the API request being made?
   - What is the response status and data?

## Contact Information

If issue persists, provide:

- Browser console errors (screenshot)
- Network tab showing API request/response (screenshot)
- Browser and version
- Frontend URL (e.g., http://localhost:3000)
