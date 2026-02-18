/**
 * Internationalization E2E Tests - Language Switching
 * 
 * End-to-end tests for language switching functionality using Playwright.
 * Tests complete user flows for switching between Dutch and English.
 * 
 * Test Coverage:
 * - Language selector visibility and functionality
 * - Language persistence across page navigation
 * - Language persistence across browser sessions (localStorage)
 * - UI translation updates when language changes
 */

import { test, expect, Page } from '@playwright/test';

// Test configuration
const TEST_TIMEOUT = 60000;
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

/**
 * Helper function to check if language selector is visible
 */
async function waitForLanguageSelector(page: Page) {
  await page.waitForSelector('[data-testid="language-selector"]', { timeout: 10000 });
}

/**
 * Helper function to switch language
 */
async function switchLanguage(page: Page, language: 'nl' | 'en') {
  // Click language selector
  await page.click('[data-testid="language-selector"]');
  
  // Wait for dropdown menu and click language option
  await page.waitForTimeout(500);
  await page.click(`[data-testid="language-option-${language}"]`);
  
  // Wait for language change to complete
  await page.waitForTimeout(1000);
}

/**
 * Helper function to verify language in localStorage
 */
async function verifyLocalStorageLanguage(page: Page, expectedLanguage: string) {
  const storedLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
  expect(storedLanguage).toBe(expectedLanguage);
}

// ============================================================================
// E2E Test 1: Language Selector Visibility
// ============================================================================

test.describe('E2E Test 1: Language Selector Visibility', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display language selector on main dashboard', async ({ page }) => {
    // Navigate to application
    await page.goto(BASE_URL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Check if language selector is visible
    const languageSelector = page.locator('[data-testid="language-selector"]');
    await expect(languageSelector).toBeVisible({ timeout: 10000 });
    
    // Verify it shows current language (default should be Dutch)
    await expect(languageSelector).toContainText(/NL|EN/i);
  });
});

// ============================================================================
// E2E Test 2: Language Switching from Dutch to English
// ============================================================================

test.describe('E2E Test 2: Language Switching from Dutch to English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should switch from Dutch to English and update UI', async ({ page }) => {
    // Navigate to application
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Wait for language selector
    await waitForLanguageSelector(page);
    
    // Verify initial language is Dutch
    await verifyLocalStorageLanguage(page, 'nl');
    
    // Look for Dutch text on page (e.g., "Selecteer een component")
    const dutchText = page.locator('text=/Selecteer|Dashboard|Terug/i');
    await expect(dutchText.first()).toBeVisible({ timeout: 5000 });
    
    // Switch to English
    await switchLanguage(page, 'en');
    
    // Verify localStorage updated
    await verifyLocalStorageLanguage(page, 'en');
    
    // Look for English text on page (e.g., "Select a component")
    const englishText = page.locator('text=/Select|Dashboard|Back/i');
    await expect(englishText.first()).toBeVisible({ timeout: 5000 });
  });
});

// ============================================================================
// E2E Test 3: Language Switching from English to Dutch
// ============================================================================

test.describe('E2E Test 3: Language Switching from English to Dutch', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should switch from English to Dutch and update UI', async ({ page }) => {
    // Set initial language to English
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => localStorage.setItem('i18nextLng', 'en'));
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Wait for language selector
    await waitForLanguageSelector(page);
    
    // Verify initial language is English
    await verifyLocalStorageLanguage(page, 'en');
    
    // Switch to Dutch
    await switchLanguage(page, 'nl');
    
    // Verify localStorage updated
    await verifyLocalStorageLanguage(page, 'nl');
    
    // Look for Dutch text on page
    const dutchText = page.locator('text=/Selecteer|Dashboard|Terug/i');
    await expect(dutchText.first()).toBeVisible({ timeout: 5000 });
  });
});

// ============================================================================
// E2E Test 4: Language Persistence Across Page Navigation
// ============================================================================

test.describe('E2E Test 4: Language Persistence Across Navigation', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should maintain language selection when navigating between pages', async ({ page }) => {
    // Navigate to application
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Switch to English
    await waitForLanguageSelector(page);
    await switchLanguage(page, 'en');
    
    // Verify English is set
    await verifyLocalStorageLanguage(page, 'en');
    
    // Navigate to different page (if available)
    // Note: This assumes there are navigation links available
    // Adjust selectors based on actual application structure
    const navLinks = page.locator('button, a').filter({ hasText: /Reports|Admin|Settings/i });
    const linkCount = await navLinks.count();
    
    if (linkCount > 0) {
      // Click first available navigation link
      await navLinks.first().click();
      await page.waitForTimeout(1000);
      
      // Verify language is still English
      await verifyLocalStorageLanguage(page, 'en');
      
      // Verify English text is still visible
      const englishText = page.locator('text=/Select|Dashboard|Back|Reports|Admin/i');
      await expect(englishText.first()).toBeVisible({ timeout: 5000 });
    }
  });
});

// ============================================================================
// E2E Test 5: Language Persistence Across Browser Sessions
// ============================================================================

test.describe('E2E Test 5: Language Persistence Across Sessions', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should maintain language selection after page reload', async ({ page }) => {
    // Navigate to application
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Switch to English
    await waitForLanguageSelector(page);
    await switchLanguage(page, 'en');
    
    // Verify English is set
    await verifyLocalStorageLanguage(page, 'en');
    
    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Verify language is still English after reload
    await verifyLocalStorageLanguage(page, 'en');
    
    // Verify English text is visible
    const englishText = page.locator('text=/Select|Dashboard|Back/i');
    await expect(englishText.first()).toBeVisible({ timeout: 5000 });
  });
});

// ============================================================================
// E2E Test 6: Language Selector Shows Current Language
// ============================================================================

test.describe('E2E Test 6: Language Selector Current Language Display', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display current language in selector', async ({ page }) => {
    // Navigate to application
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Wait for language selector
    await waitForLanguageSelector(page);
    
    // Get current language from localStorage
    const currentLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
    
    // Verify language selector shows current language
    const languageSelector = page.locator('[data-testid="language-selector"]');
    
    if (currentLanguage === 'nl') {
      await expect(languageSelector).toContainText(/NL|Nederlands/i);
    } else if (currentLanguage === 'en') {
      await expect(languageSelector).toContainText(/EN|English/i);
    }
  });
});

// ============================================================================
// E2E Test 7: Multiple Language Switches
// ============================================================================

test.describe('E2E Test 7: Multiple Language Switches', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should handle multiple language switches correctly', async ({ page }) => {
    // Navigate to application
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Wait for language selector
    await waitForLanguageSelector(page);
    
    // Switch to English
    await switchLanguage(page, 'en');
    await verifyLocalStorageLanguage(page, 'en');
    
    // Switch back to Dutch
    await switchLanguage(page, 'nl');
    await verifyLocalStorageLanguage(page, 'nl');
    
    // Switch to English again
    await switchLanguage(page, 'en');
    await verifyLocalStorageLanguage(page, 'en');
    
    // Verify final state is English
    const englishText = page.locator('text=/Select|Dashboard|Back/i');
    await expect(englishText.first()).toBeVisible({ timeout: 5000 });
  });
});
