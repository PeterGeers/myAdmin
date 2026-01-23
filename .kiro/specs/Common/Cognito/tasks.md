# AWS Cognito Implementation Tasks for myAdmin

## Overview

This document outlines all tasks required to implement AWS Cognito authentication and authorization in myAdmin, including infrastructure setup, backend integration, frontend integration, and deployment.

## Phase 1: Infrastructure Setup (Day 1 - Morning)

### Task 1.1: Deploy Cognito User Pool ⏱️ 15 minutes

**Status**: Ready to start
**Prerequisites**:

- ✅ AWS CLI configured (eu-west-1)
- ✅ Terraform installed
- ✅ AWS credentials valid

**Steps**:

```powershell
# Deploy Cognito infrastructure
- [x] start .\infrastructure\setup-cognito.ps1 -AdminEmail "peter@pgeers.nl"
```

- [x] **Expected Output**:

- User Pool ID: `eu-west-1_XXXXXXX`
- Client ID: `abc123...`
- Client Secret: `xyz789...`
- Hosted UI URL: `https://myadmin-xxx.auth.eu-west-1.amazoncognito.com`

**Verification**:

```powershell
# Check User Pool exists
- [x] aws cognito-idp list-user-pools --max-results 10 --region eu-west-1

# Verify .env files updated
Get-Content .env | Select-String "COGNITO"
Get-Content backend/.env | Select-String "COGNITO"
Get-Content frontend/.env | Select-String "COGNITO"
```

**Deliverables**:

- ✅ Cognito User Pool created
- ✅ 3 user groups created (Administrators, Accountants, Viewers)
- ✅ OAuth 2.0 configured
- ✅ .env files updated with credentials

---

### Task 1.2: Create Initial Users ⏱️ 10 minutes

**Status**: Waiting for Task 1.1
**Prerequisites**: Task 1.1 complete

**Steps**:

```powershell
# Create admin user
- [x] .\infrastructure\create-cognito-user.ps1 `
    -Email "peter@pgeers.nl" `
    -Name "Peter Geers" `
    -Group "Administrators"

# Create test accountant
- [x] .\infrastructure\create-cognito-user.ps1 `
    -Email "accountant@test.com" `
    -Name "Test Accountant" `
    -Group "Accountants"

# Create test viewer
- [x] .\infrastructure\create-cognito-user.ps1 `
    -Email "viewer@test.com" `
    -Name "Test Viewer" `
    -Group "Viewers"
```

**Verification**:

```powershell
# List all users
- [x] aws cognito-idp list-users `
    --user-pool-id <USER_POOL_ID> `
    --region eu-west-1
```

**Deliverables**:

- ✅ Admin user created and assigned to Administrators group
- ✅ Test users created for each role
- ✅ Passwords set for all users

---

### Task 1.3: Test Hosted UI ⏱️ 5 minutes

**Status**: Waiting for Task 1.2
**Prerequisites**: Tasks 1.1 and 1.2 complete

**Steps**:

- [x] 1. Open Hosted UI URL from Task 1.1 output
- [x] 2. Try logging in with admin credentials
- [x] 3. Verify JWT token contains `cognito:groups` claim

**Verification**:

- [x] Visit: `https://myadmin-xxx.auth.eu-west-1.amazoncognito.com/login?client_id=<CLIENT_ID>&response_type=code&redirect_uri=http://localhost:3000/callback`
- Login with admin credentials
- Check browser console for JWT token
- Decode token at jwt.io and verify `cognito:groups` contains `["Administrators"]`

**Deliverables**:

- ✅ Hosted UI accessible
- ✅ Login works
- ✅ JWT token contains correct groups

---

## Phase 2: Backend Integration (Day 1 - Afternoon)

### Task 2.1: Install Backend Dependencies ⏱️ 5 minutes

**Status**: Waiting for Phase 1
**Prerequisites**: Phase 1 complete

**Steps**:

```powershell
cd backend

# Install Python packages
- [x] pip install pyjwt boto3 python-jose[cryptography]

# Update requirements.txt
- [x] pip freeze | Select-String "PyJWT|boto3|python-jose" >> requirements.txt
```

**Verification**:

```powershell
- [x] python -c "import jwt; import boto3; print('Dependencies OK')"
```

**Deliverables**:

- ✅ JWT libraries installed
- ✅ AWS SDK (boto3) available
- ✅ requirements.txt updated

---

### Task 2.2: Create Authentication Utilities ⏱️ 30 minutes

**Status**: Waiting for Task 2.1
**Prerequisites**: Task 2.1 complete

**Steps**:

- [x] 1. Create `backend/src/auth/cognito_utils.py`
- [x] 2. Implement JWT token decoding
- [x] 3. Implement role extraction from `cognito:groups`
- [x] 4. Create authentication decorator

**Reference**: See `.kiro/specs/Common/Cognito/implementation-guide.md` section "Backend Implementation"

- [x] **Key Functions to Implement**:

```python
def extract_user_credentials(event):
    """Extract email and roles from JWT token"""
    pass

def validate_permissions(user_roles, required_permissions):
    """Check if user has required permissions"""
    pass

def cognito_required(required_roles=[]):
    """Decorator to protect routes"""
    pass
```

**Verification**:

```powershell
# Run unit tests
- [x] pytest backend/tests/test_auth.py
```

**Deliverables**:

- ✅ `cognito_utils.py` created
- ✅ JWT decoding working
- ✅ Role validation working
- ✅ Unit tests passing

---

### Task 2.3: Protect API Endpoints ⏱️ 45 minutes

**Status**: Waiting for Task 2.2
**Prerequisites**: Task 2.2 complete

**Steps**:

- [x] 1. Add authentication to existing routes
- [x] 2. Apply `@cognito_required` decorator
- [x] 3. Add role-based access control

**Example**:

```python
from src.auth.cognito_utils import cognito_required

@app.route('/api/invoices', methods=['GET'])
@cognito_required(required_roles=['Administrators', 'Accountants'])
def get_invoices():
    # Only admins and accountants can access
    pass

@app.route('/api/reports', methods=['GET'])
@cognito_required(required_roles=['Administrators', 'Accountants', 'Viewers'])
def get_reports():
    # All authenticated users can access
    pass
```

**Verification**:

```powershell
# First, verify authentication is required (should fail without token)
curl http://localhost:5000/api/reports/available-years
# Expected: {"error": "Missing Authorization header"}

# Get token for admin user from Cognito Hosted UI
# 1. Visit the Hosted UI URL from Task 1.1
# 2. Login with admin credentials
# 3. Copy the ID token from the browser console or callback URL
$adminToken = "<JWT_ID_TOKEN_FROM_COGNITO>"

# Test admin access to reports (should work)
curl -H "Authorization: Bearer $adminToken" http://localhost:5000/api/reports/available-years

# Test admin access to scalability dashboard (should work - Administrators only)
curl -H "Authorization: Bearer $adminToken" http://localhost:5000/api/scalability/dashboard

# Get token for viewer user
$viewerToken = "<JWT_ID_TOKEN_FROM_COGNITO>"

# Test viewer access to admin endpoint (should fail - insufficient permissions)
curl -H "Authorization: Bearer $viewerToken" http://localhost:5000/api/scalability/dashboard

# Test viewer access to reports (should work - all roles have reports_read)
curl -H "Authorization: Bearer $viewerToken" http://localhost:5000/api/reports/available-years
```

**Deliverables**:

- ✅ Admin can access all endpoints
- ✅ Accountants can access financial endpoints
- ✅ Viewers can only access read-only endpoints
- ✅ Unauthorized access properly blocked

---

## ⏸️ WAIT STAGE 1: Backend Deployment

**Before proceeding to frontend, ensure**:

- ✅ Backend authentication fully working locally
- ✅ All tests passing
- ✅ API endpoints properly protected
- ✅ Role-based access control verified

**Optional**: Deploy backend to Railway/staging environment for frontend testing

---

## Phase 3: Frontend Integration (Day 2 - Morning)

### Task 3.1: Install Frontend Dependencies ⏱️ 5 minutes

**Status**: Waiting for Wait Stage 1
**Prerequisites**: Backend authentication working

**Steps**:

```powershell
cd frontend

# Install AWS Amplify v6
npm install aws-amplify @aws-amplify/ui-react

# Install JWT decode
npm install jwt-decode
```

**Verification**:

```powershell
npm list aws-amplify jwt-decode
```

**Deliverables**:

- ✅ AWS Amplify installed
- ✅ JWT decode library installed
- ✅ package.json updated

---

- [x] ### Task 3.2: Configure AWS Amplify ⏱️ 15 minutes

**Status**: Waiting for Task 3.1
**Prerequisites**: Task 3.1 complete

**Steps**:

1. Create `frontend/src/aws-exports.ts`
2. Configure Cognito User Pool
3. Set up OAuth flows

**Configuration**:

````typescript
const awsconfig = {
  Auth: {
    Cognito: {
      userPoolId: process.env.REACT_APP_COGNITO_USER_POOL_ID,
      userPoolClientId: process.env.REACT_APP_COGNITO_CLIENT_ID,
      loginWith: {
        oauth: {
          domain: "myadmine Authentication Service ⏱️ 30 minutes

**Status**: Waiting for Task 3.2
**Prerequisites**: Task 3.2 complete

- [x] 3.3 **Steps**:
1. Create `frontend/src/services/authService.ts`
2. Implement JWT token utilities
3. Implement role extraction
4. Create API service with authentication

**Reference**: See `.kiro/specs/Common/Cognito/implementation-guide.md` section "Frontend Implementation"

**Key Functions**:
```typescript
export function decodeJWTPayload(token: string): JWTPayload | null
export async function getCurrentAuthTokens(): Promise<AuthTokens | null>
export async function getCurrentUserRoles(): Promise<string[]>
export function validateRoleCombinations(roles: string[])
````

**Verification**:

```powershell
# Run frontend tests
npm test -- authService.test.ts
```

**Deliverables**:

- ✅ `authService.ts` created
- ✅ JWT utilities working
- ✅ Role extraction working
- ✅ Tests passing

---

- [x] ### Task 3.4: Create Authentication Context ⏱️ 30 minutes

**Status**: Waiting for Task 3.3
**Prerequisites**: Task 3.3 complete

**Steps**:

1. Create `frontend/src/context/AuthContext.tsx`
2. Implement authentication state management
3. Create `useAuth` hook
4. Wrap app with AuthProvider

**Implementation**:

```typescript
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Check auth state on mount
  // Provide login/logout functions
  // Provide role checking functions
}

export function useAuth() {
  return useContext(AuthContext);
}
```

**Verification**:

```typescript
// In any component
const { user, isAuthenticated, hasRole } = useAuth();
```

**Deliverables**:

- ✅ AuthContext created
- ✅ useAuth hook working
- ✅ App wrapped with AuthProvider
- ✅ Authentication state managed

---

- [x] ### Task 3.5: Create Login Page ⏱️ 45 minutes

**Status**: Waiting for Task 3.4
**Prerequisites**: Task 3.4 complete

**Steps**:

1. Create `frontend/src/pages/Login.tsx`
   1.1 add logo backend\frontend\jabaki-logo.png
2. Implement login form
3. Add Cognito Hosted UI option
4. Handle authentication callbacks
5. Store JWT tokens

**Features**:

- Email/password login
- "Sign in with Cognito" button
- Remember me option
- Forgot password link
- Redirect after login

**Verification**:

1. Visit http://localhost:3000/login
2. Try logging in with test credentials
3. Verify redirect to dashboard
4. Check JWT token in localStorage

**Deliverables**:

- ✅ Login page created
- ✅ Authentication working
- ✅ Tokens stored securely
- ✅ Redirect working

---

- [x] ### Task 3.6: Implement Protected Routes ⏱️ 30 minutes

**Status**: Waiting for Task 3.5
**Prerequisites**: Task 3.5 complete

**Steps**:

1. Create `ProtectedRoute` component
2. Check authentication before rendering
3. Redirect to login if not authenticated
4. Check roles for role-based routes

**Implementation**:

```typescript
function ProtectedRoute({ children, requiredRoles = [] }) {
  const { isAuthenticated, hasRole } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" />;
  }

  if (requiredRoles.length > 0 && !requiredRoles.some(hasRole)) {
    return <Navigate to="/unauthorized" />;
  }

  return children;
}
```

**Routes to Protect**:

```typescript
<Route path="/dashboard" element={
  <ProtectedRoute>
    <Dashboard />
  </ProtectedRoute>
} />

<Route path="/users" element={
  <ProtectedRoute requiredRoles={['Administrators']}>
    <UserManagement />
  </ProtectedRoute>
} />
```

**Deliverables**:

- ✅ ProtectedRoute component created
- ✅ All routes protected
- ✅ Role-based routing working
- ✅ Unauthorized access redirects

---

### Task 3.7: Update API Calls with JWT ⏱️ 30 minutes

**Status**: Waiting for Task 3.6
**Prerequisites**: Task 3.6 complete

**Steps**:

1. Update `apiService.ts` to include JWT token
2. Add Authorization header to all requests
3. Handle token expiration
4. Implement token refresh

**Implementation**:

```typescript
export async function authenticatedRequest(endpoint, options = {}) {
  const tokens = await getCurrentAuthTokens();

  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${tokens.idToken}`,
    ...options.headers,
  };

  return fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });
}
```

**Verification**:

```typescript
// All API calls should now include JWT token
const invoices = await authenticatedRequest("/api/invoices");
```

**Deliverables**:

- ✅ All API calls include JWT token
- ✅ Token expiration handled
- ✅ Automatic token refresh working
- ✅ Error handling for auth failures

---

### Task 3.8: Test Frontend Authentication ⏱️ 45 minutes

**Status**: Waiting for Task 3.7
**Prerequisites**: Task 3.7 complete

**Steps**:

1. Test login flow
2. Test protected routes
3. Test role-based access
4. Test logout
5. Test token expiration

**Test Scenarios**:

- ✅ Login with admin → Access all pages
- ✅ Login with accountant → Access financial pages only
- ✅ Login with viewer → Access reports only
- ✅ Try accessing admin page as viewer → Redirect to unauthorized
- ✅ Logout → Redirect to login
- ✅ Token expires → Auto-refresh or redirect to login

**Deliverables**:

- ✅ All authentication flows working
- ✅ Role-based access enforced
- ✅ Token management working
- ✅ User experience smooth

---

## ⏸️ WAIT STAGE 2: Integration Testing

**Before proceeding to deployment, ensure**:

- ✅ Backend authentication fully working
- ✅ Frontend authentication fully working
- ✅ Backend + Frontend integration working
- ✅ All roles tested
- ✅ All edge cases handled

**Integration Tests**:

1. Admin user can access everything
2. Accountant can access financial data
3. Viewer can only view reports
4. Unauthorized access properly blocked
5. Token expiration handled gracefully

---

## Phase 4: Deployment (Day 2 - Afternoon)

### Task 4.1: Update Railway Environment Variables ⏱️ 10 minutes

**Status**: Waiting for Wait Stage 2
**Prerequisites**: All integration tests passing

**Steps**:

1. Go to Railway dashboard
2. Add Cognito environment variables:
   ```
   COGNITO_USER_POOL_ID=eu-west-1_XXXXXXX
   COGNITO_CLIENT_ID=abc123...
   COGNITO_CLIENT_SECRET=xyz789...
   AWS_REGION=eu-west-1
   ```

**Verification**:

```powershell
# Check Railway environment
railway variables
```

**Deliverables**:

- ✅ All Cognito variables set in Railway
- ✅ Backend can access Cognito
- ✅ Frontend can access Cognito

---

### Task 4.2: Deploy Backend to Railway ⏱️ 15 minutes

**Status**: Waiting for Task 4.1
**Prerequisites**: Task 4.1 complete

**Steps**:

```powershell
cd backend

# Deploy to Railway
git add .
git commit -m "Add Cognito authentication"
git push railway main
```

**Verification**:

```powershell
# Test production API
curl -H "Authorization: Bearer <TOKEN>" https://your-app.railway.app/api/invoices
```

**Deliverables**:

- ✅ Backend deployed with Cognito
- ✅ Authentication working in production
- ✅ API endpoints protected

---

### Task 4.3: Deploy Frontend to Railway ⏱️ 15 minutes

**Status**: Waiting for Task 4.2
**Prerequisites**: Task 4.2 complete

**Steps**:

```powershell
cd frontend

# Update callback URLs in Cognito
# Add: https://your-app.railway.app/callback

# Deploy to Railway
git add .
git commit -m "Add Cognito authentication"
git push railway main
```

**Verification**:

1. Visit https://your-app.railway.app
2. Try logging in
3. Verify authentication works
4. Test protected routes

**Deliverables**:

- ✅ Frontend deployed with Cognito
- ✅ Login working in production
- ✅ Protected routes working

---

### Task 4.4: Update Cognito Callback URLs ⏱️ 5 minutes

**Status**: Waiting for Task 4.3
**Prerequisites**: Task 4.3 complete

**Steps**:

```powershell
# Edit infrastructure/cognito.tf
# Update callback_urls with Railway URL

# Apply changes
cd infrastructure
terraform apply
```

**Callback URLs to Add**:

- `https://your-app.railway.app/callback`
- `https://your-app.railway.app/`

**Deliverables**:

- ✅ Production URLs added to Cognito
- ✅ OAuth flow working in production

---

### Task 4.5: Production Testing ⏱️ 30 minutes

**Status**: Waiting for Task 4.4
**Prerequisites**: Task 4.4 complete

**Steps**:

1. Test login in production
2. Test all user roles
3. Test API access
4. Test token expiration
5. Test logout

**Test Checklist**:

- ✅ Admin login works
- ✅ Accountant login works
- ✅ Viewer login works
- ✅ Role-based access enforced
- ✅ API calls authenticated
- ✅ Token refresh works
- ✅ Logout works
- ✅ No console errors

**Deliverables**:

- ✅ Production authentication fully working
- ✅ All roles tested in production
- ✅ No critical issues

---

## Phase 5: Documentation & Handoff (Day 3)

### Task 5.1: Create User Documentation ⏱️ 30 minutes

**Status**: Waiting for Phase 4
**Prerequisites**: Production deployment complete

**Documents to Create**:

1. User login guide
2. Password reset guide
3. Role descriptions
4. FAQ

**Deliverables**:

- ✅ User documentation complete
- ✅ Screenshots included
- ✅ Common issues documented

---

### Task 5.2: Create Admin Documentation ⏱️ 30 minutes

**Status**: Waiting for Task 5.1
**Prerequisites**: Task 5.1 complete

**Documents to Create**:

1. User management guide
2. Role assignment guide
3. Troubleshooting guide
4. Monitoring guide

**Deliverables**:

- ✅ Admin documentation complete
- ✅ User management procedures documented
- ✅ Troubleshooting steps documented

---

### Task 5.3: Create Developer Documentation ⏱️ 30 minutes

**Status**: Waiting for Task 5.2
**Prerequisites**: Task 5.2 complete

**Documents to Create**:

1. Architecture overview
2. API authentication guide
3. Adding new protected routes
4. Testing guide

**Deliverables**:

- ✅ Developer documentation complete
- ✅ Code examples included
- ✅ Best practices documented

---

## Summary

### Total Time Estimate

- **Phase 1**: 30 minutes (Infrastructure)
- **Phase 2**: 2 hours (Backend)
- **Phase 3**: 3.5 hours (Frontend)
- **Phase 4**: 1.5 hours (Deployment)
- **Phase 5**: 1.5 hours (Documentation)
- **Total**: ~9 hours (1-2 days)

### Critical Path

1. Deploy Cognito (Phase 1)
2. Backend integration (Phase 2)
3. Frontend integration (Phase 3)
4. Production deployment (Phase 4)

### Dependencies

- Phase 2 depends on Phase 1
- Phase 3 depends on Phase 2 (Wait Stage 1)
- Phase 4 depends on Phase 3 (Wait Stage 2)
- Phase 5 depends on Phase 4

### Success Criteria

- ✅ All users can log in
- ✅ Role-based access working
- ✅ Production deployment successful
- ✅ No security vulnerabilities
- ✅ Documentation complete

Extrav tattention points

- [ ] Actually, I realize the current app doesn't use React Router yet. Should we implement React Router now??

- [ ] The bundle size is significantly larger than recommended.
      File sizes after gzip:

  1.38 MB build\static\js\537.0bac0150.chunk.js
  408.43 kB build\static\js\main.0ae75f52.js
  1.76 kB build\static\js\453.8701dc61.chunk.js
  263 B build\static\css\main.e6c13ad2.css

The bundle size is significantly larger than recommended.
Consider reducing it with code splitting: https://goo.gl/9VhYWB
You can also analyze the project dependencies: https://goo.gl/LeUzfb
