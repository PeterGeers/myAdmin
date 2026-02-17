/**
 * Unit tests for internationalization formatting utilities.
 */

import { formatDate, formatNumber, formatCurrency } from './formatting';

describe('formatDate', () => {
  const testDate = new Date('2026-02-17T12:00:00Z');

  test('formats date in Dutch locale', () => {
    const result = formatDate(testDate, 'nl');
    expect(result).toMatch(/17[-/]02[-/]2026/); // Allow for different separators
  });

  test('formats date in English locale', () => {
    const result = formatDate(testDate, 'en');
    expect(result).toMatch(/02[-/]17[-/]2026/); // Allow for different separators
  });

  test('uses custom format string', () => {
    const result = formatDate(testDate, 'nl', 'yyyy-MM-dd');
    expect(result).toBe('2026-02-17');
  });

  test('defaults to English for unknown locale', () => {
    const result = formatDate(testDate, 'unknown');
    expect(result).toMatch(/02[-/]17[-/]2026/);
  });
});

describe('formatNumber', () => {
  test('formats number in Dutch locale with comma decimal', () => {
    const result = formatNumber(1234.56, 'nl');
    expect(result).toBe('1.234,56');
  });

  test('formats number in English locale with dot decimal', () => {
    const result = formatNumber(1234.56, 'en');
    expect(result).toBe('1,234.56');
  });

  test('formats number with custom decimal places', () => {
    const result = formatNumber(1234.567, 'nl', 3);
    expect(result).toBe('1.234,567');
  });

  test('formats number with zero decimals', () => {
    const result = formatNumber(1234.56, 'nl', 0);
    expect(result).toBe('1.235'); // Rounded
  });

  test('formats negative numbers', () => {
    const resultNl = formatNumber(-1234.56, 'nl');
    const resultEn = formatNumber(-1234.56, 'en');
    expect(resultNl).toBe('-1.234,56');
    expect(resultEn).toBe('-1,234.56');
  });

  test('formats zero', () => {
    const result = formatNumber(0, 'nl');
    expect(result).toBe('0,00');
  });

  test('formats large numbers', () => {
    const result = formatNumber(1234567.89, 'nl');
    expect(result).toBe('1.234.567,89');
  });
});

describe('formatCurrency', () => {
  test('formats currency in Dutch locale', () => {
    const result = formatCurrency(1234.56, 'nl');
    expect(result).toMatch(/€\s*1\.234,56/); // € 1.234,56 or €1.234,56
  });

  test('formats currency in English locale', () => {
    const result = formatCurrency(1234.56, 'en');
    expect(result).toMatch(/€\s*1,234\.56/); // €1,234.56 or € 1,234.56
  });

  test('formats negative currency', () => {
    const resultNl = formatCurrency(-1234.56, 'nl');
    const resultEn = formatCurrency(-1234.56, 'en');
    expect(resultNl).toContain('-');
    expect(resultNl).toContain('€');
    expect(resultEn).toContain('-');
    expect(resultEn).toContain('€');
  });

  test('formats zero currency', () => {
    const result = formatCurrency(0, 'nl');
    expect(result).toMatch(/€\s*0,00/);
  });

  test('formats large currency amounts', () => {
    const result = formatCurrency(1234567.89, 'nl');
    expect(result).toMatch(/€\s*1\.234\.567,89/);
  });

  test('always uses EUR currency symbol', () => {
    const resultNl = formatCurrency(100, 'nl');
    const resultEn = formatCurrency(100, 'en');
    expect(resultNl).toContain('€');
    expect(resultEn).toContain('€');
  });
});
