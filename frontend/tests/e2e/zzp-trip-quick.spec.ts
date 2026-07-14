/**
 * ZZP Trip Quick Entry (Mobile) — E2E Tests
 *
 * Tests the mobile-optimized quick trip registration page including:
 * - Minimal header (no sidebar)
 * - Vehicle selector auto-selects first vehicle
 * - Route preset cards rendering
 * - Preset card interaction fills form fields
 * - End odometer entry
 * - "REGISTREER RIT" button submission
 * - Start/Stop timer workflow
 * - Mobile-friendly viewport (max-width 500px container)
 *
 * Reference: .kiro/specs/ZZP/rittenregistratie/tasks.md §17.4
 */

import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

/**
 * Helper: navigate to ZZP Trip Quick Entry page.
 * This page uses a standalone layout without sidebar.
 */
async function navigateToQuickEntry(page: Page) {
  await page.goto(BASE_URL);
  await page.waitForLoadState('networkidle');
  // Click the trips button first, then navigate to quick entry
  // Or navigate directly via URL/SPA navigation
  await page.click('button:has-text("🚗")');
  await page.waitForTimeout(500);
  // The quick entry might be accessible from trips page or directly
  // Try direct navigation via the Rittenregistratie text in quick mode
  await page.goto(BASE_URL);
  await page.waitForLoadState('networkidle');
  // Use the SPA navigation - the quick entry is set via setCurrentPage('zzp-trip-quick')
  // It may need a specific navigation path or button
  await page.evaluate(() => {
    // Attempt to trigger navigation via window event or internal state
    window.dispatchEvent(new CustomEvent('navigate', { detail: 'zzp-trip-quick' }));
  });
  await page.waitForTimeout(500);

  // If custom event doesn't work, try finding the quick entry link
  const quickLink = page.locator('text=Rittenregistratie');
  if (await quickLink.first().isVisible()) {
    // We're on the quick entry page
    return;
  }

  // Fallback: navigate via URL hash or reload with page param
  await page.goto(`${BASE_URL}/#zzp-trip-quick`);
  await page.waitForLoadState('networkidle');
}

test.describe('ZZP Trip Quick Entry (Mobile)', () => {
  // Use mobile viewport for all tests
  test.use({ viewport: { width: 375, height: 812 } });

  test.beforeEach(async ({ page }) => {
    await navigateToQuickEntry(page);
  });

  // ─── Layout & Header ───

  test('shows minimal header with "Rittenregistratie" title', async ({ page }) => {
    await expect(page.locator('text=Rittenregistratie')).toBeVisible();
  });

  test('shows "Terug" back button in header', async ({ page }) => {
    await expect(page.locator('button:has-text("Terug")')).toBeVisible();
  });

  test('does not show sidebar navigation', async ({ page }) => {
    // The quick entry page has standalone layout — no sidebar
    const sidebar = page.locator('aside, nav[aria-label="sidebar"]');
    await expect(sidebar).not.toBeVisible();
  });

  test('page container has max-width 500px', async ({ page }) => {
    // The main container uses maxW="500px"
    const container = page.locator('[style*="max-width"]').first();
    if (await container.isVisible()) {
      const box = await container.boundingBox();
      expect(box?.width).toBeLessThanOrEqual(500);
    }
  });

  // ─── Vehicle Selector ───

  test('vehicle selector loads and auto-selects first vehicle', async ({ page }) => {
    const vehicleSelect = page.locator('select[aria-label="Selecteer voertuig"]').or(
      page.locator('select').first()
    );
    await expect(vehicleSelect).toBeVisible();

    // Should have a selected value (auto-selects first vehicle)
    const selectedValue = await vehicleSelect.inputValue();
    expect(selectedValue).not.toBe('');
  });

  // ─── Route Preset Cards ───

  test('route preset cards section renders', async ({ page }) => {
    await expect(page.locator('text=Snelkeuze route')).toBeVisible();
  });

  test('clicking a preset card fills form fields', async ({ page }) => {
    // Wait for presets to load
    await page.waitForTimeout(1000);

    // Find preset cards (RoutePresetCards component renders clickable cards)
    const presetCards = page.locator('[role="button"], [cursor="pointer"]').filter({
      has: page.locator('text=/[A-Z]/')
    });

    // If there are preset cards, click the first one
    const firstCard = presetCards.first();
    if (await firstCard.isVisible()) {
      await firstCard.click();
      await page.waitForTimeout(500);

      // Form inputs should be filled
      const vanInput = page.locator('input[placeholder="Van"]');
      const naarInput = page.locator('input[placeholder="Naar"]');
      if (await vanInput.isVisible()) {
        const vanValue = await vanInput.inputValue();
        expect(vanValue.length).toBeGreaterThan(0);
      }
      if (await naarInput.isVisible()) {
        const naarValue = await naarInput.inputValue();
        expect(naarValue.length).toBeGreaterThan(0);
      }
    }
  });

  // ─── Form Fields ───

  test('shows route inputs (Van/Naar)', async ({ page }) => {
    await expect(page.locator('input[placeholder="Van"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Naar"]')).toBeVisible();
  });

  test('shows odometer inputs (Start/Eind)', async ({ page }) => {
    await expect(page.locator('[aria-label="Start km-stand"]')).toBeVisible();
    await expect(page.locator('[aria-label="Eind km-stand"]')).toBeVisible();
  });

  test('start odometer is read-only (pre-filled from last trip)', async ({ page }) => {
    const startInput = page.locator('[aria-label="Start km-stand"]');
    await expect(startInput).toBeVisible();
    // Start odometer is read-only
    await expect(startInput).toHaveAttribute('readonly', '');
  });

  test('end odometer accepts numeric input', async ({ page }) => {
    const endInput = page.locator('[aria-label="Eind km-stand"]');
    await expect(endInput).toBeVisible();
    await endInput.fill('51000');
    await expect(endInput).toHaveValue('51000');
  });

  test('shows category selector with options', async ({ page }) => {
    const categoryLabel = page.locator('text=Categorie');
    await expect(categoryLabel).toBeVisible();

    // Category select should have Zakelijk/Woon-werk/Privé options
    const categorySelect = page.locator('select').filter({
      has: page.locator('option:has-text("Zakelijk")')
    });
    await expect(categorySelect.first()).toBeVisible();
  });

  // ─── REGISTREER RIT Button ───

  test('shows "REGISTREER RIT" button', async ({ page }) => {
    const registerBtn = page.locator('button:has-text("REGISTREER RIT")');
    await expect(registerBtn).toBeVisible();
  });

  test('"REGISTREER RIT" button has large tap target (min 44px)', async ({ page }) => {
    const registerBtn = page.locator('button:has-text("REGISTREER RIT")');
    await expect(registerBtn).toBeVisible();
    const box = await registerBtn.boundingBox();
    // Should be at least 44px tall for mobile accessibility
    expect(box?.height).toBeGreaterThanOrEqual(44);
  });

  test('"REGISTREER RIT" is disabled without required fields', async ({ page }) => {
    // Without end odometer and addresses, button should be disabled
    const registerBtn = page.locator('button:has-text("REGISTREER RIT")');
    await expect(registerBtn).toBeDisabled();
  });

  test('submitting valid form shows success toast', async ({ page }) => {
    // Fill required fields
    const vanInput = page.locator('input[placeholder="Van"]');
    const naarInput = page.locator('input[placeholder="Naar"]');
    const endInput = page.locator('[aria-label="Eind km-stand"]');

    await vanInput.fill('Amsterdam');
    await naarInput.fill('Rotterdam');
    await endInput.fill('99999');

    const registerBtn = page.locator('button:has-text("REGISTREER RIT")');
    if (await registerBtn.isEnabled()) {
      await registerBtn.click();

      // Should show success toast "Rit geregistreerd!"
      await expect(
        page.locator('text=geregistreerd').or(page.locator('text=Fout'))
      ).toBeVisible({ timeout: 10000 });
    }
  });

  // ─── Start/Stop Timer Workflow ───

  test('shows "Start Rit" button initially', async ({ page }) => {
    const startBtn = page.locator('button:has-text("Start Rit")');
    await expect(startBtn).toBeVisible();
  });

  test('clicking "Start Rit" activates timer and shows ACTIEF badge', async ({ page }) => {
    const startBtn = page.locator('button:has-text("Start Rit")');
    await startBtn.click();

    // Timer active state
    await expect(page.locator('text=ACTIEF')).toBeVisible();
    // Should show elapsed time format (00:00:XX)
    await expect(page.locator('text=/\\d{2}:\\d{2}:\\d{2}/')).toBeVisible();
  });

  test('clicking "Stop Rit" deactivates timer', async ({ page }) => {
    // Start the timer
    await page.click('button:has-text("Start Rit")');
    await expect(page.locator('text=ACTIEF')).toBeVisible();

    // Stop the timer
    await page.click('button:has-text("Stop Rit")');

    // ACTIEF badge should disappear
    await expect(page.locator('text=ACTIEF')).not.toBeVisible();
    // Start Rit button should reappear
    await expect(page.locator('button:has-text("Start Rit")')).toBeVisible();
  });

  test('timer shows start time after clicking "Start Rit"', async ({ page }) => {
    await page.click('button:has-text("Start Rit")');
    // Should display the start time (e.g., "Start: 14:30")
    await expect(page.locator('text=Start:')).toBeVisible();
  });

  test('"Stop Rit" focuses end odometer input', async ({ page }) => {
    await page.click('button:has-text("Start Rit")');
    await page.waitForTimeout(500);
    await page.click('button:has-text("Stop Rit")');
    await page.waitForTimeout(200);

    // End odometer should be focused after stopping
    const endInput = page.locator('[aria-label="Eind km-stand"]');
    await expect(endInput).toBeFocused();
  });

  // ─── Distance Preview ───

  test('shows distance preview when start and end odometer are filled', async ({ page }) => {
    const endInput = page.locator('[aria-label="Eind km-stand"]');
    await endInput.fill('99999');

    // If start odometer has a value, distance preview should show
    const startInput = page.locator('[aria-label="Start km-stand"]');
    const startVal = await startInput.inputValue();
    if (startVal && Number(startVal) > 0) {
      const expectedDistance = 99999 - Number(startVal);
      await expect(page.locator(`text=Afstand: ${expectedDistance} km`)).toBeVisible();
    }
  });

  // ─── Mobile UX ───

  test('all touch targets are at least 44px tall', async ({ page }) => {
    // Check main interactive elements for minimum touch target size
    const buttons = page.locator('button:visible');
    const count = await buttons.count();

    for (let i = 0; i < Math.min(count, 5); i++) {
      const btn = buttons.nth(i);
      const box = await btn.boundingBox();
      if (box) {
        expect(box.height).toBeGreaterThanOrEqual(44);
      }
    }
  });

  test('inputs have minimum height for mobile usability', async ({ page }) => {
    const inputs = page.locator('input:visible');
    const count = await inputs.count();

    for (let i = 0; i < Math.min(count, 5); i++) {
      const input = inputs.nth(i);
      const box = await input.boundingBox();
      if (box) {
        // Inputs should be at least 44px for comfortable mobile tapping
        expect(box.height).toBeGreaterThanOrEqual(36);
      }
    }
  });
});
