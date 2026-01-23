# Authentication Context

This directory contains the authentication context and utilities for myAdmin.

## Overview

The `AuthContext` provides authentication state management throughout the application using AWS Cognito and Amplify v6.

## Files

- **AuthContext.tsx** - Main authentication context and provider
- **AuthContext.test.tsx** - Unit tests for the authentication context
- **AuthContext.example.tsx** - Example usage patterns
- **README.md** - This file

## Usage

### 1. Wrap Your App with AuthProvider

The `AuthProvider` is already configured in `App.tsx`:

```tsx
import { AuthProvider } from "./context/AuthContext";

function App() {
  return (
    <ChakraProvider theme={theme}>
      <AuthProvider>{/* Your app components */}</AuthProvider>
    </ChakraProvider>
  );
}
```

### 2. Use the useAuth Hook

In any component, use the `useAuth` hook to access authentication state:

```tsx
import { useAuth } from "./context/AuthContext";

function MyComponent() {
  const { user, isAuthenticated, loading, hasRole, logout } = useAuth();

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!isAuthenticated) {
    return <div>Please login</div>;
  }

  return (
    <div>
      <p>Welcome {user.email}</p>
      {hasRole("Administrators") && <AdminPanel />}
      <button onClick={logout}>Logout</button>
    </div>
  );
}
```

## API Reference

### AuthContext Value

The `useAuth` hook returns an object with the following properties:

#### State

- **user**: `User | null` - Current user information
  - `username`: string - User's username
  - `email`: string | null - User's email address
  - `roles`: string[] - User's Cognito groups (roles)
  - `sub`: string - User's unique identifier

- **loading**: `boolean` - True while checking authentication state

- **isAuthenticated**: `boolean` - True if user is logged in

#### Actions

- **logout()**: `Promise<void>` - Sign out the current user

- **refreshUserRoles()**: `Promise<void>` - Refresh user roles from Cognito (useful after role changes)

#### Role Checking

- **hasRole(role: string)**: `boolean` - Check if user has a specific role

  ```tsx
  if (hasRole("Administrators")) {
    // Show admin content
  }
  ```

- **hasAnyRole(roles: string[])**: `boolean` - Check if user has any of the specified roles

  ```tsx
  if (hasAnyRole(["Administrators", "Finance_CRUD"])) {
    // Show content for admins or finance users
  }
  ```

- **hasAllRoles(roles: string[])**: `boolean` - Check if user has all of the specified roles

  ```tsx
  if (hasAllRoles(["Finance_CRUD", "Tenant_All"])) {
    // Show content only if user has both roles
  }
  ```

- **validateRoles()**: `RoleValidation` - Validate current user's role combinations
  ```tsx
  const validation = validateRoles();
  if (!validation.isValid) {
    console.log("Missing roles:", validation.missingRoles);
  }
  ```

## Role-Based Access Control

The authentication system uses Cognito groups as roles. Common roles include:

### System Roles

- `System_CRUD` - Full system access
- `System_User_Management` - User and role management
- `System_Logs_Read` - Audit log access

### Permission Roles

- `Finance_CRUD` - Full financial data management
- `Finance_Read` - Read-only financial access
- `Finance_Export` - Export financial data
- `STR_CRUD` - Full short-term rental management
- `STR_Read` - Read-only STR access
- `STR_Export` - Export STR data

### Tenant Roles (Multi-Tenant)

- `Tenant_All` - Access to all tenants
- `Tenant_PeterPrive` - PeterPrive tenant only
- `Tenant_GoodwinSolutions` - GoodwinSolutions tenant only

### Basic User Roles

- `myAdminUsers` - Regular users (self-service access)
- `myAdminApplicants` - Applicants (limited self-service)

## Examples

See `AuthContext.example.tsx` for complete examples of:

- Displaying authentication status
- Role-based rendering
- Role validation
- Logout functionality

## Testing

Run tests with:

```bash
npm test -- --watchAll=false --testPathPattern="AuthContext.test"
```

## Integration with API Calls

The authentication context works seamlessly with the `authService` for making authenticated API requests:

```tsx
import { useAuth } from "./context/AuthContext";
import { authenticatedRequest } from "./services/apiService";

function MyComponent() {
  const { isAuthenticated } = useAuth();

  const fetchData = async () => {
    if (!isAuthenticated) return;

    const response = await authenticatedRequest("/api/invoices");
    const data = await response.json();
    // Use data...
  };

  // ...
}
```

## Error Handling

The AuthContext handles authentication errors gracefully:

- If authentication fails, `user` is set to `null`
- If token is expired, `isAuthenticated` returns `false`
- Errors are logged to console for debugging
- The app continues to function, showing login prompts where needed

## Best Practices

1. **Always check `loading` state** before rendering content
2. **Use role-based rendering** instead of hiding elements with CSS
3. **Refresh roles after assignment** using `refreshUserRoles()`
4. **Handle unauthenticated state** gracefully with redirects or login prompts
5. **Use `hasAnyRole`** for OR conditions, `hasAllRoles` for AND conditions
6. **Validate role combinations** to ensure users have complete permission sets

## Troubleshooting

### User is null after login

- Check that Amplify is configured correctly in `aws-exports.ts`
- Verify Cognito User Pool ID and Client ID are correct
- Check browser console for authentication errors

### Roles are empty

- Verify user is assigned to Cognito groups
- Check that JWT token contains `cognito:groups` claim
- Ensure groups are created in Cognito User Pool

### Token expired errors

- Tokens automatically refresh when using Amplify
- If issues persist, call `refreshUserRoles()` manually
- Check token validity settings in Cognito

## Related Files

- `../services/authService.ts` - JWT utilities and role validation
- `../aws-exports.ts` - Amplify configuration
- `../index.tsx` - Amplify initialization
- `../App.tsx` - AuthProvider setup
