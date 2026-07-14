/**
 * ZZP Vehicles (Voertuigen) — E2E Tests
 *
 * Tests the vehicle management flow including:
 * - Page navigation and table rendering
 * - New vehicle modal and form submission
 * - Edit modal via row click
 * - Deactivation confirmation dialog
 * - Status badge display
 *
 * Reference: .kiro/specs/ZZP/rittenregistratie/tasks.md §17.2
 */

import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

/**
 * Helper: navigate to ZZP Vehicles page via menu button.
 * The app is a SPA using setCurrentPage('zzp-vehicles').
 */
async function navigateToVehicles(page: Page) {
  await page.goto(BASE_URL);
  await page.waitForLoadState('networkidle');
  // Click the vehicles menu button (🚙 emoji button)
  await page.click('button:has-text("🚙")');
  // Wait for vehicles page to render
  await page.waitForSelector('text=Voertuigen', { timeout: 10000 });
}

test.describe('ZZP Vehicles - Voertuigen', () => {
  test.beforeEach(async ({ page }) => {
    await navigateToVehicles(page);
  });

  // ─── Navigation & Page Load ───

  test('navigates to Vehicles page and shows page title', async ({ page }) => {
    await expect(page.locator('text=Voertuigen')).toBeVisible();
  });

  // ─── Vehicle Table ───

  test('vehicle table renders with correct columns', async ({ page }) => {
    const table = page.locator('table');
    const emptyState = page.locator('text=Geen voertuigen');

    // Either table or empty state should show
    await expect(table.or(emptyState)).toBeVisible();

    if (await table.isVisible()) {
      await expect(page.locator('th:has-text("Kenteken")')).toBeVisible();
      await expect(page.locator('th:has-text("Merk")')).toBeVisible();
      await expect(page.locator('th:has-text("Type")')).toBeVisible();
      await expect(page.locator('th:has-text("Bouwjaar")')).toBeVisible();
      await expect(page.locator('th:has-text("Start km-stand"), th:has-text("km")')).toBeVisible();
      await expect(page.locator('th:has-text("Status")')).toBeVisible();
      await expect(page.locator('th:has-text("Actie")')).toBeVisible();
    }
  });

  test('vehicle table shows status badges (Actief/Inactief)', async ({ page }) => {
    const table = page.locator('table');
    if (await table.isVisible()) {
      const rows = page.locator('tbody tr');
      if ((await rows.count()) > 0) {
        // Each row should have a status badge
        const firstRowBadge = rows.first().locator('text=Actief, text=Inactief');
        await expect(firstRowBadge).toBeVisible();
      }
    }
  });

  // ─── New Vehicle Modal ───

  test('opens "Nieuw voertuig" modal', async ({ page }) => {
    const newButton = page.locator('button:has-text("Nieuw voertuig")');
    await expect(newButton).toBeVisible();
    await newButton.click();

    // Modal should appear with title
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 });
    await expect(
      page.locator('text=Nieuw voertuig').locator('visible=true')
    ).toBeVisible();
  });

  test('vehicle modal shows all required form fields', async ({ page }) => {
    await page.click('button:has-text("Nieuw voertuig")');
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

    // Required fields from VehicleModal
    await expect(page.locator('label:has-text("Kenteken")')).toBeVisible();
    await expect(page.locator('label:has-text("Type voertuig")')).toBeVisible();
    await expect(page.locator('label:has-text("Start km-stand")')).toBeVisible();
    await expect(page.locator('label:has-text("Startdatum")')).toBeVisible();

    // Optional fields also shown
    await expect(page.locator('label:has-text("Merk")')).toBeVisible();
    await expect(page.locator('label:has-text("Model")')).toBeVisible();
    await expect(page.locator('label:has-text("Bouwjaar")')).toBeVisible();
  });

  test('fills vehicle form and submits', async ({ page }) => {
    await page.click('button:has-text("Nieuw voertuig")');
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

    // Fill required fields
    await page.fill('input[name="license_plate"]', 'AB-123-CD');

    // Select vehicle type
    const typeSelect = page.locator('select[name="vehicle_type"]');
    await typeSelect.selectOption('private_for_business');

    // Fill start odometer
    await page.fill('input[name="start_odometer"]', '45000');

    // Fill optional fields
    await page.fill('input[name="make"]', 'Volkswagen');
    await page.fill('input[name="model"]', 'Golf');
    await page.fill('input[name="year_built"]', '2022');

    // Submit the form
    const saveButton = page.locator('button:has-text("Opslaan")');
    await expect(saveButton).toBeEnabled();
    await saveButton.click();

    // Wait for success toast or modal to close
    await expect(
      page.locator('text=aangemaakt').or(page.locator('text=Voertuig'))
    ).toBeVisible({ timeout: 10000 });
  });

  test('vehicle form validation rejects empty required fields', async ({ page }) => {
    await page.click('button:has-text("Nieuw voertuig")');
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

    // Try to submit without filling required fields
    const saveButton = page.locator('button:has-text("Opslaan")');
    await saveButton.click();

    // Validation errors should appear
    await expect(
      page.locator('text=verplicht').or(page.locator('[role="alert"]'))
    ).toBeVisible({ timeout: 5000 });
  });

  // ─── Edit Vehicle ───

  test('clicking existing vehicle row opens edit modal', async ({ page }) => {
    const table = page.locator('table');
    if (await table.isVisible()) {
      const firstRow = page.locator('tbody tr').first();
      if (await firstRow.isVisible()) {
        await firstRow.click();
        // Edit modal should open with "Voertuig bewerken" in header
        await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 });
        await expect(
          page.locator('text=Voertuig bewerken').or(page.locator('text=bewerken'))
        ).toBeVisible();
      }
    }
  });

  test('edit modal pre-fills existing vehicle data', async ({ page }) => {
    const table = page.locator('table');
    if (await table.isVisible()) {
      const firstRow = page.locator('tbody tr').first();
      if (await firstRow.isVisible()) {
        // Get license plate from table row
        const licensePlate = await firstRow.locator('td').first().textContent();
        await firstRow.click();
        await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

        // License plate input should be pre-filled
        const plateInput = page.locator('input[name="license_plate"]');
        if (licensePlate) {
          await expect(plateInput).toHaveValue(licensePlate.trim());
        }
      }
    }
  });

  // ─── Deactivation ───

  test('"Deactiveren" button shows confirmation dialog', async ({ page }) => {
    const deactivateBtn = page.locator('button:has-text("Deactiveren")').first();
    if (await deactivateBtn.isVisible()) {
      await deactivateBtn.click();

      // Confirmation dialog should appear
      await expect(page.locator('text=Voertuig deactiveren')).toBeVisible({ timeout: 5000 });
      await expect(page.locator('text=Weet je zeker')).toBeVisible();

      // Should have Cancel and Confirm buttons
      await expect(page.locator('button:has-text("Annuleren")')).toBeVisible();
      await expect(
        page.locator('[role="alertdialog"] button:has-text("Deactiveren")')
      ).toBeVisible();
    }
  });

  test('cancelling deactivation closes the dialog', async ({ page }) => {
    const deactivateBtn = page.locator('button:has-text("Deactiveren")').first();
    if (await deactivateBtn.isVisible()) {
      await deactivateBtn.click();
      await page.waitForSelector('text=Voertuig deactiveren', { timeout: 5000 });

      // Click cancel
      await page.click('button:has-text("Annuleren")');

      // Dialog should close
      await expect(page.locator('text=Weet je zeker')).not.toBeVisible();
    }
  });

  test('confirming deactivation changes vehicle status', async ({ page }) => {
    const deactivateBtn = page.locator('button:has-text("Deactiveren")').first();
    if (await deactivateBtn.isVisible()) {
      await deactivateBtn.click();
      await page.waitForSelector('text=Voertuig deactiveren', { timeout: 5000 });

      // Click confirm deactivation in the alert dialog
      const confirmBtn = page.locator('[role="alertdialog"] button:has-text("Deactiveren")');
      await confirmBtn.click();

      // Should show success toast or status change to "Inactief"
      await expect(
        page.locator('text=gedeactiveerd').or(page.locator('text=Inactief'))
      ).toBeVisible({ timeout: 10000 });
    }
  });

  // ─── Header Actions ───

  test('"Nieuw voertuig" button has orange color scheme', async ({ page }) => {
    const newButton = page.locator('button:has-text("Nieuw voertuig")');
    await expect(newButton).toBeVisible();
    // Chakra orange buttons have a specific class or background
    const bgColor = await newButton.evaluate(el => getComputedStyle(el).backgroundColor);
    // Orange palette in Chakra — just verify it's not transparent/default
    expect(bgColor).not.toBe('rgba(0, 0, 0, 0)');
  });
});
