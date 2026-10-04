/**
 * Email Verification Utilities
 *
 * Shared validation and formatting logic for the SES email verification feature.
 * Extracted for testability and reuse across components.
 *
 * Requirements: 5.5, 9.7
 */

import * as Yup from 'yup';

// Re-export the canonical email validator so there is a single implementation.
// `isValidEmail` lives in `validationHelpers` (the format-validation home); this
// module keeps re-exporting it under the same name for the SES email-verification
// call sites. See utils/validationHelpers.ts for the implementation.
export { isValidEmail } from './validationHelpers';

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




