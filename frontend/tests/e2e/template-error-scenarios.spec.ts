/**
 * E2E Tests for Template Management Error Scenarios
 * 
 * Tests error handling and edge cases:
 * 1. No sample data available
 * 2. AI service unavailable
 * 3. Google Drive upload failures
 * 4. Network errors
 * 5. Database errors
 */

import { test, expect, Page } from '@playwright/test';

// Test configuration
const TEST_USER_EMAIL = 'test@example.com';
const TEST_USER_PASSWORD = 'TestPassword123!';

/**
 * Helper: Login to the application
 */
async function login(page: Page) {
  await page.goto('/login');
  await page.fill('input[name="email"]', TEST_USER_EMAIL);
  await page.fill('input[name="password"]', TEST_USER_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL('/dashboard', { timeout: 10000 });
}

/**
 * Helper: Navigate to template management
 */
async function navigateToTemplateManagement(page: Page) {
  await page.click('text=Tenant Admin');
  await page.click('text=Template Management');
  await page.waitForSelector('h1:has-text("Template Management")');
}

/**
 * Helper: Create a valid template
 */
function createValidTemplate(): string {
  return `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Invoice {{ invoice_number }}</title>
      </head>
      <body>
        <h1>{{ company_name }}</h1>
        <p>Guest: {{ guest_name }}</p>
        <p>Amount: {{ amount_gross }}</p>
      </body>
    </html>
  `;
}

test.describe('Template Management - Error Scenarios', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);
  });

  test('should handle no sample data available gracefully', async ({ page }) => {
    // Mock API to return no sample data
    await page.route('**/api/tenant-admin/templates/preview', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          preview_html: '<html><body><p>No sample data available</p></body></html>',
          validation: {
            is_valid: true,
            errors: [],
            warnings: ['No sample data available for preview'],
          },
          sample_data_info: {
            source: 'placeholder',
            message: 'No real data available, using placeholder values',
          },
        }),
      });
    });

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(createValidTemplate());
    await fileInput.setInputFiles({
      name: 'template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify warning is displayed
    const warning = await page.locator('text=No sample data available').isVisible();
    expect(warning).toBeTruthy();

    // Verify preview still shows (with placeholder data)
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();
  });

  test('should handle AI service unavailable', async ({ page }) => {
    // Mock API to return AI service error
    await page.route('**/api/tenant-admin/templates/ai-help', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'AI service temporarily unavailable',
          message: 'Please try again later or fix errors manually',
        }),
      });
    });

    // Upload invalid template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const invalidTemplate = '<html><body><p>Missing placeholders</p></body></html>';
    const buffer = Buffer.from(invalidTemplate);
    await fileInput.setInputFiles({
      name: 'invalid.html',
      mimeType: 'text/html',
      buffer,
    });

    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Click AI help button
    await page.click('button:has-text("Get AI Help")');

    // Wait for error message
    await page.waitForSelector('text=AI service temporarily unavailable', { timeout: 10000 });

    // Verify fallback message is shown
    const fallbackMessage = await page.locator('text=Please try again later or fix errors manually').isVisible();
    expect(fallbackMessage).toBeTruthy();

    // Verify user can still manually fix errors
    const approveButton = page.locator('button:has-text("Approve Template")');
    await expect(approveButton).toBeDisabled(); // Still disabled due to errors
  });

  test('should handle Google Drive upload failure', async ({ page }) => {
    // Mock API to return Google Drive error
    await page.route('**/api/tenant-admin/templates/approve', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Failed to upload to Google Drive',
          message: 'Google Drive service is temporarily unavailable',
          details: 'Connection timeout',
        }),
      });
    });

    // Upload valid template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(createValidTemplate());
    await fileInput.setInputFiles({
      name: 'template.html',
      mimeType: 'text/html',
      buffer,
    });

    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Try to approve
    await page.fill('textarea[name="approvalNotes"]', 'Test approval');
    await page.click('button:has-text("Approve Template")');
    await page.click('button:has-text("Confirm")');

    // Wait for error message
    await page.waitForSelector('text=Failed to upload to Google Drive', { timeout: 10000 });

    // Verify error details are shown
    const errorDetails = await page.locator('text=Google Drive service is temporarily unavailable').isVisible();
    expect(errorDetails).toBeTruthy();

    // Verify user can retry
    const retryButton = page.locator('button:has-text("Retry")');
    await expect(retryButton).toBeVisible();
  });

  test('should handle network timeout during preview', async ({ page }) => {
    // Mock API to timeout
    await page.route('**/api/tenant-admin/templates/preview', async (route) => {
      // Delay response to simulate timeout
      await new Promise(resolve => setTimeout(resolve, 35000));
      await route.fulfill({
        status: 504,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Request timeout',
          message: 'The server took too long to respond',
        }),
      });
    });

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(createValidTemplate());
    await fileInput.setInputFiles({
      name: 'template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for timeout error
    await page.waitForSelector('text=Request timeout', { timeout: 40000 });

    // Verify error message is shown
    const errorMessage = await page.locator('text=The server took too long to respond').isVisible();
    expect(errorMessage).toBeTruthy();

    // Verify user can retry
    const uploadButton = page.locator('button:has-text("Upload & Preview")');
    await expect(uploadButton).toBeEnabled();
  });

  test('should handle database connection error', async ({ page }) => {
    // Mock API to return database error
    await page.route('**/api/tenant-admin/templates/preview', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Database connection failed',
          message: 'Unable to fetch sample data from database',
          details: 'Connection refused',
        }),
      });
    });

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(createValidTemplate());
    await fileInput.setInputFiles({
      name: 'template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for error message
    await page.waitForSelector('text=Database connection failed', { timeout: 10000 });

    // Verify error details are shown
    const errorDetails = await page.locator('text=Unable to fetch sample data from database').isVisible();
    expect(errorDetails).toBeTruthy();
  });

  test('should handle invalid JSON response from API', async ({ page }) => {
    // Mock API to return invalid JSON
    await page.route('**/api/tenant-admin/templates/preview', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: 'This is not valid JSON',
      });
    });

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(createValidTemplate());
    await fileInput.setInputFiles({
      name: 'template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for error message
    await page.waitForSelector('text=Failed to parse server response', { timeout: 10000 });

    // Verify generic error message is shown
    const errorMessage = await page.locator('text=An unexpected error occurred').isVisible();
    expect(errorMessage).toBeTruthy();
  });

  test('should handle authentication expiration during workflow', async ({ page }) => {
    // Mock API to return 401 Unauthorized
    await page.route('**/api/tenant-admin/templates/approve', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Unauthorized',
          message: 'Your session has expired. Please log in again.',
        }),
      });
    });

    // Upload valid template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(createValidTemplate());
    await fileInput.setInputFiles({
      name: 'template.html',
      mimeType: 'text/html',
      buffer,
    });

    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Try to approve
    await page.fill('textarea[name="approvalNotes"]', 'Test approval');
    await page.click('button:has-text("Approve Template")');
    await page.click('button:has-text("Confirm")');

    // Wait for authentication error
    await page.waitForSelector('text=Your session has expired', { timeout: 10000 });

    // Verify user is redirected to login
    await page.waitForURL('/login', { timeout: 10000 });
  });

  test('should handle concurrent template uploads', async ({ page }) => {
    // This test verifies that the UI handles concurrent operations gracefully
    
    // Upload first template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer1 = Buffer.from(createValidTemplate());
    await fileInput.setInputFiles({
      name: 'template1.html',
      mimeType: 'text/html',
      buffer: buffer1,
    });

    // Click upload (don't wait for completion)
    await page.click('button:has-text("Upload & Preview")');

    // Immediately try to upload another template
    const buffer2 = Buffer.from(createValidTemplate());
    await fileInput.setInputFiles({
      name: 'template2.html',
      mimeType: 'text/html',
      buffer: buffer2,
    });

    // Verify that the UI prevents concurrent uploads
    const uploadButton = page.locator('button:has-text("Upload & Preview")');
    await expect(uploadButton).toBeDisabled();

    // Wait for first upload to complete
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify upload button is re-enabled
    await expect(uploadButton).toBeEnabled();
  });

  test('should handle template with security violations', async ({ page }) => {
    // Create template with script tags (security violation)
    const maliciousTemplate = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Invoice {{ invoice_number }}</title>
          <script>alert('XSS');</script>
        </head>
        <body>
          <h1>{{ company_name }}</h1>
          <button onclick="alert('XSS')">Click me</button>
        </body>
      </html>
    `;

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(maliciousTemplate);
    await fileInput.setInputFiles({
      name: 'malicious.html',
      mimeType: 'text/html',
      buffer,
    });

    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify security errors are shown
    const securityError = await page.locator('text=Security violation').isVisible();
    expect(securityError).toBeTruthy();

    // Verify specific violations are listed
    const scriptError = await page.locator('text=Script tags are not allowed').isVisible();
    expect(scriptError).toBeTruthy();

    const eventHandlerError = await page.locator('text=Event handlers are not allowed').isVisible();
    expect(eventHandlerError).toBeTruthy();

    // Verify approve button is disabled
    const approveButton = page.locator('button:has-text("Approve Template")');
    await expect(approveButton).toBeDisabled();
  });
});
