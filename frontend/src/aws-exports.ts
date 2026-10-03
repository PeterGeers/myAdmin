/**
 * AWS Amplify Configuration for myAdmin
 *
 * This file configures AWS Amplify v6 for Cognito authentication.
 *
 * Cognito pool selection (Requirements 1.4, 1.5, 2.3, 8.1-8.5):
 * The active Cognito identity (user pool id + app client id) is selected SOLELY from
 * the resolved APP_ENV via the Environment_Resolver (`./config/appEnv` → `RESOLVED`),
 * NOT from `window.location.hostname`. The former `isLocal = hostname === 'localhost'`
 * switch has been removed — the environment is decided once, by the explicit APP_ENV
 * selector, and this plane merely consumes the resolved value (one decision, many
 * consumers). The resolver fails fast at module load when VITE_APP_ENV is unset or
 * unrecognized, so there is no silent prod/test default here.
 *
 * Non-identity OAuth config (Cognito Hosted-UI domain, scopes, redirect URLs) that does
 * NOT select the environment is preserved as-is and still read from Vite env vars.
 */

import { RESOLVED } from './config/appEnv';

// Determine redirect URLs based on current environment
const getRedirectUrls = () => {
  const isDevelopment = window.location.port === '3000';
  const baseUrl = isDevelopment ? 'http://localhost:3000' : 'http://localhost:5000';

  return {
    signIn: [
      `${baseUrl}/`,
      `${baseUrl}/callback`,
      'http://localhost:3000/',
      'http://localhost:3000/callback',
      'http://localhost:5000/',
      'http://localhost:5000/callback',
      import.meta.env.VITE_REDIRECT_SIGN_IN || 'http://localhost:5000/'
    ],
    signOut: [
      `${baseUrl}/`,
      `${baseUrl}/login`,
      'http://localhost:3000/',
      'http://localhost:3000/login',
      'http://localhost:5000/',
      'http://localhost:5000/login',
      import.meta.env.VITE_REDIRECT_SIGN_OUT || 'http://localhost:5000/'
    ]
  };
};

const redirectUrls = getRedirectUrls();

// The active Cognito pool/client come from the resolved APP_ENV only (never the
// hostname). `RESOLVED.cognito` is the test pool (eu-west-1_xyrlzfqbl) when
// APP_ENV=test and production Pool A (eu-west-1_Hdp40eWmu) when APP_ENV=production,
// read from the committed Environment_Definition (Req 8.1-8.2, 8.5). The frontend
// never carries a client secret (test pool has none — Req 8.4).
const cognitoUserPoolId = RESOLVED.cognito.poolId;
const cognitoClientId = RESOLVED.cognito.clientId;

const awsconfig = {
  Auth: {
    Cognito: {
      // User Pool ID resolved from APP_ENV (test pool for test, Pool A for production)
      userPoolId: cognitoUserPoolId,

      // App Client ID resolved from APP_ENV
      userPoolClientId: cognitoClientId,

      // OAuth configuration for Hosted UI
      loginWith: {
        oauth: {
          // Cognito domain for Hosted UI
          domain: import.meta.env.VITE_COGNITO_DOMAIN || '',

          // OAuth scopes - what information to request
          scopes: ['openid', 'email', 'profile'],

          // Redirect URLs after successful login
          redirectSignIn: redirectUrls.signIn,

          // Redirect URLs after logout
          redirectSignOut: redirectUrls.signOut,

          // OAuth response type - 'code' for authorization code flow
          responseType: 'code' as const
        }
      }
    }
  }
};

export default awsconfig;
