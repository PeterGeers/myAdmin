/**
 * AWS Amplify Configuration for myAdmin
 * 
 * This file configures AWS Amplify v6 for Cognito authentication.
 * Environment variables are loaded from frontend/.env
 */

const awsconfig = {
  Auth: {
    Cognito: {
      // User Pool ID from Cognito
      userPoolId: process.env.REACT_APP_COGNITO_USER_POOL_ID || 'eu-west-1_Hdp40eWmu',
      
      // App Client ID from Cognito
      userPoolClientId: process.env.REACT_APP_COGNITO_CLIENT_ID || '6sgh53un5ttsojn7o2aj9hi7en',
      
      // OAuth configuration for Hosted UI
      loginWith: {
        oauth: {
          // Cognito domain for Hosted UI
          domain: process.env.REACT_APP_COGNITO_DOMAIN || 'myadmin.auth.eu-west-1.amazoncognito.com',
          
          // OAuth scopes - what information to request
          scopes: ['openid', 'email', 'profile'],
          
          // Redirect URLs after successful login
          redirectSignIn: [
            'http://localhost:3000/',
            'http://localhost:3000/callback',
            process.env.REACT_APP_REDIRECT_SIGN_IN || 'http://localhost:3000/'
          ],
          
          // Redirect URLs after logout
          redirectSignOut: [
            'http://localhost:3000/',
            'http://localhost:3000/login',
            process.env.REACT_APP_REDIRECT_SIGN_OUT || 'http://localhost:3000/'
          ],
          
          // OAuth response type - 'code' for authorization code flow
          responseType: 'code' as const
        }
      }
    }
  }
};

export default awsconfig;
