/**
 * API service for parameter administration.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';
import { ParametersResponse, ParameterCreateRequest, ParameterUpdateRequest } from '../types/parameterTypes';

const BASE = '/api/tenant-admin/parameters';

export async function getParameters(namespace?: string): Promise<ParametersResponse> {
  const params = namespace ? `?namespace=${encodeURIComponent(namespace)}` : '';
  const resp = await authenticatedGet(buildEndpoint(`${BASE}${params}`));
  return resp.json();
}

export async function createParameter(data: ParameterCreateRequest): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateParameter(id: number, data: ParameterUpdateRequest): Promise<any> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteParameter(id: number): Promise<any> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}
