/**
 * Internationalization formatting utilities for dates, numbers, and currency.
 * 
 * Supports Dutch (nl) and English (en) locales with proper formatting conventions:
 * - Dutch: 1.234,56 (dot thousands, comma decimal)
 * - English: 1,234.56 (comma thousands, dot decimal)
 * - Currency: EUR (€) for both locales
 */

import { format as dateFnsFormat } from 'date-fns';
import { nl, enUS } from 'date-fns/locale';

const locales = { nl, en: enUS };

/**
 * Format a date according to the specified language locale.
 * 
 * @param date - Date to format
 * @param language - Language code ('nl' or 'en')
 * @param formatStr - Optional date-fns format string (defaults to 'P' for localized date)
 * @returns Formatted date string
 * 
 * @example
 * formatDate(new Date('2026-02-17'), 'nl') // "17-02-2026"
 * formatDate(new Date('2026-02-17'), 'en') // "02/17/2026"
 */
export function formatDate(date: Date, language: string, formatStr: string = 'P'): string {
  const locale = locales[language as keyof typeof locales] || locales.en;
  return dateFnsFormat(date, formatStr, { locale });
}

/**
 * Format a number according to the specified language locale.
 * 
 * @param value - Number to format
 * @param language - Language code ('nl' or 'en')
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted number string
 * 
 * @example
 * formatNumber(1234.56, 'nl') // "1.234,56"
 * formatNumber(1234.56, 'en') // "1,234.56"
 */
export function formatNumber(value: number, language: string, decimals: number = 2): string {
  const locale = language === 'nl' ? 'nl-NL' : 'en-US';
  
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(value);
}

/**
 * Format a currency amount in EUR according to the specified language locale.
 * 
 * @param value - Amount to format
 * @param language - Language code ('nl' or 'en')
 * @returns Formatted currency string with € symbol
 * 
 * @example
 * formatCurrency(1234.56, 'nl') // "€ 1.234,56"
 * formatCurrency(1234.56, 'en') // "€1,234.56"
 */
export function formatCurrency(value: number, language: string): string {
  const locale = language === 'nl' ? 'nl-NL' : 'en-US';
  
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'EUR'
  }).format(value);
}
