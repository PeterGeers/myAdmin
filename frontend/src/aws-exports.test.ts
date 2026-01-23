/**
 * Tests for AWS Amplify Configuration
 */

import awsconfig from './aws-exports';

describe('AWS Amplify Configuration', () => {
  it('should have Auth configuration', () => {
    expect(awsconfig).toBeDefined();
    expect(awsconfig.Auth).toBeDefined();
  });

  it('should have Cognito configuration', () => {
    expect(awsconfig.Auth.Cognito).toBeDefined();
    expect(awsconfig.Auth.Cognito.userPoolId).toBeDefined();
    expect(awsconfig.Auth.Cognito.userPoolClientId).toBeDefined();
  });

  it('should have OAuth configuration', () => {
    expect(awsconfig.Auth.Cognito.loginWith).toBeDefined();
    expect(awsconfig.Auth.Cognito.loginWith.oauth).toBeDefined();
  });

  it('should have OAuth domain', () => {
    const oauth = awsconfig.Auth.Cognito.loginWith.oauth;
    expect(oauth.domain).toBeDefined();
    expect(typeof oauth.domain).toBe('string');
  });

  it('should have OAuth scopes', () => {
    const oauth = awsconfig.Auth.Cognito.loginWith.oauth;
    expect(oauth.scopes).toBeDefined();
    expect(Array.isArray(oauth.scopes)).toBe(true);
    expect(oauth.scopes).toContain('openid');
    expect(oauth.scopes).toContain('email');
    expect(oauth.scopes).toContain('profile');
  });

  it('should have redirect URLs', () => {
    const oauth = awsconfig.Auth.Cognito.loginWith.oauth;
    expect(oauth.redirectSignIn).toBeDefined();
    expect(Array.isArray(oauth.redirectSignIn)).toBe(true);
    expect(oauth.redirectSignIn.length).toBeGreaterThan(0);
    
    expect(oauth.redirectSignOut).toBeDefined();
    expect(Array.isArray(oauth.redirectSignOut)).toBe(true);
    expect(oauth.redirectSignOut.length).toBeGreaterThan(0);
  });

  it('should have response type set to code', () => {
    const oauth = awsconfig.Auth.Cognito.loginWith.oauth;
    expect(oauth.responseType).toBe('code');
  });

  it('should use environment variables or fallback values', () => {
    const { userPoolId, userPoolClientId } = awsconfig.Auth.Cognito;
    
    // Should have valid format (either from env or fallback)
    expect(userPoolId).toMatch(/^[a-z]+-[a-z]+-\d+_[A-Za-z0-9]+$/);
    expect(userPoolClientId).toMatch(/^[a-z0-9]+$/);
  });
});
