/**
 * Member sender-identity API service (R0, design §6.2).
 *
 * Drives the tenant-admin sender-identity surface: read the tenant's sender
 * address with its SES status, add + begin verifying a new address, and resend
 * the SES verification email for a pending/failed/expired address.
 *
 * Plane: **Flask tenant-admin plane** (NOT the SAM Members Lambda). SES identity
 * verification is authoring/source-of-truth state persisted in MySQL
 * (`email_verifications`, keyed by `administration`) and reused from the ZZP
 * sender-verification service — so these routes live on Flask. The SAM Members
 * Lambda is a config CONSUMER and implements no sender-identity route.
 *
 * Routes (Flask, `members_sender_identity_routes.py`):
 *   - GET  /api/members/sender-identities          — current sender + SES status
 *   - POST /api/members/sender-identities          — add + VerifyEmailIdentity
 *   - POST /api/members/sender-identities/resend    — resend verification
 *
 * Gate: `members:admin` (tenant admin). Follows the API response & error
 * standard v1.0 (steering 37): `{success, data}` / `{success:false, error, code}`.
 * Uses the shared authenticated Flask helpers (JWT + X-Tenant injected).
 *
 * Note (single-address, Option A): the Flask plane tracks ONE active sender per
 * tenant. `getSenderIdentities` therefore wraps the single current identity into
 * a 0-or-1-element `identities[]` so the list-shaped UI stays unchanged.
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
  MemberSenderIdentity,
} from '../types/memberSenderIdentityTypes';

const BASE = '/api/members/sender-identities';

/** The single-identity envelope the Flask GET/POST return under `data`. */
interface FlaskIdentityData {
  email: string | null;
  status: MemberSenderIdentity['status'] | null;
  last_checked?: string | null;
}

/**
 * List the tenant's sender address(es) and SES verification status.
 * GET /api/members/sender-identities
 *
 * The Flask plane returns a SINGLE current identity (`{email, status,
 * last_checked}`); this wraps it into a 0-or-1-element `identities[]` (empty when
 * the tenant has no sender yet) so the table UI is unchanged.
 */
export async function getSenderIdentities(): Promise<SenderIdentitiesListResponse> {
  const resp = await authenticatedGet(buildEndpoint(BASE));
  const body = (await resp.json()) as {
    success: boolean;
    data?: FlaskIdentityData;
    error?: string;
    code?: string;
  };

  if (!body.success || !body.data || !body.data.email || !body.data.status) {
    return {
      success: body.success,
      data: { identities: [] },
      error: body.error,
      code: body.code,
    };
  }

  return {
    success: true,
    data: {
      identities: [
        {
          email: body.data.email,
          status: body.data.status,
          lastChecked: body.data.last_checked ?? null,
        },
      ],
    },
  };
}

/**
 * Add a sender address and begin SES identity verification.
 * POST /api/members/sender-identities
 *
 * @param email The sender email address to verify.
 */
export async function addSenderIdentity(
  email: string
): Promise<AddSenderIdentityResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), { email });
  const body = (await resp.json()) as {
    success: boolean;
    data?: FlaskIdentityData;
    error?: string;
    code?: string;
  };

  if (!body.success || !body.data || !body.data.email || !body.data.status) {
    return { success: body.success, error: body.error, code: body.code };
  }

  return {
    success: true,
    data: {
      email: body.data.email,
      status: body.data.status,
      lastChecked: body.data.last_checked ?? null,
    },
  };
}

/**
 * Resend the SES verification email for the tenant's pending sender address.
 * POST /api/members/sender-identities/resend
 *
 * The Flask plane resolves the address from the active verification record, so
 * no body is sent. (The `email` arg is accepted for a stable call signature with
 * the per-row UI action but is not transmitted.)
 */
export async function resendSenderIdentity(
  _email?: string
): Promise<ResendSenderIdentityResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/resend`), {});
  return resp.json();
}
