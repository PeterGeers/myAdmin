/**
 * E2E Tests with Real Templates
 * 
 * Tests using actual template files from the project:
 * 1. Real STR invoice templates (NL/EN)
 * 2. Real BTW aangifte template
 * 3. Real Aangifte IB template
 * 4. Real Toeristenbelasting template
 * 5. Real Financial report template
 */

import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// Test configuration
const TEST_USER_EMAIL = 'test@example.com';
const TEST_USER_PASSWORD = 'TestPassword123!';

// Template file paths (relative to project root)
const TEMPLATE_PATHS = {
  str_invoice_nl: 'backend/templates/html/str_invoice_nl_template.html',
  str_invoice_en: 'backend/templates/html/str_invoice_en_template.html',
  btw_aangifte: 'backend/templates/html/btw_aangifte_template.html',
  aangifte_ib: 'backend/templates/html/aangifte_ib_template.html',
  toeristenbelasting: 'backend/templates/html/toeristenbelasting_template.html',
  financial_report: 'backend/templates/html/financial_report_template.html',
};

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
 * Helper: Load real template file
 */
function loadRealTemplate(templateKey: keyof typeof TEMPLATE_PATHS): string {
  const templatePath = TEMPLATE_PATHS[templateKey];
  const fullPath = path.join(process.cwd(), '..', templatePath);
  
  if (!fs.existsSync(fullPath)) {
    throw new Error(`Template file not found: ${fullPath}`);
  }
  
  return fs.readFileSync(fullPath, 'utf-8');
}

test.describe('Template Management - Real Templates', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);
  });

  test('should validate and preview real STR invoice NL template', async ({ page }) => {
    // Load real template
    const templateContent = loadRealTemplate('str_invoice_nl');

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'str_invoice_nl_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview is displayed
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();

    // Verify template-specific content
    const hasInvoiceContent = await previewFrame.locator('text=Factuur').isVisible();
    expect(hasInvoiceContent).toBeTruthy();
  });

  test('should validate and preview real STR invoice EN template', async ({ page }) => {
    // Load real template
    const templateContent = loadRealTemplate('str_invoice_en');

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl'); // Use same type, different language
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'str_invoice_en_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview is displayed
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();

    // Verify template-specific content (English)
    const hasInvoiceContent = await previewFrame.locator('text=Invoice').isVisible();
    expect(hasInvoiceContent).toBeTruthy();
  });

  test('should validate and preview real BTW aangifte template', async ({ page }) => {
    // Load real template
    const templateContent = loadRealTemplate('btw_aangifte');

    // Upload template
    await page.selectOption('select[name="templateType"]', 'btw_aangifte');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'btw_aangifte_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview is displayed
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();

    // Verify template-specific content
    const hasBTWContent = await previewFrame.locator('text=BTW').isVisible();
    expect(hasBTWContent).toBeTruthy();
  });

  test('should validate and preview real Aangifte IB template', async ({ page }) => {
    // Load real template
    const templateContent = loadRealTemplate('aangifte_ib');

    // Upload template
    await page.selectOption('select[name="templateType"]', 'aangifte_ib');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'aangifte_ib_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview is displayed
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();

    // Verify template-specific content
    const hasIBContent = await previewFrame.locator('text=Inkomstenbelasting').isVisible();
    expect(hasIBContent).toBeTruthy();
  });

  test('should validate and preview real Toeristenbelasting template', async ({ page }) => {
    // Load real template
    const templateContent = loadRealTemplate('toeristenbelasting');

    // Upload template
    await page.selectOption('select[name="templateType"]', 'toeristenbelasting');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'toeristenbelasting_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview is displayed
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();

    // Verify template-specific content
    const hasTouristTaxContent = await previewFrame.locator('text=Toeristenbelasting').isVisible();
    expect(hasTouristTaxContent).toBeTruthy();
  });

  test('should handle real template with complex styling', async ({ page }) => {
    // Load real template (BTW aangifte has complex tables and styling)
    const templateContent = loadRealTemplate('btw_aangifte');

    // Upload template
    await page.selectOption('select[name="templateType"]', 'btw_aangifte');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'btw_aangifte_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');

    // Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();

    // Verify preview renders tables correctly
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    const hasTable = await previewFrame.locator('table').isVisible();
    expect(hasTable).toBeTruthy();

    // Verify CSS styles are applied
    const hasStyledElements = await previewFrame.locator('[style]').count();
    expect(hasStyledElements).toBeGreaterThan(0);
  });

  test('should approve real template and save to database', async ({ page }) => {
    // Load real template
    const templateContent = loadRealTemplate('str_invoice_nl');

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'str_invoice_nl_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Approve template
    await page.fill('textarea[name="approvalNotes"]', 'E2E test: Real template approval');
    await page.click('button:has-text("Approve Template")');
    await page.click('button:has-text("Confirm")');

    // Wait for success message
    await page.waitForSelector('text=Template approved successfully', { timeout: 10000 });

    // Verify success message
    const successMessage = await page.locator('text=Template approved successfully').isVisible();
    expect(successMessage).toBeTruthy();

    // Verify file ID is returned
    const fileIdMessage = await page.locator('text=File ID:').isVisible();
    expect(fileIdMessage).toBeTruthy();
  });
});

test.describe('Template Management - AI Assistance with Real API', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);
  });

  test('should get AI help with real OpenRouter API', async ({ page }) => {
    // Skip if OPENROUTER_API_KEY is not set
    if (!process.env.OPENROUTER_API_KEY) {
      test.skip();
    }

    // Create template with intentional errors
    const invalidTemplate = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Invoice</title>
        </head>
        <body>
          <h1>Missing required placeholders</h1>
          <p>This template is missing invoice_number, company_name, guest_name, etc.</p>
        </body>
      </html>
    `;

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(invalidTemplate);
    await fileInput.setInputFiles({
      name: 'invalid_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Click AI help button
    await page.click('button:has-text("Get AI Help")');

    // Wait for AI response (may take 10-30 seconds)
    await page.waitForSelector('[data-testid="ai-suggestions"]', { timeout: 60000 });

    // Verify AI suggestions are displayed
    const suggestions = await page.locator('[data-testid="ai-suggestion"]').count();
    expect(suggestions).toBeGreaterThan(0);

    // Verify suggestions have analysis text
    const analysisText = await page.locator('[data-testid="ai-analysis"]').isVisible();
    expect(analysisText).toBeTruthy();

    // Verify suggestions have code examples
    const codeExamples = await page.locator('code').count();
    expect(codeExamples).toBeGreaterThan(0);

    // Verify confidence indicators are shown
    const confidenceIndicator = await page.locator('[data-testid="confidence-indicator"]').isVisible();
    expect(confidenceIndicator).toBeTruthy();
  });

  test('should apply AI fixes with real OpenRouter API', async ({ page }) => {
    // Skip if OPENROUTER_API_KEY is not set
    if (!process.env.OPENROUTER_API_KEY) {
      test.skip();
    }

    // Create template with fixable errors
    const fixableTemplate = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Invoice</title>
        </head>
        <body>
          <h1>Company Name</h1>
          <p>Missing placeholders for invoice data</p>
        </body>
      </html>
    `;

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(fixableTemplate);
    await fileInput.setInputFiles({
      name: 'fixable_template.html',
      mimeType: 'text/html',
      buffer,
    });

    // Click upload & preview
    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Click AI help button
    await page.click('button:has-text("Get AI Help")');
    await page.waitForSelector('[data-testid="ai-suggestions"]', { timeout: 60000 });

    // Apply all auto-fixes
    await page.click('button:has-text("Apply All Auto-Fixes")');

    // Wait for fixes to be applied
    await page.waitForSelector('text=Fixes applied successfully', { timeout: 10000 });

    // Verify validation is re-run
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Verify errors are reduced or eliminated
    const errorCount = await page.locator('[data-testid="validation-error"]').count();
    // After AI fixes, there should be fewer errors (or none)
    expect(errorCount).toBeLessThan(5); // Assuming original had more errors
  });

  test('should handle AI API rate limiting gracefully', async ({ page }) => {
    // Skip if OPENROUTER_API_KEY is not set
    if (!process.env.OPENROUTER_API_KEY) {
      test.skip();
    }

    // Create invalid template
    const invalidTemplate = '<html><body><p>Missing placeholders</p></body></html>';

    // Upload template
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    const buffer = Buffer.from(invalidTemplate);
    await fileInput.setInputFiles({
      name: 'invalid.html',
      mimeType: 'text/html',
      buffer,
    });

    await page.click('button:has-text("Upload & Preview")');
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });

    // Make multiple rapid AI help requests
    for (let i = 0; i < 5; i++) {
      await page.click('button:has-text("Get AI Help")');
      await page.waitForTimeout(1000); // Small delay between requests
    }

    // Verify rate limit message is shown (if rate limited)
    const rateLimitMessage = await page.locator('text=Too many requests').isVisible();
    if (rateLimitMessage) {
      // Verify user is informed about rate limit
      const retryMessage = await page.locator('text=Please try again later').isVisible();
      expect(retryMessage).toBeTruthy();
    }
  });
});
