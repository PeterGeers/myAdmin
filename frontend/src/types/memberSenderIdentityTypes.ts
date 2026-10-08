/**
 * Member sender-identity TypeScript type definitions (R0, design §6.2).
 *
 * A tenant admin verifies/activates one or more sender email addresses that the
 * Members mail worker uses as the `From` for that tenant. The backend drives SES
 * identity verification (`VerifyEmailIdentity` / domain verification) in the
 * nonprofit-deploy account and tracks each address's status.
 *
 * This mirrors the design §6.2 contract for `POST /members/sender-identities`
 * (add an address), its status `GET` (list addresses with SES status), and the
 * resend action. Distinct from the single-sender invoice flow in
 * {@link ./VerificationTypes} (one address, FIN plane) — the Members plane
 * supports MULTIPLE addresses per tenant.
 */

/**
 * SES verification state of a tenant sender address.
 *
 * `pending`  — verification requested, awaiting the SES confirmation click.
 * `verified` — SES confirmed; the worker may send `From` this address.
 * `failed`   — SES reported the identity verification failed.
 * `expired`  — the pending verification request lapsed; resend to retry.
 */
export type SenderIdentityStatus = 'pending' | 'verified' | 'failed' | 'expired';

/**
 * One tenant sender address and its SES verification state.
 */
export interface MemberSenderIdentity {
  /** The sender email address (SES identity). */
  email: string;
  /** Current SES verification state. */
  status: SenderIdentityStatus;
  /** ISO timestamp of the last SES status check, or null if never checked. */
  lastChecked: string | null;
}

/**
 * Response from `GET /members/sender-identities` — the tenant's sender addresses.
 * API response & error standard v1.0 (steering 37): `{success, data}`.
 */
export interface SenderIdentitiesListResponse {
  success: boolean;
  data?: {
    identities: MemberSenderIdentity[];
  };
  error?: string;
  code?: string;
}

/**
 * Response from `POST /members/sender-identities` — add + begin verifying an address.
 */
export interface AddSenderIdentityResponse {
  success: boolean;
  data?: MemberSenderIdentity;
  error?: string;
  code?: string;
}

/**
 * Response from `POST /members/sender-identities/resend` — resend the SES
 * verification email for a pending/failed/expired address.
 */
export interface ResendSenderIdentityResponse {
  success: boolean;
  error?: string;
  code?: string;
}
