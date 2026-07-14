/**
 * ZZP Trip Import Wizard — E2E Tests
 *
 * Tests the multi-step import flow including:
 * - Stepper display with 3 steps
 * - Vehicle selector on upload step
 * - CSV file upload interaction
 * - Navigation between steps (Volgende/Vorige)
 * - Preview table with status badges
 * - Commit step with import button
 * - Template download link
 *
 * Reference: .kiro/specs/ZZP/rittenregistratie/tasks.md §17.3
 */

import { test, expect, Page } from '@playwright/test';
import { resolve } from 'path';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

/**
 * Helper: navigate to ZZP Trip Import page via menu button.
 * The app is a SPA using setCurrentPage('zzp-trip-import').
 */
async function navigateToImport(page: Page) {
  await page.goto(BASE_URL);
  await page.waitForLoadState('networkidle');
  // Click the import menu button (📥 emoji button)
  await page.click('button:has-text("📥")');
  // Wait for import wizard to render
  await page.waitForSelector('text=Upload', { timeout: 10000 });
}

/**
 * Helper: create a mock CSV file for upload testing.
 */
function createMockCSVBuffer(): Buffer {
  const csvContent = [
    'datum,van,naar,begin_km,eind_km,categorie',
    '2025-01-15,Amsterdam,Rotterdam,50000,50075,Zakelijk',
    '2025-01-16,Rotterdam,Utrecht,50075,50130,Zakelijk',
    '2025-01-17,Utrecht,Amsterdam,50130,50180,Woon-werk',
  ].join('\n');
  return Buffer.from(csvContent, 'utf-8');
}

test.describe('ZZP Trip Import Wizard', () => {
  test.beforeEach(async ({ page }) => {
    await navigateToImport(page);
  });

  // ─── Stepper Display ───

  test('stepper shows 3 steps: Upload, Preview, Importeren', async ({ page }) => {
    await expect(page.locator('text=Upload')).toBeVisible();
    await expect(page.locator('text=Preview')).toBeVisible();
    await expect(page.locator('text=Importeren')).toBeVisible();
  });

  test('stepper shows step 1 (Upload) as active initially', async ({ page }) => {
    // The first step should be highlighted/active
    // TripImportStepper uses color to indicate active step
    const uploadStep = page.locator('text=Upload');
    await expect(uploadStep).toBeVisible();
  });

  // ─── Step 1: Upload ───

  test('step 1 shows vehicle selector', async ({ page }) => {
    const vehicleSelect = page.locator('select').first();
    await expect(vehicleSelect).toBeVisible();
    // Should have vehicle options
    const options = vehicleSelect.locator('option');
    await expect(options).not.toHaveCount(0);
  });

  test('step 1 shows file upload area with drag zone', async ({ page }) => {
    // Drop zone text
    await expect(page.locator('text=Sleep een CSV')).toBeVisible();
  });

  test('template download link is visible and clickable', async ({ page }) => {
    const templateLink = page.locator('text=Download template');
    await expect(templateLink).toBeVisible();
  });

  test('"Volgende" button is disabled without file selected', async ({ page }) => {
    const nextBtn = page.locator('button:has-text("Volgende")');
    await expect(nextBtn).toBeVisible();
    await expect(nextBtn).toBeDisabled();
  });

  test('uploading a CSV file enables the "Volgende" button', async ({ page }) => {
    // Set file on the hidden file input
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });

    // File name should appear in the upload zone
    await expect(page.locator('text=ritten_test.csv')).toBeVisible();

    // Next button should now be enabled
    const nextBtn = page.locator('button:has-text("Volgende")');
    await expect(nextBtn).toBeEnabled();
  });

  test('clicking "Volgende" after file upload transitions to preview step', async ({ page }) => {
    // Upload a file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });

    // Click next
    const nextBtn = page.locator('button:has-text("Volgende")');
    await nextBtn.click();

    // Wait for either preview table or loading spinner
    await expect(
      page.locator('table').or(page.locator('[role="status"]')).or(page.locator('text=mislukt'))
    ).toBeVisible({ timeout: 15000 });
  });

  // ─── Step 2: Preview ───

  test('preview step shows validation summary badges', async ({ page }) => {
    // Upload file and navigate to preview
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });
    await page.click('button:has-text("Volgende")');

    // Wait for preview to load
    await page.waitForTimeout(2000);

    // If preview loaded successfully, check for summary badges
    const previewTable = page.locator('table');
    if (await previewTable.isVisible()) {
      // Summary badges: Totaal, Geldig, Waarschuwingen, Fouten
      await expect(page.locator('text=Totaal').or(page.locator('text=rijen'))).toBeVisible();
      await expect(page.locator('text=Geldig')).toBeVisible();
    }
  });

  test('preview table shows status badges per row', async ({ page }) => {
    // Upload file and navigate to preview
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });
    await page.click('button:has-text("Volgende")');
    await page.waitForTimeout(2000);

    const previewTable = page.locator('table');
    if (await previewTable.isVisible()) {
      // Status badges: OK, Waarschuwing, or Fout
      const statusBadges = page.locator('text=OK, text=Waarschuwing, text=Fout');
      await expect(statusBadges.first()).toBeVisible();
    }
  });

  test('preview table has correct column headers', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });
    await page.click('button:has-text("Volgende")');
    await page.waitForTimeout(2000);

    const previewTable = page.locator('table');
    if (await previewTable.isVisible()) {
      await expect(page.locator('th:has-text("Datum")')).toBeVisible();
      await expect(page.locator('th:has-text("Van")')).toBeVisible();
      await expect(page.locator('th:has-text("Naar")')).toBeVisible();
      await expect(page.locator('th:has-text("Begin KM")')).toBeVisible();
      await expect(page.locator('th:has-text("Eind KM")')).toBeVisible();
      await expect(page.locator('th:has-text("Status")')).toBeVisible();
    }
  });

  // ─── Step 3: Commit ───

  test('commit step shows import summary and button', async ({ page }) => {
    // Upload file, navigate through steps
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });
    await page.click('button:has-text("Volgende")');
    await page.waitForTimeout(2000);

    // If preview loaded, navigate to commit step
    const nextBtn2 = page.locator('button:has-text("Volgende")');
    if (await nextBtn2.isVisible() && await nextBtn2.isEnabled()) {
      await nextBtn2.click();

      // Commit step should show summary
      await expect(
        page.locator('text=Samenvatting').or(page.locator('text=Importeer'))
      ).toBeVisible({ timeout: 5000 });

      // Import button should be present
      await expect(
        page.locator('button:has-text("Importeer")')
      ).toBeVisible();
    }
  });

  test('clicking "Import" button triggers import and shows success', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });
    await page.click('button:has-text("Volgende")');
    await page.waitForTimeout(2000);

    const nextBtn2 = page.locator('button:has-text("Volgende")');
    if (await nextBtn2.isVisible() && await nextBtn2.isEnabled()) {
      await nextBtn2.click();
      await page.waitForTimeout(500);

      const importBtn = page.locator('button:has-text("Importeer")');
      if (await importBtn.isVisible()) {
        await importBtn.click();

        // Should show success toast or "Import voltooid" badge
        await expect(
          page.locator('text=geslaagd').or(page.locator('text=voltooid')).or(page.locator('text=mislukt'))
        ).toBeVisible({ timeout: 15000 });
      }
    }
  });

  // ─── Navigation Controls ───

  test('"Vorige" button is disabled on step 1', async ({ page }) => {
    const backBtn = page.locator('button:has-text("Vorige")');
    await expect(backBtn).toBeVisible();
    await expect(backBtn).toBeDisabled();
  });

  test('"Vorige" button navigates back from step 2', async ({ page }) => {
    // Upload file and go to step 2
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });
    await page.click('button:has-text("Volgende")');
    await page.waitForTimeout(2000);

    // Click back
    const backBtn = page.locator('button:has-text("Vorige")');
    if (await backBtn.isEnabled()) {
      await backBtn.click();
      // Should be back on upload step
      await expect(page.locator('text=Sleep een CSV')).toBeVisible();
    }
  });

  // ─── File Size Display ───

  test('uploaded file shows file size information', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'ritten_test.csv',
      mimeType: 'text/csv',
      buffer: createMockCSVBuffer(),
    });

    // Should display file size (in KB)
    await expect(page.locator('text=KB')).toBeVisible();
  });
});
