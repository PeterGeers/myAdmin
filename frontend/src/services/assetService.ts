/**
 * Asset Service — API calls for asset administration
 */

import { buildApiUrl } from '../config';
import { fetchAuthSession } from 'aws-amplify/auth';

async function getAuthHeaders(): Promise<HeadersInit> {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  if (!token) throw new Error('Not authenticated');
  return {
    'Authorization': `Bearer ${token}`,
    'X-Tenant': localStorage.getItem('currentTenant') || '',
  };
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || error.message || `HTTP ${response.status}`);
  }
  return response.json();
}

export interface Asset {
  id: number;
  administration: string;
  description: string;
  category: string | null;
  ledger_account: string;
  depreciation_account: string | null;
  purchase_date: string;
  purchase_amount: number;
  depreciation_method: string;
  depreciation_frequency: string;
  useful_life_years: number | null;
  residual_value: number;
  status: 'active' | 'disposed';
  disposal_date: string | null;
  disposal_amount: number | null;
  reference_number: string | null;
  notes: string | null;
  total_depreciation: number;
  book_value: number;
  created_at: string;
  updated_at: string;
}

export interface AssetDetail extends Asset {
  transactions: AssetTransaction[];
}

export interface AssetTransaction {
  ID: number;
  TransactionDate: string;
  TransactionDescription: string;
  TransactionAmount: number;
  Debet: string;
  Credit: string;
  ReferenceNumber: string;
  Ref1: string;
  Ref2: string;
  type: 'purchase' | 'depreciation' | 'disposal';
}

export async function getAssets(params?: {
  status?: string;
  category?: string;
  ledger_account?: string;
}): Promise<{ assets: Asset[]; count: number }> {
  const headers = await getAuthHeaders();
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set('status', params.status);
  if (params?.category) searchParams.set('category', params.category);
  if (params?.ledger_account) searchParams.set('ledger_account', params.ledger_account);
  const url = buildApiUrl('/api/assets', searchParams);
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

export async function getAsset(id: number): Promise<{ asset: AssetDetail }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/assets/${id}`);
  const response = await fetch(url, { headers });
  return handleResponse(response);
}

export async function createAsset(data: Record<string, unknown>): Promise<{ success: boolean; asset_id: number }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl('/api/assets');
  const response = await fetch(url, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function updateAsset(id: number, data: Record<string, unknown>): Promise<{ success: boolean }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/assets/${id}`);
  const response = await fetch(url, {
    method: 'PUT',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function disposeAsset(id: number, data: {
  disposal_date: string;
  disposal_amount: number;
  credit_account?: string;
}): Promise<{ success: boolean; write_off: number }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl(`/api/assets/${id}/dispose`);
  const response = await fetch(url, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function generateDepreciation(data: {
  year: number;
  period: string;
}): Promise<{ success: boolean; entries_created: number; entries_skipped: number; details: unknown[] }> {
  const headers = await getAuthHeaders();
  const url = buildApiUrl('/api/assets/generate-depreciation');
  const response = await fetch(url, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}
