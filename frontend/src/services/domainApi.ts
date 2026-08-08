/**
 * Domain Management API Service
 *
 * API functions for managing tenant domain configurations:
 * - Jabaki subdomain (slug.jabaki.nl) enable/disable
 * - Custom domain registration, verification, and removal
 */

import { authenticatedGet, authenticatedPost, authenticatedDelete } from './apiService';

// ============================================================================
// Types
// ============================================================================

export interface JabakiStatus {
  enabled: boolean;
  domain: string | null;
  status: 'active' | 'inactive' | 'no_slug';
}

export interface CustomDomainStatus {
  domain: string | null;
  status: 'pending_dns' | 'validating' | 'issued' | 'failed' | 'revoked' | null;
  is_active: boolean;
  dns_instructions: DnsInstructions | null;
}

export interface DnsRecord {
  purpose: 'domain_verification' | 'routing';
  name: string;
  value: string;
}

export interface DnsInstructions {
  type: 'CNAME';
  records: DnsRecord[];
}

export interface DomainsResponse {
  jabaki: JabakiStatus;
  custom: CustomDomainStatus;
}

export interface EnableJabakiResponse {
  success: boolean;
  domain: string;
  message: string;
}

export interface DisableJabakiResponse {
  success: boolean;
  message: string;
}

export interface RegisterDomainResponse {
  success: boolean;
  data: {
    domain: string;
    status: string;
    dns_instructions: DnsInstructions;
  };
  error?: string;
}

export interface VerifyDomainResponse {
  success: boolean;
  data: {
    domain: string;
    status: string;
    is_active: boolean;
    message: string;
  };
  error?: string;
}

export interface RemoveDomainResponse {
  success: boolean;
  message: string;
  error?: string;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Get domain configuration for the current tenant.
 * Returns Jabaki subdomain status + custom domain status.
 */
export async function getDomains(): Promise<DomainsResponse> {
  const response = await authenticatedGet('/api/landing/domains');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  const result = await response.json();
  if (!result.success) {
    throw new Error(result.error || 'Failed to load domain settings');
  }
  return result.data;
}

/**
 * Enable the Jabaki subdomain for the current tenant.
 */
export async function enableJabaki(): Promise<EnableJabakiResponse> {
  const response = await authenticatedPost('/api/landing/domains/jabaki/enable');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Disable the Jabaki subdomain for the current tenant.
 */
export async function disableJabaki(): Promise<DisableJabakiResponse> {
  const response = await authenticatedPost('/api/landing/domains/jabaki/disable');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Register a custom domain for the current tenant.
 * Returns DNS instructions for domain verification.
 */
export async function registerCustomDomain(domain: string): Promise<RegisterDomainResponse> {
  const response = await authenticatedPost('/api/landing/domains/custom', { domain });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Verify custom domain certificate status.
 * If issued, activates the domain automatically.
 */
export async function verifyCustomDomain(): Promise<VerifyDomainResponse> {
  const response = await authenticatedPost('/api/landing/domains/custom/verify');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Remove the custom domain for the current tenant.
 * Cleans up certificate, CloudFront CNAME, and KVS mapping.
 */
export async function removeCustomDomain(): Promise<RemoveDomainResponse> {
  const response = await authenticatedDelete('/api/landing/domains/custom');
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}
