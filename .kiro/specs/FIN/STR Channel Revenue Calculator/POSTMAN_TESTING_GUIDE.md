REMOVE: test_str_channel_api.py

Alternatively, the real solution is to use Postman's pre-request script to automatically get a fresh token. But for now, just open the frontend and navigate to any page, then I'll grab the token from the logs.

# Postman API Testing Guide - STR Channel BTW Rate

## Overview

This guide explains how to test the STR Channel BTW rate changes using Postman, following the same authentication process you used successfully yesterday.

## Collection Details

- **Collection Name:** STR Channel Revenue API - BTW Rate Testing
- **Collection ID:** `48572055-50144ccb-b513-4f1a-b156-8b6d8406729c`
- **Environment:** myAdmin Local
- **Environment ID:** `48572055-b5badd2a-5904-4fed-8ada-9dd1fd59235d`
- **Backend URL:** http://localhost:5000
- **Backend Status:** ✅ Running in Docker

## Test Requests

The collection includes 3 automated test requests:

### 1. Calculate December 2025 (9% BTW)

- **Endpoint:** POST `/api/str-channel/calculate`
- **Expected:** Credit account '2021', 9% VAT rate
- **Tests:** 3 automated assertions

### 2. Calculate January 2026 (21% BTW)

- **Endpoint:** POST `/api/str-channel/calculate`
- **Expected:** Credit account '2020', 21% VAT rate
- **Tests:** 3 automated assertions

### 3. Calculate February 2026 (21% BTW)

- **Endpoint:** POST `/api/str-channel/calculate`
- **Expected:** Credit account '2020', 21% VAT rate
- **Tests:** 2 automated assertions

## Authentication Setup

The API requires the same Cognito authentication you used yesterday for other endpoints.

### Step 1: Get Your JWT Token

1. Open myAdmin frontend: http://localhost:3000
2. Log in with your credentials
3. Open browser DevTools (F12)
4. Go to: **Application** tab → **Local Storage** → http://localhost:3000
5. Find and copy the **`idToken`** value

### Step 2: Configure Postman Environment

1. Open Postman Desktop App
2. In the top-right corner, select environment: **"myAdmin Local"**
3. Click the eye icon (👁️) next to the environment dropdown
4. Click **Edit**
5. Find the `auth_token` variable
6. Set its **CURRENT VALUE** to: `Bearer <paste-your-token-here>`
   - Example: `Bearer eyJraWQiOiJxxx...`
7. Click **Save**

### Step 3: Run the Collection

1. In Postman, navigate to **"Peter's Workspace"**
2. Find **"STR Channel Revenue API - BTW Rate Testing"** collection
3. Click the **"Run"** button (or right-click → Run collection)
4. Ensure **"myAdmin Local"** environment is selected
5. Click **"Run STR Channel Revenue API - BTW Rate Testing"**
6. Watch the tests execute

## Expected Results (When Authenticated)

### ✅ All Tests Should Pass

**December 2025 Request:**

- ✅ Status code is 200
- ✅ Response has transactions array
- ✅ VAT transactions use Credit account '2021' and 9% rate

**January 2026 Request:**

- ✅ Status code is 200
- ✅ Response has transactions array
- ✅ VAT transactions use Credit account '2020' and 21% rate

**February 2026 Request:**

- ✅ Status code is 200
- ✅ VAT transactions use Credit account '2020'

## Troubleshooting

### Issue: "401 Unauthorized" or Authentication Errors

**Solution:** Your JWT token has expired (tokens typically expire after 1 hour)

1. Get a fresh token from the frontend (repeat Step 1)
2. Update the `auth_token` in Postman environment
3. Run the collection again

### Issue: "Cannot connect to localhost:5000"

**Solution:** Backend container is not running

```powershell
docker ps  # Check if myadmin-backend-1 is running
docker-compose up -d  # Start if needed
```

### Issue: Tests fail with "undefined is not valid JSON"

**Solution:** Missing or incorrect authentication token

1. Verify you added "Bearer " prefix to the token
2. Check the token is set in the **CURRENT VALUE** field (not just INITIAL VALUE)
3. Ensure you selected the "myAdmin Local" environment before running

## Alternative: Run via Kiro

If you have the Postman power configured in Kiro:

```
Ask Kiro: "Run Postman collection 48572055-50144ccb-b513-4f1a-b156-8b6d8406729c with environment 48572055-b5badd2a-5904-4fed-8ada-9dd1fd59235d"
```

Note: You still need to set the auth_token in the environment first.

## Why This Matches Yesterday's Testing

Yesterday when you tested other myAdmin endpoints successfully, you used:

- ✅ Same Cognito authentication
- ✅ Same JWT token from frontend
- ✅ Same backend running in Docker
- ✅ Same Postman environment setup

This STR Channel collection follows the exact same pattern. The only difference is the specific endpoint being tested.

## Summary

The Postman collection is ready and configured correctly. To run the tests:

1. **Get token** from frontend (idToken in Local Storage)
2. **Set token** in Postman environment (myAdmin Local → auth_token)
3. **Run collection** and verify all 8 tests pass

This validates that the BTW rate logic correctly switches from 9% to 21% on January 1, 2026.
