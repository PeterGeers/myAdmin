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


