/**
 * AWS Amplify Configuration for myAdmin
 * 
 * This file configures AWS Amplify v6 for Cognito authentication.
 * Environment variables are loaded from frontend/.env
 */

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

// Local dev ALWAYS authenticates against the dev/test Cognito pool (myAdmin-test),
// mirroring sam/members/env-vars.local.json HDCN_COGNITO_* which point at the same
// test pool. That way a local SPA login yields a token the local Members API accepts.
// Off-localhost (deployed), or if the VITE_TEST_* vars are unset, we fall back to the
// primary (prod) pool. Detection is hostname-based so it works on any Vite port.
const isLocal =
  typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
const cognitoUserPoolId =
  (isLocal && import.meta.env.VITE_TEST_COGNITO_USER_POOL_ID) ||
  import.meta.env.VITE_COGNITO_USER_POOL_ID ||
  '';
const cognitoClientId =
  (isLocal && import.meta.env.VITE_TEST_COGNITO_CLIENT_ID) ||
  import.meta.env.VITE_COGNITO_CLIENT_ID ||
  '';

const awsconfig = {
  Auth: {
    Cognito: {
      // User Pool ID from Cognito (test pool on localhost, prod otherwise)
      userPoolId: cognitoUserPoolId,

      // App Client ID from Cognito (test pool on localhost, prod otherwise)
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
