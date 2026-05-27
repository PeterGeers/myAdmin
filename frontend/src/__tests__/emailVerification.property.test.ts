/**
 * Property-Based Tests — SES Email Verification (Frontend)
 *
 * Property 9 (frontend): Email validation — generate random strings with fast-check,
 * verify Yup schema matches backend validation rules.
 *
 * Property 14 (frontend): Locale greeting — generate random locale strings,
 * verify correct greeting selection logic.
 *
 * **Validates: Requirements 5.5, 9.7**
 */
import fc from 'fast-check';
import { isValidEmail, getLocaleGreeting } from '../utils/emailVerificationUtils';

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

// ---------------------------------------------------------------------------
// Property 14 (frontend): Locale greeting
// Feature: ses-email-verification, Property 14: Locale-aware signature greeting
// Validates: Requirements 9.7
// ---------------------------------------------------------------------------

describe('Property 14 (frontend): Locale greeting', () => {
  /**
   * Feature: ses-email-verification, Property 14: Locale-aware signature greeting
   *
   * For locale 'nl_NL', the greeting SHALL be "Met vriendelijke groet,".
   *
   * **Validates: Requirements 9.7**
   */
  it('PROPERTY: nl_NL locale always returns Dutch greeting', () => {
    // The nl_NL locale is fixed, but we test it with property style
    // to confirm it's deterministic regardless of other conditions
    fc.assert(
      fc.property(fc.constant('nl_NL'), (locale) => {
        const greeting = getLocaleGreeting(locale);
        return greeting === 'Met vriendelijke groet,';
      }),
      { numRuns: 10 }
    );
  });

  /**
   * Feature: ses-email-verification, Property 14: Locale-aware signature greeting
   *
   * For any locale string that is NOT 'nl_NL', the greeting SHALL be "Kind regards,".
   *
   * **Validates: Requirements 9.7**
   */
  it('PROPERTY: any non-nl_NL locale returns English greeting', () => {
    // Generate random locale-like strings that are NOT 'nl_NL'
    const nonNlLocaleArb = fc.oneof(
      // Common locale patterns
      fc.constantFrom(
        'en_US', 'en_GB', 'de_DE', 'fr_FR', 'es_ES', 'it_IT',
        'pt_BR', 'ja_JP', 'zh_CN', 'ko_KR', 'nl_BE', 'nl',
        'en', 'de', 'fr', 'es', ''
      ),
      // Random locale-like strings (xx_YY pattern)
      fc.tuple(
        fc.stringMatching(/^[a-z]{2}$/),
        fc.stringMatching(/^[A-Z]{2}$/),
      ).map(([lang, country]) => `${lang}_${country}`),
      // Random arbitrary strings
      fc.string({ minLength: 0, maxLength: 10 }),
    ).filter(locale => locale !== 'nl_NL');

    fc.assert(
      fc.property(nonNlLocaleArb, (locale) => {
        const greeting = getLocaleGreeting(locale);
        return greeting === 'Kind regards,';
      }),
      { numRuns: 200 }
    );
  });

  /**
   * Feature: ses-email-verification, Property 14: Locale-aware signature greeting
   *
   * For any locale string, the greeting SHALL be one of the two valid options.
   *
   * **Validates: Requirements 9.7**
   */
  it('PROPERTY: greeting is always one of the two valid options', () => {
    const anyLocaleArb = fc.oneof(
      fc.constant('nl_NL'),
      fc.string({ minLength: 0, maxLength: 20 }),
    );

    fc.assert(
      fc.property(anyLocaleArb, (locale) => {
        const greeting = getLocaleGreeting(locale);
        return (
          greeting === 'Met vriendelijke groet,' ||
          greeting === 'Kind regards,'
        );
      }),
      { numRuns: 200 }
    );
  });
});
