# Health Check & API Testing - Design

**Status**: Draft
**Created**: February 9, 2026
**Last Updated**: February 9, 2026

---

## Architecture Overview

The Health Check and API Testing features will be implemented as two new tabs in the SysAdminDashboard, following the existing pattern of Tenant Management and Role Management.

```
SysAdminDashboard
├── Tenant Management (existing)
├── Role Management (existing)
├── Health Check (new)
└── API Testing (new)
```

## Component Structure

### Frontend Components

```
frontend/src/components/SysAdmin/
├── HealthCheck.tsx           # Health monitoring dashboard
├── APITesting.tsx            # API endpoint testing interface
├── EndpointStatusCheck.tsx   # Bulk endpoint testing
└── DiagnosticTests.tsx       # Pre-built diagnostic tests
```

### Backend Endpoints

```
backend/src/routes/
├── sysadmin_health.py        # Health check endpoints
├── sysadmin_api_test.py      # API testing proxy (optional)
└── sysadmin_endpoints.py     # Endpoint status check
```

## Data Models

### Health Check Response

```typescript
interface HealthStatus {
  service: string;
  status: "healthy" | "degraded" | "unhealthy";
  responseTime: number; // milliseconds
  message?: string;
  lastChecked: string; // ISO timestamp
  details?: Record<string, any>;
}

interface SystemHealth {
  overall: "healthy" | "degraded" | "unhealthy";
  services: HealthStatus[];
  timestamp: string;
}
```

### Endpoint Status Check

```typescript
interface EndpointDefinition {
  id: string;
  category: string; // 'tenant' | 'role' | 'module' | 'user' | 'health' | 'report'
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  description: string;
  requiresTenant: boolean;
  sampleBody?: any;
}

interface EndpointTestResult {
  endpoint: EndpointDefinition;
  status: "pass" | "fail";
  statusCode: number;
  responseTime: number;
  error?: string;
  timestamp: string;
}

interface BulkTestResult {
  totalEndpoints: number;
  passed: number;
  failed: number;
  averageResponseTime: number;
  results: EndpointTestResult[];
  timestamp: string;
}
```

### API Test Configuration

```typescript
interface APITestConfig {
  id: string;
  name: string;
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  endpoint: string;
  headers: Record<string, string>;
  body?: string; // JSON string
  tenant?: string; // For X-Tenant header
  timeout: number; // milliseconds
}

interface APITestResult {
  config: APITestConfig;
  statusCode: number;
  responseTime: number;
  responseHeaders: Record<string, string>;
  responseBody: any;
  error?: string;
  timestamp: string;
}
```

## API Specifications

### Health Check Endpoints

#### GET /api/sysadmin/health

Get overall system health status

**Authorization**: SysAdmin role required

**Response**:

```json
{
  "overall": "healthy",
  "services": [
    {
      "service": "database",
      "status": "healthy",
      "responseTime": 12,
      "message": "Connected to MySQL 8.0",
      "lastChecked": "2026-02-09T10:30:00Z",
      "details": {
        "host": "localhost",
        "database": "finance",
        "connections": 5
      }
    },
    {
      "service": "cognito",
      "status": "healthy",
      "responseTime": 145,
      "message": "AWS Cognito accessible",
      "lastChecked": "2026-02-09T10:30:00Z"
    },
    {
      "service": "sns",
      "status": "healthy",
      "responseTime": 98,
      "message": "AWS SNS accessible",
      "lastChecked": "2026-02-09T10:30:00Z"
    },
    {
      "service": "google_drive",
      "status": "degraded",
      "responseTime": 2340,
      "message": "Slow response time",
      "lastChecked": "2026-02-09T10:30:00Z"
    },
    {
      "service": "openrouter",
      "status": "healthy",
      "responseTime": 234,
      "message": "OpenRouter API accessible",
      "lastChecked": "2026-02-09T10:30:00Z"
    }
  ],
  "timestamp": "2026-02-09T10:30:00Z"
}
```

#### GET /api/sysadmin/health/history

Get health check history (last 24 hours)

**Authorization**: SysAdmin role required

**Query Parameters**:

- `hours` (optional): Number of hours to retrieve (default: 24, max: 168)

**Response**:

```json
{
  "history": [
    {
      "timestamp": "2026-02-09T10:30:00Z",
      "overall": "healthy",
      "services": { ... }
    },
    ...
  ]
}
```

### API Testing Endpoints

#### POST /api/sysadmin/api-test

Execute an API test (proxy through backend for security)

**Authorization**: SysAdmin role required

**Request Body**:

```json
{
  "method": "GET",
  "endpoint": "/api/sysadmin/tenants",
  "headers": {
    "X-Tenant": "GoodwinSolutions"
  },
  "body": null,
  "timeout": 30000
}
```

**Response**:

```json
{
  "statusCode": 200,
  "responseTime": 145,
  "responseHeaders": {
    "content-type": "application/json",
    "content-length": "1234"
  },
  "responseBody": { ... },
  "timestamp": "2026-02-09T10:30:00Z"
}
```

### Diagnostic Test Endpoints

#### GET /api/sysadmin/diagnostics

Get list of available diagnostic tests

**Authorization**: SysAdmin role required

**Response**:

```json
{
  "tests": [
    {
      "id": "auth-test",
      "name": "Authentication Test",
      "description": "Verify Cognito authentication flow",
      "category": "authentication"
    },
    {
      "id": "tenant-access-test",
      "name": "Tenant Access Test",
      "description": "Verify tenant context and data access",
      "category": "authorization"
    },
    ...
  ]
}
```

#### POST /api/sysadmin/diagnostics/{test_id}

Run a specific diagnostic test

**Authorization**: SysAdmin role required

**Response**:

```json
{
  "testId": "auth-test",
  "status": "passed",
  "message": "Authentication successful",
  "details": {
    "user": "admin@example.com",
    "roles": ["SysAdmin"],
    "tokenExpiry": "2026-02-09T11:30:00Z"
  },
  "timestamp": "2026-02-09T10:30:00Z"
}
```

## UI Design

### Health Check Tab

**Layout**:

```
┌─────────────────────────────────────────────────────────┐
│ Health Check                          [Auto-refresh: Off]│
│                                       [Refresh Now]       │
├─────────────────────────────────────────────────────────┤
│ Overall Status: ● Healthy                                │
│ Last checked: 2 minutes ago                              │
├─────────────────────────────────────────────────────────┤
│ Service          Status      Response Time   Details     │
│ ─────────────────────────────────────────────────────── │
│ ● Database       Healthy     12ms            [View]      │
│ ● AWS Cognito    Healthy     145ms           [View]      │
│ ● AWS SNS        Healthy     98ms            [View]      │
│ ⚠ Google Drive   Degraded    2340ms          [View]      │
│ ● OpenRouter     Healthy     234ms           [View]      │
└─────────────────────────────────────────────────────────┘
```

**Features**:

- Color-coded status indicators (green, yellow, red)
- Expandable details for each service
- Auto-refresh toggle with interval selector
- Manual refresh button
- Export health report button

### API Testing Tab

**Layout**:

```
┌─────────────────────────────────────────────────────────┐
│ API Testing                                              │
├─────────────────────────────────────────────────────────┤
│ Method: [GET ▼]  Endpoint: [/api/sysadmin/tenants    ] │
│                                                          │
│ Headers:                                    [+ Add]      │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Authorization: Bearer eyJ...                       │ │
│ │ X-Tenant: [GoodwinSolutions ▼]                    │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ Body (JSON):                                             │
│ ┌────────────────────────────────────────────────────┐ │
│ │ {                                                  │ │
│ │   "page": 1,                                       │ │
│ │   "per_page": 10                                   │ │
│ │ }                                                  │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ [Send Request]  [Save Config]  [Load Config ▼]          │
├─────────────────────────────────────────────────────────┤
│ Response:                                                │
│ Status: 200 OK (145ms)                                   │
│ ┌────────────────────────────────────────────────────┐ │
│ │ {                                                  │ │
│ │   "tenants": [...],                                │ │
│ │   "total": 5                                       │ │
│ │ }                                                  │ │
│ └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Features**:

- HTTP method selector
- Endpoint input with autocomplete
- Header management (add/remove)
- JSON body editor with syntax highlighting
- Tenant context selector
- Save/load test configurations
- Request history sidebar
- Response viewer with formatting

### Diagnostic Tests Tab (Optional)

**Layout**:

```
┌─────────────────────────────────────────────────────────┐
│ Diagnostic Tests                                         │
├─────────────────────────────────────────────────────────┤
│ Quick Diagnostics:                                       │
│                                                          │
│ ┌──────────────────────────┐ ┌──────────────────────┐  │
│ │ Authentication Test      │ │ Tenant Access Test   │  │
│ │ Verify Cognito login     │ │ Verify tenant data   │  │
│ │ [Run Test]               │ │ [Run Test]           │  │
│ └──────────────────────────┘ └──────────────────────┘  │
│                                                          │
│ ┌──────────────────────────┐ ┌──────────────────────┐  │
│ │ User Management Test     │ │ File Upload Test     │  │
│ │ Test user CRUD ops       │ │ Test file storage    │  │
│ │ [Run Test]               │ │ [Run Test]           │  │
│ └──────────────────────────┘ └──────────────────────┘  │
│                                                          │
│ Test Results:                                            │
│ ┌────────────────────────────────────────────────────┐ │
│ │ ✓ Authentication Test - Passed (234ms)             │ │
│ │   User: admin@example.com                          │ │
│ │   Roles: SysAdmin                                  │ │
│ └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Health Check (2-3 days)

1. Backend health check endpoint
2. Frontend HealthCheck component
3. Service status indicators
4. Manual refresh functionality

### Phase 2: API Testing (3-4 days)

1. Frontend APITesting component
2. Request builder interface
3. Response viewer
4. Save/load configurations
5. Request history

### Phase 3: Diagnostic Tests (2-3 days)

1. Backend diagnostic endpoints
2. Frontend DiagnosticTests component
3. Pre-built test suite
4. Test result display

### Phase 4: Polish & Enhancement (1-2 days)

1. Auto-refresh for health checks
2. Export functionality
3. Mobile responsiveness
4. Accessibility improvements

## Security Considerations

1. **Authentication**: All endpoints require SysAdmin role
2. **Authorization**: Verify user has SysAdmin group membership
3. **Data Masking**: Mask sensitive data in responses (passwords, tokens)
4. **Audit Logging**: Log all health checks and API tests
5. **Rate Limiting**: Prevent abuse of testing endpoints
6. **Input Validation**: Sanitize all user inputs
7. **CORS**: Restrict API testing to same-origin requests

## Performance Considerations

1. **Caching**: Cache health check results for 30 seconds
2. **Async Execution**: Run health checks asynchronously
3. **Timeouts**: Set reasonable timeouts for all checks (5s default)
4. **Throttling**: Limit frequency of health checks per user
5. **Connection Pooling**: Reuse database connections

## Error Handling

1. **Service Unavailable**: Show degraded status, not complete failure
2. **Timeout**: Display timeout message with retry option
3. **Network Errors**: Clear error messages with troubleshooting tips
4. **Invalid Requests**: Validation errors with helpful messages
5. **Permission Denied**: Clear authorization error messages

## Testing Strategy

1. **Unit Tests**: Test individual health check functions
2. **Integration Tests**: Test health check endpoints
3. **E2E Tests**: Test full user workflows
4. **Security Tests**: Verify role-based access control
5. **Performance Tests**: Verify health checks don't impact system

## Documentation

1. **User Guide**: How to use health check and API testing
2. **API Documentation**: Swagger/OpenAPI specs for new endpoints
3. **Troubleshooting Guide**: Common issues and solutions
4. **Developer Guide**: How to add new health checks

### Endpoint Status Check Endpoints

#### GET /api/sysadmin/endpoints

Get list of all testable endpoints

**Authorization**: SysAdmin role required

**Response**:

```json
{
  "endpoints": [
    {
      "id": "list-tenants",
      "category": "tenant",
      "method": "GET",
      "path": "/api/sysadmin/tenants",
      "description": "List all tenants with pagination",
      "requiresTenant": false
    },
    {
      "id": "get-tenant",
      "category": "tenant",
      "method": "GET",
      "path": "/api/sysadmin/tenants/{administration}",
      "description": "Get specific tenant details",
      "requiresTenant": false
    },
    {
      "id": "create-tenant",
      "category": "tenant",
      "method": "POST",
      "path": "/api/sysadmin/tenants",
      "description": "Create new tenant",
      "requiresTenant": false,
      "sampleBody": {
        "administration": "test-tenant",
        "display_name": "Test Tenant",
        "contact_email": "test@example.com",
        "enabled_modules": ["FIN"]
      }
    },
    {
      "id": "list-roles",
      "category": "role",
      "method": "GET",
      "path": "/api/sysadmin/roles",
      "description": "List all Cognito roles",
      "requiresTenant": false
    },
    {
      "id": "list-tenant-users",
      "category": "user",
      "method": "GET",
      "path": "/api/tenant-admin/users",
      "description": "List users in tenant",
      "requiresTenant": true
    },
    {
      "id": "system-health",
      "category": "health",
      "method": "GET",
      "path": "/api/sysadmin/health",
      "description": "Check system health",
      "requiresTenant": false
    }
  ],
  "categories": [
    { "id": "tenant", "name": "Tenant Management", "count": 5 },
    { "id": "role", "name": "Role Management", "count": 3 },
    { "id": "module", "name": "Module Management", "count": 2 },
    { "id": "user", "name": "User Management", "count": 6 },
    { "id": "health", "name": "Health & Diagnostics", "count": 2 }
  ]
}
```

#### POST /api/sysadmin/endpoints/test-all

Test all endpoints in bulk

**Authorization**: SysAdmin role required

**Request Body**:

```json
{
  "tenant": "GoodwinSolutions", // Optional: tenant context for tenant-scoped endpoints
  "categories": ["tenant", "role"], // Optional: filter by categories
  "skipDestructive": true // Optional: skip POST/PUT/DELETE operations
}
```

**Response**:

```json
{
  "totalEndpoints": 15,
  "passed": 13,
  "failed": 2,
  "averageResponseTime": 234,
  "results": [
    {
      "endpoint": {
        "id": "list-tenants",
        "category": "tenant",
        "method": "GET",
        "path": "/api/sysadmin/tenants",
        "description": "List all tenants with pagination"
      },
      "status": "pass",
      "statusCode": 200,
      "responseTime": 145,
      "timestamp": "2026-02-09T10:30:00Z"
    },
    {
      "endpoint": {
        "id": "get-tenant",
        "category": "tenant",
        "method": "GET",
        "path": "/api/sysadmin/tenants/myAdmin",
        "description": "Get specific tenant details"
      },
      "status": "pass",
      "statusCode": 200,
      "responseTime": 89,
      "timestamp": "2026-02-09T10:30:01Z"
    },
    {
      "endpoint": {
        "id": "list-tenant-users",
        "category": "user",
        "method": "GET",
        "path": "/api/tenant-admin/users",
        "description": "List users in tenant"
      },
      "status": "fail",
      "statusCode": 500,
      "responseTime": 1234,
      "error": "Internal server error: Database connection timeout",
      "timestamp": "2026-02-09T10:30:02Z"
    }
  ],
  "timestamp": "2026-02-09T10:30:00Z"
}
```

#### POST /api/sysadmin/endpoints/test-one

Test a single endpoint

**Authorization**: SysAdmin role required

**Request Body**:

```json
{
  "endpointId": "list-tenants",
  "tenant": "GoodwinSolutions",  // Optional
  "customBody": { ... }  // Optional: override sample body
}
```

**Response**:

```json
{
  "endpoint": {
    "id": "list-tenants",
    "category": "tenant",
    "method": "GET",
    "path": "/api/sysadmin/tenants",
    "description": "List all tenants with pagination"
  },
  "status": "pass",
  "statusCode": 200,
  "responseTime": 145,
  "responseBody": { ... },
  "timestamp": "2026-02-09T10:30:00Z"
}
```

## UI Design (Updated)

### Endpoint Status Check Tab

**Layout**:

```
┌─────────────────────────────────────────────────────────────────┐
│ Endpoint Status Check                                            │
├─────────────────────────────────────────────────────────────────┤
│ [Test All Endpoints]  [Re-test Failed]  [Export Results]        │
│                                                                   │
│ Endpoint: [All Endpoints ▼]  Category: [All ▼]  Tenant: [▼]     │
│                                                                   │
│ ☐ Skip destructive operations (POST/PUT/DELETE)                  │
├─────────────────────────────────────────────────────────────────┤
│ Results: 13/15 passed (87%)  Avg Response: 234ms                 │
│                                                                   │
│ Filter: [All] [Passed] [Failed] [Slow (>1s)]                     │
├─────────────────────────────────────────────────────────────────┤
│ Category         Endpoint                Status    Time    Action│
│ ──────────────────────────────────────────────────────────────  │
│ Tenant Mgmt      GET /tenants            ✓ 200    145ms   [Test]│
│ Tenant Mgmt      GET /tenants/{id}       ✓ 200    89ms    [Test]│
│ Tenant Mgmt      POST /tenants           ✓ 201    234ms   [Test]│
│ Role Mgmt        GET /roles              ✓ 200    123ms   [Test]│
│ User Mgmt        GET /users              ✗ 500    1234ms  [Test]│
│                  Error: Database timeout                         │
│ Module Mgmt      GET /modules            ✓ 200    98ms    [Test]│
│ Health           GET /health             ✓ 200    45ms    [Test]│
└─────────────────────────────────────────────────────────────────┘
```

**Features**:

1. **Test All Button**: Executes all endpoint tests sequentially
   - Shows progress bar during execution
   - Updates results in real-time
   - Can be cancelled mid-execution

2. **Endpoint Selector Dropdown**:
   - Lists all available endpoints grouped by category
   - Shows endpoint method and path
   - Includes description on hover
   - Select to test individual endpoint

3. **Category Filter**:
   - Filter by: All, Tenant Management, Role Management, Module Management, User Management, Health

4. **Tenant Context Selector**:
   - Select tenant for tenant-scoped endpoints
   - Auto-populated from available tenants
   - Optional (only needed for tenant-scoped tests)

5. **Skip Destructive Operations**:
   - Checkbox to skip POST/PUT/DELETE operations
   - Useful for production testing
   - Only tests read operations (GET)

6. **Results Table**:
   - Category column (grouped)
   - Endpoint column (method + path)
   - Status column (✓/✗ with status code)
   - Response time column (color-coded: green <500ms, yellow <1s, red >1s)
   - Action column (individual test button)
   - Expandable error details for failed tests

7. **Result Filters**:
   - Show all results
   - Show only passed
   - Show only failed
   - Show only slow (>1s)

8. **Re-test Failed Button**:
   - Re-runs only endpoints that failed
   - Useful after fixing issues

9. **Export Results Button**:
   - Export as JSON
   - Export as CSV
   - Include timestamp and summary

### Integration with Existing Tabs

The Endpoint Status Check can be:

- **Option A**: Separate tab in SysAdminDashboard
- **Option B**: Integrated into Health Check tab as "API Endpoints" section
- **Option C**: Integrated into API Testing tab as "Bulk Test" mode

**Recommendation**: Option A (separate tab) for clarity and focus.

## Implementation Notes

### Backend Implementation

1. **Endpoint Registry**: Maintain a registry of all testable endpoints
   - Can be hardcoded or auto-discovered from Flask routes
   - Include metadata (category, description, sample body)

2. **Test Execution**:
   - Execute tests sequentially to avoid overwhelming the system
   - Use actual API calls (not mocked)
   - Inject authentication headers automatically
   - Handle tenant context switching

3. **Safety Measures**:
   - Skip destructive operations by default in production
   - Use test data for POST/PUT operations
   - Clean up test data after execution
   - Add rate limiting to prevent abuse

### Frontend Implementation

1. **Progress Tracking**:
   - Show progress bar during bulk testing
   - Update results in real-time as tests complete
   - Allow cancellation of in-progress tests

2. **Result Visualization**:
   - Color-coded status indicators
   - Sortable and filterable table
   - Expandable error details
   - Response time visualization (bar chart)

3. **State Management**:
   - Store test results in component state
   - Persist last test results in localStorage
   - Clear results on new test execution

### Security Considerations

1. **Authorization**: Only SysAdmin can access endpoint testing
2. **Audit Logging**: Log all endpoint tests with user and timestamp
3. **Rate Limiting**: Limit bulk tests to once per minute
4. **Data Safety**: Use test tenant/data for destructive operations
5. **Error Masking**: Don't expose sensitive error details to frontend
