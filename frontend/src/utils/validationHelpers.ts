/**
 * Validation Helper Functions
 * 
 * Provides reusable validation functions for common input formats.
 * These functions validate format only and should be combined with
 * translated error messages from the 'validation' namespace.
 * 
 * @module utils/validationHelpers
 */

/**
 * Email validation regex pattern.
 * Validates basic email format: user@domain.tld
 */
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * URL validation regex pattern.
 * Validates HTTP and HTTPS URLs.
 */
const URL_REGEX = /^https?:\/\/.+/;

/**
 * Phone validation regex pattern.
 * Validates international phone format with optional + prefix and separators.
 */
const PHONE_REGEX = /^\+?[\d\s-()]+$/;

/**
 * IBAN validation regex pattern (basic format check).
 * Validates country code (2 letters) + check digits (2 numbers) + account number.
 * Note: This is a basic format check, not a full IBAN validation with checksum.
 */
const IBAN_REGEX = /^[A-Z]{2}\d{2}[A-Z0-9]+$/;

/**
 * Validate email address format.
 * 
 * Checks if the email matches the pattern: user@domain.tld
 * 
 * @param email - Email address to validate
 * @returns true if email format is valid, false otherwise
 * 
 * @example
 * ```typescript
 * isValidEmail('user@example.com'); // true
 * isValidEmail('invalid-email'); // false
 * isValidEmail('user@domain'); // false
 * ```
 * 
 * @example
 * ```typescript
 * // With translation
 * import { useTypedTranslation } from '../hooks/useTypedTranslation';
 * import { isValidEmail } from '../utils/validationHelpers';
 * 
 * function EmailInput() {
 *   const { t } = useTypedTranslation('validation');
 *   const [email, setEmail] = useState('');
 *   const [error, setError] = useState('');
 *   
 *   const handleBlur = () => {
 *     if (!isValidEmail(email)) {
 *       setError(t('format.email')); // "Invalid email address"
 *     }
 *   };
 * }
 * ```
 */
export function isValidEmail(email: string): boolean {
  return EMAIL_REGEX.test(email);
}

/**
 * Validate URL format.
 * 
 * Checks if the URL starts with http:// or https://
 * 
 * @param url - URL to validate
 * @returns true if URL format is valid, false otherwise
 * 
 * @example
 * ```typescript
 * isValidUrl('https://example.com'); // true
 * isValidUrl('http://example.com'); // true
 * isValidUrl('ftp://example.com'); // false
 * isValidUrl('example.com'); // false
 * ```
 */
export function isValidUrl(url: string): boolean {
  return URL_REGEX.test(url);
}

/**
 * Validate phone number format.
 * 
 * Checks if the phone number contains only digits, spaces, hyphens, parentheses,
 * and optionally starts with a + for international format.
 * 
 * @param phone - Phone number to validate
 * @returns true if phone format is valid, false otherwise
 * 
 * @example
 * ```typescript
 * isValidPhone('+31 6 12345678'); // true
 * isValidPhone('06-12345678'); // true
 * isValidPhone('(020) 123-4567'); // true
 * isValidPhone('invalid-phone'); // false
 * ```
 */
export function isValidPhone(phone: string): boolean {
  return PHONE_REGEX.test(phone);
}

/**
 * Validate IBAN format (basic check).
 * 
 * Checks if the IBAN matches the basic format:
 * - 2 uppercase letters (country code)
 * - 2 digits (check digits)
 * - Alphanumeric account number
 * 
 * Note: This is a basic format check only. It does not validate the checksum.
 * For production use, consider using a full IBAN validation library.
 * 
 * @param iban - IBAN to validate (spaces are automatically removed)
 * @returns true if IBAN format is valid, false otherwise
 * 
 * @example
 * ```typescript
 * isValidIBAN('NL91ABNA0417164300'); // true
 * isValidIBAN('NL91 ABNA 0417 1643 00'); // true (spaces removed)
 * isValidIBAN('INVALID'); // false
 * isValidIBAN('NL91'); // false (too short)
 * ```
 */
export function isValidIBAN(iban: string): boolean {
  return IBAN_REGEX.test(iban.replace(/\s/g, ''));
}
