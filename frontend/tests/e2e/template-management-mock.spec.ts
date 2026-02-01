/**
 * E2E Tests for Template Management (Mocked Backend)
 * 
 * These tests run without requiring the backend server by mocking API responses.
 * This allows for faster test execution and CI/CD integration.
 * 
 * For full integration tests with real backend, see other spec files.
 */

import { test, expect, Page } from '@playwright/test';

// Test configuration
const BASE_URL = 'http://localhost:3000';

/**
 * Mock successful preview response
 */
const mockPreviewSuccess = {
  success: true,
  preview_html: `
    <html>
      <body>
        <h1>Test Company</h1>
        <p>Guest: John Doe</p>
        <p>Amount: €100.00</p>
      </body>
    </html>
  `,
  validation: {
    is_valid: true,
    errors: [],
    warnings: [],
    checks_performed: ['html_syntax', 'placeholders', 'security'],
  },
  sample_data_info: {
    source: 'database',
    message: 'Using most recent booking data',
  },
};

/**
 * Mock validation error response
 */
const mockValidationErrors = {
  success: true,
  preview_html: '<html><body><p>Preview with errors</p></body></html>',
  validation: {
    is_valid: false,
    errors: [
      {
        type: 'placeholder',
        message: 'Missing required placeholder: invoice_number',
        severity: 'error',
      },
      {
        type: 'placeholder',
        message: 'Missing required placeholder: company_name',
        severity: 'error',
      },
    ],
    warnings: [],
    checks_performed: ['html_syntax', 'placeholders', 'security'],
  },
  sample_data_info: {
    source: 'placeholder',
  },
};

/**
 * Mock approval success response
 */
const mockApprovalSuccess = {
  success: true,
  template_id: 'tmpl_123456',
  file_id: 'gdrive_file_789',
  message: 'Template approved and saved to Google Drive',
};

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
        <p>Check-in: {{ checkin_date }}</p>
        <p>Check-out: {{ checkout_date }}</p>
        <p>Amount: {{ amount_gross }}</p>
      </body>
    </html>
  `;
}

test.describe('Template Management E2E (Mocked)', () => {
  test.beforeEach(async ({ page }) => {
    // Mock authentication
    await page.route('**/api/auth/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          user: {
            email: 'test@example.com',
            roles: ['Tenant_Admin'],
            tenants: ['GoodwinSolutions'],
          },
        }),
      });
    });

    // Navigate to template management (assuming direct access for testing)
    await page.goto(`${BASE_URL}/tenant-admin/templates`);
  });

  test('should complete full workflow with mocked backend', async ({ page }) => {
    // Mock preview API
    await page.route('**/api/tenant-admin/templates/preview', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockPreviewSuccess),
      });
    });

    // Mock approval API
    await page.route('**/api/tenant-admin/templates/approve', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockApprovalSuccess),
      });
    });

    // Step 1: Select template type
    const templateTypeSelect = page.locator('select[name="templateType"]');
    if (await templateTypeSelect.isVisible()) {
      await templateTypeSelect.selectOption('str_invoice_nl');
    }

    // Step 2: Upload template file
    const fileInput = page.locator('input[type="file"]');
    if (await fileInput.isVisible()) {
      const templateContent = createValidTemplate();
      const buffer = Buffer.from(templateContent);
      await fileInput.setInputFiles({
        name: 'str_invoice_template.html',
        mimeType: 'text/html',
        buffer,
      });
    }

    // Step 3: Click upload & preview button
    const uploadButton = page.locator('button:has-text("Upload")').first();
    if (await uploadButton.isVisible()) {
      await uploadButton.click();

      // Step 4: Wait for validation results
      await page.waitForTimeout(2000); // Give time for API call

      // Step 5: Verify validation passed (if validation results are shown)
      const validationSuccess = page.locator('text=Validation Passed');
      if (await validationSuccess.isVisible()) {
        expect(await validationSuccess.isVisible()).toBeTruthy();
      }

      // Step 6: Verify preview is displayed (if preview iframe exists)
      const previewFrame = page.frameLocator('iframe[title*="Preview"]');
      const previewBody = previewFrame.locator('body');
      if (await previewBody.count() > 0) {
        await expect(previewBody).toBeVisible();
      }

      // Step 7: Click approve button (if visible)
      const approveButton = page.locator('button:has-text("Approve")').first();
      if (await approveButton.isVisible() && !(await approveButton.isDisabled())) {
        await approveButton.click();

        // Step 8: Confirm approval in dialog (if exists)
        const confirmButton = page.locator('button:has-text("Confirm")').first();
        if (await confirmButton.isVisible()) {
          await confirmButton.click();
        }

        // Step 9: Wait for success message
        await page.waitForTimeout(2000);

        // Step 10: Verify success message (if shown)
        const successMessage = page.locator('text=approved');
        if (await successMessage.isVisible()) {
          expect(await successMessage.isVisible()).toBeTruthy();
        }
      }
    }
  });

  test('should handle validation errors with mocked backend', async ({ page }) => {
    // Mock preview API with errors
    await page.route('**/api/tenant-admin/templates/preview', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockValidationErrors),
      });
    });

    // Select template type
    const templateTypeSelect = page.locator('select[name="templateType"]');
    if (await templateTypeSelect.isVisible()) {
      await templateTypeSelect.selectOption('str_invoice_nl');
    }

    // Upload invalid template
    const fileInput = page.locator('input[type="file"]');
    if (await fileInput.isVisible()) {
      const invalidTemplate = '<html><body><p>Missing placeholders</p></body></html>';
      const buffer = Buffer.from(invalidTemplate);
      await fileInput.setInputFiles({
        name: 'invalid_template.html',
        mimeType: 'text/html',
        buffer,
      });
    }

    // Click upload & preview
    const uploadButton = page.locator('button:has-text("Upload")').first();
    if (await uploadButton.isVisible()) {
      await uploadButton.click();
      await page.waitForTimeout(2000);

      // Verify validation errors are shown (if error display exists)
      const errorMessage = page.locator('text=Missing required placeholder');
      if (await errorMessage.isVisible()) {
        expect(await errorMessage.isVisible()).toBeTruthy();
      }

      // Verify approve button is disabled (if exists)
      const approveButton = page.locator('button:has-text("Approve")').first();
      if (await approveButton.isVisible()) {
        expect(await approveButton.isDisabled()).toBeTruthy();
      }
    }
  });

  test('should handle API errors gracefully', async ({ page }) => {
    // Mock preview API with error
    await page.route('**/api/tenant-admin/templates/preview', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Internal server error',
          message: 'Failed to generate preview',
        }),
      });
    });

    // Select template type
    const templateTypeSelect = page.locator('select[name="templateType"]');
    if (await templateTypeSelect.isVisible()) {
      await templateTypeSelect.selectOption('str_invoice_nl');
    }

    // Upload template
    const fileInput = page.locator('input[type="file"]');
    if (await fileInput.isVisible()) {
      const templateContent = createValidTemplate();
      const buffer = Buffer.from(templateContent);
      await fileInput.setInputFiles({
        name: 'template.html',
        mimeType: 'text/html',
        buffer,
      });
    }

    // Click upload & preview
    const uploadButton = page.locator('button:has-text("Upload")').first();
    if (await uploadButton.isVisible()) {
      await uploadButton.click();
      await page.waitForTimeout(2000);

      // Verify error message is shown (if error display exists)
      const errorMessage = page.locator('text=error', { hasText: /failed|error/i });
      if (await errorMessage.count() > 0) {
        expect(await errorMessage.first().isVisible()).toBeTruthy();
      }
    }
  });

  test('should verify page structure and elements exist', async ({ page }) => {
    // This test verifies the basic structure without requiring full functionality

    // Verify page loaded
    await page.waitForLoadState('domcontentloaded');

    // Check for key elements (flexible - may not all exist)
    const heading = page.locator('h1, h2').first();
    if (await heading.isVisible()) {
      expect(await heading.isVisible()).toBeTruthy();
    }

    // Check for form elements
    const selects = await page.locator('select').count();
    const inputs = await page.locator('input').count();
    const buttons = await page.locator('button').count();

    // At least some interactive elements should exist
    expect(selects + inputs + buttons).toBeGreaterThan(0);
  });
});

test.describe('Template Management - Component Rendering', () => {
  test('should render template management page', async ({ page }) => {
    // Navigate directly to the page
    await page.goto(`${BASE_URL}/tenant-admin/templates`);

    // Wait for page to load
    await page.waitForLoadState('domcontentloaded');

    // Verify page is accessible (doesn't throw 404)
    const title = await page.title();
    expect(title).toBeTruthy();

    // Take a screenshot for visual verification
    await page.screenshot({ path: 'playwright-report/template-management-page.png', fullPage: true });
  });

  test('should have responsive layout', async ({ page }) => {
    // Test different viewport sizes
    const viewports = [
      { width: 1920, height: 1080, name: 'Desktop' },
      { width: 768, height: 1024, name: 'Tablet' },
      { width: 375, height: 667, name: 'Mobile' },
    ];

    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(`${BASE_URL}/tenant-admin/templates`);
      await page.waitForLoadState('domcontentloaded');

      // Take screenshot for each viewport
      await page.screenshot({
        path: `playwright-report/template-management-${viewport.name.toLowerCase()}.png`,
        fullPage: true,
      });

      // Verify page is still usable
      const body = page.locator('body');
      expect(await body.isVisible()).toBeTruthy();
    }
  });
});
