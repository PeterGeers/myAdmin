# Pages Directory

This directory contains page-level components for the myAdmin application.

## Login Page

**File**: `Login.tsx`

The Login page provides authentication for the myAdmin application using AWS Cognito.

### Features

- **Cognito Hosted UI Integration**: Redirects users to AWS Cognito's secure hosted authentication page
- **Automatic Redirect**: After successful authentication, users are redirected back to the dashboard
- **Forgot Password**: Link to Cognito's password reset flow
- **Error Handling**: Displays user-friendly error messages if authentication fails
- **Loading States**: Shows loading indicator during authentication process

### Usage

The Login component is automatically displayed when a user is not authenticated. The App.tsx component checks authentication status and shows the Login page if needed.

```tsx
import Login from "./pages/Login";

// In App.tsx
if (!isAuthenticated && !loading) {
  return <Login onLoginSuccess={() => setCurrentPage("menu")} />;
}
```

### Authentication Flow

1. User clicks "Sign in with Cognito" button
2. App calls `signInWithRedirect()` from AWS Amplify
3. User is redirected to Cognito Hosted UI
4. User enters credentials on Cognito's secure page
5. After successful authentication, Cognito redirects back to the app
6. AWS Amplify automatically processes the OAuth callback
7. AuthContext detects the authenticated state
8. User is shown the dashboard

### Environment Variables

The Login page uses the following environment variables from `.env`:

- `REACT_APP_COGNITO_DOMAIN`: Cognito domain for Hosted UI
- `REACT_APP_COGNITO_CLIENT_ID`: Cognito App Client ID

These are configured in `frontend/src/aws-exports.ts`.

### Styling

The Login page uses Chakra UI components with the myAdmin theme:

- Dark background (`gray.900`)
- Orange accent color for branding
- Responsive design that works on all screen sizes
- Logo display (jabaki-logo.png from public directory)

## Callback Page

**File**: `Callback.tsx`

The Callback page handles OAuth redirects from Cognito after authentication.

### Features

- **Loading State**: Shows a spinner while processing authentication
- **Automatic Redirect**: Redirects to dashboard after successful authentication
- **Error Handling**: Redirects to login page if authentication fails

### Usage

This page is shown briefly during the OAuth callback flow. Users typically don't interact with it directly.

## Future Pages

Additional pages can be added to this directory as the application grows:

- User Profile page
- Settings page
- Admin panel pages
- etc.
