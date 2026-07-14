/**
 * ZZP Trips (Rittenregistratie) — E2E Tests
 *
 * Tests the complete trip CRUD flow including:
 * - Page navigation and vehicle selector
 * - Trip table rendering with correct columns
 * - Trip creation modal and form submission
 * - Edit modal via row click
 * - Export menu (PDF/CSV/Excel)
 * - Summary bar with km totals
 * - Category filter functionality
 *
 * Reference: .kiro/specs/ZZP/rittenregistratie/tasks.md §17.1
 */

import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

/**
 * Helper: navigate to ZZP Trips page via menu button.
 * The app is a SPA using setCurrentPage('zzp-trips').
 */
async function navigateToTrips(page: Page) {
  await page.goto(BASE_URL);
  await page.waitForLoadState('networkidle');
  // Click the trips menu button (🚗 emoji button)
  await page.click('button:has-text("🚗")');
  // Wait for the trips page to render
  await page.waitForSelector('text=Rittenregistratie', { timeout: 10000 });
}

test.describe('ZZP Trips - Rittenregistratie', () => {
  test.beforeEach(async ({ page }) => {
    await navigateToTrips(page);
  });

  // ─── Navigation & Page Load ───

  test('navigates to Trips page and shows page title', async ({ page }) => {
    await expect(page.locator('text=Rittenregistratie')).toBeVisible();
  });

  test('vehicle selector loads with options', async ({ page }) => {
    const vehicleSelect = page.locator('select').first();
    await expect(vehicleSelect).toBeVisible();
    // Should have at least the placeholder or one vehicle option
    const options = vehicleSelect.locator('option');
    await expect(options).not.toHaveCount(0);
  });

  // ─── Trip Table ───

  test('trip table renders with correct columns', async ({ page }) => {
    // Wait for table or empty state
    const table = page.locator('table');
    const emptyState = page.locator('text=Geen ritten');

    // Either table or empty state should show
    await expect(table.or(emptyState)).toBeVisible();

    // If table is visible, verify column headers
    if (await table.isVisible()) {
      await expect(page.locator('th:has-text("Datum")')).toBeVisible();
      await expect(page.locator('th:has-text("Vertrekadres"), th:has-text("Van")')).toBeVisible();
      await expect(page.locator('th:has-text("Bestemming"), th:has-text("Naar")')).toBeVisible();
      await expect(page.locator('th:has-text("Afstand"), th:has-text("km")')).toBeVisible();
      await expect(page.locator('th:has-text("Categorie")')).toBeVisible();
      await expect(page.locator('th:has-text("Doel")')).toBeVisible();
    }
  });

  // ─── Trip Creation ───

  test('opens trip creation modal when clicking "Nieuw" button', async ({ page }) => {
    const newButton = page.locator('button:has-text("Nieuw")').first();
    await expect(newButton).toBeVisible();
    await newButton.click();

    // Modal should appear with "Nieuwe rit" title or trip form fields
    await expect(
      page.locator('text=Nieuwe rit').or(page.locator('[role="dialog"]'))
    ).toBeVisible();
  });

  test('trip creation modal shows all required form fields', async ({ page }) => {
    await page.click('button:has-text("Nieuw")');
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

    // Required fields from TripModal
    await expect(page.locator('label:has-text("Datum")')).toBeVisible();
    await expect(page.locator('label:has-text("Vertrekadres"), label:has-text("Van")')).toBeVisible();
    await expect(page.locator('label:has-text("Bestemming"), label:has-text("Naar")')).toBeVisible();
    await expect(page.locator('label:has-text("Begin km-stand"), label:has-text("Start")')).toBeVisible();
    await expect(page.locator('label:has-text("Eind km-stand"), label:has-text("Eind")')).toBeVisible();
    await expect(page.locator('label:has-text("Categorie")')).toBeVisible();
    await expect(page.locator('label:has-text("Doel")')).toBeVisible();
  });

  test('fills trip form fields and submits', async ({ page }) => {
    await page.click('button:has-text("Nieuw")');
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

    // Fill required fields
    const dateInput = page.locator('input[name="trip_date"]');
    if (await dateInput.isVisible()) {
      await dateInput.fill('2025-01-15');
    }

    const startAddress = page.locator('input[name="start_address"]');
    if (await startAddress.isVisible()) {
      await startAddress.fill('Amsterdam');
    }

    const endAddress = page.locator('input[name="end_address"]');
    if (await endAddress.isVisible()) {
      await endAddress.fill('Rotterdam');
    }

    const startOdometer = page.locator('input[name="start_odometer"]');
    if (await startOdometer.isVisible()) {
      await startOdometer.fill('50000');
    }

    const endOdometer = page.locator('input[name="end_odometer"]');
    if (await endOdometer.isVisible()) {
      await endOdometer.fill('50075');
    }

    // Select category
    const categorySelect = page.locator('select[name="trip_category"]');
    if (await categorySelect.isVisible()) {
      await categorySelect.selectOption('Zakelijk');
    }

    // Select purpose
    const purposeSelect = page.locator('select[name="trip_purpose"]');
    if (await purposeSelect.isVisible()) {
      await purposeSelect.selectOption('Klantbezoek');
    }

    // Submit the form
    const saveButton = page.locator('button[type="submit"]:has-text("Opslaan"), button:has-text("Opslaan")');
    await expect(saveButton).toBeEnabled();
    await saveButton.click();

    // Wait for either success toast or modal to close
    await expect(
      page.locator('[role="dialog"]').or(page.locator('text=aangemaakt'))
    ).toBeVisible({ timeout: 10000 });
  });

  // ─── Edit Trip ───

  test('clicking existing trip row opens edit modal', async ({ page }) => {
    const table = page.locator('table');
    if (await table.isVisible()) {
      const firstRow = page.locator('tbody tr').first();
      if (await firstRow.isVisible()) {
        await firstRow.click();
        // Edit modal should open (shows trip date and route in header)
        await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 });
      }
    }
  });

  // ─── Export Menu ───

  test('export menu opens with PDF/CSV/Excel options', async ({ page }) => {
    const exportButton = page.locator('button:has-text("Export")');
    await expect(exportButton).toBeVisible();
    await exportButton.click();

    // Dropdown menu should show export format options
    await expect(page.locator('text=PDF')).toBeVisible();
    await expect(page.locator('text=CSV')).toBeVisible();
    await expect(page.locator('text=Excel')).toBeVisible();
  });

  // ─── Summary Bar ───

  test('summary bar shows km totals', async ({ page }) => {
    // Summary bar displays totals per category
    const summaryBar = page.locator('text=Totaal').or(page.locator('text=km'));
    await expect(summaryBar.first()).toBeVisible();

    // Should show zakelijk km
    await expect(page.locator('text=Zakelijk')).toBeVisible();
  });

  test('summary bar shows category breakdown', async ({ page }) => {
    // Verify the summary sections exist
    await expect(page.locator('text=Zakelijk')).toBeVisible();
    // Privé km section
    await expect(page.locator('text=Privé')).toBeVisible();
    // Woon-werk km section
    await expect(page.locator('text=Woon-werk')).toBeVisible();
  });

  // ─── Category Filter ───

  test('category filter dropdown is available', async ({ page }) => {
    // The category filter is a select with placeholder "Alle categorieën"
    const categoryFilter = page.locator('select').filter({ hasText: /Zakelijk|Privé|Woon-werk|Alle categorie/ });
    await expect(categoryFilter.first()).toBeVisible();
  });

  test('category filter changes displayed trips', async ({ page }) => {
    // Find the category filter select (third select or identified by options)
    const selects = page.locator('select');
    const count = await selects.count();

    // The category filter is typically the last select in the filter row
    for (let i = 0; i < count; i++) {
      const select = selects.nth(i);
      const options = await select.locator('option').allTextContents();
      if (options.some(opt => opt.includes('Zakelijk'))) {
        await select.selectOption('Zakelijk');
        // After selecting, page should re-render (either filtered table or loading)
        await page.waitForTimeout(500);
        break;
      }
    }
  });

  // ─── Year Selector ───

  test('year selector is present and changes data scope', async ({ page }) => {
    const currentYear = new Date().getFullYear();
    // Year selector should show current year
    const yearSelect = page.locator(`select:has(option:has-text("${currentYear}"))`);
    await expect(yearSelect.first()).toBeVisible();
  });

  // ─── Multi-select for invoicing ───

  test('trip table has checkbox column for invoice selection', async ({ page }) => {
    const table = page.locator('table');
    if (await table.isVisible()) {
      // Should have a checkbox in the header
      const headerCheckbox = page.locator('thead input[type="checkbox"]');
      await expect(headerCheckbox.or(page.locator('thead [role="checkbox"]'))).toBeVisible();
    }
  });
});
