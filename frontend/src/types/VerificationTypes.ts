/**
 * Email Verification TypeScript type definitions
 *
 * Types for the SES email verification feature, covering verification status,
 * API responses, and related data structures.
 */

/**
 * Possible verification states for a tenant's sender email
 */
export type VerificationStatusValue = 'pending' | 'verified' | 'failed' | 'expired';

/**
 * Core verification status data returned by the API
 */
export interface VerificationStatus {
  email: string;
  status: VerificationStatusValue;
  lastChecked: string | null;
  fallbackSender: string;
}

/**
 * Response from GET /api/tenant-admin/sender-verification
 */
export interface VerificationStatusResponse {
  success: boolean;
  data: VerificationStatus;
}

/**
 * Response from POST /api/tenant-admin/sender-verification/resend
 */
export interface ResendVerificationResponse {
  success: boolean;
  message?: string;
  error?: string;
}

/**
 * Response from PUT /api/tenant-admin/sender-verification/email
 */
export interface UpdateEmailResponse {
  success: boolean;
  data?: {
    email: string;
    status: VerificationStatusValue;
  };
  error?: string;
}
