/**
 * SysAdmin Service
 * 
 * API service for System Administrator operations
 * Handles tenant management, role management, and module management
 */

import { fetchAuthSession } from 'aws-amplify/auth';
import { buildApiUrl } from '../config';

// ============================================================================
// Types
// ============================================================================

export interface Tenant {
  administration: string;
  display_name: string;
  status: 'active' | 'suspended' | 'inactive' | 'deleted';
  contact_email: string;
  phone_number?: string;
  street_address?: string;
  city?: string;
  zipcode?: string;
  country?: string;
  enabled_modules: string[];
  user_count: number;
  created_at: string;
  updated_at?: string;
  created_by?: string;
  updated_by?: string;
}

export interface Role {
  name: string;
  description: string;
  precedence: number;
  category?: 'platform' | 'module' | 'other';
  user_count?: number;
  created_date?: string;
}

export interface TenantModule {
  administration: string;
  module_name: string;
  is_active: boolean;
  created_at: string;
}

export interface CreateTenantRequest {
  administration: string;
  display_name: string;
  contact_email: string;
  phone_number?: string;
  street_address?: string;
  city?: string;
  zipcode?: string;
  country?: string;
  enabled_modules: string[];
}

export interface UpdateTenantRequest {
  display_name?: string;
  status?: 'active' | 'suspended' | 'inactive' | 'deleted';
  contact_email?: string;
  phone_number?: string;
  street_address?: string;
  city?: string;
  zipcode?: string;
  country?: string;
}

// ============================================================================
// Helper Functions
// ============================================================================

async function getAuthHeaders(): Promise<HeadersInit> {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  
  if (!token) {
    throw new Error('No authentication token available');
  }
  
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || error.message || `HTTP ${response.status}`);
  }
  return response.json();
}

// ============================================================================
// Tenant Management
// ============================================================================

export async function getTenants(params?: {
  page?: number;
  per_page?: number;
  status?: string;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}): Promise<{
  tenants: Tenant[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}> {
  const headers = await getAuthHeaders();
  const queryParams = new URLSearchParams();
  
  if (params?.page) queryParams.append('page', params.page.toString());
  if (params?.per_page) queryParams.append('per_page', params.per_page.toString());
  if (params?.status) queryParams.append('status', params.status);
  if (params?.search) queryParams.append('search', params.search);
  if (params?.sort_by) queryParams.append('sort_by', params.sort_by);
  if (params?.sort_order) queryParams.append('sort_order', params.sort_order);
  
  const url = buildApiUrl(`/api/sysadmin/tenants?${queryParams.toString()}`);
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

export async function getTenant(administration: string): Promise<Tenant> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/sysadmin/tenants/${administration}`);
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

export async function createTenant(data: CreateTenantRequest): Promise<{ success: boolean; message: string }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl('/api/sysadmin/tenants');
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(data)
  });
  return handleResponse(response);
}

export async function updateTenant(
  administration: string,
  data: UpdateTenantRequest
): Promise<{ success: boolean; message: string }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/sysadmin/tenants/${administration}`);
  const response = await fetch(url, {
    method: 'PUT',
    headers,
    body: JSON.stringify(data)
  });
  return handleResponse(response);
}

export async function deleteTenant(administration: string): Promise<{ success: boolean; message: string }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/sysadmin/tenants/${administration}`);
  const response = await fetch(url, {
    method: 'DELETE',
    headers
  });
  return handleResponse(response);
}

// ============================================================================
// Role Management
// ============================================================================

export async function getRoles(): Promise<{ roles: Role[] }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl('/api/sysadmin/roles');
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

export async function createRole(data: {
  name: string;
  description: string;
  precedence?: number;
}): Promise<{ success: boolean; message: string }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl('/api/sysadmin/roles');
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(data)
  });
  return handleResponse(response);
}

export async function updateRole(
  roleName: string,
  data: {
    description?: string;
    precedence?: number;
  }
): Promise<{ success: boolean; message: string }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/sysadmin/roles/${roleName}`);
  const response = await fetch(url, {
    method: 'PUT',
    headers,
    body: JSON.stringify(data)
  });
  return handleResponse(response);
}

export async function deleteRole(roleName: string): Promise<{ success: boolean; message: string }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/sysadmin/roles/${roleName}`);
  const response = await fetch(url, {
    method: 'DELETE',
    headers
  });
  return handleResponse(response);
}

// ============================================================================
// Module Management
// ============================================================================

export async function getTenantModules(administration: string): Promise<{ modules: TenantModule[] }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/sysadmin/tenants/${administration}/modules`);
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

export async function updateTenantModules(
  administration: string,
  modules: Array<{ name: string; is_active: boolean }>
): Promise<{ success: boolean; message: string }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/sysadmin/tenants/${administration}/modules`);
  const response = await fetch(url, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ modules })
  });
  return handleResponse(response);
}

// ============================================================================
// Health Check
// ============================================================================

export interface HealthStatus {
  service: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  responseTime: number;
  message?: string;
  lastChecked: string;
  details?: Record<string, any>;
}

export interface SystemHealth {
  overall: 'healthy' | 'degraded' | 'unhealthy';
  services: HealthStatus[];
  timestamp: string;
}

export async function getSystemHealth(): Promise<SystemHealth> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl('/api/sysadmin/health');
  const response = await fetch(url, { headers });
  return handleResponse(response);
}
