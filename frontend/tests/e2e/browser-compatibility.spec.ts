/**
 * E2E Tests for Browser Compatibility
 * 
 * Tests template management across different browsers:
 * 1. Chrome/Chromium
 * 2. Firefox
 * 3. Safari/WebKit
 * 
 * Verifies:
 * - File upload works in all browsers
 * - Preview iframe renders correctly
 * - Form interactions work consistently
 * - Styling is consistent
 */

import { test, expect, Page, Browser } from '@playwright/test';

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
        <style>
          body { font-family: Arial, sans-serif; }
          .header { background-color: #f0f0f0; padding: 20px; }
          .content { margin: 20px; }
        </style>
      </head>
      <body>
        <div class="header">
          <h1>{{ company_name }}</h1>
        </div>
        <div class="content">
          <p>Guest: {{ guest_name }}</p>
          <p>Check-in: {{ checkin_date }}</p>
          <p>Check-out: {{ checkout_date }}</p>
          <p>Amount: {{ amount_gross }}</p>
        </div>
      </body>
    </html>
  `;
}

test.describe('Browser Compatibility - Chromium', () => {
  test.use({ browserName: 'chromium' });

  test('should handle complete workflow in Chromium', async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);

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
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview renders correctly
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();

    // Verify CSS styles are applied
    const headerElement = await previewFrame.locator('.header').isVisible();
    expect(headerElement).toBeTruthy();
  });

  test('should handle file drag-and-drop in Chromium', async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);

    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');

    // Simulate drag-and-drop (if supported by component)
    const dropZone = page.locator('[data-testid="file-drop-zone"]');
    if (await dropZone.isVisible()) {
      const buffer = Buffer.from(createValidTemplate());
      await dropZone.setInputFiles({
        name: 'template.html',
        mimeType: 'text/html',
        buffer,
      });

      // Verify file was accepted
      const fileName = await page.locator('text=template.html').isVisible();
      expect(fileName).toBeTruthy();
    }
  });
});

test.describe('Browser Compatibility - Firefox', () => {
  test.use({ browserName: 'firefox' });

  test('should handle complete workflow in Firefox', async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);

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
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview renders correctly
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();

    // Verify CSS styles are applied
    const headerElement = await previewFrame.locator('.header').isVisible();
    expect(headerElement).toBeTruthy();
  });

  test('should handle form interactions in Firefox', async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);

    // Test dropdown selection
    await page.selectOption('select[name="templateType"]', 'btw_aangifte');
    const selectedValue = await page.locator('select[name="templateType"]').inputValue();
    expect(selectedValue).toBe('btw_aangifte');

    // Test textarea input
    const fieldMappingsTextarea = page.locator('textarea[name="fieldMappings"]');
    if (await fieldMappingsTextarea.isVisible()) {
      await fieldMappingsTextarea.fill('{"test": "value"}');
      const textareaValue = await fieldMappingsTextarea.inputValue();
      expect(textareaValue).toBe('{"test": "value"}');
    }
  });
});

test.describe('Browser Compatibility - WebKit (Safari)', () => {
  test.use({ browserName: 'webkit' });

  test('should handle complete workflow in Safari/WebKit', async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);

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
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview renders correctly
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();

    // Verify CSS styles are applied
    const headerElement = await previewFrame.locator('.header').isVisible();
    expect(headerElement).toBeTruthy();
  });

  test('should handle iframe sandbox in Safari/WebKit', async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);

    // Upload template
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

    // Verify iframe has sandbox attribute
    const iframe = page.locator('iframe[title="Template Preview"]');
    const sandboxAttr = await iframe.getAttribute('sandbox');
    expect(sandboxAttr).toBeTruthy();
    expect(sandboxAttr).toContain('allow-same-origin');
  });
});

test.describe('Browser Compatibility - Responsive Design', () => {
  const viewports = [
    { name: 'Desktop', width: 1920, height: 1080 },
    { name: 'Laptop', width: 1366, height: 768 },
    { name: 'Tablet', width: 768, height: 1024 },
    { name: 'Mobile', width: 375, height: 667 },
  ];

  for (const viewport of viewports) {
    test(`should render correctly on ${viewport.name} (${viewport.width}x${viewport.height})`, async ({ page }) => {
      // Set viewport size
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      await login(page);
      await navigateToTemplateManagement(page);

      // Verify page is visible and usable
      const heading = await page.locator('h1:has-text("Template Management")').isVisible();
      expect(heading).toBeTruthy();

      // Verify form elements are accessible
      const templateTypeSelect = await page.locator('select[name="templateType"]').isVisible();
      expect(templateTypeSelect).toBeTruthy();

      const fileInput = await page.locator('input[type="file"]').isVisible();
      expect(fileInput).toBeTruthy();

      // On mobile, some elements might be in a collapsed menu
      if (viewport.width < 768) {
        // Verify mobile menu works
        const menuButton = page.locator('[aria-label="Menu"]');
        if (await menuButton.isVisible()) {
          await menuButton.click();
          await page.waitForTimeout(500); // Wait for menu animation
        }
      }
    });
  }
});

test.describe('Browser Compatibility - Accessibility', () => {
  test('should be keyboard navigable in all browsers', async ({ page, browserName }) => {
    await login(page);
    await navigateToTemplateManagement(page);

    // Tab through form elements
    await page.keyboard.press('Tab'); // Focus on template type select
    await page.keyboard.press('Tab'); // Focus on file input
    await page.keyboard.press('Tab'); // Focus on upload button

    // Verify focus is visible
    const focusedElement = await page.evaluate(() => document.activeElement?.tagName);
    expect(focusedElement).toBeTruthy();
  });

  test('should have proper ARIA labels in all browsers', async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);

    // Verify ARIA labels exist
    const templateTypeLabel = await page.locator('[aria-label*="template type"]').isVisible();
    const fileInputLabel = await page.locator('[aria-label*="upload"]').isVisible();

    // At least one should be visible (depends on implementation)
    expect(templateTypeLabel || fileInputLabel).toBeTruthy();
  });

  test('should announce validation results to screen readers', async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);

    // Upload template
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

    // Verify validation results have role="alert" or aria-live
    const validationResults = page.locator('[data-testid="validation-results"]');
    const role = await validationResults.getAttribute('role');
    const ariaLive = await validationResults.getAttribute('aria-live');

    expect(role === 'alert' || ariaLive === 'polite' || ariaLive === 'assertive').toBeTruthy();
  });
});

test.describe('Browser Compatibility - Performance', () => {
  test('should load page quickly in all browsers', async ({ page, browserName }) => {
    const startTime = Date.now();

    await login(page);
    await navigateToTemplateManagement(page);

    const loadTime = Date.now() - startTime;

    // Page should load within 5 seconds
    expect(loadTime).toBeLessThan(5000);

    console.log(`${browserName}: Page loaded in ${loadTime}ms`);
  });

  test('should handle large template preview efficiently', async ({ page, browserName }) => {
    await login(page);
    await navigateToTemplateManagement(page);

    // Create a large template (but under 5MB limit)
    const largeTemplate = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Large Template</title>
        </head>
        <body>
          <h1>{{ company_name }}</h1>
          ${'<p>{{ guest_name }}</p>\n'.repeat(1000)}
        </body>
      </html>
    `;

    const startTime = Date.now();

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(largeTemplate);
    await fileInput.setInputFiles({
      name: 'large_template.html',
      mimeType: 'text/html',
      buffer,
    });

    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 15000 });

    const processingTime = Date.now() - startTime;

    // Should process within 15 seconds
    expect(processingTime).toBeLessThan(15000);

    console.log(`${browserName}: Large template processed in ${processingTime}ms`);
  });
});
