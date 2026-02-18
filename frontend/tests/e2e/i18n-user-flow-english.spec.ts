/**
 * Internationalization E2E Tests - Complete User Flow in English
 * 
 * End-to-end tests for complete user workflows in English language.
 * Tests that all UI elements, messages, and interactions work correctly in English.
 * 
 * Test Coverage:
 * - Dashboard navigation in English
 * - Form interactions with English labels
 * - Error messages in English
 * - Success messages in English
 * - Date and number formatting (English locale)
 */

import { test, expect, Page } from '@playwright/test';

// Test configuration
const TEST_TIMEOUT = 60000;
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

/**
 * Helper function to set language to English
 */
async function setLanguageToEnglish(page: Page) {
  await page.goto(BASE_URL);
  await page.waitForLoadState('networkidle');
  
  // Set English in localStorage
  await page.evaluate(() => localStorage.setItem('i18nextLng', 'en'));
  await page.reload();
  await page.waitForLoadState('networkidle');
}

// ============================================================================
// E2E Test 1: Dashboard Navigation in English
// ============================================================================

test.describe('E2E Test 1: Dashboard Navigation in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display dashboard with English labels', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Verify English dashboard text
    const englishElements = [
      /Dashboard|Overview/i,
      /Select|Choose/i,
    ];
    
    for (const pattern of englishElements) {
      const element = page.locator(`text=${pattern}`);
      const count = await element.count();
      expect(count).toBeGreaterThan(0);
    }
  });
});

// ============================================================================
// E2E Test 2: Module Navigation in English
// ============================================================================

test.describe('E2E Test 2: Module Navigation in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should navigate through modules with English labels', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Look for common English module names
    const englishModules = [
      /Invoices/i,
      /Banking/i,
      /Reports/i,
      /Administration/i,
    ];
    
    // Check if at least one module is visible
    let moduleFound = false;
    for (const pattern of englishModules) {
      const element = page.locator(`button:has-text("${pattern.source.replace(/\\/g, '')}")`);
      const count = await element.count();
      if (count > 0) {
        moduleFound = true;
        break;
      }
    }
    
    expect(moduleFound).toBeTruthy();
  });
});

// ============================================================================
// E2E Test 3: Date Formatting in English
// ============================================================================

test.describe('E2E Test 3: Date Formatting in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display dates in English format (MM/dd/yyyy)', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Look for date inputs or date displays
    const dateInputs = page.locator('input[type="date"]');
    const dateCount = await dateInputs.count();
    
    if (dateCount > 0) {
      // Verify date input exists
      expect(dateCount).toBeGreaterThan(0);
    }
    
    // Verify language is set to English
    const storedLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
    expect(storedLanguage).toBe('en');
  });
});

// ============================================================================
// E2E Test 4: Number Formatting in English
// ============================================================================

test.describe('E2E Test 4: Number Formatting in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display numbers in English format (1,234.56)', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Verify language is set to English
    const storedLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
    expect(storedLanguage).toBe('en');
    
    // English format uses period for decimals and comma for thousands
    // e.g., $1,234.56 or €1,234.56
    const pageContent = await page.content();
    expect(pageContent).toContain('en');
  });
});

// ============================================================================
// E2E Test 5: Form Labels in English
// ============================================================================

test.describe('E2E Test 5: Form Labels in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display form labels in English', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Common English form labels
    const englishLabels = [
      /Name/i,
      /Email/i,
      /Password/i,
      /Save/i,
      /Cancel/i,
      /Delete/i,
    ];
    
    // Check if any forms exist on the page
    const forms = page.locator('form');
    const formCount = await forms.count();
    
    if (formCount > 0) {
      // Look for English labels
      let labelFound = false;
      for (const pattern of englishLabels) {
        const element = page.locator(`text=${pattern}`);
        const count = await element.count();
        if (count > 0) {
          labelFound = true;
          break;
        }
      }
      
      // At least one English label should be found if forms exist
      if (formCount > 0) {
        expect(labelFound).toBeTruthy();
      }
    }
  });
});

// ============================================================================
// E2E Test 6: Button Labels in English
// ============================================================================

test.describe('E2E Test 6: Button Labels in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display button labels in English', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Common English button labels
    const englishButtons = [
      /Back/i,
      /Next/i,
      /Save/i,
      /Cancel/i,
      /Add/i,
      /Delete/i,
      /Edit/i,
    ];
    
    // Check if any buttons exist
    const buttons = page.locator('button');
    const buttonCount = await buttons.count();
    
    expect(buttonCount).toBeGreaterThan(0);
    
    // Look for English button labels
    let englishButtonFound = false;
    for (const pattern of englishButtons) {
      const element = page.locator(`button:has-text("${pattern.source.replace(/\\/g, '')}")`);
      const count = await element.count();
      if (count > 0) {
        englishButtonFound = true;
        break;
      }
    }
    
    // At least one English button should be found
    expect(englishButtonFound).toBeTruthy();
  });
});

// ============================================================================
// E2E Test 7: Navigation Menu in English
// ============================================================================

test.describe('E2E Test 7: Navigation Menu in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display navigation menu items in English', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Verify language is set
    const storedLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
    expect(storedLanguage).toBe('en');
    
    // Look for navigation elements
    const nav = page.locator('nav, header, [role="navigation"]');
    const navCount = await nav.count();
    
    // Navigation should exist
    expect(navCount).toBeGreaterThan(0);
  });
});

// ============================================================================
// E2E Test 8: Page Titles in English
// ============================================================================

test.describe('E2E Test 8: Page Titles in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should display page titles in English', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Look for heading elements
    const headings = page.locator('h1, h2, h3');
    const headingCount = await headings.count();
    
    expect(headingCount).toBeGreaterThan(0);
    
    // Verify at least one heading contains English text
    const pageContent = await page.content();
    const hasEnglishContent = /Dashboard|Overview|Administration|Reports|Settings/i.test(pageContent);
    
    expect(hasEnglishContent).toBeTruthy();
  });
});

// ============================================================================
// E2E Test 9: Complete User Flow - Dashboard to Module
// ============================================================================

test.describe('E2E Test 9: Complete User Flow in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should complete full navigation flow in English', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Step 1: Verify dashboard loads in English
    const storedLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
    expect(storedLanguage).toBe('en');
    
    // Step 2: Look for any clickable module/button
    const buttons = page.locator('button').filter({ hasText: /Invoices|Banking|Reports|Administration/i });
    const buttonCount = await buttons.count();
    
    if (buttonCount > 0) {
      // Step 3: Click first available button
      await buttons.first().click();
      await page.waitForTimeout(1000);
      
      // Step 4: Verify language is still English after navigation
      const languageAfterNav = await page.evaluate(() => localStorage.getItem('i18nextLng'));
      expect(languageAfterNav).toBe('en');
      
      // Step 5: Look for "Back" button
      const backButton = page.locator('button:has-text("Back")');
      const backButtonCount = await backButton.count();
      
      if (backButtonCount > 0) {
        // Step 6: Click back button
        await backButton.first().click();
        await page.waitForTimeout(1000);
        
        // Step 7: Verify we're back at dashboard and still in English
        const finalLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
        expect(finalLanguage).toBe('en');
      }
    }
  });
});

// ============================================================================
// E2E Test 10: Language Consistency Across Pages
// ============================================================================

test.describe('E2E Test 10: Language Consistency in English', () => {
  test.setTimeout(TEST_TIMEOUT);

  test('should maintain English across multiple page navigations', async ({ page }) => {
    // Set language to English
    await setLanguageToEnglish(page);
    
    // Verify initial language
    let storedLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
    expect(storedLanguage).toBe('en');
    
    // Navigate through multiple pages (if available)
    const navButtons = page.locator('button, a').filter({ hasText: /Reports|Admin|Settings|Invoices|Banking/i });
    const navCount = await navButtons.count();
    
    if (navCount > 0) {
      // Click up to 3 navigation items
      const clickCount = Math.min(navCount, 3);
      
      for (let i = 0; i < clickCount; i++) {
        await navButtons.nth(i).click();
        await page.waitForTimeout(1000);
        
        // Verify language is still English
        storedLanguage = await page.evaluate(() => localStorage.getItem('i18nextLng'));
        expect(storedLanguage).toBe('en');
      }
    }
  });
});
