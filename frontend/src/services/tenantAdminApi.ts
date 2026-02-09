/**
 * Tenant Admin API Service
 * 
 * API functions for Tenant_Admin role to manage users, credentials, storage, and settings.
 */

import { fetchAuthSession } from 'aws-amplify/auth';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

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
  facturen_folder_id?: string;
  invoices_folder_id?: string;
  reports_folder_id?: string;
}

export interface StorageUsage {
  [folderName: string]: {
    folder_id: string;
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
  [key: string]: any;
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
    details: any;
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
// User Management API
// ============================================================================

export async function createUser(userData: UserData): Promise<any> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/users`, {
    method: 'POST',
    headers,
    body: JSON.stringify(userData),
  });
  return handleResponse(response);
}

export async function listUsers(filters?: UserListFilters): Promise<any> {
  const headers = await getAuthHeaders();
  const params = new URLSearchParams();
  
  if (filters?.role) params.append('role', filters.role);
  if (filters?.search) params.append('search', filters.search);
  
  const url = `${API_BASE_URL}/api/tenant-admin/users${params.toString() ? '?' + params.toString() : ''}`;
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

export async function assignRole(username: string, role: string): Promise<any> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/users/${username}/groups`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ group_name: role }),
  });
  return handleResponse(response);
}

export async function removeRole(username: string, role: string): Promise<any> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/users/${username}/groups/${role}`, {
    method: 'DELETE',
    headers,
  });
  return handleResponse(response);
}

export async function removeUser(username: string): Promise<any> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/users/${username}`, {
    method: 'DELETE',
    headers,
  });
  return handleResponse(response);
}

export async function getAvailableRoles(): Promise<any> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/roles`, { headers });
  return handleResponse(response);
}

// ============================================================================
// Credentials Management API
// ============================================================================

export async function uploadCredentials(file: File, credentialType: string): Promise<any> {
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

export async function testCredentials(credentialType?: string): Promise<any> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/credentials/test`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ credential_type: credentialType || 'google_drive' }),
  });
  return handleResponse(response);
}

export async function startOAuth(service: string = 'google_drive'): Promise<any> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/credentials/oauth/start`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ service }),
  });
  return handleResponse(response);
}

export async function completeOAuth(code: string, state: string, service: string = 'google_drive'): Promise<any> {
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

export async function updateStorageConfig(config: StorageConfig, validate: boolean = false): Promise<any> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/storage/config`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ ...config, validate }),
  });
  return handleResponse(response);
}

export async function testFolder(folderId: string): Promise<any> {
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
// Tenant Settings API
// ============================================================================

export async function getSettings(): Promise<{ settings: TenantSettings }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/settings`, { headers });
  return handleResponse(response);
}

export async function updateSettings(settings: Partial<TenantSettings>): Promise<any> {
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
