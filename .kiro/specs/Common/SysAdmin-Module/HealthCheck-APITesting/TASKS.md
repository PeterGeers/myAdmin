# Health Check & API Testing - Implementation Tasks

**Status**: Not Started
**Created**: February 9, 2026
**Last Updated**: February 9, 2026

---

## Overview

Implementation tasks for Health Check and API Testing features in the SysAdmin module.

**Estimated Time**: 8-12 days

**Phase Breakdown**:

- Phase 1: Health Check Backend (1-2 days)
- Phase 2: Health Check Frontend (1-2 days)
- Phase 3: API Testing Backend (1-2 days)
- Phase 4: API Testing Frontend (2-3 days)
- Phase 5: Diagnostic Tests (2-3 days)
- Phase 6: Polish & Testing (1-2 days)

---

## Phase 1: Health Check Backend (1-2 days)

### 1.1 Create Health Check Route

- [x] Create `backend/src/routes/sysadmin_health.py`
- [x] Import required libraries (Flask, boto3, mysql-connector, etc.)
- [x] Create blueprint `sysadmin_health_bp`
- [x] Register blueprint in `backend/src/app.py`

### 1.2 Implement Health Check Functions

- [x] Create `check_database_health()` function
  - [x] Test MySQL connection
  - [x] Get connection pool stats
  - [x] Measure response time
  - [x] Return status and details
- [x] Create `check_cognito_health()` function
  - [x] Test AWS Cognito API access
  - [x] List user pools (verify permissions)
  - [x] Measure response time
  - [x] Return status and details
- [x] Create `check_sns_health()` function
  - [x] Test AWS SNS API access
  - [x] List topics (verify permissions)
  - [x] Measure response time
  - [x] Return status and details
- [x] Create `check_google_drive_health()` function
  - [x] Test Google Drive API access
  - [x] Verify credentials
  - [x] Measure response time
  - [x] Return status and details
  - [x] Handle optional (may not be configured)
- [x] Create `check_openrouter_health()` function
  - [x] Test OpenRouter API access
  - [x] Verify API key
  - [x] Measure response time
  - [x] Return status and details
  - [x] Handle optional (may not be configured)

### 1.3 Implement Health Check Endpoints

- [x] Implement `GET /api/sysadmin/health`
  - [x] Add `@cognito_required(required_roles=['SysAdmin'])`
  - [x] Run all health checks in parallel (asyncio or threading)
  - [x] Aggregate results
  - [x] Determine overall status (healthy/degraded/unhealthy)
  - [x] Return JSON response
  - [x] Add error handling
  - [x] Add logging
- [ ] Implement `GET /api/sysadmin/health/history` (optional)
  - [ ] Store health check results in database or cache
  - [ ] Query historical data
  - [ ] Return time-series data
  - [ ] Add pagination

### 1.4 Add Caching

- [ ] Implement caching for health check results (30s TTL)
- [ ] Use in-memory cache or Redis
- [ ] Add cache invalidation on manual refresh

### 1.5 Testing

- [ ] Write unit tests for health check functions
- [ ] Write integration tests for endpoints
- [ ] Test with various failure scenarios
- [ ] Test caching behavior

**Estimated Time**: 1-2 days

---

## Phase 2: Health Check Frontend (1-2 days)

### 2.1 Create Service Functions

- [x] Update `frontend/src/services/sysadminService.ts`
- [x] Add `HealthStatus` interface
- [x] Add `SystemHealth` interface
- [x] Add `getSystemHealth()` function
- [ ] Add `getHealthHistory()` function (optional - skipped)

### 2.2 Create HealthCheck Component

- [x] Create `frontend/src/components/SysAdmin/HealthCheck.tsx`
- [x] Import Chakra UI components
- [x] Setup state management
  - [x] `health: SystemHealth | null`
  - [x] `loading: boolean`
  - [x] `autoRefresh: boolean`
  - [x] `refreshInterval: number`
  - [x] `lastChecked: Date | null`
- [x] Implement `loadHealth()` function
- [x] Implement `handleRefresh()` function
- [x] Implement auto-refresh with `useEffect` and `setInterval`

### 2.3 Implement UI Components

- [x] Create overall status indicator
  - [x] Large status badge (Healthy/Degraded/Unhealthy)
  - [x] Color-coded (green/yellow/red)
  - [x] Last checked timestamp
- [x] Create service status table
  - [x] Service name column
  - [x] Status indicator column (colored dot + text)
  - [x] Response time column
  - [x] Details button column
- [x] Create service details modal
  - [x] Show full service information
  - [x] Display error messages if unhealthy
  - [x] Show connection details
- [x] Create refresh controls
  - [x] Manual refresh button
  - [x] Auto-refresh toggle
  - [x] Refresh interval selector (30s, 1m, 5m)
- [ ] Create export button (optional - skipped for now)
  - [ ] Export health report as JSON
  - [ ] Export health report as CSV

### 2.4 Add Loading and Error States

- [x] Add loading spinner while fetching
- [x] Add error message display
- [x] Add retry button on error
- [x] Add empty state (no data)

### 2.5 Integrate into SysAdminDashboard

- [x] Update `frontend/src/components/SysAdmin/SysAdminDashboard.tsx`
- [x] Add "Health Check" tab
- [x] Import HealthCheck component
- [x] Add tab content

### 2.6 Testing

- [ ] Test manual refresh (manual testing required)
- [ ] Test auto-refresh (manual testing required)
- [ ] Test service details modal (manual testing required)
- [ ] Test error handling (manual testing required)
- [ ] Test responsive design (manual testing required)

**Estimated Time**: 1-2 days
**Actual Time**: ~1 hour
**Status**: ✅ Complete (ready for manual testing)

- [ ] Update `frontend/src/services/sysadminService.ts`
- [ ] Add `HealthStatus` interface
- [ ] Add `SystemHealth` interface
- [ ] Add `getSystemHealth()` function
- [ ] Add `getHealthHistory()` function (optional)

### 2.2 Create HealthCheck Component

- [ ] Create `frontend/src/components/SysAdmin/HealthCheck.tsx`
- [ ] Import Chakra UI components
- [ ] Setup state management
  - [ ] `health: SystemHealth | null`
  - [ ] `loading: boolean`
  - [ ] `autoRefresh: boolean`
  - [ ] `refreshInterval: number`
  - [ ] `lastChecked: Date | null`
- [ ] Implement `loadHealth()` function
- [ ] Implement `handleRefresh()` function
- [ ] Implement auto-refresh with `useEffect` and `setInterval`

### 2.3 Implement UI Components

- [ ] Create overall status indicator
  - [ ] Large status badge (Healthy/Degraded/Unhealthy)
  - [ ] Color-coded (green/yellow/red)
  - [ ] Last checked timestamp
- [ ] Create service status table
  - [ ] Service name column
  - [ ] Status indicator column (colored dot + text)
  - [ ] Response time column
  - [ ] Details button column
- [ ] Create service details modal
  - [ ] Show full service information
  - [ ] Display error messages if unhealthy
  - [ ] Show connection details
- [ ] Create refresh controls
  - [ ] Manual refresh button
  - [ ] Auto-refresh toggle
  - [ ] Refresh interval selector (30s, 1m, 5m)
- [ ] Create export button (optional)
  - [ ] Export health report as JSON
  - [ ] Export health report as CSV

### 2.4 Add Loading and Error States

- [ ] Add loading spinner while fetching
- [ ] Add error message display
- [ ] Add retry button on error
- [ ] Add empty state (no data)

### 2.5 Integrate into SysAdminDashboard

- [ ] Update `frontend/src/components/SysAdmin/SysAdminDashboard.tsx`
- [ ] Add "Health Check" tab
- [ ] Import HealthCheck component
- [ ] Add tab content

### 2.6 Testing

- [ ] Test manual refresh
- [ ] Test auto-refresh
- [ ] Test service details modal
- [ ] Test error handling
- [ ] Test responsive design

**Estimated Time**: 1-2 days

---

## Phase 3: API Testing Backend (1-2 days)

### 3.1 Create API Testing Route (Optional)

**Note**: API testing can be done entirely client-side by calling endpoints directly. Backend proxy is optional for additional security/logging.

- [ ] Create `backend/src/routes/sysadmin_api_test.py` (optional)
- [ ] Create blueprint `sysadmin_api_test_bp`
- [ ] Register blueprint in `backend/src/app.py`

### 3.2 Implement API Testing Endpoint (Optional)

- [ ] Implement `POST /api/sysadmin/api-test`
  - [ ] Add `@cognito_required(required_roles=['SysAdmin'])`
  - [ ] Parse request (method, endpoint, headers, body)
  - [ ] Validate inputs
  - [ ] Execute API request (using requests library)
  - [ ] Measure response time
  - [ ] Return response details
  - [ ] Add error handling
  - [ ] Add audit logging

### 3.3 Add Security Measures

- [ ] Validate endpoint URLs (whitelist internal endpoints only)
- [ ] Sanitize request headers
- [ ] Mask sensitive data in logs
- [ ] Add rate limiting
- [ ] Add request timeout (30s default)

### 3.4 Testing

- [ ] Write unit tests for API testing function
- [ ] Write integration tests for endpoint
- [ ] Test with various HTTP methods
- [ ] Test error scenarios

**Estimated Time**: 1-2 days (or skip if doing client-side only)

---

## Phase 4: API Testing Frontend (2-3 days)

### 4.1 Create Service Functions

- [ ] Update `frontend/src/services/sysadminService.ts`
- [ ] Add `APITestConfig` interface
- [ ] Add `APITestResult` interface
- [ ] Add `executeAPITest()` function
- [ ] Add `saveTestConfig()` function (localStorage)
- [ ] Add `loadTestConfigs()` function (localStorage)
- [ ] Add `getTestHistory()` function (localStorage)

### 4.2 Create APITesting Component

- [ ] Create `frontend/src/components/SysAdmin/APITesting.tsx`
- [ ] Import Chakra UI components
- [ ] Import code editor component (e.g., react-simple-code-editor or Monaco)
- [ ] Setup state management
  - [ ] `method: string`
  - [ ] `endpoint: string`
  - [ ] `headers: Record<string, string>`
  - [ ] `body: string`
  - [ ] `tenant: string`
  - [ ] `result: APITestResult | null`
  - [ ] `loading: boolean`
  - [ ] `savedConfigs: APITestConfig[]`
  - [ ] `history: APITestResult[]`

### 4.3 Implement Request Builder UI

- [ ] Create HTTP method selector
  - [ ] Dropdown with GET, POST, PUT, DELETE, PATCH
  - [ ] Color-coded by method
- [ ] Create endpoint input
  - [ ] Text input with autocomplete
  - [ ] Suggest common endpoints
  - [ ] Validate URL format
- [ ] Create headers editor
  - [ ] Key-value pair inputs
  - [ ] Add/remove header buttons
  - [ ] Auto-populate Authorization header with JWT
  - [ ] Tenant selector for X-Tenant header
- [ ] Create body editor
  - [ ] JSON editor with syntax highlighting
  - [ ] Format/prettify button
  - [ ] Validate JSON syntax
  - [ ] Show/hide based on HTTP method

### 4.4 Implement Response Viewer UI

- [ ] Create status code display
  - [ ] Large badge with status code
  - [ ] Color-coded (green for 2xx, yellow for 3xx, orange for 4xx, red for 5xx)
  - [ ] Response time display
- [ ] Create response headers display
  - [ ] Collapsible section
  - [ ] Key-value list
- [ ] Create response body display
  - [ ] JSON viewer with syntax highlighting
  - [ ] Collapsible/expandable sections
  - [ ] Copy to clipboard button
  - [ ] Download as file button

### 4.5 Implement Configuration Management

- [ ] Create "Save Config" button
  - [ ] Modal to name configuration
  - [ ] Save to localStorage
  - [ ] Add to saved configs list
- [ ] Create "Load Config" dropdown
  - [ ] List saved configurations
  - [ ] Load configuration on select
  - [ ] Delete configuration option
- [ ] Create request history sidebar
  - [ ] Show last 10 requests
  - [ ] Click to load request
  - [ ] Clear history button

### 4.6 Implement Test Execution

- [ ] Create `handleSendRequest()` function
  - [ ] Validate inputs
  - [ ] Build request configuration
  - [ ] Execute API call (direct or via backend proxy)
  - [ ] Handle response
  - [ ] Update result state
  - [ ] Add to history
  - [ ] Handle errors
- [ ] Add loading state during execution
- [ ] Add error handling and display

### 4.7 Integrate into SysAdminDashboard

- [ ] Update `frontend/src/components/SysAdmin/SysAdminDashboard.tsx`
- [ ] Add "API Testing" tab
- [ ] Import APITesting component
- [ ] Add tab content

### 4.8 Testing

- [ ] Test all HTTP methods
- [ ] Test with various endpoints
- [ ] Test header management
- [ ] Test body editor
- [ ] Test save/load configurations
- [ ] Test request history
- [ ] Test error handling
- [ ] Test responsive design

**Estimated Time**: 2-3 days

---

## Phase 5: Diagnostic Tests (2-3 days)

### 5.1 Create Diagnostic Tests Backend

- [ ] Create `backend/src/routes/sysadmin_diagnostics.py`
- [ ] Create blueprint `sysadmin_diagnostics_bp`
- [ ] Register blueprint in `backend/src/app.py`

### 5.2 Implement Diagnostic Test Functions

- [ ] Create `test_authentication()` function
  - [ ] Verify current user authentication
  - [ ] Check token validity
  - [ ] Return user details and roles
- [ ] Create `test_tenant_access()` function
  - [ ] Test tenant context switching
  - [ ] Query tenant data
  - [ ] Verify data isolation
- [ ] Create `test_user_management()` function
  - [ ] Test user CRUD operations
  - [ ] Create test user
  - [ ] Update test user
  - [ ] Delete test user
  - [ ] Verify operations
- [ ] Create `test_file_upload()` function
  - [ ] Test file upload to Google Drive
  - [ ] Upload test file
  - [ ] Verify file exists
  - [ ] Delete test file
- [ ] Create `test_notification()` function
  - [ ] Test SNS notification
  - [ ] Send test notification
  - [ ] Verify delivery (if possible)

### 5.3 Implement Diagnostic Endpoints

- [ ] Implement `GET /api/sysadmin/diagnostics`
  - [ ] Return list of available tests
  - [ ] Include test metadata (name, description, category)
- [ ] Implement `POST /api/sysadmin/diagnostics/{test_id}`
  - [ ] Add `@cognito_required(required_roles=['SysAdmin'])`
  - [ ] Execute specified test
  - [ ] Return test result (passed/failed)
  - [ ] Include detailed information
  - [ ] Add error handling
  - [ ] Add logging

### 5.4 Create DiagnosticTests Component

- [ ] Create `frontend/src/components/SysAdmin/DiagnosticTests.tsx`
- [ ] Import Chakra UI components
- [ ] Setup state management
  - [ ] `tests: DiagnosticTest[]`
  - [ ] `results: Map<string, DiagnosticResult>`
  - [ ] `loading: Map<string, boolean>`

### 5.5 Implement Diagnostic Tests UI

- [ ] Create test cards grid
  - [ ] Card for each diagnostic test
  - [ ] Test name and description
  - [ ] "Run Test" button
  - [ ] Loading spinner during execution
  - [ ] Result indicator (pass/fail)
- [ ] Create test result display
  - [ ] Expandable result section
  - [ ] Show test details
  - [ ] Show error messages on failure
  - [ ] Show suggested fixes
  - [ ] Timestamp of last run
- [ ] Create "Run All Tests" button
  - [ ] Execute all tests sequentially
  - [ ] Show overall progress
  - [ ] Display summary of results

### 5.6 Integrate into SysAdminDashboard

- [ ] Update `frontend/src/components/SysAdmin/SysAdminDashboard.tsx`
- [ ] Add "Diagnostics" tab (optional, or integrate into Health Check)
- [ ] Import DiagnosticTests component
- [ ] Add tab content

### 5.7 Testing

- [ ] Test each diagnostic test
- [ ] Test "Run All" functionality
- [ ] Test error handling
- [ ] Test result display
- [ ] Test responsive design

**Estimated Time**: 2-3 days

---

## Phase 6: Polish & Testing (1-2 days)

### 6.1 UI/UX Improvements

- [ ] Add tooltips to all buttons and controls
- [ ] Add help text and documentation links
- [ ] Improve loading states (skeleton loaders)
- [ ] Improve error messages (actionable, helpful)
- [ ] Add keyboard shortcuts (e.g., Ctrl+Enter to send request)
- [ ] Add dark mode support (if not already)

### 6.2 Accessibility

- [ ] Add ARIA labels to all interactive elements
- [ ] Test keyboard navigation
- [ ] Test with screen reader
- [ ] Ensure color contrast meets WCAG AA
- [ ] Add focus indicators

### 6.3 Mobile Responsiveness

- [ ] Test on mobile devices
- [ ] Adjust layouts for small screens
- [ ] Ensure touch-friendly controls
- [ ] Test on tablets

### 6.4 Performance Optimization

- [ ] Optimize health check caching
- [ ] Debounce auto-refresh
- [ ] Lazy load components
- [ ] Optimize re-renders

### 6.5 Security Review

- [ ] Review all endpoints for authorization
- [ ] Review data masking in logs
- [ ] Review input validation
- [ ] Review rate limiting
- [ ] Conduct security testing

### 6.6 Documentation

- [ ] Write user guide for Health Check
- [ ] Write user guide for API Testing
- [ ] Write user guide for Diagnostic Tests
- [ ] Update API documentation (Swagger)
- [ ] Write troubleshooting guide
- [ ] Write developer guide for adding new health checks

### 6.7 Testing

- [ ] Run full E2E test suite
- [ ] Test all user workflows
- [ ] Test error scenarios
- [ ] Test edge cases
- [ ] Performance testing
- [ ] Security testing

### 6.8 Deployment

- [ ] Update environment variables (if needed)
- [ ] Update database schema (if needed)
- [ ] Deploy backend changes
- [ ] Deploy frontend changes
- [ ] Verify in production

**Estimated Time**: 1-2 days

---

## Summary

**Total Estimated Time**: 8-12 days

**Priority**:

1. Health Check (most valuable for monitoring)
2. Diagnostic Tests (quick troubleshooting)
3. API Testing (nice-to-have, can use Postman as alternative)

**Dependencies**:

- Existing SysAdmin infrastructure
- AWS Cognito authentication
- Database access
- External API credentials (Google Drive, OpenRouter)

**Risks**:

- Health checks could impact system performance (mitigate with caching)
- API testing could be misused (mitigate with strict authorization)
- Complexity could overwhelm users (mitigate with progressive disclosure)
