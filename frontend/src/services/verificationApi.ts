/**
 * Verification API Service
 *
 * API functions for managing SES email sender verification.
 * Follows the same patterns as tenantAdminApi.ts.
 */

import { fetchAuthSession } from 'aws-amplify/auth';
import type {
  VerificationStatusResponse,
  ResendVerificationResponse,
  UpdateEmailResponse,
} from '@/types/VerificationTypes';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// ============================================================================
// Helper Functions
// ============================================================================

async function getAuthHeaders(): Promise<HeadersInit> {
  try {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    const tenant = localStorage.getItem('selectedTenant') || '';

    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'X-Tenant': tenant,
    };
  } catch (error) {
    console.error('Failed to get auth headers:', error);
    throw new Error('Authentication failed');
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Verification API
// ============================================================================

/**
 * Get the current sender email verification status for the authenticated tenant.
 * GET /api/tenant-admin/sender-verification
 */
export async function getVerificationStatus(): Promise<VerificationStatusResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/sender-verification`, {
    headers,
  });
  return handleResponse<VerificationStatusResponse>(response);
}

/**
 * Resend the SES verification email for the authenticated tenant.
 * POST /api/tenant-admin/sender-verification/resend
 */
export async function resendVerification(): Promise<ResendVerificationResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/sender-verification/resend`, {
    method: 'POST',
    headers,
  });
  return handleResponse<ResendVerificationResponse>(response);
}

/**
 * Update the sender email address and initiate verification.
 * PUT /api/tenant-admin/sender-verification/email
 */
export async function updateSenderEmail(email: string): Promise<UpdateEmailResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/sender-verification/email`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ email }),
  });
  return handleResponse<UpdateEmailResponse>(response);
}
