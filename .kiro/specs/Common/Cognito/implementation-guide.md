### Phase 0: 🚨 CRITICAL - Implement Authentication (1-2 days)

**Goal**: Implement AWS Cognito authentication BEFORE any production deployment

**MUST COMPLETE BEFORE PROCEEDING TO PHASE 1**

**⭐ Recommended: AWS Cognito (Production-Ready Solution!)**

1. ✅ Create Cognito User Pool in AWS Console or CLI
   ```bash
   aws cognito-idp create-user-pool --pool-name myAdmin-users --region eu-west-1
   ```
2. ✅ Create App Client for myAdmin
   ```bash
   aws cognito-idp create-user-pool-client --user-pool-id <ID> --client-name myAdmin-web
   ```
3. ✅ Install required packages:
   ```bash
   pip install warrant pyjwt
   # boto3 already installed
   ```
4. ✅ Create Cognito helper and authentication routes:
   - `/api/auth/login` - User login with Cognito
   - `/api/auth/logout` - User logout
   - `/api/auth/check` - Check authentication status
5. ✅ Protect all API routes with `@cognito_required` decorator
6. ✅ Create login page in React frontend with token storage
7. ✅ Test authentication locally with Docker Compose
8. ✅ Create initial admin user via AWS CLI:
   ```bash
   aws cognito-idp admin-create-user --user-pool-id <ID> --username admin
   ```

**Deliverables**:

- Working Cognito login/logout functionality
- All API endpoints protected with JWT token verification
- Frontend login page with token management
- At least one admin user created in Cognito

# AWS Cognito Authentication & Authorization Implementation Guide

## Overview

This document provides a comprehensive functional and technical design for implementing AWS Cognito-based authentication and authorization in serverless applications. It's based on a production implementation for a membership management system but designed to be reusable for other projects.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Role-Based Access Control (RBAC) Design](#role-based-access-control-rbac-design)
3. [Backend Implementation](#backend-implementation)
4. [Frontend Implementation](#frontend-implementation)
5. [Key Code References](#key-code-references)
6. [Deployment Configuration](#deployment-configuration)
7. [Best Practices & Tips](#best-practices--tips)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ AWS Amplify  │  │ Auth Service │  │  Auth Context/Hook   │  │
│  │   (v6)       │  │  (JWT Utils) │  │  (State Management)  │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS + JWT Token
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway (REST API)                        │
│                    CORS + Authorization                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Lambda Functions                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Shared Auth Layer (Lambda Layer)            │  │
│  │  • JWT Token Decoding                                    │  │
│  │  • Role Extraction (cognito:groups)                      │  │
│  │  • Permission Validation                                 │  │
│  │  • Tenant Access Control                               │  │
│  │  • Audit Logging                                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Business Logic Handlers                     │  │
│  │  • Extract credentials                                   │  │
│  │  • Validate permissions                                  │  │
│  │  • Execute business logic                                │  │
│  │  • Return response                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AWS Cognito User Pool                       │
│  • User Management                                               │
│  • Groups (Roles)                                                │
│  • JWT Token Generation                                          │
│  • Lambda Triggers (Custom Messages, Post-Auth, etc.)           │
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

1. **AWS Cognito User Pool**: Central authentication service
2. **Cognito Groups**: Used as roles for RBAC
3. **JWT Tokens**: Contain user identity and roles in `cognito:groups` claim
4. **Lambda Layer**: Shared authentication utilities across all handlers
5. **API Gateway**: Entry point with CORS configuration
6. **Lambda Functions**: Business logic with built-in authorization

---

## Role-Based Access Control (RBAC) Design

### Role Structure

Our implementation uses a **two-dimensional role structure**:

1. **Permission Roles**: Define WHAT users can do
2. **Tenant Roles**: Define WHERE users can operate (optional, for multi-tenant scenarios)

#### Permission Roles

```
System Roles (Full Access):
├── System_CRUD                    # Full system access
├── System_User_Management         # User and role management
└── System_Logs_Read              # Audit log access

Resource Permission Roles:
├── Finance_CRUD                   # Create, Read, Update, Delete financial data
├── Finance_Read                   # Read-only financial access
├── Finance_Export                 # Export financial data
├── STR_CRUD                       # Full short-term rental management
├── STR_Read                       # Read-only STR access
├── STR_Export                     # Export STR data
├── Products_CRUD                  # Full product management
├── Webshop_Management            # Complete webshop access
└── Communication_CRUD            # Communication management

Basic myAdmin User Roles:
├── myAdminUsers                  # Regular users (self-service access)
└── myAdminApplicants             # Applicants (limited self-service)
```

#### Tenant Roles (Multi-Tenant Support)

```
Tenant Access:
├── Tenant_All                    # Access to all tenants
├── Tenant_PeterPrive             # PeterPrive tenant only
├── Tenant_GoodwinSolutions       # GoodwinSolutions tenant only
└── (Add more tenants as needed)
```

### Permission Mapping

The auth layer maps roles to specific permissions:

```python
role_permissions = {
    # System roles
    'System_CRUD': ['*'],  # All permissions
    'System_User_Management': ['users_manage', 'roles_assign'],

    # Resource permissions
    'Finance_CRUD': [
        'finance_create', 'finance_read',
        'finance_update', 'finance_delete', 'finance_export'
    ],
    'Finance_Read': ['finance_read', 'finance_list'],

    # Basic user permissions
    'myAdminUsers': [
        'profile_read', 'profile_update_own',
        'invoices_self_read', 'invoices_self_update',
        'reports_read', 'reports_list',
        'dashboard_read'
    ],

    'myAdminApplicants': [
        'profile_self_read', 'profile_self_create', 'profile_self_update'
    ]
}
```

### Role Validation Rules

1. **System roles** bypass all tenant requirements
2. **Permission roles** require tenant roles (except basic user roles)
3. **Basic user roles** (myAdminUsers, myAdminApplicants) don't require tenant roles
4. Users can have multiple permission roles but should have consistent tenant access

---

## Backend Implementation

### 1. Shared Authentication Layer

**Location**: `backend/layers/auth-layer/python/shared/auth_utils.py`

This is the core of the authentication system, packaged as a Lambda Layer for reuse across all functions.

#### Key Functions

##### Extract User Credentials

```python
def extract_user_credentials(event):
    """
    Extract user credentials from Lambda event

    Returns:
        tuple: (user_email, user_roles, error_response)
    """
    # 1. Extract Authorization header
    headers = event.get('headers', {})
    auth_header = headers.get('Authorization')

    # 2. Validate Bearer token format
    if not auth_header or not auth_header.startswith('Bearer '):
        return None, None, error_response

    # 3. Extract and decode JWT token
    jwt_token = auth_header.replace('Bearer ', '')
    parts = jwt_token.split('.')

    # 4. Decode payload (base64)
    payload_encoded = parts[1]
    payload_encoded += '=' * (4 - len(payload_encoded) % 4)
    payload_decoded = base64.urlsafe_b64decode(payload_encoded)
    payload = json.loads(payload_decoded)

    # 5. Extract user email and roles
    user_email = payload.get('email') or payload.get('username')
    user_roles = payload.get('cognito:groups', [])

    return user_email, user_roles, None
```

##### Validate Permissions

```python
def validate_permissions_with_tenants(
    user_roles,
    required_permissions,
    user_email=None,
    resource_context=None
):
    """
    Validate user has required permissions and tenant access

    Returns:
        tuple: (is_authorized, error_response, tenant_info)
    """
    # 1. Check for system admin roles (full access)
    if any(role in ['System_CRUD', 'System_User_Management'] for role in user_roles):
        return True, None, {'has_full_access': True}

    # 2. Validate permissions
    is_authorized, error = validate_permissions(user_roles, required_permissions)
    if not is_authorized:
        return False, error, None

    # 3. Determine tenant access
    tenant_info = determine_tenant_access(user_roles, resource_context)

    return True, None, tenant_info
```

##### CORS Headers

```python
def cors_headers():
    """Standard CORS headers for all API responses"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE,PATCH",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Enhanced-Groups",
        "Access-Control-Allow-Credentials": "false"
    }
```

### 2. Lambda Handler Pattern

**Example**: `backend/handler/get_finance_data/app.py`

Every Lambda handler follows this pattern:

```python
import json
import boto3

# Import from shared auth layer
from shared.auth_utils import (
    extract_user_credentials,
    validate_permissions_with_tenants,
    cors_headers,
    handle_options_request,
    create_error_response,
    create_success_response,
    log_successful_access
)

def lambda_handler(event, context):
    """
    Standard Lambda handler with authentication
    """
    try:
        # 1. Handle OPTIONS request (CORS preflight)
        if event.get('httpMethod') == 'OPTIONS':
            return handle_options_request()

        # 2. Extract user credentials from JWT token
        user_email, user_roles, auth_error = extract_user_credentials(event)
        if auth_error:
            return auth_error

        # 3. Validate permissions
        is_authorized, error_response, tenant_info = validate_permissions_with_tenants(
            user_roles,
            ['finance_read'],  # Required permissions
            user_email,
            {'operation': 'get_finance_data'}
        )
        if not is_authorized:
            return error_response

        # 4. Log successful access (audit trail)
        log_successful_access(user_email, user_roles, 'get_finance_data')

        # 5. Execute business logic
        result = execute_business_logic(event, user_email, user_roles, tenant_info)

        # 6. Return success response
        return create_success_response(result)

    except Exception as e:
        print(f"Error: {str(e)}")
        return create_error_response(500, 'Internal server error')
```

### 3. Cognito Admin Handler

**Location**: `backend/handler/myAdmin_cognito_admin/app.py`

This handler provides user and role management capabilities:

**Key Endpoints**:

- `GET /cognito/users` - List all users
- `POST /cognito/users` - Create new user
- `GET /cognito/users/{username}/groups` - Get user's roles
- `POST /cognito/users/{username}/groups/{groupName}` - Assign role
- `DELETE /cognito/users/{username}/groups/{groupName}` - Remove role
- `GET /cognito/groups` - List all available roles

**Role Assignment Validation**:

```python
def validate_role_assignment_rules(user_id, role, requesting_user):
    """
    Validate business rules for role assignments
    """
    # 1. Prevent conflicting roles
    # 2. Prevent self-assignment of admin roles
    # 3. Validate tenant role requirements

    return True  # or False with reason
```

### 4. SAM Template Configuration

**Location**: `backend/template.yaml`

#### Lambda Layer Definition

```yaml
Resources:
  AuthLayer:
    Type: AWS::Serverless::LayerVersion
    Properties:
      LayerName: !Sub "${AWS::StackName}-auth-layer"
      Description: "Shared authentication utilities"
      ContentUri: layers/auth-layer/
      CompatibleRuntimes:
        - python3.11
      RetentionPolicy: Retain
```

#### Lambda Function with Auth Layer

```yaml
GetFinanceDataFunction:
  Type: AWS::Serverless::Function
  Properties:
    CodeUri: handler/get_finance_data
    Handler: app.lambda_handler
    Runtime: python3.11
    Layers:
      - !Ref AuthLayer # Include auth layer
    Role: !GetAtt DynamoDBRole.Arn
    Events:
      GetFinanceData:
        Type: Api
        Properties:
          RestApiId: !Ref MyApi
          Path: /finance/data
          Method: get
```

#### IAM Roles

```yaml
# Role for regular Lambda functions
DynamoDBRole:
  Type: AWS::IAM::Role
  Properties:
    Policies:
      - PolicyName: CognitoReadAccess
        PolicyDocument:
          Statement:
            - Effect: Allow
              Action:
                - cognito-idp:AdminGetUser
                - cognito-idp:AdminListGroupsForUser
              Resource: !Sub "arn:aws:cognito-idp:${AWS::Region}:${AWS::AccountId}:userpool/*"

# Role for Cognito admin functions
CognitoAdminRole:
  Type: AWS::IAM::Role
  Properties:
    Policies:
      - PolicyName: CognitoAdminAccess
        PolicyDocument:
          Statement:
            - Effect: Allow
              Action:
                - cognito-idp:ListUsers
                - cognito-idp:AdminCreateUser
                - cognito-idp:AdminAddUserToGroup
                - cognito-idp:AdminRemoveUserFromGroup
                - cognito-idp:ListGroups
                - cognito-idp:CreateGroup
              Resource: !Sub "arn:aws:cognito-idp:${AWS::Region}:${AWS::AccountId}:userpool/*"
```

#### Global CORS Configuration

```yaml
Globals:
  Api:
    Cors:
      AllowMethods: "'OPTIONS,GET,POST,PUT,DELETE,PATCH'"
      AllowHeaders: "'Content-Type,Authorization,X-Enhanced-Groups'"
      AllowOrigin: "'*'"
      AllowCredentials: false
```

---

## Frontend Implementation

### 1. AWS Amplify Configuration

**Location**: `frontend/src/aws-exports.ts`

```typescript
const awsconfig = {
  Auth: {
    Cognito: {
      userPoolId: "eu-west-1_XXXXXXX",
      userPoolClientId: "xxxxxxxxxxxxxxxxxx",
      loginWith: {
        oauth: {
          domain: "your-domain.auth.eu-west-1.amazoncognito.com",
          scopes: ["openid", "email", "profile"],
          redirectSignIn: ["http://localhost:3000/", "https://yourdomain.com/"],
          redirectSignOut: [
            "http://localhost:3000/",
            "https://yourdomain.com/",
          ],
          responseType: "code",
        },
      },
    },
  },
};

export default awsconfig;
```

### 2. Authentication Service

**Location**: `frontend/src/services/authService.ts`

#### JWT Token Utilities

```typescript
export interface JWTPayload {
  "cognito:groups"?: string[];
  username?: string;
  email?: string;
  sub?: string;
  exp?: number;
}

/**
 * Decode JWT payload from token string
 */
export function decodeJWTPayload(token: string): JWTPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    // Decode payload (second part)
    const payload = parts[1];
    const paddedPayload = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    const decodedPayload = JSON.parse(atob(paddedPayload));

    return decodedPayload as JWTPayload;
  } catch (error) {
    console.error("Failed to decode JWT:", error);
    return null;
  }
}

/**
 * Get current authentication tokens from Amplify
 */
export async function getCurrentAuthTokens(): Promise<AuthTokens | null> {
  try {
    const session = await fetchAuthSession();

    if (!session.tokens) return null;

    return {
      idToken: session.tokens.idToken?.toString(),
      accessToken: session.tokens.accessToken?.toString(),
    };
  } catch (error) {
    console.error("Failed to get auth tokens:", error);
    return null;
  }
}

/**
 * Extract user roles from JWT token
 */
export async function getCurrentUserRoles(): Promise<string[]> {
  try {
    const tokens = await getCurrentAuthTokens();
    if (!tokens?.accessToken) return [];

    const payload = decodeJWTPayload(tokens.accessToken);
    if (!payload) return [];

    return payload["cognito:groups"] || [];
  } catch (error) {
    console.error("Failed to extract user roles:", error);
    return [];
  }
}
```

#### Role Validation

```typescript
/**
 * Validate role combinations
 */
export function validateRoleCombinations(roles: string[]): {
  isValid: boolean;
  hasPermissions: boolean;
  hasTenants: boolean;
  missingRoles: string[];
} {
  const permissionRoles = roles.filter(
    (role) =>
      role.includes("_CRUD") ||
      role.includes("_Read") ||
      role.includes("_Export"),
  );

  const tenantRoles = roles.filter((role) => role.startsWith("Tenant_"));
  const systemRoles = roles.filter((role) => role.startsWith("System_"));
  const basicRoles = roles.filter((role) =>
    ["myAdminUsers", "myAdminApplicants"].includes(role),
  );

  // System roles bypass all requirements
  if (systemRoles.length > 0) {
    return {
      isValid: true,
      hasPermissions: true,
      hasTenants: true,
      missingRoles: [],
    };
  }

  // Basic roles don't need additional permissions
  if (basicRoles.length > 0 && permissionRoles.length === 0) {
    return {
      isValid: true,
      hasPermissions: false,
      hasTenants: true,
      missingRoles: [],
    };
  }

  // Permission roles require tenant roles
  const missingRoles: string[] = [];
  if (permissionRoles.length > 0 && tenantRoles.length === 0) {
    missingRoles.push("Tenant role (Tenant_*)");
  }

  return {
    isValid: missingRoles.length === 0,
    hasPermissions: permissionRoles.length > 0,
    hasTenants: tenantRoles.length > 0,
    missingRoles,
  };
}
```

### 3. Authentication Hook

**Location**: `frontend/src/hooks/useAuth.ts`

```typescript
export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuthState();
  }, []);

  const checkAuthState = async () => {
    try {
      const currentUser = await getCurrentUser();
      const roles = await getCurrentUserRoles();

      setUser({
        ...currentUser,
        roles,
      });
    } catch (error) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const hasRole = (role: string): boolean => {
    return user?.roles?.includes(role) || false;
  };

  const logout = async () => {
    await signOut();
    setUser(null);
  };

  return {
    user,
    loading,
    isAuthenticated: !!user,
    hasRole,
    logout,
    refreshUserRoles: checkAuthState,
  };
}
```

### 4. API Service with JWT

**Location**: `frontend/src/services/apiService.ts`

```typescript
/**
 * Make authenticated API request
 */
export async function authenticatedRequest(
  endpoint: string,
  options: RequestInit = {},
): Promise<Response> {
  // Get current JWT token
  const tokens = await getCurrentAuthTokens();

  if (!tokens?.idToken) {
    throw new Error("Not authenticated");
  }

  // Add Authorization header
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

### 5. User Management Component

**Location**: `frontend/src/modules/members/components/UserManagement.tsx`

```typescript
function UserManagement() {
  const [users, setUsers] = useState<CognitoUser[]>([]);
  const [groups, setGroups] = useState<CognitoGroup[]>([]);

  const loadData = async () => {
    const [usersResponse, groupsResponse] = await Promise.all([
      cognitoService.listUsers(),
      cognitoService.listGroups()
    ]);
    setUsers(usersResponse.Users || []);
    setGroups(groupsResponse.Groups || []);
  };

  const handleAddToGroup = async (username: string, groupName: string) => {
    await cognitoService.addUserToGroup(username, groupName);
    toast({ title: 'Role assigned successfully' });
    loadData();
  };

  return (
    <Table>
      {/* User list with role assignment dropdown */}
      {users.map(user => (
        <Tr key={user.Username}>
          <Td>{user.email}</Td>
          <Td>
            <Menu>
              <MenuButton as={Button}>Assign Role</MenuButton>
              <MenuList>
                {groups.map(group => (
                  <MenuItem
                    key={group.GroupName}
                    onClick={() => handleAddToGroup(user.Username, group.GroupName)}
                  >
                    {group.GroupName}
                  </MenuItem>
                ))}
              </MenuList>
            </Menu>
          </Td>
        </Tr>
      ))}
    </Table>
  );
}
```

---

## Key Code References

### Backend Files

| File                                           | Purpose                          |
| ---------------------------------------------- | -------------------------------- |
| `backend/shared/auth_utils.py`                 | Core authentication utilities    |
| `backend/handler/get_finance_data/app.py`      | Example handler with auth        |
| `backend/handler/myAdmin_cognito_admin/app.py` | User/role management API         |
| `backend/template.yaml`                        | SAM infrastructure configuration |
| `backend/layers/auth-layer/`                   | Lambda layer structure           |

### Frontend Files

| File                                                         | Purpose                           |
| ------------------------------------------------------------ | --------------------------------- |
| `frontend/src/services/authService.ts`                       | JWT utilities and role extraction |
| `frontend/src/context/AuthContext.tsx`                       | Authentication state management   |
| `frontend/src/hooks/useAuth.ts`                              | Authentication hook               |
| `frontend/src/modules/members/components/UserManagement.tsx` | Role assignment UI                |
| `frontend/src/aws-exports.ts`                                | Amplify configuration             |

---

## Infrastructure as Code with Terraform

### Why Use Terraform for Cognito?

The implementation patterns in this guide work perfectly with Terraform-managed infrastructure. Using Terraform provides:

1. **Version Control** - Your authentication infrastructure is code
2. **Repeatability** - Deploy identical setups across environments
3. **Documentation** - Infrastructure is self-documenting
4. **Automation** - One-command deployment and updates
5. **Consistency** - No manual configuration drift

### Terraform vs Manual Setup

| Aspect                    | Manual Setup        | Terraform Approach    |
| ------------------------- | ------------------- | --------------------- |
| **User Pool Creation**    | AWS Console/CLI     | `terraform apply`     |
| **Configuration Updates** | Manual changes      | Edit .tf files, apply |
| **Environment Variables** | Manual .env updates | Automated via scripts |
| **Repeatability**         | Error-prone         | Guaranteed identical  |
| **Documentation**         | Separate docs       | Self-documenting code |
| **Version Control**       | Not tracked         | Full git history      |

### Quick Start with Terraform

```powershell
# One command to deploy everything
.\infrastructure\setup-cognito.ps1 -AdminEmail "admin@example.com"
```

This script:

1. Runs `terraform apply` to create Cognito infrastructure
2. Creates initial admin user
3. Updates `.env`, `backend/.env`, and `frontend/.env` files
4. Outputs Hosted UI URL and credentials

### Terraform Configuration Example

```hcl
resource "aws_cognito_user_pool" "myadmin" {
  name = "myAdmin"

  # Email-based authentication
  username_attributes = ["email"]
  auto_verified_attributes = ["email"]

  # Password policy
  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  # Custom attributes for multi-tenancy
  schema {
    name                = "tenant_id"
    attribute_data_type = "String"
    mutable            = false
  }

  schema {
    name                = "tenant_name"
    attribute_data_type = "String"
    mutable            = true
  }

  # Advanced security
  user_pool_add_ons {
    advanced_security_mode = "AUDIT"
  }
}

# App Client
resource "aws_cognito_user_pool_client" "myadmin_client" {
  name         = "myAdmin-client"
  user_pool_id = aws_cognito_user_pool.myadmin.id

  generate_secret = true

  # OAuth configuration
  allowed_oauth_flows = ["code", "implicit"]
  allowed_oauth_scopes = ["email", "openid", "profile"]

  callback_urls = [
    "http://localhost:3000/callback",
    "https://your-app.railway.app/callback"
  ]

  # Token validity
  refresh_token_validity = 30
  access_token_validity  = 60
  id_token_validity      = 60
}

# User Groups
resource "aws_cognito_user_group" "administrators" {
  name         = "Administrators"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Full system access"
  precedence   = 1
}

resource "aws_cognito_user_group" "accountants" {
  name         = "Accountants"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Financial data access"
  precedence   = 5
}

resource "aws_cognito_user_group" "viewers" {
  name         = "Viewers"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Read-only access"
  precedence   = 10
}
```

### Adding More Groups

To add fine-grained groups from the RBAC design:

```hcl
# System roles
resource "aws_cognito_user_group" "system_user_management" {
  name         = "System_User_Management"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "User and role management"
  precedence   = 2
}

# Resource roles
resource "aws_cognito_user_group" "finance_crud" {
  name         = "Finance_CRUD"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Full financial data management"
  precedence   = 10
}

resource "aws_cognito_user_group" "finance_read" {
  name         = "Finance_Read"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Read-only financial access"
  precedence   = 15
}

resource "aws_cognito_user_group" "str_crud" {
  name         = "STR_CRUD"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Full short-term rental management"
  precedence   = 11
}

resource "aws_cognito_user_group" "str_read" {
  name         = "STR_Read"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Read-only STR access"
  precedence   = 16
}

# Tenant roles
resource "aws_cognito_user_group" "tenant_all" {
  name         = "Tenant_All"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Access to all tenants"
  precedence   = 20
}

resource "aws_cognito_user_group" "tenant_peter_prive" {
  name         = "Tenant_PeterPrive"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "PeterPrive tenant access"
  precedence   = 21
}

resource "aws_cognito_user_group" "tenant_goodwin_solutions" {
  name         = "Tenant_GoodwinSolutions"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "GoodwinSolutions tenant access"
  precedence   = 22
}
```

### Terraform Outputs

```hcl
output "cognito_user_pool_id" {
  value       = aws_cognito_user_pool.myadmin.id
  description = "Cognito User Pool ID"
}

output "cognito_client_id" {
  value       = aws_cognito_user_pool_client.myadmin_client.id
  description = "Cognito App Client ID"
}

output "cognito_client_secret" {
  value       = aws_cognito_user_pool_client.myadmin_client.client_secret
  description = "Cognito App Client Secret"
  sensitive   = true
}

output "cognito_hosted_ui_url" {
  value       = "https://${aws_cognito_user_pool_domain.myadmin.domain}.auth.${var.aws_region}.amazoncognito.com"
  description = "Cognito Hosted UI URL"
}
```

### Compatibility with Implementation Guide

✅ **100% Compatible** - All code patterns in this guide work unchanged with Terraform infrastructure:

- **Backend Code**: `extract_user_credentials()`, `validate_permissions()` work identically
- **Frontend Code**: AWS Amplify configuration uses Terraform outputs
- **JWT Structure**: Same `cognito:groups` claim structure
- **Role Validation**: Same permission mapping logic
- **API Integration**: Same authentication patterns

### Migration from Manual Setup

If you already have a manually created Cognito User Pool:

1. **Import existing resources**:

   ```bash
   terraform import aws_cognito_user_pool.myadmin eu-west-1_XXXXXXX
   ```

2. **Update Terraform config** to match existing setup

3. **Verify with plan**:

   ```bash
   terraform plan  # Should show no changes
   ```

4. **Now manage with Terraform** going forward

### Recommended Workflow

1. **Infrastructure**: Use Terraform for Cognito User Pool, Groups, App Client
2. **Application Code**: Use patterns from this implementation guide
3. **Deployment**:
   - Terraform for infrastructure changes
   - SAM/Serverless/Railway for application deployment
4. **Environment Management**: Terraform workspaces for dev/staging/prod

---

## Deployment Configuration

### 1. Create Lambda Layer

```bash
# Structure
backend/layers/auth-layer/
└── python/
    └── shared/
        ├── __init__.py
        └── auth_utils.py

# Deploy with SAM
sam build
sam deploy
```

### 2. Create Cognito Groups

```python
import boto3

cognito = boto3.client('cognito-idp')
user_pool_id = 'eu-west-1_XXXXXXX'

# Create permission roles
roles = [
    'System_CRUD',
    'Finance_CRUD',
    'Finance_Read',
    'STR_CRUD',
    'myAdminUsers',
    'myAdminApplicants'
]

for role in roles:
    cognito.create_group(
        UserPoolId=user_pool_id,
        GroupName=role,
        Description=f'{role} role'
    )

# Create tenant roles
tenants = ['Tenant_All', 'Tenant_PeterPrive', 'Tenant_GoodwinSolutions']
for tenant in tenants:
    cognito.create_group(
        UserPoolId=user_pool_id,
        GroupName=tenant,
        Description=f'{tenant} access'
    )
```

### 3. Assign Roles to Users

```python
# Assign roles via Cognito Admin API
cognito.admin_add_user_to_group(
    UserPoolId=user_pool_id,
    Username='user@example.com',
    GroupName='Finance_CRUD'
)

cognito.admin_add_user_to_group(
    UserPoolId=user_pool_id,
    Username='user@example.com',
    GroupName='Tenant_All'
)
```

---

## Best Practices & Tips

### Infrastructure as Code (IaC)

1. **Use Terraform for Cognito Infrastructure** - Version control your authentication infrastructure
   - Define User Pool, App Client, and Groups in Terraform
   - Automatic deployment and updates with `terraform apply`
   - Easy to replicate across environments (dev, staging, prod)
   - Self-documenting infrastructure configuration

2. **Automate Environment Configuration** - Use scripts to update .env files
   - PowerShell/Bash scripts to extract Terraform outputs
   - Automatically populate COGNITO_USER_POOL_ID, CLIENT_ID, CLIENT_SECRET
   - Reduces manual configuration errors
   - Consistent across backend and frontend

3. **Start Simple, Scale Later** - Begin with basic groups, add complexity as needed
   - Initial groups: Administrators, Accountants, Viewers
   - Add fine-grained groups (Finance_CRUD, STR_CRUD, etc.) when required
   - Easy to extend Terraform configuration
   - Avoid over-engineering early on

### User Pool Configuration

1. **Custom Attributes for Multi-Tenancy** - Use custom attributes for tenant isolation

   ```hcl
   schema {
     name                = "tenant_id"
     attribute_data_type = "String"
     mutable            = false
   }
   ```

   - Store tenant_id, tenant_name, role as custom attributes
   - Immutable tenant_id prevents tenant switching
   - Query users by tenant for isolation

2. **Password Policy Best Practices** - Balance security and usability
   - Minimum 8 characters (not too restrictive)
   - Require mixed case, numbers, and symbols
   - Enable optional MFA for sensitive roles
   - Auto-verify email addresses

3. **Token Validity Configuration** - Set appropriate token lifetimes
   - Refresh tokens: 30 days (balance security and UX)
   - Access tokens: 60 minutes (short-lived for security)
   - ID tokens: 60 minutes (matches access token)
   - Adjust based on your security requirements

### Group and Role Strategy

1. **Group Precedence Matters** - Lower numbers = higher priority

   ```hcl
   resource "aws_cognito_user_group" "administrators" {
     precedence = 1  # Highest priority
   }
   resource "aws_cognito_user_group" "accountants" {
     precedence = 5  # Medium priority
   }
   resource "aws_cognito_user_group" "viewers" {
     precedence = 10 # Lower priority
   }
   ```

2. **Group Naming Convention** - Use consistent, descriptive names
   - System roles: `System_CRUD`, `System_User_Management`
   - Resource roles: `Finance_CRUD`, `STR_Read`, `STR_Export`
   - Tenant roles: `Tenant_All`, `Tenant_PeterPrive`, `Tenant_GoodwinSolutions`
   - Basic roles: `myAdminUsers`, `myAdminApplicants`

3. **Avoid Role Explosion** - Don't create too many groups initially
   - Start with 3-5 basic groups
   - Add more as specific needs arise
   - Use permission mapping in code for flexibility
   - Easier to add groups than remove them

### Deployment and Management

1. **One-Command Deployment** - Simplify infrastructure setup

   ```powershell
   .\infrastructure\setup-cognito.ps1 -AdminEmail "admin@example.com"
   ```

   - Runs Terraform apply
   - Creates initial admin user
   - Updates all .env files
   - Outputs Hosted UI URL

2. **Environment-Specific Configuration** - Use Terraform workspaces or separate configs

   ```bash
   terraform workspace new production
   terraform workspace new staging
   terraform workspace new development
   ```

3. **Backup and Disaster Recovery** - Export user data regularly
   ```bash
   aws cognito-idp list-users --user-pool-id <ID> > users-backup.json
   ```

### Security

1. **Always validate JWT tokens server-side** - Never trust client-side validation alone
2. **Use HTTPS only** - Never send JWT tokens over unencrypted connections
3. **Implement token expiration** - Set appropriate token lifetimes in Cognito
4. **Log all authorization failures** - Monitor for potential security issues
5. **Use least privilege principle** - Grant minimum required permissions
6. **Enable Advanced Security Features** - Use Cognito's built-in threat protection
   ```hcl
   user_pool_add_ons {
     advanced_security_mode = "AUDIT"  # or "ENFORCED"
   }
   ```

### Performance

1. **Use Lambda Layers** - Share auth code across all functions to reduce deployment size
2. **Cache Cognito group lookups** - Reduce API calls by caching role information
3. **Optimize JWT decoding** - Decode tokens once per request, not multiple times
4. **Use connection pooling** - Reuse boto3 clients across Lambda invocations
5. **Minimize Custom Attributes** - Only add attributes you actually need

### Error Handling

1. **Provide clear error messages** - Help users understand authorization failures
2. **Implement fallback mechanisms** - Handle auth service outages gracefully
3. **Log detailed errors** - Include context for debugging
4. **Return appropriate HTTP status codes**:
   - 401: Unauthorized (missing/invalid token)
   - 403: Forbidden (valid token, insufficient permissions)
   - 500: Internal server error

### Testing

1. **Test with different role combinations** - Verify permission logic
2. **Test token expiration** - Ensure proper handling of expired tokens
3. **Test CORS configuration** - Verify preflight requests work
4. **Test tenant access** - Validate multi-tenant scenarios
5. **Load test authentication** - Ensure scalability

### Monitoring

1. **CloudWatch Logs** - Monitor authentication failures
2. **Custom Metrics** - Track authorization patterns
3. **Audit Trail** - Log all role assignments and changes
4. **Alert on anomalies** - Detect unusual access patterns

### Common Pitfalls

1. **Forgetting OPTIONS handler** - Always handle CORS preflight
2. **Inconsistent CORS headers** - Match API Gateway and Lambda CORS settings
3. **Not validating role combinations** - Ensure users have complete permission sets
4. **Hardcoding User Pool IDs** - Use environment variables or parameters
5. **Missing IAM permissions** - Ensure Lambda roles can access Cognito
6. **Creating too many groups upfront** - Start simple, add complexity later
7. **Not using infrastructure as code** - Manual changes are error-prone and not repeatable
8. **Forgetting to update .env files** - Automate this process

### JWT Token Structure

Example decoded JWT payload:

```json
{
  "sub": "12345678-1234-1234-1234-123456789012",
  "cognito:groups": ["Finance_CRUD", "Tenant_All"],
  "email": "user@example.com",
  "username": "user@example.com",
  "exp": 1640000000,
  "iat": 1639996400
}
```

### Tenant Filtering Example

```python
def filter_by_tenant(items, user_roles, tenant_info):
    """Filter data based on user's tenant access"""

    # Full access users see everything
    if tenant_info['has_full_access']:
        return items

    # Tenant users see only their tenants
    allowed_tenants = tenant_info['allowed_tenants']
    return [
        item for item in items
        if item.get('tenant') in allowed_tenants
    ]
```

### Role Assignment UI Pattern

```typescript
// Check if user can assign roles
const canManageUsers = user?.roles?.includes("System_User_Management");

// Validate role combinations before assignment
const validateAssignment = (existingRoles: string[], newRole: string) => {
  const updatedRoles = [...existingRoles, newRole];
  const validation = validateRoleCombinations(updatedRoles);

  if (!validation.isValid) {
    alert(`Invalid role combination: ${validation.missingRoles.join(", ")}`);
    return false;
  }

  return true;
};
```

---

## Summary

This implementation provides:

✅ **Secure authentication** using AWS Cognito and JWT tokens  
✅ **Flexible RBAC** with permission and tenant roles  
✅ **Reusable auth layer** via Lambda Layers  
✅ **Comprehensive audit logging** for compliance  
✅ **Frontend integration** with AWS Amplify v6  
✅ **User management UI** for role assignment  
✅ **Multi-tenant support** via tenant roles  
✅ **Infrastructure as Code** with Terraform for repeatability  
✅ **Automated deployment** with one-command setup  
✅ **Environment management** across dev/staging/prod

### Implementation Approach

**Recommended Stack**:

- **Infrastructure**: Terraform (Cognito User Pool, Groups, App Client)
- **Backend**: Python with Flask/Lambda + auth utilities from this guide
- **Frontend**: React with AWS Amplify v6 + auth service patterns
- **Deployment**: Railway/AWS with automated .env configuration

### Getting Started

1. **Deploy Infrastructure**:

   ```powershell
   .\infrastructure\setup-cognito.ps1 -AdminEmail "admin@example.com"
   ```

2. **Implement Backend** using patterns from "Backend Implementation" section

3. **Implement Frontend** using patterns from "Frontend Implementation" section

4. **Test Locally** with Docker Compose or local dev servers

5. **Deploy to Production** with environment variables from Terraform outputs

### Scaling Strategy

**Phase 1: Start Simple**

- 3 basic groups (Administrators, Accountants, Viewers)
- Core authentication and authorization
- Single tenant or tenant-agnostic

**Phase 2: Add Complexity**

- Fine-grained permission groups (Finance_CRUD, STR_Read, etc.)
- Multi-tenant support with Tenant\_\* groups
- Advanced role validation

**Phase 3: Enterprise Features**

- Custom Lambda triggers for advanced workflows
- Integration with external identity providers
- Advanced security features (MFA enforcement, risk-based auth)

The design is production-tested and can be adapted for various use cases by:

- Adjusting the role structure to match your domain
- Modifying permission mappings in the auth layer
- Customizing the frontend components
- Extending the Cognito admin API for your needs
- Adding more groups via Terraform as requirements grow

For questions or improvements, refer to the code references section for specific implementation details.
