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



/**
 * IBAN validation (ISO 13616 **mod-97 checksum**).
 *
 * A regex can only check SHAPE — it cannot verify the checksum — so IBAN gets a real algorithm
 * (spec `Members/application-app` R6.2 / R7.6, the `IBAN` `FieldFormat` checker). This mirrors the
 * SAM-plane server check so the client form validates the SAME rule the server enforces
 * authoritatively (R10a.2 parity).
 *
 * Algorithm:
 *   1. strip spaces, upper-case;
 *   2. basic shape: 2 letters (country) + 2 digits (check) + up to 30 alphanumerics;
 *   3. enforce the per-country fixed length;
 *   4. move the first four chars to the end;
 *   5. replace each letter with two digits (A=10 … Z=35);
 *   6. the IBAN is valid when the resulting big integer mod 97 === 1.
 */

/** Per-country IBAN total lengths (ISO 13616 registry). Unlisted countries fail the length gate. */
const IBAN_COUNTRY_LENGTHS: Readonly<Record<string, number>> = {
  AD: 24, AE: 23, AL: 28, AT: 20, AZ: 28, BA: 20, BE: 16, BG: 22, BH: 22, BR: 29,
  BY: 28, CH: 21, CR: 22, CY: 28, CZ: 24, DE: 22, DK: 18, DO: 28, EE: 20, EG: 29,
  ES: 24, FI: 18, FO: 18, FR: 27, GB: 22, GE: 22, GI: 23, GL: 18, GR: 27, GT: 28,
  HR: 21, HU: 28, IE: 22, IL: 23, IQ: 23, IS: 26, IT: 27, JO: 30, KW: 30, KZ: 20,
  LB: 28, LC: 32, LI: 21, LT: 20, LU: 20, LV: 21, MC: 27, MD: 24, ME: 22, MK: 19,
  MR: 27, MT: 31, MU: 30, NL: 18, NO: 15, PK: 24, PL: 28, PS: 29, PT: 25, QA: 29,
  RO: 24, RS: 22, SA: 24, SC: 31, SE: 24, SI: 19, SK: 24, SM: 27, ST: 25, SV: 28,
  TL: 23, TN: 24, TR: 26, UA: 29, VA: 22, VG: 24, XK: 20,
};

/** Shape gate before the checksum: country (2 alpha) + check (2 digit) + 1..30 alphanumerics. */
const IBAN_SHAPE_REGEX = /^[A-Z]{2}\d{2}[A-Z0-9]{1,30}$/;

/** Compute `value mod 97` over a long digit STRING without overflowing Number (piecewise). */
function mod97(digits: string): number {
  let remainder = 0;
  for (let i = 0; i < digits.length; i += 7) {
    remainder = Number(String(remainder) + digits.slice(i, i + 7)) % 97;
  }
  return remainder;
}

/**
 * Validate an IBAN via the ISO 13616 mod-97 checksum.
 *
 * @param iban - the IBAN to validate (spaces/case are normalized)
 * @returns true when the IBAN passes shape, country-length, and the mod-97 checksum
 *
 * @example
 * isValidIban('NL91 ABNA 0417 1643 00'); // true
 * isValidIban('NL00 ABNA 0417 1643 00'); // false (bad checksum)
 * isValidIban('GB82 WEST 1234 5698 7654 32'); // true
 */
export function isValidIban(iban: string): boolean {
  if (!iban) return false;
  const normalized = iban.replace(/\s+/g, '').toUpperCase();
  if (!IBAN_SHAPE_REGEX.test(normalized)) return false;

  const country = normalized.slice(0, 2);
  const expectedLength = IBAN_COUNTRY_LENGTHS[country];
  if (expectedLength === undefined || normalized.length !== expectedLength) return false;

  // Rotate the first four chars (country + check digits) to the end.
  const rearranged = normalized.slice(4) + normalized.slice(0, 4);
  // Letters → digits (A=10 … Z=35).
  let digits = '';
  for (const ch of rearranged) {
    if (ch >= '0' && ch <= '9') {
      digits += ch;
    } else {
      digits += String(ch.charCodeAt(0) - 'A'.charCodeAt(0) + 10);
    }
  }
  return mod97(digits) === 1;
}
