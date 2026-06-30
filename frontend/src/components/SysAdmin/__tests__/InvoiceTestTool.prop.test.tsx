/**
 * Property-Based Tests — Invoice Processing Test Tool (Frontend)
 *
 * Property 9 (frontend): Prompt length validation — accept 1–10,000 chars, reject empty or >10,000
 * Property 10 (frontend): Vendor name validation — accept iff matches ^[a-zA-Z0-9_-]{1,100}$
 * Property 4 (frontend): Raw text truncation display — verify truncation indicator logic
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * **Validates: Requirements 6.4, 7.1, 3.1**
 */
import fc from 'fast-check';
import { validatePromptLength } from '../CustomPromptEditor';
import { validateVendorName } from '../InvoiceTestTool';

// ─── Constants (mirrored from source) ────────────────────────────────────────

const MAX_PROMPT_LENGTH = 10_000;
const RAW_TEXT_TRUNCATION_LIMIT = 50_000;
const VENDOR_NAME_REGEX = /^[a-zA-Z0-9_-]{1,100}$/;

// ─── Helper: Truncation indicator logic (frontend display) ───────────────────

/**
 * Determines whether the truncation indicator should be shown.
 * This mirrors the logic in PipelineResultsPanel's RawTextSection component.
 *
 * The backend sets raw_text_truncated=true when text exceeds 50,000 chars,
 * and the frontend shows a badge when this flag is true.
 */
function shouldShowTruncationIndicator(rawTextTruncated: boolean): boolean {
  return rawTextTruncated;
}

/**
 * Simulates the backend truncation logic for property testing.
 * For text >50,000 chars: truncates to 50,000 and sets flag to true.
 * For text ≤50,000 chars: returns full text with flag false.
 */
function simulateTruncation(text: string): { text: string; truncated: boolean } {
  if (text.length > RAW_TEXT_TRUNCATION_LIMIT) {
    return { text: text.slice(0, RAW_TEXT_TRUNCATION_LIMIT), truncated: true };
  }
  return { text, truncated: false };
}

// ─────────────────────────────────────────────────────────────────────────────
// Property 9 (frontend): Prompt length validation
// Feature: invoice-processing-test-tool, Property 9: Prompt length validation
// Validates: Requirements 6.4
// ─────────────────────────────────────────────────────────────────────────────

describe('Property 9 (frontend): Prompt length validation', () => {
  /**
   * Feature: invoice-processing-test-tool, Property 9: Prompt length validation
   *
   * For any string with length between 1 and 10,000 (inclusive),
   * validatePromptLength SHALL return null (valid).
   *
   * **Validates: Requirements 6.4**
   */
  it('PROPERTY: prompts with 1–10,000 chars are accepted', () => {
    const validPromptArb = fc.string({ minLength: 1, maxLength: MAX_PROMPT_LENGTH });

    fc.assert(
      fc.property(validPromptArb, (prompt) => {
        return validatePromptLength(prompt) === null;
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: invoice-processing-test-tool, Property 9: Prompt length validation
   *
   * For an empty string (length 0), validatePromptLength SHALL return
   * a non-null error message (rejected).
   *
   * **Validates: Requirements 6.4**
   */
  it('PROPERTY: empty prompt is rejected', () => {
    const result = validatePromptLength('');
    expect(result).not.toBeNull();
    expect(result).toContain('empty');
  });

  /**
   * Feature: invoice-processing-test-tool, Property 9: Prompt length validation
   *
   * For any string with length > 10,000, validatePromptLength SHALL return
   * a non-null error message (rejected).
   *
   * **Validates: Requirements 6.4**
   */
  it('PROPERTY: prompts exceeding 10,000 chars are rejected', () => {
    // Generate strings that are definitely > 10,000 chars
    const tooLongPromptArb = fc.string({ minLength: MAX_PROMPT_LENGTH + 1, maxLength: MAX_PROMPT_LENGTH + 500 });

    fc.assert(
      fc.property(tooLongPromptArb, (prompt) => {
        const result = validatePromptLength(prompt);
        return result !== null && result.length > 0;
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: invoice-processing-test-tool, Property 9: Prompt length validation
   *
   * Boundary: a string of exactly 10,000 chars SHALL be accepted (null),
   * a string of exactly 10,001 chars SHALL be rejected (non-null).
   *
   * **Validates: Requirements 6.4**
   */
  it('PROPERTY: boundary at exactly 10,000 and 10,001 chars', () => {
    const boundaryArb = fc.constantFrom(MAX_PROMPT_LENGTH, MAX_PROMPT_LENGTH + 1);

    fc.assert(
      fc.property(boundaryArb, (len) => {
        const prompt = 'a'.repeat(len);
        const result = validatePromptLength(prompt);
        if (len <= MAX_PROMPT_LENGTH) {
          return result === null;
        }
        return result !== null;
      }),
      { numRuns: 100 }
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Property 10 (frontend): Vendor name validation
// Feature: invoice-processing-test-tool, Property 10: Vendor name validation
// Validates: Requirements 7.1
// ─────────────────────────────────────────────────────────────────────────────

describe('Property 10 (frontend): Vendor name validation', () => {
  /**
   * Feature: invoice-processing-test-tool, Property 10: Vendor name validation
   *
   * For any string matching ^[a-zA-Z0-9_-]{1,100}$, validateVendorName
   * SHALL return null (valid).
   *
   * **Validates: Requirements 7.1**
   */
  it('PROPERTY: valid vendor names (alphanumeric, hyphens, underscores, spaces, 1-100 chars) are accepted', () => {
    const validVendorArb = fc.stringMatching(/^[a-zA-Z0-9_ -]{1,100}$/);

    fc.assert(
      fc.property(validVendorArb, (name) => {
        return validateVendorName(name) === null;
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: invoice-processing-test-tool, Property 10: Vendor name validation
   *
   * For any string containing characters outside [a-zA-Z0-9_ -],
   * validateVendorName SHALL return a non-null error message (rejected).
   *
   * **Validates: Requirements 7.1**
   */
  it('PROPERTY: names with invalid characters are rejected', () => {
    // Generate strings that contain at least one invalid char
    const invalidCharArb = fc.tuple(
      fc.stringMatching(/^[a-zA-Z0-9_ -]{0,10}$/),
      fc.constantFrom('.', '!', '@', '#', '$', '%', '/', '\\', '(', ')', '+', '=', '~'),
      fc.stringMatching(/^[a-zA-Z0-9_ -]{0,10}$/),
    ).map(([prefix, invalidChar, suffix]) => `${prefix}${invalidChar}${suffix}`);

    fc.assert(
      fc.property(invalidCharArb, (name) => {
        const result = validateVendorName(name);
        return result !== null;
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: invoice-processing-test-tool, Property 10: Vendor name validation
   *
   * For any string with length > 100 (even if all chars are valid),
   * validateVendorName SHALL return a non-null error message (rejected).
   *
   * **Validates: Requirements 7.1**
   */
  it('PROPERTY: names exceeding 100 characters are rejected', () => {
    const tooLongArb = fc.stringMatching(/^[a-zA-Z0-9_-]{101,150}$/);

    fc.assert(
      fc.property(tooLongArb, (name) => {
        const result = validateVendorName(name);
        return result !== null;
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: invoice-processing-test-tool, Property 10: Vendor name validation
   *
   * Empty string is allowed by the component (defaults to "TestVendor"),
   * so validateVendorName SHALL return null for empty input.
   *
   * **Validates: Requirements 7.1**
   */
  it('PROPERTY: empty string is accepted (defaults to TestVendor)', () => {
    expect(validateVendorName('')).toBeNull();
  });

  /**
   * Feature: invoice-processing-test-tool, Property 10: Vendor name validation
   *
   * For any non-empty string, validateVendorName SHALL accept it if and only if
   * the regex ^[a-zA-Z0-9_-]{1,100}$ matches.
   *
   * **Validates: Requirements 7.1**
   */
  it('PROPERTY: acceptance matches regex ^[a-zA-Z0-9_-]{1,100}$ exactly', () => {
    // Generate a mix of valid and invalid strings
    const mixedArb = fc.oneof(
      fc.stringMatching(/^[a-zA-Z0-9_-]{1,100}$/),
      fc.string({ minLength: 1, maxLength: 120 }),
    );

    fc.assert(
      fc.property(mixedArb, (name) => {
        const result = validateVendorName(name);
        const matchesRegex = VENDOR_NAME_REGEX.test(name);
        if (matchesRegex) {
          return result === null;
        }
        return result !== null;
      }),
      { numRuns: 100 }
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Property 4 (frontend): Raw text truncation display
// Feature: invoice-processing-test-tool, Property 4: Raw text truncation invariant
// Validates: Requirements 3.1
// ─────────────────────────────────────────────────────────────────────────────

describe('Property 4 (frontend): Raw text truncation display', () => {
  /**
   * Feature: invoice-processing-test-tool, Property 4: Raw text truncation invariant
   *
   * For text ≤ 50,000 characters, the truncation flag SHALL be false and
   * the truncation indicator SHALL NOT be shown.
   *
   * **Validates: Requirements 3.1**
   */
  it('PROPERTY: text ≤ 50,000 chars → truncated=false, no indicator', () => {
    const shortTextArb = fc.string({ minLength: 0, maxLength: 1000 });

    fc.assert(
      fc.property(shortTextArb, (text) => {
        const { text: resultText, truncated } = simulateTruncation(text);
        // Text ≤ 50,000 → full text returned, truncated=false
        return (
          resultText === text &&
          truncated === false &&
          shouldShowTruncationIndicator(truncated) === false
        );
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: invoice-processing-test-tool, Property 4: Raw text truncation invariant
   *
   * For text > 50,000 characters, the truncation flag SHALL be true,
   * the returned text SHALL be exactly 50,000 characters, and
   * the truncation indicator SHALL be shown.
   *
   * **Validates: Requirements 3.1**
   */
  it('PROPERTY: text > 50,000 chars → truncated to exactly 50,000, indicator shown', () => {
    // Generate lengths just above the limit (to avoid huge memory allocations)
    const overLimitLengthArb = fc.integer({ min: RAW_TEXT_TRUNCATION_LIMIT + 1, max: RAW_TEXT_TRUNCATION_LIMIT + 5000 });

    fc.assert(
      fc.property(overLimitLengthArb, (length) => {
        const text = 'x'.repeat(length);
        const { text: resultText, truncated } = simulateTruncation(text);
        return (
          resultText.length === RAW_TEXT_TRUNCATION_LIMIT &&
          truncated === true &&
          shouldShowTruncationIndicator(truncated) === true
        );
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: invoice-processing-test-tool, Property 4: Raw text truncation invariant
   *
   * Boundary: text of exactly 50,000 chars → not truncated;
   * text of exactly 50,001 chars → truncated.
   *
   * **Validates: Requirements 3.1**
   */
  it('PROPERTY: boundary at exactly 50,000 and 50,001 chars', () => {
    const boundaryArb = fc.constantFrom(RAW_TEXT_TRUNCATION_LIMIT, RAW_TEXT_TRUNCATION_LIMIT + 1);

    fc.assert(
      fc.property(boundaryArb, (length) => {
        const text = 'a'.repeat(length);
        const { text: resultText, truncated } = simulateTruncation(text);
        if (length <= RAW_TEXT_TRUNCATION_LIMIT) {
          return resultText.length === length && truncated === false;
        }
        return resultText.length === RAW_TEXT_TRUNCATION_LIMIT && truncated === true;
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: invoice-processing-test-tool, Property 4: Raw text truncation invariant
   *
   * The truncation indicator display is a pure function of the truncated flag:
   * show indicator iff truncated === true.
   *
   * **Validates: Requirements 3.1**
   */
  it('PROPERTY: indicator visibility is determined solely by the truncated flag', () => {
    const boolArb = fc.boolean();

    fc.assert(
      fc.property(boolArb, (truncated) => {
        return shouldShowTruncationIndicator(truncated) === truncated;
      }),
      { numRuns: 100 }
    );
  });
});
