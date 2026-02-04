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
      process.env.REACT_APP_REDIRECT_SIGN_IN || 'http://localhost:5000/'
    ],
    signOut: [
      `${baseUrl}/`,
      `${baseUrl}/login`,
      'http://localhost:3000/',
      'http://localhost:3000/login',
      'http://localhost:5000/',
      'http://localhost:5000/login',
      process.env.REACT_APP_REDIRECT_SIGN_OUT || 'http://localhost:5000/'
    ]
  };
};

const redirectUrls = getRedirectUrls();

const awsconfig = {
  Auth: {
    Cognito: {
      // User Pool ID from Cognito
      userPoolId: process.env.REACT_APP_COGNITO_USER_POOL_ID || '',
      
      // App Client ID from Cognito
      userPoolClientId: process.env.REACT_APP_COGNITO_CLIENT_ID || '',
      
      // OAuth configuration for Hosted UI
      loginWith: {
        oauth: {
          // Cognito domain for Hosted UI
          domain: process.env.REACT_APP_COGNITO_DOMAIN || '',
          
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
