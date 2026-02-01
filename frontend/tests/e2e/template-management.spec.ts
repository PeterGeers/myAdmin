/**
 * E2E Tests for Template Management Workflow
 * 
 * Tests the complete workflow from UI to database:
 * 1. Upload template
 * 2. Validate template
 * 3. Preview template
 * 4. Get AI help (if errors)
 * 5. Approve/Reject template
 * 6. Verify database storage
 */

import { test, expect, Page } from '@playwright/test';

// Test configuration
const TEST_USER_EMAIL = 'test@example.com';
const TEST_USER_PASSWORD = 'TestPassword123!';
const TEST_ADMINISTRATION = 'GoodwinSolutions';

// Template types to test
const TEMPLATE_TYPES = [
  'str_invoice_nl',
  'btw_aangifte',
  'aangifte_ib',
  'toeristenbelasting',
] as const;

/**
 * Helper: Login to the application
 */
async function login(page: Page) {
  await page.goto('/login');
  
  // Fill in login form
  await page.fill('input[name="email"]', TEST_USER_EMAIL);
  await page.fill('input[name="password"]', TEST_USER_PASSWORD);
  
  // Submit form
  await page.click('button[type="submit"]');
  
  // Wait for navigation to dashboard
  await page.waitForURL('/dashboard', { timeout: 10000 });
}

/**
 * Helper: Navigate to template management
 */
async function navigateToTemplateManagement(page: Page) {
  // Click on Tenant Admin menu
  await page.click('text=Tenant Admin');
  
  // Click on Template Management
  await page.click('text=Template Management');
  
  // Wait for page to load
  await page.waitForSelector('h1:has-text("Template Management")');
}

/**
 * Helper: Create a valid template
 */
function createValidTemplate(templateType: string): string {
  const templates: Record<string, string> = {
    str_invoice_nl: `
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
    `,
    btw_aangifte: `
      <!DOCTYPE html>
      <html>
        <head>
          <title>BTW Aangifte {{ year }} Q{{ quarter }}</title>
        </head>
        <body>
          <h1>{{ company_name }}</h1>
          <p>Year: {{ year }}</p>
          <p>Quarter: {{ quarter }}</p>
          <table>{{ btw_table_rows }}</table>
        </body>
      </html>
    `,
    aangifte_ib: `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Aangifte IB {{ year }}</title>
        </head>
        <body>
          <h1>{{ company_name }}</h1>
          <p>Year: {{ year }}</p>
          <table>{{ aangifte_table_rows }}</table>
        </body>
      </html>
    `,
    toeristenbelasting: `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Toeristenbelasting {{ year }}</title>
        </head>
        <body>
          <h1>{{ company_name }}</h1>
          <p>Year: {{ year }}</p>
          <p>Nights: {{ total_nights }}</p>
          <p>Tax: {{ tourist_tax_amount }}</p>
        </body>
      </html>
    `,
  };
  
  return templates[templateType] || templates.str_invoice_nl;
}

/**
 * Helper: Create an invalid template (missing required placeholders)
 */
function createInvalidTemplate(): string {
  return `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Invalid Template</title>
      </head>
      <body>
        <h1>Missing Required Placeholders</h1>
        <p>This template is missing required fields</p>
      </body>
    </html>
  `;
}

/**
 * Helper: Create a template with HTML syntax errors
 */
function createMalformedTemplate(): string {
  return `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Malformed Template</title>
      </head>
      <body>
        <h1>Unclosed tag
        <p>Missing closing tag
        <div>
      </body>
    </html>
  `;
}

test.describe('Template Management E2E', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await login(page);
    
    // Navigate to template management
    await navigateToTemplateManagement(page);
  });

  test('should complete full workflow: upload → validate → preview → approve', async ({ page }) => {
    // Step 1: Select template type
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    
    // Step 2: Upload template file
    const templateContent = createValidTemplate('str_invoice_nl');
    const fileInput = page.locator('input[type="file"]');
    
    // Create a file from template content
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'str_invoice_template.html',
      mimeType: 'text/html',
      buffer,
    });
    
    // Step 3: Click upload & preview button
    await page.click('button:has-text("Upload & Preview")');
    
    // Step 4: Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });
    
    // Step 5: Verify validation passed
    const validationSuccess = await page.locator('text=Validation Passed').isVisible();
    expect(validationSuccess).toBeTruthy();
    
    // Step 6: Verify preview is displayed
    const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
    await expect(previewFrame.locator('body')).toBeVisible();
    
    // Step 7: Add approval notes
    await page.fill('textarea[name="approvalNotes"]', 'E2E test approval');
    
    // Step 8: Click approve button
    await page.click('button:has-text("Approve Template")');
    
    // Step 9: Confirm approval in dialog
    await page.click('button:has-text("Confirm")');
    
    // Step 10: Wait for success message
    await page.waitForSelector('text=Template approved successfully', { timeout: 10000 });
    
    // Step 11: Verify template is saved (check for success indicator)
    const successMessage = await page.locator('text=Template approved successfully').isVisible();
    expect(successMessage).toBeTruthy();
  });

  test('should handle invalid template with validation errors', async ({ page }) => {
    // Step 1: Select template type
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    
    // Step 2: Upload invalid template
    const templateContent = createInvalidTemplate();
    const fileInput = page.locator('input[type="file"]');
    
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'invalid_template.html',
      mimeType: 'text/html',
      buffer,
    });
    
    // Step 3: Click upload & preview button
    await page.click('button:has-text("Upload & Preview")');
    
    // Step 4: Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });
    
    // Step 5: Verify validation failed
    const validationErrors = await page.locator('[data-testid="validation-error"]').count();
    expect(validationErrors).toBeGreaterThan(0);
    
    // Step 6: Verify approve button is disabled
    const approveButton = page.locator('button:has-text("Approve Template")');
    await expect(approveButton).toBeDisabled();
    
    // Step 7: Verify AI help button is enabled
    const aiHelpButton = page.locator('button:has-text("Get AI Help")');
    await expect(aiHelpButton).toBeEnabled();
  });

  test('should handle malformed HTML template', async ({ page }) => {
    // Step 1: Select template type
    await page.selectOption('select[name="templateType"]', 'btw_aangifte');
    
    // Step 2: Upload malformed template
    const templateContent = createMalformedTemplate();
    const fileInput = page.locator('input[type="file"]');
    
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'malformed_template.html',
      mimeType: 'text/html',
      buffer,
    });
    
    // Step 3: Click upload & preview button
    await page.click('button:has-text("Upload & Preview")');
    
    // Step 4: Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });
    
    // Step 5: Verify HTML syntax errors are shown
    const syntaxError = await page.locator('text=HTML syntax error').isVisible();
    expect(syntaxError).toBeTruthy();
    
    // Step 6: Verify error details are displayed
    const errorDetails = await page.locator('[data-testid="validation-error"]').count();
    expect(errorDetails).toBeGreaterThan(0);
  });

  test('should reject template with reason', async ({ page }) => {
    // Step 1: Select template type
    await page.selectOption('select[name="templateType"]', 'aangifte_ib');
    
    // Step 2: Upload valid template
    const templateContent = createValidTemplate('aangifte_ib');
    const fileInput = page.locator('input[type="file"]');
    
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'aangifte_ib_template.html',
      mimeType: 'text/html',
      buffer,
    });
    
    // Step 3: Click upload & preview button
    await page.click('button:has-text("Upload & Preview")');
    
    // Step 4: Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });
    
    // Step 5: Click reject button
    await page.click('button:has-text("Reject Template")');
    
    // Step 6: Fill in rejection reason
    await page.fill('textarea[name="rejectionReason"]', 'E2E test rejection - template needs revision');
    
    // Step 7: Confirm rejection
    await page.click('button:has-text("Confirm Rejection")');
    
    // Step 8: Wait for success message
    await page.waitForSelector('text=Template rejected', { timeout: 10000 });
    
    // Step 9: Verify rejection was logged
    const rejectionMessage = await page.locator('text=Template rejected').isVisible();
    expect(rejectionMessage).toBeTruthy();
  });

  test('should handle file size validation', async ({ page }) => {
    // Step 1: Select template type
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    
    // Step 2: Create a large file (>5MB)
    const largeContent = '<html><body>' + 'x'.repeat(6 * 1024 * 1024) + '</body></html>';
    const fileInput = page.locator('input[type="file"]');
    
    const buffer = Buffer.from(largeContent);
    await fileInput.setInputFiles({
      name: 'large_template.html',
      mimeType: 'text/html',
      buffer,
    });
    
    // Step 3: Verify error message is shown
    await page.waitForSelector('text=File size exceeds maximum', { timeout: 5000 });
    
    // Step 4: Verify upload button is disabled
    const uploadButton = page.locator('button:has-text("Upload & Preview")');
    await expect(uploadButton).toBeDisabled();
  });

  test('should handle non-HTML file rejection', async ({ page }) => {
    // Step 1: Select template type
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    
    // Step 2: Try to upload a non-HTML file
    const fileInput = page.locator('input[type="file"]');
    
    const buffer = Buffer.from('This is a text file');
    await fileInput.setInputFiles({
      name: 'document.txt',
      mimeType: 'text/plain',
      buffer,
    });
    
    // Step 3: Verify error message is shown
    await page.waitForSelector('text=Only HTML files are allowed', { timeout: 5000 });
    
    // Step 4: Verify upload button is disabled
    const uploadButton = page.locator('button:has-text("Upload & Preview")');
    await expect(uploadButton).toBeDisabled();
  });
});

test.describe('Template Management - AI Assistance E2E', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);
  });

  test('should get AI help for template errors', async ({ page }) => {
    // Step 1: Select template type
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    
    // Step 2: Upload invalid template
    const templateContent = createInvalidTemplate();
    const fileInput = page.locator('input[type="file"]');
    
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'invalid_template.html',
      mimeType: 'text/html',
      buffer,
    });
    
    // Step 3: Click upload & preview button
    await page.click('button:has-text("Upload & Preview")');
    
    // Step 4: Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });
    
    // Step 5: Click AI help button
    await page.click('button:has-text("Get AI Help")');
    
    // Step 6: Wait for AI response
    await page.waitForSelector('[data-testid="ai-suggestions"]', { timeout: 30000 });
    
    // Step 7: Verify AI suggestions are displayed
    const suggestions = await page.locator('[data-testid="ai-suggestion"]').count();
    expect(suggestions).toBeGreaterThan(0);
    
    // Step 8: Verify fix suggestions have code examples
    const codeExample = await page.locator('code').first().isVisible();
    expect(codeExample).toBeTruthy();
  });

  test('should apply AI auto-fixes', async ({ page }) => {
    // Step 1: Select template type
    await page.selectOption('select[name="templateType"]', 'str_invoice_nl');
    
    // Step 2: Upload invalid template
    const templateContent = createInvalidTemplate();
    const fileInput = page.locator('input[type="file"]');
    
    const buffer = Buffer.from(templateContent);
    await fileInput.setInputFiles({
      name: 'invalid_template.html',
      mimeType: 'text/html',
      buffer,
    });
    
    // Step 3: Click upload & preview button
    await page.click('button:has-text("Upload & Preview")');
    
    // Step 4: Wait for validation results
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });
    
    // Step 5: Click AI help button
    await page.click('button:has-text("Get AI Help")');
    
    // Step 6: Wait for AI response
    await page.waitForSelector('[data-testid="ai-suggestions"]', { timeout: 30000 });
    
    // Step 7: Click apply all fixes button
    await page.click('button:has-text("Apply All Auto-Fixes")');
    
    // Step 8: Wait for fixes to be applied
    await page.waitForSelector('text=Fixes applied successfully', { timeout: 10000 });
    
    // Step 9: Verify template content was updated
    const successMessage = await page.locator('text=Fixes applied successfully').isVisible();
    expect(successMessage).toBeTruthy();
    
    // Step 10: Verify validation is re-run automatically
    await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });
  });
});

test.describe('Template Management - Multiple Template Types', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToTemplateManagement(page);
  });

  for (const templateType of TEMPLATE_TYPES) {
    test(`should handle ${templateType} template workflow`, async ({ page }) => {
      // Step 1: Select template type
      await page.selectOption('select[name="templateType"]', templateType);
      
      // Step 2: Upload valid template for this type
      const templateContent = createValidTemplate(templateType);
      const fileInput = page.locator('input[type="file"]');
      
      const buffer = Buffer.from(templateContent);
      await fileInput.setInputFiles({
        name: `${templateType}_template.html`,
        mimeType: 'text/html',
        buffer,
      });
      
      // Step 3: Click upload & preview button
      await page.click('button:has-text("Upload & Preview")');
      
      // Step 4: Wait for validation results
      await page.waitForSelector('[data-testid="validation-results"]', { timeout: 10000 });
      
      // Step 5: Verify validation passed
      const validationSuccess = await page.locator('text=Validation Passed').isVisible();
      expect(validationSuccess).toBeTruthy();
      
      // Step 6: Verify preview is displayed
      const previewFrame = page.frameLocator('iframe[title="Template Preview"]');
      await expect(previewFrame.locator('body')).toBeVisible();
      
      // Step 7: Verify template-specific content is rendered
      const hasContent = await previewFrame.locator('h1').isVisible();
      expect(hasContent).toBeTruthy();
    });
  }
});
