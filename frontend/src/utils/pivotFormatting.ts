/**
 * Pivot number formatting utilities.
 *
 * Provides locale-aware number formatting for pivot result tables and CSV export.
 * Three display modes: decimal (2dp), whole (0dp), k-notation (abbreviated).
 *
 * Uses Intl.NumberFormat for locale-correct thousand separators and decimal marks.
 *
 * Requirements: 3.6, 3.7
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §5 PivotResultTable
 */

import type { NumberFormat } from '../types/pivot';

/**
 * Abbreviation thresholds for k-notation mode.
 * Ordered largest-first so the first match wins.
 */
const ABBREVIATIONS: { threshold: number; suffix: string; divisor: number }[] = [
  { threshold: 1_000_000, suffix: 'M', divisor: 1_000_000 },
  { threshold: 1_000, suffix: 'K', divisor: 1_000 },
];

/**
 * Format a numeric value according to the selected display mode and locale.
 *
 * @param value   - The number to format. Returns '' for null/undefined/NaN.
 * @param format  - Display mode: 'decimal' (2dp), 'whole' (0dp), 'k-notation' (abbreviated).
 * @param locale  - BCP 47 locale string (e.g. 'nl-NL', 'en-US'). Defaults to 'nl-NL'.
 * @returns Formatted string representation of the value.
 *
 * @example
 * formatPivotNumber(12345.678, 'decimal', 'nl-NL')   // "12.345,68"
 * formatPivotNumber(12345.678, 'whole', 'nl-NL')      // "12.346"
 * formatPivotNumber(12345.678, 'k-notation', 'nl-NL') // "12,3K"
 * formatPivotNumber(1500000, 'k-notation', 'en-US')    // "1.5M"
 */
export function formatPivotNumber(
  value: number | null | undefined,
  format: NumberFormat,
  locale: string = 'nl-NL',
): string {
  if (value == null || Number.isNaN(value)) {
    return '';
  }

  switch (format) {
    case 'decimal':
      return new Intl.NumberFormat(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);

    case 'whole':
      return new Intl.NumberFormat(locale, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(value);

    case 'k-notation':
      return formatAbbreviated(value, locale);

    default:
      // Fallback: treat unknown format as decimal
      return new Intl.NumberFormat(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
  }
}

/**
 * Format a number with k/M suffix abbreviation.
 *
 * Values below 1 000 are shown with 1 decimal place.
 * Values ≥ 1 000 use the largest matching suffix (k or M) with 1 decimal place.
 * Negative values are handled by formatting the absolute value and prepending '−'.
 */
function formatAbbreviated(value: number, locale: string): string {
  const absValue = Math.abs(value);
  const sign = value < 0 ? '−' : '';

  for (const { threshold, suffix, divisor } of ABBREVIATIONS) {
    if (absValue >= threshold) {
      const abbreviated = absValue / divisor;
      const formatted = new Intl.NumberFormat(locale, {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }).format(abbreviated);
      return `${sign}${formatted}${suffix}`;
    }
  }

  // Below 1 000: show with 1 decimal place
  const formatted = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(absValue);
  return `${sign}${formatted}`;
}

/**
 * Resolve a BCP 47 locale string from an i18n language code.
 *
 * Maps short language codes used by i18next (e.g. 'nl', 'en') to full
 * BCP 47 locale strings expected by Intl.NumberFormat.
 */
export function resolveLocale(language: string): string {
  switch (language) {
    case 'nl':
      return 'nl-NL';
    case 'en':
      return 'en-US';
    default:
      return language.includes('-') ? language : `${language}-${language.toUpperCase()}`;
  }
}
