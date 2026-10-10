/**
 * Member sender-identity API service (R0, design §6.2).
 *
 * Drives the tenant-admin sender-identity surface: list the tenant's sender
 * addresses with their SES status, add + begin verifying a new address, and
 * resend the SES verification email for a pending/failed/expired address.
 *
 * Routes (design §3 / §6.2) on the Members Lambda:
 *   - GET  /members/sender-identities              — list with status
 *   - POST /members/sender-identities              — add + VerifyEmailIdentity
 *   - POST /members/sender-identities/resend        — resend verification
 *
 * Gate: `members:admin` (tenant admin). Follows the API response & error
 * standard v1.0 (steering 37): `{success, data}` / `{success:false, error, code}`.
 * Uses the shared authenticated request helpers (JWT + X-Tenant injected).
 */
import {
  authenticatedGet,
  authenticatedPost,
  buildEndpoint,
} from './apiService';
import type {
  SenderIdentitiesListResponse,
  AddSenderIdentityResponse,
  ResendSenderIdentityResponse,
} from '../types/memberSenderIdentityTypes';

const BASE = '/members/sender-identities';

/**
 * List the tenant's sender addresses and their SES verification status.
 * GET /members/sender-identities
 */
export async function getSenderIdentities(): Promise<SenderIdentitiesListResponse> {
  const resp = await authenticatedGet(buildEndpoint(BASE));
  return resp.json();
}

/**
 * Add a sender address and begin SES identity verification.
 * POST /members/sender-identities
 *
 * @param email The sender email address to verify.
 */
export async function addSenderIdentity(
  email: string
): Promise<AddSenderIdentityResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), { email });
  return resp.json();
}

/**
 * Resend the SES verification email for an existing (pending/failed/expired)
 * sender address.
 * POST /members/sender-identities/resend
 *
 * @param email The sender address to re-verify.
 */
export async function resendSenderIdentity(
  email: string
): Promise<ResendSenderIdentityResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/resend`), { email });
  return resp.json();
}
