/**
 * API service for parameter administration.
 */
import { ParametersResponse, ParameterCreateRequest, ParameterUpdateRequest, ParameterDefaultResponse, ParameterMutationResponse } from '../types/parameterTypes';
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';

const BASE = '/api/tenant-admin/parameters';

export async function getParameters(namespace?: string): Promise<ParametersResponse> {
  const params = namespace ? `?namespace=${encodeURIComponent(namespace)}` : '';
  const resp = await authenticatedGet(buildEndpoint(`${BASE}${params}`));
  return resp.json();
}

export async function createParameter(data: ParameterCreateRequest): Promise<ParameterMutationResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateParameter(id: number, data: ParameterUpdateRequest): Promise<ParameterMutationResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteParameter(id: number): Promise<ParameterMutationResponse> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function getParameterDefault(namespace: string, key: string): Promise<ParameterDefaultResponse> {
  const params = new URLSearchParams({ namespace, key });
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/default`, params));
  return resp.json();
}
