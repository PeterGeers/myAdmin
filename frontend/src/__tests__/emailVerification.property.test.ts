/**
 * Property-Based Tests — SES Email Verification (Frontend)
 *
 * Property 9 (frontend): Email validation — generate random strings with fast-check,
 * verify Yup schema matches backend validation rules.
 *
 * **Validates: Requirements 5.5**
 */
import fc from 'fast-check';
import { isValidEmail } from '../utils/emailVerificationUtils';

// ---------------------------------------------------------------------------
// Property 9 (frontend): Email validation
// Feature: ses-email-verification, Property 9: Email validation
// Validates: Requirements 5.5
// ---------------------------------------------------------------------------

describe('Property 9 (frontend): Email validation', () => {
  /**
   * Feature: ses-email-verification, Property 9: Email validation
   *
   * For any string that is a well-formed email address (contains exactly one @,
   * has non-empty local and domain parts, domain contains a dot), validation
   * SHALL pass.
   *
   * **Validates: Requirements 5.5**
   */
  it('PROPERTY: well-formed emails pass validation', () => {
    // Generator for valid email addresses
    const validEmailArb = fc.tuple(
      // Local part: 1-20 chars from allowed set (letters, digits, dots, hyphens)
      fc.stringMatching(/^[a-zA-Z0-9][a-zA-Z0-9.+_-]{0,19}$/),
      // Domain name: 1-15 chars (letters, digits, hyphens)
      fc.stringMatching(/^[a-zA-Z0-9][a-zA-Z0-9-]{0,14}$/),
      // TLD: 2-6 lowercase letters
      fc.stringMatching(/^[a-zA-Z]{2,6}$/),
    ).map(([local, domain, tld]) => `${local}@${domain}.${tld}`);

    fc.assert(
      fc.property(validEmailArb, (email) => {
        return isValidEmail(email) === true;
      }),
      { numRuns: 200 }
    );
  });

  /**
   * Feature: ses-email-verification, Property 9: Email validation
   *
   * Strings without an '@' symbol SHALL fail validation.
   *
   * **Validates: Requirements 5.5**
   */
  it('PROPERTY: strings without @ fail validation', () => {
    // Generate strings that do not contain '@'
    const noAtArb = fc.stringMatching(/^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]{1,30}$/);

    fc.assert(
      fc.property(noAtArb, (str) => {
        // Ensure no @ is present
        if (str.includes('@')) return true; // skip if regex accidentally includes @
        return isValidEmail(str) === false;
      }),
      { numRuns: 200 }
    );
  });

  /**
   * Feature: ses-email-verification, Property 9: Email validation
   *
   * Strings with multiple '@' symbols SHALL fail validation.
   *
   * **Validates: Requirements 5.5**
   */
  it('PROPERTY: strings with multiple @ fail validation', () => {
    const multipleAtArb = fc.tuple(
      fc.stringMatching(/^[a-z]{1,10}$/),
      fc.stringMatching(/^[a-z]{1,10}$/),
      fc.stringMatching(/^[a-z]{1,10}\.[a-z]{2,4}$/),
    ).map(([a, b, c]) => `${a}@${b}@${c}`);

    fc.assert(
      fc.property(multipleAtArb, (str) => {
        return isValidEmail(str) === false;
      }),
      { numRuns: 200 }
    );
  });

  /**
   * Feature: ses-email-verification, Property 9: Email validation
   *
   * Strings with empty local part (starting with @) SHALL fail validation.
   *
   * **Validates: Requirements 5.5**
   */
  it('PROPERTY: empty local part fails validation', () => {
    const emptyLocalArb = fc.stringMatching(/^[a-z]{2,10}\.[a-z]{2,4}$/)
      .map(domain => `@${domain}`);

    fc.assert(
      fc.property(emptyLocalArb, (str) => {
        return isValidEmail(str) === false;
      }),
      { numRuns: 200 }
    );
  });

  /**
   * Feature: ses-email-verification, Property 9: Email validation
   *
   * Strings where domain has no dot SHALL fail validation.
   *
   * **Validates: Requirements 5.5**
   */
  it('PROPERTY: domain without dot fails validation', () => {
    const noDotDomainArb = fc.tuple(
      fc.stringMatching(/^[a-z]{1,10}$/),
      fc.stringMatching(/^[a-z]{2,10}$/),
    ).map(([local, domain]) => `${local}@${domain}`);

    fc.assert(
      fc.property(noDotDomainArb, (str) => {
        return isValidEmail(str) === false;
      }),
      { numRuns: 200 }
    );
  });

  /**
   * Feature: ses-email-verification, Property 9: Email validation
   *
   * Strings containing spaces SHALL fail validation.
   *
   * **Validates: Requirements 5.5**
   */
  it('PROPERTY: strings with spaces fail validation', () => {
    const withSpaceArb = fc.tuple(
      fc.stringMatching(/^[a-z]{1,5}$/),
      fc.stringMatching(/^[a-z]{1,5}$/),
      fc.stringMatching(/^[a-z]{2,5}\.[a-z]{2,3}$/),
    ).map(([a, b, domain]) => `${a} ${b}@${domain}`);

    fc.assert(
      fc.property(withSpaceArb, (str) => {
        return isValidEmail(str) === false;
      }),
      { numRuns: 200 }
    );
  });
});


