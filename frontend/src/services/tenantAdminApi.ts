/**
 * Tenant Admin API Service
 * 
 * API functions for Tenant_Admin role to manage users, credentials, storage, and settings.
 */

import { fetchAuthSession } from 'aws-amplify/auth';
import type { ScopeGrant, ScopeDimensionOption } from '../types/members';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// ============================================================================
// Types
// ============================================================================

export interface UserData {
  email: string;
  given_name?: string;
  family_name?: string;
  role?: string;
}

export interface UserListFilters {
  role?: string;
  search?: string;
}

export interface CredentialInfo {
  type: string;
  created_at: string;
  updated_at: string;
}

export interface StorageFolder {
  id: string;
  name: string;
  url: string;
}

export interface StorageConfig {
  [key: string]: string; // Dynamic keys like "google_drive_invoices_folder_id"
}

export interface StorageUsage {
  [folderName: string]: {
    folder_id: string;
    folder_name?: string;
    folder_url?: string;
    file_count: number;
    total_size_bytes: number;
    total_size_mb: number;
    accessible: boolean;
    error?: string;
  };
}

export interface TenantSettings {
  notifications?: {
    email_enabled?: boolean;
    sms_enabled?: boolean;
  };
  preferences?: {
    language?: string;
    timezone?: string;
  };
  storage?: StorageConfig;
  [key: string]: Record<string, unknown> | StorageConfig | undefined;
}

export interface ActivityStats {
  date_range: {
    start: string;
    end: string;
  };
  total_actions: number;
  actions_by_type: { [key: string]: number };
  actions_by_user: { [key: string]: number };
  recent_actions: Array<{
    action_type: string;
    user_email: string;
    timestamp: string;
    details: Record<string, unknown>;
  }>;
  error?: string;
}

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
// API Response Types
// ============================================================================

export interface ApiResponse {
  success: boolean;
  error?: string;
  message?: string;
}

export interface UserListResponse extends ApiResponse {
  users?: Array<Record<string, unknown>>;
}

export interface RolesResponse extends ApiResponse {
  roles?: Array<{ name: string; description?: string }>;
}

export interface TenantDetailResponse extends ApiResponse {
  tenant?: Record<string, unknown>;
}

export interface UserCreateResponse extends ApiResponse {
  username?: string;
}

export interface CredentialResponse extends ApiResponse {
  credential_type?: string;
}

export interface AccessCheckResponse extends ApiResponse {
  accessible?: boolean;
}

// ============================================================================
// User Management API
// ============================================================================

export async function createUser(userData: UserData): Promise<UserCreateResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/users`, {
    method: 'POST',
    headers,
    body: JSON.stringify(userData),
  });
  return handleResponse(response);
}

export async function listUsers(filters?: UserListFilters): Promise<UserListResponse> {
  const headers = await getAuthHeaders();
  const params = new URLSearchParams();

  if (filters?.role) params.append('role', filters.role);
  if (filters?.search) params.append('search', filters.search);

  const url = `${API_BASE_URL}/api/tenant-admin/users${params.toString() ? '?' + params.toString() : ''}`;
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

export async function assignRole(username: string, role: string): Promise<ApiResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/users/${username}/groups`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ group_name: role }),
  });
  return handleResponse(response);
}

export async function removeRole(username: string, role: string): Promise<ApiResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/users/${username}/groups/${role}`, {
    method: 'DELETE',
    headers,
  });
  return handleResponse(response);
}

export async function removeUser(username: string): Promise<ApiResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/users/${username}`, {
    method: 'DELETE',
    headers,
  });
  return handleResponse(response);
}

export async function getAvailableRoles(): Promise<RolesResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/roles`, { headers });
  return handleResponse(response);
}

// ============================================================================
// Credentials Management API
// ============================================================================

export async function uploadCredentials(file: File, credentialType: string): Promise<CredentialResponse> {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  const tenant = localStorage.getItem('selectedTenant') || '';

  const formData = new FormData();
  formData.append('file', file);
  formData.append('credential_type', credentialType);

  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/credentials`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'X-Tenant': tenant,
    },
    body: formData,
  });
  return handleResponse(response);
}

export async function listCredentials(): Promise<{ credentials: CredentialInfo[] }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/credentials`, { headers });
  return handleResponse(response);
}

export async function testCredentials(credentialType?: string): Promise<AccessCheckResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/credentials/test`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ credential_type: credentialType || 'google_drive' }),
  });
  return handleResponse(response);
}

export async function startOAuth(service: string = 'google_drive'): Promise<ApiResponse & { auth_url?: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/credentials/oauth/start`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ service }),
  });
  return handleResponse(response);
}

export async function completeOAuth(code: string, state: string, service: string = 'google_drive'): Promise<ApiResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/credentials/oauth/complete`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ code, state, service }),
  });
  return handleResponse(response);
}

// ============================================================================
// Storage Configuration API
// ============================================================================

export async function browseFolders(): Promise<{ folders: StorageFolder[] }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/storage/folders`, { headers });
  return handleResponse(response);
}

export async function getStorageConfig(): Promise<{ config: StorageConfig }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/storage/config`, { headers });
  return handleResponse(response);
}

export async function updateStorageConfig(config: StorageConfig, validate: boolean = false): Promise<ApiResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/storage/config`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ ...config, validate }),
  });
  return handleResponse(response);
}

export async function testFolder(folderId: string): Promise<AccessCheckResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/storage/test`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ folder_id: folderId }),
  });
  return handleResponse(response);
}

export async function getStorageUsage(): Promise<{ usage: StorageUsage }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/storage/usage`, { headers });
  return handleResponse(response);
}

// ============================================================================
// Tenant Details API
// ============================================================================

export interface TenantDetails {
  administration: string;
  display_name?: string;
  contact_email?: string;
  phone_number?: string;
  street?: string;
  city?: string;
  zipcode?: string;
  country?: string;
  bank_account_number?: string;
  bank_name?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
}

export async function getTenantDetails(): Promise<{ tenant: TenantDetails }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/details`, { headers });
  return handleResponse(response);
}

export async function updateTenantDetails(details: Partial<TenantDetails>): Promise<TenantDetailResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/details`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(details),
  });
  return handleResponse(response);
}

// ============================================================================
// Tenant Settings API
// ============================================================================

export async function getSettings(): Promise<{ settings: TenantSettings }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/settings`, { headers });
  return handleResponse(response);
}

export async function updateSettings(settings: Partial<TenantSettings>): Promise<ApiResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/settings`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(settings),
  });
  return handleResponse(response);
}

export async function getActivity(dateRange?: { start_date?: string; end_date?: string }): Promise<{ activity: ActivityStats }> {
  const headers = await getAuthHeaders();
  const params = new URLSearchParams();

  if (dateRange?.start_date) params.append('start_date', dateRange.start_date);
  if (dateRange?.end_date) params.append('end_date', dateRange.end_date);

  const url = `${API_BASE_URL}/api/tenant-admin/activity${params.toString() ? '?' + params.toString() : ''}`;
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

// ============================================================================
// Member-Scope Authoring API (s5d task 6.1)
// ============================================================================
//
// Client for the Tenant_Admin scope-authoring routes (backend task 5.2/5.3,
// `tenant_admin_scope.py`). All calls carry the `X-Tenant` header + Bearer token
// via `getAuthHeaders()` and unwrap the JSON via `handleResponse()` — the tenant
// is ALWAYS the verified context tenant, never a body value (Property 1). s5d
// serves the `members` module path segment.

/** Response shape of `GET /api/tenant-admin/users/<username>/scope/<module>`. */
export interface UserScopeResponse extends ApiResponse {
  tenant?: string;
  module?: string;
  username?: string;
  /** The user's grant for this module — `{}` when none exists. */
  scopes?: ScopeGrant;
}

/** Response shape of `GET /api/tenant-admin/scope-dimensions/<module>`. */
export interface ScopeDimensionsResponse extends ApiResponse {
  tenant?: string;
  module?: string;
  dimensions?: ScopeDimensionOption[];
  count?: number;
}

/** Response shape of `POST /api/tenant-admin/projection/resync`. */
export interface ResyncResponse extends ApiResponse {
  tenant?: string;
  /** Number of projection rows (re)written. */
  written?: number;
  /** Number of obsolete projection rows removed. */
  removed?: number;
}

/**
 * Fetch a user's current scope grant for the current tenant + module.
 *
 * `GET /api/tenant-admin/users/<username>/scope/<module>` → returns the `scopes`
 * object (an empty object when the user has no grant). s5d serves `module = members`.
 */
export async function getUserScope(username: string, module: string): Promise<ScopeGrant> {
  const headers = await getAuthHeaders();
  const response = await fetch(
    `${API_BASE_URL}/api/tenant-admin/users/${encodeURIComponent(username)}/scope/${encodeURIComponent(module)}`,
    { headers },
  );
  const data = await handleResponse<UserScopeResponse>(response);
  return data.scopes ?? {};
}

/**
 * Atomically overwrite a user's scope grant for the current tenant + module.
 *
 * `PUT /api/tenant-admin/users/<username>/scope/<module>` with body
 * `{ "scopes": {...} }`. Clearing all dimensions removes the grant (deny). The
 * backend validates each dimension key + value against the tenant's
 * `<module>.scope_dimensions` and rejects unknown ones with a 400 — which
 * `handleResponse` surfaces as a thrown validation error. Returns the normalized
 * scopes the backend stored.
 */
export async function setUserScope(
  username: string,
  module: string,
  scopes: ScopeGrant,
): Promise<ScopeGrant> {
  const headers = await getAuthHeaders();
  const response = await fetch(
    `${API_BASE_URL}/api/tenant-admin/users/${encodeURIComponent(username)}/scope/${encodeURIComponent(module)}`,
    {
      method: 'PUT',
      headers,
      body: JSON.stringify({ scopes }),
    },
  );
  const data = await handleResponse<UserScopeResponse>(response);
  return data.scopes ?? {};
}

/**
 * Fetch the enabled scope dimensions + canonical values for the picker.
 *
 * `GET /api/tenant-admin/scope-dimensions/<module>` — sourced directly from the
 * tenant's `<module>.scope_dimensions` param (D4/R5.1). Returns the dimension
 * option list (empty when the tenant configures no scope dimensions).
 */
export async function getScopeDimensions(module: string): Promise<ScopeDimensionOption[]> {
  const headers = await getAuthHeaders();
  const response = await fetch(
    `${API_BASE_URL}/api/tenant-admin/scope-dimensions/${encodeURIComponent(module)}`,
    { headers },
  );
  const data = await handleResponse<ScopeDimensionsResponse>(response);
  return data.dimensions ?? [];
}

/**
 * Force a full re-projection of the current tenant ("Re-sync now").
 *
 * `POST /api/tenant-admin/projection/resync` — a convenience/recovery action that
 * returns a `{ written, removed }` summary. A backend failure answers 500 with
 * `{ success: false, error }`, which `handleResponse` surfaces as a thrown error
 * so the UI can show it.
 */
export async function resyncProjection(): Promise<ResyncResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/projection/resync`, {
    method: 'POST',
    headers,
  });
  return handleResponse<ResyncResponse>(response);
}
