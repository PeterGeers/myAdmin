/**
 * Validation Helper Functions
 * 
 * Provides reusable validation functions with i18n support.
 */

/**
 * Email validation regex
 */
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * URL validation regex
 */
const URL_REGEX = /^https?:\/\/.+/;

/**
 * Phone validation regex (international format)
 */
const PHONE_REGEX = /^\+?[\d\s-()]+$/;

/**
 * IBAN validation regex (basic)
 */
const IBAN_REGEX = /^[A-Z]{2}\d{2}[A-Z0-9]+$/;

/**
 * Validate email format
 */
export function isValidEmail(email: string): boolean {
  return EMAIL_REGEX.test(email);
}

/**
 * Validate URL format
 */
export function isValidUrl(url: string): boolean {
  return URL_REGEX.test(url);
}

/**
 * Validate phone format
 */
export function isValidPhone(phone: string): boolean {
  return PHONE_REGEX.test(phone);
}

/**
 * Validate IBAN format
 */
export function isValidIBAN(iban: string): boolean {
  return IBAN_REGEX.test(iban.replace(/\s/g, ''));
}
