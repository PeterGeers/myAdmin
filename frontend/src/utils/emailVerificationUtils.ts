/**
 * Email Verification Utilities
 *
 * Shared validation and formatting logic for the SES email verification feature.
 * Extracted for testability and reuse across components.
 *
 * Requirements: 5.5, 9.7
 */

import * as Yup from 'yup';

/**
 * Yup validation schema for email addresses.
 *
 * Matches backend validation rules:
 * - Contains exactly one '@'
 * - Non-empty local part
 * - Non-empty domain part with at least one dot
 * - No spaces
 *
 * Requirement 5.5
 */
export const emailValidationSchema = Yup.object().shape({
  email: Yup.string()
    .required('Email address is required')
    .email('Please enter a valid email address')
    .matches(
      /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
      'Please enter a valid email address'
    ),
});

/**
 * Validate an email address string against the Yup schema.
 *
 * Returns true if the email passes validation, false otherwise.
 * This mirrors the backend _validate_email() logic.
 *
 * Requirement 5.5
 */
export function isValidEmail(email: string): boolean {
  try {
    // Check basic structural rules that match backend:
    // 1. Not empty
    if (!email || typeof email !== 'string') return false;

    const trimmed = email.trim();

    // 2. No spaces
    if (trimmed.includes(' ')) return false;

    // 3. Exactly one '@'
    const atParts = trimmed.split('@');
    if (atParts.length !== 2) return false;

    const [local, domain] = atParts;

    // 4. Non-empty local part
    if (!local || local.length === 0) return false;

    // 5. Non-empty domain part with at least one dot
    if (!domain || domain.length === 0) return false;
    if (!domain.includes('.')) return false;

    // 6. Domain parts around dots must be non-empty
    const domainParts = domain.split('.');
    if (domainParts.some(part => part.length === 0)) return false;

    return true;
  } catch {
    return false;
  }
}


