Nieuwe gebruiker aanmaken

E-mail*
pjageers@gmail.com
Weergavenaam
PJA
Tijdelijk wachtwoord*
••••••••••••••
Rollen

Blijft hangen. Zelfs als je de modal verlaat en weer terugkomt lijkt het proces nog te lopen???

## Investigation (2026-02-18)

### Root Cause Analysis

The user creation endpoint exists and is properly configured:

- **Endpoint**: `POST /api/tenant-admin/users`
- **File**: `backend/src/routes/tenant_admin_users.py` (line 193)
- **Blueprint**: `tenant_admin_users_bp` (registered in app.py)

The hang is likely caused by one of these issues:

1. **Email Service Timeout** (Most Likely)
   - After creating user, the endpoint sends invitation email via SNS (lines 400-450)
   - If SNS is slow or timing out, the request hangs waiting for email to send
   - The code doesn't fail user creation if email fails, but it may be blocking

2. **Invitation Service Database Lock**
   - Creates invitation record before user creation (lines 360-375)
   - If database is slow or locked, this could cause hang

3. **Cognito API Slowness**
   - Multiple Cognito API calls: create user, add to groups, update attributes
   - If Cognito is slow, request could timeout

### Potential Solutions

1. **Make email sending asynchronous** (Recommended)
   - Move email sending to background task/queue
   - Return success immediately after user creation
   - Send email asynchronously

2. **Add timeout to SNS calls**
   - Configure boto3 SNS client with shorter timeout
   - Catch timeout exceptions and log warning

3. **Add request timeout on frontend**
   - Set reasonable timeout (e.g., 30 seconds) on fetch request
   - Show error message if timeout occurs
   - User creation may still succeed even if frontend times out

4. **Add progress indicator**
   - Show "Creating user..." → "Sending invitation email..." states
   - Give user feedback about what's happening

### Immediate Workaround

Check backend logs to see if user was actually created despite frontend hang:

```bash
# Check if user exists in Cognito
# Check invitation_log table for status
```

If user was created, the issue is purely frontend timeout - user creation succeeded but frontend didn't receive response.

