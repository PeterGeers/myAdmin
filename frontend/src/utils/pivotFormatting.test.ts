/**
 * Unit tests for pivotFormatting utilities.
 *
 * Tests formatPivotNumber() across all three display modes (decimal, whole, k-notation)
 * and edge cases (null, NaN, negative, zero).
 *
 * Requirements: 3.6, 3.7
 */

import { formatPivotNumber, resolveLocale } from './pivotFormatting';

describe('formatPivotNumber', () => {
  describe('decimal mode (2dp)', () => {
    it('formats a positive number with 2 decimal places', () => {
      const result = formatPivotNumber(12345.678, 'decimal', 'en-US');
      expect(result).toBe('12,345.68');
    });

    it('formats zero with 2 decimal places', () => {
      const result = formatPivotNumber(0, 'decimal', 'en-US');
      expect(result).toBe('0.00');
    });

    it('formats a negative number with 2 decimal places', () => {
      const result = formatPivotNumber(-500.1, 'decimal', 'en-US');
      expect(result).toBe('-500.10');
    });

    it('formats with Dutch locale', () => {
      const result = formatPivotNumber(12345.678, 'decimal', 'nl-NL');
      expect(result).toBe('12.345,68');
    });

    it('pads short decimals to 2 places', () => {
      const result = formatPivotNumber(100, 'decimal', 'en-US');
      expect(result).toBe('100.00');
    });
  });

  describe('whole mode (0dp)', () => {
    it('rounds to whole number', () => {
      const result = formatPivotNumber(12345.678, 'whole', 'en-US');
      expect(result).toBe('12,346');
    });

    it('formats zero as whole number', () => {
      const result = formatPivotNumber(0, 'whole', 'en-US');
      expect(result).toBe('0');
    });

    it('rounds negative numbers', () => {
      const result = formatPivotNumber(-500.4, 'whole', 'en-US');
      expect(result).toBe('-500');
    });

    it('formats with Dutch locale', () => {
      const result = formatPivotNumber(12345.678, 'whole', 'nl-NL');
      expect(result).toBe('12.346');
    });
  });

  describe('k-notation mode (abbreviated)', () => {
    it('abbreviates thousands with k suffix', () => {
      const result = formatPivotNumber(12345, 'k-notation', 'en-US');
      expect(result).toBe('12.3K');
    });

    it('abbreviates millions with M suffix', () => {
      const result = formatPivotNumber(1500000, 'k-notation', 'en-US');
      expect(result).toBe('1.5M');
    });

    it('shows small numbers without suffix', () => {
      const result = formatPivotNumber(999, 'k-notation', 'en-US');
      expect(result).toBe('999.0');
    });

    it('handles exactly 1000', () => {
      const result = formatPivotNumber(1000, 'k-notation', 'en-US');
      expect(result).toBe('1.0K');
    });

    it('handles exactly 1000000', () => {
      const result = formatPivotNumber(1000000, 'k-notation', 'en-US');
      expect(result).toBe('1.0M');
    });

    it('handles negative values with k suffix', () => {
      const result = formatPivotNumber(-5000, 'k-notation', 'en-US');
      expect(result).toMatch(/5\.0K/);
    });

    it('handles negative values with M suffix', () => {
      const result = formatPivotNumber(-2500000, 'k-notation', 'en-US');
      expect(result).toMatch(/2\.5M/);
    });

    it('formats with Dutch locale (comma decimal)', () => {
      const result = formatPivotNumber(12345, 'k-notation', 'nl-NL');
      expect(result).toBe('12,3K');
    });

    it('formats zero in k-notation', () => {
      const result = formatPivotNumber(0, 'k-notation', 'en-US');
      expect(result).toBe('0.0');
    });
  });

  describe('edge cases', () => {
    it('returns empty string for null', () => {
      expect(formatPivotNumber(null, 'decimal')).toBe('');
    });

    it('returns empty string for undefined', () => {
      expect(formatPivotNumber(undefined, 'decimal')).toBe('');
    });

    it('returns empty string for NaN', () => {
      expect(formatPivotNumber(NaN, 'decimal')).toBe('');
    });

    it('defaults to nl-NL locale when no locale provided', () => {
      const result = formatPivotNumber(1234.56, 'decimal');
      expect(result).toBe('1.234,56');
    });
  });
});

describe('resolveLocale', () => {
  it('maps nl to nl-NL', () => {
    expect(resolveLocale('nl')).toBe('nl-NL');
  });

  it('maps en to en-US', () => {
    expect(resolveLocale('en')).toBe('en-US');
  });

  it('passes through full locale strings', () => {
    expect(resolveLocale('de-DE')).toBe('de-DE');
  });

  it('constructs locale from short code', () => {
    expect(resolveLocale('fr')).toBe('fr-FR');
  });
});
