/**
 * Tenant Admin E2E Tests
 * 
 * End-to-end tests for Tenant Administration workflows using Playwright.
 * Tests complete user flows in a real browser environment.
 * 
 * Target: 3+ E2E tests
 */

import { test, expect, Page } from '@playwright/test';

// Test configuration
const TEST_TIMEOUT = 60000;
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

// Mock user credentials (for testing purposes)
const MOCK_ADMIN_USER = {
  email: 'admin@example.com',
  password: 'TestPassword123!',
  tenant: 'TestTenant',
};

/**
 * Helper function to login (mock implementation)
 * In real scenario, this would use AWS Cognito authentication
 */
async function loginAsAdmin(page: Page) {
  // Navigate to login page
  await page.goto(`${BASE_URL}/login`);
  
  // Wait for login form to be visible
  await page.waitForSelector('input[type="email"]', { timeout: 10000 });
  
  // Fill in credentials
  await page.fill('input[type="email"]', MOCK_ADMIN_USER.email);
  await page.fill('input[type="password"]', MOCK_ADMIN_USER.password);
  
  // Click login button
  await page.click('button[type="submit"]');
  
  // Wait for navigation to complete
  await page.waitForURL('**/dashboard', { timeout: 30000 });
}

/**
 * Helper function to navigate to Tenant Admin
 */
async function navigateToTenantAdmin(page: Page) {
  // Look for Tenant Admin link in navigation
  await page.click('text=Tenant Admin');
  
  // Wait for Tenant Admin dashboard to load
  await page.waitForSelector('text=Tenant Administration', { timeout: 10000 });
}

// ============================================================================
// E2E Test 1: User Management Workflow
// ============================================================================

test.describe('E2E Test 1: User Management Workflow', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should create user, assign role, and verify in list', async ({ page }) => {
    // Skip if not in test environment
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    // Step 1: Login as admin
    await loginAsAdmin(page);
    
    // Step 2: Navigate to Tenant Admin
    await navigateToTenantAdmin(page);
    
    // Step 3: Navigate to User Management
    await page.click('text=User Management');
    await page.waitForSelector('text=Users', { timeout: 10000 });
    
    // Step 4: Click Create User button
    await page.click('button:has-text("Create User")');
    
    // Step 5: Fill in user details
    await page.waitForSelector('input[name="email"]', { timeout: 5000 });
    await page.fill('input[name="email"]', 'newuser@example.com');
    await page.fill('input[name="given_name"]', 'New');
    await page.fill('input[name="family_name"]', 'User');
    
    // Step 6: Select role
    await page.check('input[value="Tenant_Admin"]');
    
    // Step 7: Submit form
    await page.click('button:has-text("Create")');
    
    // Step 8: Wait for success message
    await page.waitForSelector('text=User created successfully', { timeout: 10000 });
    
    // Step 9: Verify user appears in list
    await page.waitForSelector('text=newuser@example.com', { timeout: 5000 });
    
    // Step 10: Verify user has correct role
    const userRow = page.locator('tr:has-text("newuser@example.com")');
    await expect(userRow).toContainText('Tenant_Admin');
    
    // Step 11: Verify user status
    await expect(userRow).toContainText('FORCE_CHANGE_PASSWORD');
  });

  test('should handle user creation validation errors', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Navigate to User Management
    await page.click('text=User Management');
    
    // Click Create User
    await page.click('button:has-text("Create User")');
    
    // Try to submit without filling required fields
    await page.click('button:has-text("Create")');
    
    // Verify validation error appears
    await page.waitForSelector('text=Email is required', { timeout: 5000 });
  });
});

// ============================================================================
// E2E Test 2: Credential Management Workflow
// ============================================================================

test.describe('E2E Test 2: Credential Management Workflow', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should upload credentials and test connection', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    // Step 1: Login as admin
    await loginAsAdmin(page);
    
    // Step 2: Navigate to Tenant Admin
    await navigateToTenantAdmin(page);
    
    // Step 3: Navigate to Credentials Management
    await page.click('text=Credentials');
    await page.waitForSelector('text=Credentials Management', { timeout: 10000 });
    
    // Step 4: Select credential type
    await page.selectOption('select[name="credentialType"]', 'google_drive');
    
    // Step 5: Upload credentials file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'credentials.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify({ key: 'value' })),
    });
    
    // Step 6: Click Upload button
    await page.click('button:has-text("Upload")');
    
    // Step 7: Wait for success message
    await page.waitForSelector('text=Credentials uploaded successfully', { timeout: 10000 });
    
    // Step 8: Verify credentials appear in list
    await page.waitForSelector('text=google_drive', { timeout: 5000 });
    
    // Step 9: Click Test Connection button
    await page.click('button:has-text("Test Connection")');
    
    // Step 10: Wait for test result
    await page.waitForSelector('text=Connection successful', { timeout: 15000 });
  });

  test('should handle invalid credential file format', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Navigate to Credentials Management
    await page.click('text=Credentials');
    
    // Try to upload non-JSON file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'credentials.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('invalid content'),
    });
    
    // Verify error message
    await page.waitForSelector('text=Please select a JSON file', { timeout: 5000 });
  });
});

// ============================================================================
// E2E Test 3: Storage Configuration Workflow
// ============================================================================

test.describe('E2E Test 3: Storage Configuration Workflow', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should browse folders and configure storage', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    // Step 1: Login as admin
    await loginAsAdmin(page);
    
    // Step 2: Navigate to Tenant Admin
    await navigateToTenantAdmin(page);
    
    // Step 3: Navigate to Storage Configuration
    await page.click('text=Storage');
    await page.waitForSelector('text=Storage Configuration', { timeout: 10000 });
    
    // Step 4: Click Browse Folders button
    await page.click('button:has-text("Browse Folders")');
    
    // Step 5: Wait for folder list to load
    await page.waitForSelector('select[name="folderId"]', { timeout: 10000 });
    
    // Step 6: Select folder for invoices
    await page.selectOption('select[name="invoicesFolderId"]', { index: 1 });
    
    // Step 7: Select folder for templates
    await page.selectOption('select[name="templatesFolderId"]', { index: 2 });
    
    // Step 8: Click Save Configuration button
    await page.click('button:has-text("Save Configuration")');
    
    // Step 9: Wait for success message
    await page.waitForSelector('text=Storage configured successfully', { timeout: 10000 });
    
    // Step 10: Verify storage usage is displayed
    await page.waitForSelector('text=Storage Usage', { timeout: 5000 });
    
    // Step 11: Verify folder names are displayed
    await expect(page.locator('text=Invoices')).toBeVisible();
    await expect(page.locator('text=Templates')).toBeVisible();
  });

  test('should test folder access', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Navigate to Storage Configuration
    await page.click('text=Storage');
    
    // Click Test Access button for a folder
    await page.click('button:has-text("Test Access")').first();
    
    // Wait for test result
    await page.waitForSelector('text=Folder is accessible', { timeout: 10000 });
  });
});

// ============================================================================
// E2E Test 4: Responsive Design Tests
// ============================================================================

test.describe('E2E Test 4: Responsive Design', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display correctly on desktop', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    // Set desktop viewport
    await page.setViewportSize({ width: 1920, height: 1080 });
    
    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Verify navigation is visible
    await expect(page.locator('nav')).toBeVisible();
    
    // Verify main content area
    await expect(page.locator('main')).toBeVisible();
    
    // Verify sidebar (if present)
    const sidebar = page.locator('aside');
    if (await sidebar.count() > 0) {
      await expect(sidebar).toBeVisible();
    }
  });

  test('should display correctly on tablet', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    // Set tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 });
    
    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Verify content is responsive
    await expect(page.locator('main')).toBeVisible();
    
    // Verify navigation adapts to tablet size
    await expect(page.locator('nav')).toBeVisible();
  });

  test('should display correctly on mobile', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    
    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Verify mobile menu button is visible
    const menuButton = page.locator('button[aria-label="Menu"]');
    if (await menuButton.count() > 0) {
      await expect(menuButton).toBeVisible();
    }
    
    // Verify content is responsive
    await expect(page.locator('main')).toBeVisible();
  });
});

// ============================================================================
// E2E Test 5: Cross-Browser Compatibility
// ============================================================================

test.describe('E2E Test 5: Cross-Browser Compatibility', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should work correctly in Chromium', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Chromium-specific test');
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Verify basic functionality
    await expect(page.locator('text=Tenant Administration')).toBeVisible();
  });

  test('should work correctly in Firefox', async ({ page, browserName }) => {
    test.skip(browserName !== 'firefox', 'Firefox-specific test');
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Verify basic functionality
    await expect(page.locator('text=Tenant Administration')).toBeVisible();
  });

  test('should work correctly in WebKit', async ({ page, browserName }) => {
    test.skip(browserName !== 'webkit', 'WebKit-specific test');
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Verify basic functionality
    await expect(page.locator('text=Tenant Administration')).toBeVisible();
  });
});

// ============================================================================
// E2E Test 6: Error Handling and Edge Cases
// ============================================================================

test.describe('E2E Test 6: Error Handling', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should handle network errors gracefully', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Simulate network failure
    await page.route('**/api/tenant-admin/**', route => route.abort());
    
    // Try to load user list
    await page.click('text=User Management');
    
    // Verify error message is displayed
    await page.waitForSelector('text=Failed to load', { timeout: 10000 });
  });

  test('should handle session timeout', async ({ page }) => {
    test.skip(process.env.NODE_ENV !== 'test', 'Only run in test environment');

    await loginAsAdmin(page);
    await navigateToTenantAdmin(page);
    
    // Simulate session timeout by clearing cookies
    await page.context().clearCookies();
    
    // Try to perform an action
    await page.click('text=User Management');
    
    // Verify redirect to login page
    await page.waitForURL('**/login', { timeout: 10000 });
  });
});
