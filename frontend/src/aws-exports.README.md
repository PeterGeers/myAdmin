# AWS Amplify Configuration

## Overview

This directory contains the AWS Amplify configuration for myAdmin's Cognito authentication.

## Files

- `aws-exports.ts` - Main Amplify configuration file
- `aws-exports.test.ts` - Tests for the configuration

## Configuration

The configuration is set up in `aws-exports.ts` and uses environment variables from `frontend/.env`.

### Required Environment Variables

Add these to your `frontend/.env` file:

```env
REACT_APP_COGNITO_USER_POOL_ID=eu-west-1_XXXXXXX
REACT_APP_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxx
REACT_APP_COGNITO_DOMAIN=myadmin.auth.eu-west-1.amazoncognito.com
REACT_APP_AWS_REGION=eu-west-1
REACT_APP_REDIRECT_SIGN_IN=http://localhost:3000/
REACT_APP_REDIRECT_SIGN_OUT=http://localhost:3000/
```

### Initialization

Amplify is initialized in `src/index.tsx`:

```typescript
import { Amplify } from "aws-amplify";
import awsconfig from "./aws-exports";

Amplify.configure(awsconfig);
```

## OAuth Flow

The configuration uses the **Authorization Code Flow** (`responseType: 'code'`), which is the recommended OAuth 2.0 flow for web applications.

### OAuth Scopes

- `openid` - Required for OpenID Connect
- `email` - Access to user's email address
- `profile` - Access to user's profile information

### Redirect URLs

**Sign In**: After successful authentication, users are redirected to:

- `http://localhost:3000/` (local development)
- `http://localhost:3000/callback` (callback handler)

**Sign Out**: After logout, users are redirected to:

- `http://localhost:3000/` (home page)
- `http://localhost:3000/login` (login page)

## Testing

Run the configuration tests:

```bash
npm test -- aws-exports.test.ts --watchAll=false
```

## Production Configuration

For production deployment, update the environment variables with production URLs:

```env
REACT_APP_REDIRECT_SIGN_IN=https://your-app.railway.app/
REACT_APP_REDIRECT_SIGN_OUT=https://your-app.railway.app/
```

**Important**: Also update the callback URLs in AWS Cognito User Pool settings to match your production URLs.

## Next Steps

After configuring Amplify:

1. Create authentication service (`src/services/authService.ts`)
2. Create authentication context (`src/context/AuthContext.tsx`)
3. Create login page (`src/pages/Login.tsx`)
4. Implement protected routes

See `.kiro/specs/Common/Cognito/tasks.md` for the complete implementation plan.
